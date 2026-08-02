"""Release-bound Canonical V2 consumer and read-only Admin runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Literal, cast

from pydantic import ValidationError

from backend.services.canonical_v2_chat import CanonicalV2ChatAdapter
from src.data_agents.canonical_v2.candidate_projection import (
    CandidateProjectionResult,
    compose_candidate_projections,
)
from src.data_agents.canonical_v2.contracts import (
    BuildManifest,
    PublishedRelease,
    ReleaseState,
    ReleaseVerification,
)
from src.data_agents.canonical_v2.index_projection import (
    IndexProjectionRequest,
    create_ephemeral_index_projection_builder,
)
from src.data_agents.canonical_v2.knowledge_gap_postgres import (
    GapAdminPage,
    GapAdminQuery,
)
from src.data_agents.canonical_v2.knowledge_gap_feedback import (
    GapSignal,
    GapTrigger,
)
from src.data_agents.canonical_v2.knowledge_read import (
    EnumerationPlanningContext,
    EnumerationPolicy,
    EvidenceSet,
    PlanningReleaseBinding,
    QueryPlanningRequest,
    RetrievalPlan,
    SupplementalBudget,
)
from src.data_agents.canonical_v2.release_publication_isolated import (
    IsolatedReleaseBundle,
)
from src.data_agents.canonical_v2.relationship_projection import (
    RelationshipProjectionResult,
)


PublicDomain = Literal["company", "paper", "patent", "professor"]

_PUBLIC_DOMAINS: tuple[PublicDomain, ...] = (
    "company",
    "paper",
    "patent",
    "professor",
)
_COMPANY_PATENT_PATH = (
    "company_has_patent",
    "company_to_patent",
    "company",
    "patent",
)
_REPRESENTATIVE_SCOPE = (
    "representative Patents naming one displayed Company as applicant"
)
_RELATIONSHIP_VERSION = "canonical-v2-relationship-v1"
_RELATIONSHIP_ROUTES: dict[
    tuple[PublicDomain, str],
    tuple[
        PublicDomain,
        str,
        Literal["source_endpoint", "target_endpoint"],
        Literal["source_endpoint", "target_endpoint"],
        tuple[str, str, str, str],
    ],
] = {
    ("company", "company_has_patent"): (
        "patent",
        "patent_has_applicant",
        "target_endpoint",
        "source_endpoint",
        _COMPANY_PATENT_PATH,
    ),
    ("patent", "company_has_patent"): (
        "company",
        "patent_has_applicant",
        "source_endpoint",
        "target_endpoint",
        ("company_has_patent", "patent_to_company", "patent", "company"),
    ),
    ("professor", "professor_authored_paper"): (
        "paper",
        "professor_attributed_to_paper",
        "source_endpoint",
        "target_endpoint",
        ("professor_authored_paper", "professor_to_paper", "professor", "paper"),
    ),
    ("paper", "professor_authored_paper"): (
        "professor",
        "professor_attributed_to_paper",
        "target_endpoint",
        "source_endpoint",
        ("professor_authored_paper", "paper_to_professor", "paper", "professor"),
    ),
}


class CanonicalV2ConsumerIntegrityError(ValueError):
    """A consumer stage crossed or failed its accepted release graph."""


class CanonicalV2ConsumerInputError(ValueError):
    """A bounded consumer request does not identify valid release data."""


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _exact_model[T](value: object, model_type: type[T], label: str) -> T:
    if type(value) is not model_type:
        raise TypeError(f"{label} must use the exact accepted model type")
    try:
        dumped = cast(Any, value).model_dump(mode="json", warnings="error")
        validated = cast(Any, model_type).model_validate(dumped)
    except (AttributeError, TypeError, ValueError, ValidationError) as exc:
        raise CanonicalV2ConsumerIntegrityError(
            f"{label} failed exact typed round-trip"
        ) from exc
    if validated != value:
        raise CanonicalV2ConsumerIntegrityError(
            f"{label} changed during exact typed round-trip"
        )
    return cast(T, validated)


def _expected_manifest_sha256(manifest: BuildManifest) -> str:
    return _canonical_sha256(
        manifest.model_dump(mode="json", exclude={"manifest_sha256"})
    )


def _require_artifact_graph(
    *,
    published_release: PublishedRelease,
    release_verification: ReleaseVerification,
    release_bundle: IsolatedReleaseBundle,
    index_projection_request: IndexProjectionRequest,
) -> tuple[
    PublishedRelease,
    ReleaseVerification,
    IsolatedReleaseBundle,
    IndexProjectionRequest,
    CandidateProjectionResult,
    PlanningReleaseBinding,
]:
    published = _exact_model(
        published_release,
        PublishedRelease,
        "published_release",
    )
    verification = _exact_model(
        release_verification,
        ReleaseVerification,
        "release_verification",
    )
    bundle = _exact_model(
        release_bundle,
        IsolatedReleaseBundle,
        "release_bundle",
    )
    index_request = _exact_model(
        index_projection_request,
        IndexProjectionRequest,
        "index_projection_request",
    )

    release_id = bundle.release_id
    if (
        published.release_id != release_id
        or published.canonical_release_id != release_id
        or published.published_projection_release_id != release_id
        or published.index_release_id != release_id
        or verification.candidate_release_id != release_id
        or index_request.candidate_projection_request.release_id != release_id
        or index_request.candidate_projection_result.release_id != release_id
    ):
        raise CanonicalV2ConsumerIntegrityError(
            "consumer artifacts do not identify one release"
        )
    if published.state not in {ReleaseState.active, ReleaseState.rolled_back}:
        raise CanonicalV2ConsumerIntegrityError("published release is not serviceable")
    if (
        not verification.accepted
        or not verification.canonical_index_parity
        or any(
            value != 0
            for value in (
                verification.missing_points,
                verification.extra_points,
                verification.stale_points,
                verification.cross_release_points,
            )
        )
        or verification.manifest_sha256 != bundle.manifest.manifest_sha256
        or tuple(sorted(verification.evidence_ids))
        != tuple(sorted(published.verification_evidence_ids))
    ):
        raise CanonicalV2ConsumerIntegrityError(
            "release verification differs from publication authority"
        )
    if bundle.manifest.manifest_sha256 != _expected_manifest_sha256(bundle.manifest):
        raise CanonicalV2ConsumerIntegrityError(
            "manifest_sha256 does not bind the complete manifest"
        )

    try:
        candidate = compose_candidate_projections(
            index_request.candidate_projection_request
        )
        replayed_index = create_ephemeral_index_projection_builder().build(
            index_request
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise CanonicalV2ConsumerIntegrityError(
            "candidate/index graph failed exact replay"
        ) from exc
    if candidate != index_request.candidate_projection_result:
        raise CanonicalV2ConsumerIntegrityError(
            "candidate projection differs from exact replay"
        )
    if replayed_index != bundle.index_result:
        raise CanonicalV2ConsumerIntegrityError(
            "index projection differs from the isolated bundle"
        )
    candidate_manifests = {
        item.projection_id: item for item in candidate.published_projections
    }
    release_manifests = {
        item.projection_id: item for item in bundle.manifest.published_projections
    }
    if (
        len(candidate_manifests) != 7
        or len(release_manifests) != 7
        or candidate_manifests != release_manifests
    ):
        raise CanonicalV2ConsumerIntegrityError(
            "published projections differ from the release manifest"
        )
    public_domains = tuple(
        sorted(
            {
                projection.entity_type
                for projection in candidate.public_domain_projections
            }
        )
    )
    if public_domains != _PUBLIC_DOMAINS:
        raise CanonicalV2ConsumerIntegrityError(
            "candidate must retain exactly four public domains"
        )

    relationship_request = bundle.relationship_projection_request
    relationship_result = bundle.relationship_projection_result
    if relationship_request is None or relationship_result is None:
        raise CanonicalV2ConsumerIntegrityError(
            "candidate requires relationship publication authority"
        )
    candidate_internal_request = (
        index_request.candidate_projection_request.internal_reference_projection_request
    )
    candidate_internal_result = (
        index_request.candidate_projection_request.internal_reference_projection_result
    )
    if (
        relationship_request.internal_reference_projection_request
        != candidate_internal_request
        or relationship_request.internal_reference_projection_result
        != candidate_internal_result
        or relationship_result.release_id != release_id
    ):
        raise CanonicalV2ConsumerIntegrityError(
            "relationship authority is not bound to the candidate graph"
        )

    publication_state: Literal["active", "rolled_back"] = (
        "active" if published.state is ReleaseState.active else "rolled_back"
    )
    binding = PlanningReleaseBinding(
        release_id=release_id,
        publication_state=publication_state,
        published_release_sha256=_canonical_sha256(published.model_dump(mode="json")),
        publication_verification_evidence_ids=tuple(
            sorted(published.verification_evidence_ids)
        ),
        manifest_sha256=bundle.manifest.manifest_sha256,
        index_projection_request_sha256=_canonical_sha256(
            index_request.model_dump(mode="json")
        ),
        index_projection_result_sha256=bundle.index_result.content_sha256,
        candidate_projection_result_sha256=candidate.content_sha256,
        internal_reference_projection_result_sha256=(
            candidate_internal_result.content_sha256
        ),
        # These two values are owned by the accepted release-bound planner and
        # are additionally closed by RetrievalPlan validation. They are not
        # independently supplied consumer inputs.
        institution_catalog_sha256="0" * 64,
        planning_policy_sha256="0" * 64,
    )
    return published, verification, bundle, index_request, candidate, binding


def _validated_plan(
    value: object,
    *,
    request: QueryPlanningRequest,
    expected_binding: PlanningReleaseBinding,
) -> RetrievalPlan:
    plan = _exact_model(value, RetrievalPlan, "retrieval plan")
    binding = plan.release_binding
    if binding is None:
        raise CanonicalV2ConsumerIntegrityError(
            "release-bound plan requires a release binding"
        )
    expected_fields = (
        "release_id",
        "publication_state",
        "published_release_sha256",
        "publication_verification_evidence_ids",
        "manifest_sha256",
        "index_projection_request_sha256",
        "index_projection_result_sha256",
        "candidate_projection_result_sha256",
        "internal_reference_projection_result_sha256",
    )
    if any(
        getattr(binding, field) != getattr(expected_binding, field)
        for field in expected_fields
    ):
        raise CanonicalV2ConsumerIntegrityError(
            "retrieval plan differs from the aggregate release binding"
        )
    if (
        plan.release_id != request.release_id
        or plan.original_query != request.original_query
        or plan.as_of != request.as_of
        or plan.request_sha256 != request.content_sha256
    ):
        raise CanonicalV2ConsumerIntegrityError(
            "retrieval plan does not bind its planning request"
        )
    return plan


def _controlled_plan(
    plan: RetrievalPlan,
    *,
    supplemental_budget: SupplementalBudget,
) -> RetrievalPlan:
    relationship_key = None
    if len(plan.relationship_paths) == 1:
        path = plan.relationship_paths[0]
        relationship_key = (
            path.relationship_type_id,
            path.direction,
            path.source_type,
            path.target_type,
        )
    enumeration_policy: EnumerationPolicy | None = None
    if (
        relationship_key == _COMPANY_PATENT_PATH
        and plan.structured_constraints.displayed_entity_ids
    ):
        if plan.as_of is None:
            raise CanonicalV2ConsumerIntegrityError(
                "representative relationship plan requires as_of"
            )
        enumeration_policy = EnumerationPolicy(
            mode="representative",
            scope=_REPRESENTATIVE_SCOPE,
            as_of=plan.as_of,
            exhaustive=False,
            continuation_state="available",
        )
    payload = plan.model_dump(mode="json", exclude={"content_sha256"})
    payload["supplemental_budget"] = supplemental_budget.model_dump(mode="json")
    effective_enumeration_policy = enumeration_policy or plan.enumeration_policy
    payload["enumeration_policy"] = (
        None
        if effective_enumeration_policy is None
        else effective_enumeration_policy.model_dump(mode="json")
    )
    try:
        return RetrievalPlan.model_validate(payload)
    except (TypeError, ValueError, ValidationError) as exc:
        raise CanonicalV2ConsumerIntegrityError(
            "server-owned plan controls produced an invalid plan"
        ) from exc


class _ServerOwnedPlanner:
    def __init__(
        self,
        *,
        delegate: Any,
        expected_binding: PlanningReleaseBinding,
        supplemental_budget: SupplementalBudget,
    ) -> None:
        self._delegate = delegate
        self._expected_binding = expected_binding
        self._supplemental_budget = supplemental_budget

    def plan(self, request: QueryPlanningRequest) -> RetrievalPlan:
        exact_request = QueryPlanningRequest.model_validate(
            request.model_dump(mode="json")
        )
        raw = self._delegate.plan(exact_request)
        validated = _validated_plan(
            raw,
            request=exact_request,
            expected_binding=self._expected_binding,
        )
        controlled = _controlled_plan(
            validated,
            supplemental_budget=self._supplemental_budget,
        )
        return _exact_model(
            controlled,
            RetrievalPlan,
            "controlled retrieval plan",
        )


def _answer_evidence_references(evidence: EvidenceSet) -> set[str]:
    """Return evidence IDs that are live inputs to the current answer."""
    references: set[str] = set()
    replayed_handle_ids = {
        receipt.handle_id for receipt in evidence.handle_replay_receipts
    }
    for handle in evidence.entity_handles:
        handle_id = (
            handle.canonical_id if handle.kind == "canonical" else handle.handle_id
        )
        if handle_id not in replayed_handle_ids:
            references.update(handle.evidence_ids)
    for trace in evidence.candidate_traces:
        if trace.disposition == "selected":
            references.update(trace.evidence_ids)
    if evidence.sufficiency_report is not None:
        for part in evidence.sufficiency_report.parts:
            references.update(part.evidence_ids)
    if evidence.enumeration_coverage is not None:
        for outcome in evidence.enumeration_coverage.required_member_outcomes:
            references.update(outcome.evidence_ids)
    for conflict in evidence.material_conflicts:
        references.update(conflict.evidence_ids)
    for candidate in evidence.continuation_candidates:
        references.update(candidate.evidence_ids)
    return references


def _retained_evidence_references(evidence: EvidenceSet) -> set[str]:
    references = _answer_evidence_references(evidence)
    item_ids = {item.evidence_id for item in evidence.items}
    for receipt in evidence.constraint_receipts:
        if receipt.outcome != "accepted" or not all(
            raw_id.startswith("direct-object:")
            for raw_id in receipt.raw_candidate_ids
        ):
            continue
        references.update(item_ids.intersection(receipt.aggregated_evidence_ids))
    return references


def _validated_evidence_set(
    value: object,
    *,
    plan: RetrievalPlan,
) -> EvidenceSet:
    evidence = _exact_model(value, EvidenceSet, "evidence set")
    if (
        evidence.release_id != plan.release_id
        or evidence.original_query != plan.original_query
        or evidence.protected_slots != plan.protected_slots
    ):
        raise CanonicalV2ConsumerIntegrityError(
            "evidence set differs from its retrieval plan"
        )
    admitted_lanes = {*plan.lanes, "supplemental"}
    if any(
        item.lane not in admitted_lanes or item.domain not in _PUBLIC_DOMAINS
        for item in evidence.items
    ):
        raise CanonicalV2ConsumerIntegrityError(
            "evidence item escaped the planned lane/domain set"
        )
    if any(
        trace.release_id != plan.release_id or trace.lane not in admitted_lanes
        for trace in evidence.traces
    ):
        raise CanonicalV2ConsumerIntegrityError(
            "retrieval trace escaped the planned release/lane set"
        )
    item_ids = {item.evidence_id for item in evidence.items}
    if len(item_ids) != len(evidence.items):
        raise CanonicalV2ConsumerIntegrityError(
            "evidence set contains duplicate evidence IDs"
        )
    answer_references = _answer_evidence_references(evidence)
    retained_references = _retained_evidence_references(evidence)
    if item_ids and not item_ids <= retained_references:
        raise CanonicalV2ConsumerIntegrityError(
            "evidence items are not closed by retained traces/handles"
        )
    if answer_references and not answer_references <= item_ids:
        raise CanonicalV2ConsumerIntegrityError(
            "evidence metadata references an absent item"
        )
    budget = plan.supplemental_budget
    receipt = evidence.supplemental_budget_receipt
    if budget is None:
        raise CanonicalV2ConsumerIntegrityError(
            "release-bound read requires a supplemental budget"
        )
    if receipt is not None and (
        receipt.provider_calls > budget.max_provider_calls
        or receipt.retry_count > budget.max_retries
        or receipt.elapsed_ms > budget.max_wall_time_ms
        or receipt.cost_units > budget.max_cost_units
        or receipt.attempt_count > budget.max_retries + 1
    ):
        import logging as _logging

        _logging.getLogger("canonical-v2-admin").error(
            "budget receipt exceeded: elapsed_ms=%s wall=%s cost=%s cap=%s "
            "provider_calls=%s/%s retries=%s/%s attempts=%s",
            receipt.elapsed_ms,
            budget.max_wall_time_ms,
            receipt.cost_units,
            budget.max_cost_units,
            receipt.provider_calls,
            budget.max_provider_calls,
            receipt.retry_count,
            budget.max_retries,
            receipt.attempt_count,
        )
        raise CanonicalV2ConsumerIntegrityError(
            "supplemental budget receipt exceeds the server-owned plan"
        )
    return evidence


class _ValidatedKnowledgeRead:
    def __init__(self, *, delegate: Any) -> None:
        self._delegate = delegate

    def execute(self, plan: RetrievalPlan) -> EvidenceSet:
        exact_plan = RetrievalPlan.model_validate(plan.model_dump(mode="json"))
        raw = self._delegate.execute(exact_plan)
        return _validated_evidence_set(raw, plan=exact_plan)


def _projection_evidence_ids(projection: Any) -> tuple[str, ...]:
    values: list[str] = []
    for lineage in projection.field_lineage:
        values.extend(lineage.supporting_assertion_ids)
    return tuple(dict.fromkeys(values))


def _projection_payload(projection: Any) -> dict[str, Any]:
    payload = projection.model_dump(mode="json")
    payload["domain"] = projection.entity_type
    payload["evidence_ids"] = list(_projection_evidence_ids(projection))
    payload["limitations"] = [f"quality_status:{projection.quality_status}"]
    return payload


def _projection_query_text(projection: Any) -> str:
    payload = projection.model_dump(mode="json")
    for field in ("name", "title", "normalized_name"):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return f"“{value}”"
    return projection.canonical_identity_id


def _nested_reference_id(value: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get("reference_id")
    return value


def _filter_value(projection: Any, field: str) -> Any:
    payload = projection.model_dump(mode="json")
    return _nested_reference_id(payload.get(field))


@dataclass(frozen=True, slots=True)
class CanonicalV2AdminRuntime:
    """Read-only release-scoped projection and retrieval interface."""

    release_id: str
    manifest: BuildManifest
    candidate_projection: CandidateProjectionResult
    relationship_authority: RelationshipProjectionResult
    planner: _ServerOwnedPlanner
    knowledge_read: _ValidatedKnowledgeRead
    chat_adapter: CanonicalV2ChatAdapter
    gap_operations: Any

    @property
    def as_of(self) -> datetime:
        return self.candidate_projection.as_of

    def status(self) -> dict[str, Any]:
        gap_summary = _exact_model(
            self.gap_operations.list_for_admin(
                GapAdminQuery(release_id=self.release_id)
            ),
            GapAdminPage,
            "knowledge gap admin summary",
        )
        counts = {
            domain: sum(
                projection.entity_type == domain
                for projection in self.candidate_projection.public_domain_projections
            )
            for domain in _PUBLIC_DOMAINS
        }
        return {
            "release_id": self.release_id,
            "manifest_sha256": self.manifest.manifest_sha256,
            "as_of": self.as_of,
            "domains": [
                {
                    "release_id": self.release_id,
                    "domain": domain,
                    "record_count": counts[domain],
                }
                for domain in _PUBLIC_DOMAINS
            ],
            "gap_summary": gap_summary.model_dump(mode="json"),
        }

    def _projections(self, domain: PublicDomain) -> tuple[Any, ...]:
        return tuple(
            projection
            for projection in self.candidate_projection.public_domain_projections
            if projection.entity_type == domain
        )

    def _execute_read(
        self,
        *,
        query: str,
        displayed_entity_ids: tuple[str, ...] = (),
        enumeration_context: EnumerationPlanningContext | None = None,
        expected_relationship_path: tuple[str, str, str, str] | None = None,
    ) -> tuple[RetrievalPlan, EvidenceSet]:
        identity = _canonical_sha256(
            {
                "release_id": self.release_id,
                "query": query,
                "displayed_entity_ids": displayed_entity_ids,
                "enumeration_context": (
                    None
                    if enumeration_context is None
                    else enumeration_context.model_dump(mode="json")
                ),
            }
        )
        request = QueryPlanningRequest(
            request_id=f"query-request:admin:sha256:{identity}",
            release_id=self.release_id,
            original_query=query,
            as_of=self.as_of,
            displayed_entity_ids=displayed_entity_ids,
            enumeration_context=enumeration_context,
        )
        plan = self.planner.plan(request)
        if expected_relationship_path is not None and tuple(
            (
                path.relationship_type_id,
                path.direction,
                path.source_type,
                path.target_type,
            )
            for path in plan.relationship_paths
        ) != (expected_relationship_path,):
            raise CanonicalV2ConsumerIntegrityError(
                "related query plan differs from its bounded route"
            )
        evidence = self.knowledge_read.execute(plan)
        return plan, evidence

    def list_domain(
        self,
        *,
        domain: PublicDomain,
        q: str | None,
        filters: tuple[tuple[str, str], ...],
        sort: str,
        order: Literal["asc", "desc"],
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        projections = list(self._projections(domain))
        retrieval_query = q
        if retrieval_query is None and projections:
            retrieval_query = _projection_query_text(projections[0])
        _, evidence = self._execute_read(query=retrieval_query or domain)
        if q is not None:
            needle = q.casefold()
            projections = [
                projection
                for projection in projections
                if needle
                in json.dumps(
                    projection.model_dump(mode="json"), ensure_ascii=False
                ).casefold()
            ]
        for field, expected in filters:
            projections = [
                projection
                for projection in projections
                if str(_filter_value(projection, field)) == expected
            ]
        projections.sort(key=lambda value: value.canonical_identity_id)
        present = [
            projection
            for projection in projections
            if _filter_value(projection, sort) is not None
        ]
        missing = [
            projection
            for projection in projections
            if _filter_value(projection, sort) is None
        ]
        present.sort(
            key=lambda value: _filter_value(value, sort),
            reverse=order == "desc",
        )
        projections = [*present, *missing]
        total = len(projections)
        selected = projections[offset : offset + limit]
        return {
            "release_id": self.release_id,
            "domain": domain,
            "as_of": self.as_of,
            "items": [_projection_payload(item) for item in selected],
            "total": total,
            "limit": limit,
            "offset": offset,
            "sort_keys": [
                {"field": sort, "order": order},
                {"field": "canonical_identity_id", "order": "asc"},
            ],
            "filter_receipt": (
                None
                if not filters
                else {"field": filters[0][0], "value": filters[0][1]}
            ),
            "retrieval_traces": [
                trace.model_dump(mode="json") for trace in evidence.traces
            ],
            "limitations": [
                item.model_dump(mode="json") for item in evidence.limitations
            ]
            or ["path_eligibility_applies"],
        }

    def detail(
        self, *, domain: PublicDomain, canonical_id: str
    ) -> dict[str, Any] | None:
        projection = next(
            (
                item
                for item in self._projections(domain)
                if item.canonical_identity_id == canonical_id
            ),
            None,
        )
        if projection is None:
            return None
        _, evidence = self._execute_read(query=_projection_query_text(projection))
        return {
            **_projection_payload(projection),
            "retrieval_traces": [
                trace.model_dump(mode="json") for trace in evidence.traces
            ],
        }

    def facets(self, *, domain: PublicDomain, field: str) -> dict[str, Any]:
        values: dict[str, tuple[Any, int]] = {}
        for projection in self._projections(domain):
            value = _filter_value(projection, field)
            if value is None:
                continue
            key = str(value).casefold()
            display, count = values.get(key, (value, 0))
            values[key] = (display, count + 1)
        buckets = [
            {
                "value": display,
                "normalized_value": normalized,
                "count": count,
            }
            for normalized, (display, count) in values.items()
        ]
        buckets.sort(key=lambda bucket: (-bucket["count"], bucket["normalized_value"]))
        return {
            "release_id": self.release_id,
            "domain": domain,
            "field": field,
            "buckets": buckets[:100],
        }

    def related(
        self,
        *,
        domain: PublicDomain,
        canonical_id: str,
        relation_type: str,
        limit: int,
    ) -> dict[str, Any]:
        if not any(
            projection.canonical_identity_id == canonical_id
            for projection in self._projections(domain)
        ):
            raise CanonicalV2ConsumerInputError(
                "related source does not exist in the requested domain"
            )
        try:
            (
                target_domain,
                stored_relationship_type,
                source_endpoint_name,
                target_endpoint_name,
                expected_path,
            ) = _RELATIONSHIP_ROUTES[(domain, relation_type)]
        except KeyError as exc:
            raise CanonicalV2ConsumerInputError(
                "relationship route is not supported"
            ) from exc
        enumeration_context = EnumerationPlanningContext(
            requested=True,
            scope=(
                _REPRESENTATIVE_SCOPE
                if expected_path == _COMPANY_PATENT_PATH
                else f"{relation_type}:{domain}"
            ),
            as_of=self.as_of,
            finite_universe=None,
        )
        _, evidence = self._execute_read(
            query=f"Canonical V2 admin related {domain} {canonical_id}",
            displayed_entity_ids=(canonical_id,),
            enumeration_context=enumeration_context,
            expected_relationship_path=expected_path,
        )
        authority_target_ids: set[str] = set()
        for relationship in self.relationship_authority.current_relationships:
            if (
                relationship.relationship_type_id != stored_relationship_type
                or relationship.relationship_type_version != _RELATIONSHIP_VERSION
            ):
                continue
            source_endpoint = getattr(relationship, source_endpoint_name)
            target_endpoint = getattr(relationship, target_endpoint_name)
            if (
                source_endpoint.reference_kind == "canonical_identity"
                and source_endpoint.endpoint_type == domain
                and source_endpoint.canonical_identity_id == canonical_id
                and target_endpoint.reference_kind == "canonical_identity"
                and target_endpoint.endpoint_type == target_domain
                and target_endpoint.canonical_identity_id is not None
            ):
                authority_target_ids.add(target_endpoint.canonical_identity_id)
        evidence_target_ids = {
            item.object_id
            for item in evidence.items
            if item.lane == "relationship" and item.domain == target_domain
        }
        eligible_target_ids = authority_target_ids & evidence_target_ids
        targets = tuple(
            projection
            for projection in self._projections(target_domain)
            if projection.canonical_identity_id in eligible_target_ids
        )[:limit]
        relationship_lineage = [
            item.local_projection_trace.model_dump(mode="json")
            for item in evidence.items
            if item.local_projection_trace is not None
        ]
        return {
            "release_id": self.release_id,
            "domain": domain,
            "canonical_id": canonical_id,
            "relation_type": relation_type,
            "limit": limit,
            "items": [_projection_payload(item) for item in targets],
            "relationship_lineage": relationship_lineage,
            "retrieval_traces": [
                trace.model_dump(mode="json") for trace in evidence.traces
            ],
            "limitations": [
                item.model_dump(mode="json") for item in evidence.limitations
            ]
            or ["relationship_snapshot_applies"],
        }

    def export(self, *, domain: PublicDomain, ids: Sequence[str]) -> tuple[str, ...]:
        by_id = {
            projection.canonical_identity_id: projection
            for projection in self._projections(domain)
        }
        if any(canonical_id not in by_id for canonical_id in ids):
            raise CanonicalV2ConsumerInputError(
                "export IDs must all exist in the requested domain"
            )
        return tuple(
            json.dumps(
                by_id[canonical_id].model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            for canonical_id in ids
        )

    def record_chat_feedback(
        self,
        *,
        session_id: str,
        feedback_type: str,
        note: str | None,
    ) -> Any:
        checkpoint = self.chat_adapter.get_feedback_checkpoint(session_id)
        if checkpoint is None or checkpoint.release_id != self.release_id:
            raise CanonicalV2ConsumerIntegrityError(
                "chat feedback requires a same-release server checkpoint"
            )
        symptom = feedback_type.strip()
        if note is not None and note.strip():
            symptom = f"{symptom}: {note.strip()}"
        signal_identity = {
            "session_id": checkpoint.session_id,
            "turn_id": checkpoint.turn_id,
            "release_id": checkpoint.release_id,
            "query_trace_id": checkpoint.query_trace_id,
            "answer_trace_id": checkpoint.answer_trace_id,
            "feedback_type": feedback_type,
            "note": note,
            "checkpoint_sha256": checkpoint.content_sha256,
        }
        signal = GapSignal(
            signal_id=(
                "gap-signal:chat-feedback:sha256:" + _canonical_sha256(signal_identity)
            ),
            trigger=GapTrigger.user_feedback,
            release_id=checkpoint.release_id,
            affected_domains=checkpoint.affected_domains,
            affected_paths=checkpoint.affected_paths,
            query_trace_id=checkpoint.query_trace_id,
            answer_trace_id=checkpoint.answer_trace_id,
            observed_symptom=symptom,
            evidence_ids=checkpoint.evidence_ids,
            observed_at=checkpoint.observed_at,
        )
        return self.gap_operations.record(signal)


@dataclass(frozen=True, slots=True)
class CanonicalV2ConsumerRuntime:
    """One aggregate identity for every candidate consumer dependency."""

    release_id: str
    admin_runtime: CanonicalV2AdminRuntime
    chat_adapter: CanonicalV2ChatAdapter
    gap_operations: Any


def require_canonical_v2_consumer_runtime(value: object) -> CanonicalV2ConsumerRuntime:
    if type(value) is not CanonicalV2ConsumerRuntime:
        raise CanonicalV2ConsumerIntegrityError(
            "candidate consumer runtime has the wrong aggregate type"
        )
    runtime = cast(CanonicalV2ConsumerRuntime, value)
    if (
        type(runtime.admin_runtime) is not CanonicalV2AdminRuntime
        or type(runtime.chat_adapter) is not CanonicalV2ChatAdapter
        or runtime.release_id != runtime.admin_runtime.release_id
        or runtime.admin_runtime.chat_adapter is not runtime.chat_adapter
        or runtime.admin_runtime.gap_operations is not runtime.gap_operations
    ):
        raise CanonicalV2ConsumerIntegrityError(
            "candidate consumer runtime members are cross-wired"
        )
    return runtime


def compose_canonical_v2_consumer_runtime(
    *,
    published_release: PublishedRelease,
    release_verification: ReleaseVerification,
    release_bundle: IsolatedReleaseBundle,
    index_projection_request: IndexProjectionRequest,
    planner: Any,
    knowledge_read: Any,
    answer_factory: Callable[[], Any],
    answer_session_fork: Callable[[Any], Any],
    gap_operations: Any,
    supplemental_budget: SupplementalBudget,
) -> CanonicalV2ConsumerRuntime:
    """Compose one validated release graph without invoking opaque ports."""

    (
        _,
        _,
        bundle,
        _,
        candidate,
        expected_binding,
    ) = _require_artifact_graph(
        published_release=published_release,
        release_verification=release_verification,
        release_bundle=release_bundle,
        index_projection_request=index_projection_request,
    )
    exact_budget = _exact_model(
        supplemental_budget,
        SupplementalBudget,
        "supplemental_budget",
    )
    controlled_planner = _ServerOwnedPlanner(
        delegate=planner,
        expected_binding=expected_binding,
        supplemental_budget=exact_budget,
    )
    validated_read = _ValidatedKnowledgeRead(delegate=knowledge_read)
    newly_created_answer: list[Any | None] = [None]

    def per_turn_answer_factory() -> Any:
        answer = answer_factory()
        newly_created_answer[0] = answer
        return answer

    def per_turn_answer_fork(answer: Any) -> Any:
        if answer is newly_created_answer[0]:
            newly_created_answer[0] = None
        else:
            # Revalidate the configured factory on every later turn while the
            # committed session is forked copy-on-write from its prior state.
            fresh = answer_factory()
            answer_session_fork(fresh)
        return answer_session_fork(answer)

    chat_adapter = CanonicalV2ChatAdapter(
        release_id=bundle.release_id,
        planner=controlled_planner,
        knowledge_read=validated_read,
        answer_factory=per_turn_answer_factory,
        answer_session_fork=per_turn_answer_fork,
    )
    admin_runtime = CanonicalV2AdminRuntime(
        release_id=bundle.release_id,
        manifest=bundle.manifest,
        candidate_projection=candidate,
        relationship_authority=cast(
            RelationshipProjectionResult,
            bundle.relationship_projection_result,
        ),
        planner=controlled_planner,
        knowledge_read=validated_read,
        chat_adapter=chat_adapter,
        gap_operations=gap_operations,
    )
    runtime = CanonicalV2ConsumerRuntime(
        release_id=bundle.release_id,
        admin_runtime=admin_runtime,
        chat_adapter=chat_adapter,
        gap_operations=gap_operations,
    )
    return require_canonical_v2_consumer_runtime(runtime)


__all__ = [
    "CanonicalV2AdminRuntime",
    "CanonicalV2ConsumerInputError",
    "CanonicalV2ConsumerIntegrityError",
    "CanonicalV2ConsumerRuntime",
    "compose_canonical_v2_consumer_runtime",
    "require_canonical_v2_consumer_runtime",
]
