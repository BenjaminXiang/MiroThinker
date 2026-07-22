"""Build deterministic release-scoped lookup and vector projections.

The module owns logical index construction and exact upstream replay. Physical target
admission and Milvus/SQLite mechanics live behind a package-internal materializer seam.
It has no active-release, alias, promotion, or rollback capability.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
import hashlib
import json
from typing import Literal, Protocol, cast

from pydantic import Field, JsonValue, ValidationError, field_validator, model_validator

from .candidate_projection import (
    CandidateProjectionIntegrityError,
    CandidateProjectionRequest,
    CandidateProjectionResult,
    PublicDomainProjection,
    compose_candidate_projections,
)
from .contracts import (
    CanonicalDatetime,
    ContractModel,
    IndexProjectionManifest,
    InternalReferenceType,
    NonEmptyStr,
    PolicyOutcome,
    ProjectionScope,
    PublicProjectionDomain,
    Sha256,
)
from .domain_projection_models import (
    CompanyProjection,
    PaperProjection,
    PatentProjection,
    ProfessorProjection,
)
from .internal_reference_projection import (
    PersonProjection,
    TechnologyConceptProjection,
    TechnologyRouteProjection,
)
from .path_eligibility import (
    PathEligibilityEngine,
    PathEligibilityIntegrityError,
    PathEligibilityRequest,
    PathEligibilityResult,
)


LOOKUP_PROJECTION_VERSION = "canonical-v2-lookup-projection-v1"
LOOKUP_SCHEMA_VERSION = "canonical-v2-lookup-schema-v1"
_VECTOR_PATH = "semantic_recall"
_LOOKUP_PATH = "exact_lookup"


class IndexProjectionIntegrityError(ValueError):
    """The supplied projection graph cannot produce one exact index release."""


class FullRebuildRequiredError(ValueError):
    """An incremental build was requested for a release requiring full rebuild."""


class ProjectionView(str, Enum):
    default = "default"
    identity = "identity"
    research = "research"


class LookupProjectionManifest(ContractModel):
    projection_id: NonEmptyStr
    release_id: NonEmptyStr
    projection_scope: ProjectionScope
    domain: PublicProjectionDomain | None
    reference_type: InternalReferenceType | None
    path: Literal["exact_lookup"] = _LOOKUP_PATH
    projection_version: Literal["canonical-v2-lookup-projection-v1"] = (
        LOOKUP_PROJECTION_VERSION
    )
    schema_version: Literal["canonical-v2-lookup-schema-v1"] = LOOKUP_SCHEMA_VERSION
    eligibility_policy_version: NonEmptyStr
    document_count: int = Field(ge=0)
    entity_ids_sha256: Sha256
    content_sha256: Sha256
    full_rebuild: bool

    @model_validator(mode="after")
    def validate_owner(self) -> LookupProjectionManifest:
        _validate_owner(
            self.projection_scope,
            self.domain,
            self.reference_type,
        )
        return self


class LookupProjectionDocument(ContractModel):
    document_id: NonEmptyStr
    canonical_object_id: NonEmptyStr
    release_id: NonEmptyStr
    projection_id: NonEmptyStr
    projection_scope: ProjectionScope
    domain: PublicProjectionDomain | None
    reference_type: InternalReferenceType | None
    path: Literal["exact_lookup"] = _LOOKUP_PATH
    projection_view: ProjectionView
    projection_version: Literal["canonical-v2-lookup-projection-v1"] = (
        LOOKUP_PROJECTION_VERSION
    )
    schema_version: Literal["canonical-v2-lookup-schema-v1"] = LOOKUP_SCHEMA_VERSION
    eligibility_policy_version: NonEmptyStr
    eligibility_decision_id: NonEmptyStr | None
    eligibility_outcome: Literal["admitted", "limited"]
    eligibility_limitations: tuple[NonEmptyStr, ...] = ()
    source_projection_content_sha256: Sha256
    lookup_content: NonEmptyStr
    lookup_content_sha256: Sha256
    source_evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("source_evidence_ids", "eligibility_limitations")
    @classmethod
    def validate_sorted_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("lookup document lineage values must be sorted and unique")
        return values

    @model_validator(mode="after")
    def validate_document(self) -> LookupProjectionDocument:
        _validate_owner(
            self.projection_scope,
            self.domain,
            self.reference_type,
        )
        if self.projection_scope is ProjectionScope.public_domain:
            if self.eligibility_decision_id is None:
                raise ValueError(
                    "public lookup document requires an eligibility decision"
                )
        elif (
            self.eligibility_decision_id is not None
            or self.eligibility_outcome != "admitted"
            or self.eligibility_limitations
        ):
            raise ValueError(
                "internal lookup document uses decision-free admitted eligibility"
            )
        if self.eligibility_outcome == "limited" and not self.eligibility_limitations:
            raise ValueError("limited lookup document requires a visible limitation")
        if self.lookup_content_sha256 != _sha256_text(self.lookup_content):
            raise ValueError("lookup content hash does not bind lookup content")
        return self


class IndexProjectionPoint(ContractModel):
    point_id: NonEmptyStr
    canonical_object_id: NonEmptyStr
    release_id: NonEmptyStr
    projection_id: NonEmptyStr
    projection_scope: ProjectionScope
    domain: PublicProjectionDomain | None
    reference_type: InternalReferenceType | None
    path: Literal["semantic_recall"] = _VECTOR_PATH
    projection_view: ProjectionView
    projection_version: NonEmptyStr
    schema_version: NonEmptyStr
    embedding_model: NonEmptyStr
    eligibility_policy_version: NonEmptyStr
    eligibility_decision_id: NonEmptyStr | None
    eligibility_outcome: Literal["admitted", "limited"]
    eligibility_limitations: tuple[NonEmptyStr, ...] = ()
    source_projection_content_sha256: Sha256
    embedded_content: NonEmptyStr
    embedded_content_sha256: Sha256
    source_evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("source_evidence_ids", "eligibility_limitations")
    @classmethod
    def validate_sorted_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("index point lineage values must be sorted and unique")
        return values

    @model_validator(mode="after")
    def validate_point(self) -> IndexProjectionPoint:
        _validate_owner(
            self.projection_scope,
            self.domain,
            self.reference_type,
        )
        if self.projection_scope is ProjectionScope.public_domain:
            if self.eligibility_decision_id is None:
                raise ValueError("public vector point requires an eligibility decision")
        elif (
            self.eligibility_decision_id is not None
            or self.eligibility_outcome != "admitted"
            or self.eligibility_limitations
        ):
            raise ValueError(
                "internal vector point uses decision-free admitted eligibility"
            )
        if self.eligibility_outcome == "limited" and not self.eligibility_limitations:
            raise ValueError("limited vector point requires a visible limitation")
        if self.embedded_content_sha256 != _sha256_text(self.embedded_content):
            raise ValueError("embedded content hash does not bind embedded content")
        return self


class IndexProjectionPolicySnapshot(ContractModel):
    release_id: NonEmptyStr
    index_projection_version: NonEmptyStr
    lookup_projection_version: Literal["canonical-v2-lookup-projection-v1"] = (
        LOOKUP_PROJECTION_VERSION
    )
    lookup_schema_version: Literal["canonical-v2-lookup-schema-v1"] = (
        LOOKUP_SCHEMA_VERSION
    )
    vector_schema_version: NonEmptyStr
    embedding_model: NonEmptyStr
    public_path_policy_versions: tuple[NonEmptyStr, ...] = Field(min_length=1)
    internal_auxiliary_policy_version: NonEmptyStr

    @field_validator("public_path_policy_versions")
    @classmethod
    def validate_policy_versions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("public path-policy versions must be sorted and unique")
        return values


class IndexProjectionRebuildDecision(ContractModel):
    decision_id: NonEmptyStr
    release_id: NonEmptyStr
    reason_codes: tuple[
        Literal[
            "initial_release",
            "schema_version_changed",
            "embedding_model_changed",
            "eligibility_changed",
        ],
        ...,
    ] = Field(min_length=1)
    affected_projection_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("reason_codes", "affected_projection_ids")
    @classmethod
    def validate_sorted_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("rebuild decision values must be sorted and unique")
        return values


class IndexProjectionRequest(ContractModel):
    candidate_projection_request: CandidateProjectionRequest
    candidate_projection_result: CandidateProjectionResult
    public_path_eligibility_requests: tuple[PathEligibilityRequest, ...]
    public_path_eligibility_results: tuple[PathEligibilityResult, ...]
    index_projection_version: NonEmptyStr
    vector_schema_version: NonEmptyStr
    embedding_model: NonEmptyStr
    internal_auxiliary_policy_version: NonEmptyStr
    build_mode: Literal["full", "incremental"]
    prior_accepted_snapshot: IndexProjectionPolicySnapshot | None = None

    @model_validator(mode="after")
    def validate_envelope(self) -> IndexProjectionRequest:
        if (
            self.candidate_projection_request.release_id
            != self.candidate_projection_result.release_id
        ):
            raise ValueError("index projection candidate release differs")
        if len(self.public_path_eligibility_requests) != len(
            self.public_path_eligibility_results
        ):
            raise ValueError("path eligibility requests/results must be paired")
        if not self.public_path_eligibility_requests:
            raise ValueError("public index projection requires path eligibility")
        return self


class IndexProjectionActualState(ContractModel):
    index_projections: tuple[IndexProjectionManifest, ...] = Field(
        min_length=8,
        max_length=8,
    )
    lookup_projections: tuple[LookupProjectionManifest, ...] = Field(
        min_length=7,
        max_length=7,
    )


class IndexProjectionMaterializationReceipt(ContractModel):
    schema_version: Literal["canonical-v2-isolated-index-rebuild-receipt-v1"] = (
        "canonical-v2-isolated-index-rebuild-receipt-v1"
    )
    release_id: NonEmptyStr
    target_id: NonEmptyStr
    target_kind: Literal["isolated-candidate"]
    vector_backend: NonEmptyStr
    lookup_backend: NonEmptyStr
    point_ids: tuple[NonEmptyStr, ...]
    lookup_document_ids: tuple[NonEmptyStr, ...]
    index_projections: tuple[IndexProjectionManifest, ...] = Field(
        min_length=8,
        max_length=8,
    )
    lookup_projections: tuple[LookupProjectionManifest, ...] = Field(
        min_length=7,
        max_length=7,
    )
    source_inventory_sha256: Sha256
    backup_manifest_sha256: Sha256
    restore_verification_sha256: Sha256
    acceptance_record_sha256: Sha256
    built_at: CanonicalDatetime
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_receipt(self) -> IndexProjectionMaterializationReceipt:
        if self.point_ids != tuple(sorted(set(self.point_ids))):
            raise ValueError("receipt point IDs must be sorted and unique")
        if self.lookup_document_ids != tuple(sorted(set(self.lookup_document_ids))):
            raise ValueError("receipt lookup document IDs must be sorted and unique")
        payload = cast(
            JsonValue,
            self.model_dump(mode="json", exclude={"content_sha256"}),
        )
        if self.content_sha256 != _canonical_sha256(payload):
            raise ValueError("receipt hash does not bind the isolated rebuild")
        return self


class IndexProjectionResult(ContractModel):
    release_id: NonEmptyStr
    points: tuple[IndexProjectionPoint, ...]
    lookup_documents: tuple[LookupProjectionDocument, ...]
    expected_index_projections: tuple[IndexProjectionManifest, ...] = Field(
        min_length=8,
        max_length=8,
    )
    actual_index_projections: tuple[IndexProjectionManifest, ...] = Field(
        min_length=8,
        max_length=8,
    )
    expected_lookup_projections: tuple[LookupProjectionManifest, ...] = Field(
        min_length=7,
        max_length=7,
    )
    actual_lookup_projections: tuple[LookupProjectionManifest, ...] = Field(
        min_length=7,
        max_length=7,
    )
    rebuild_decisions: tuple[IndexProjectionRebuildDecision, ...]
    policy_snapshot: IndexProjectionPolicySnapshot
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_result(self) -> IndexProjectionResult:
        if self.policy_snapshot.release_id != self.release_id:
            raise ValueError("index policy snapshot release differs")
        if self.points != tuple(
            sorted(
                self.points,
                key=lambda item: (item.projection_id, item.canonical_object_id),
            )
        ):
            raise ValueError("index points must be deterministically sorted")
        if self.lookup_documents != tuple(
            sorted(
                self.lookup_documents,
                key=lambda item: (item.projection_id, item.canonical_object_id),
            )
        ):
            raise ValueError("lookup documents must be deterministically sorted")
        if self.expected_index_projections != self.actual_index_projections:
            raise ValueError(
                "isolated index readback differs from expected projections"
            )
        if self.expected_lookup_projections != self.actual_lookup_projections:
            raise ValueError(
                "isolated lookup readback differs from expected projections"
            )
        payload = cast(
            JsonValue,
            self.model_dump(mode="json", exclude={"content_sha256"}),
        )
        if self.content_sha256 != _canonical_sha256(payload):
            raise ValueError("result hash does not bind the complete index projection")
        return self


class _IndexProjectionMaterializer(Protocol):
    @property
    def last_receipt(self) -> IndexProjectionMaterializationReceipt | None: ...

    def materialize(
        self,
        *,
        request: IndexProjectionRequest,
        points: tuple[IndexProjectionPoint, ...],
        lookup_documents: tuple[LookupProjectionDocument, ...],
        expected_index_projections: tuple[IndexProjectionManifest, ...],
        expected_lookup_projections: tuple[LookupProjectionManifest, ...],
    ) -> IndexProjectionActualState: ...


class _EphemeralMaterializer:
    @property
    def last_receipt(self) -> None:
        return None

    def materialize(
        self,
        *,
        request: IndexProjectionRequest,
        points: tuple[IndexProjectionPoint, ...],
        lookup_documents: tuple[LookupProjectionDocument, ...],
        expected_index_projections: tuple[IndexProjectionManifest, ...],
        expected_lookup_projections: tuple[LookupProjectionManifest, ...],
    ) -> IndexProjectionActualState:
        del request, points, lookup_documents
        return IndexProjectionActualState(
            index_projections=expected_index_projections,
            lookup_projections=expected_lookup_projections,
        )


class IndexProjectionBuilder:
    """Replay one candidate graph and materialize its lookup/vector projections."""

    def __init__(
        self, materializer: _IndexProjectionMaterializer | None = None
    ) -> None:
        self._materializer = materializer or _EphemeralMaterializer()

    @property
    def last_materialization_receipt(
        self,
    ) -> IndexProjectionMaterializationReceipt | None:
        return self._materializer.last_receipt

    def build(self, request: IndexProjectionRequest) -> IndexProjectionResult:
        candidate_result = _replay_candidate_projection(request)
        path_pairs = _replay_path_eligibility(request, candidate_result)
        try:
            validated = IndexProjectionRequest.model_validate(
                request.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            raise IndexProjectionIntegrityError(
                "index projection request failed typed integrity validation"
            ) from exc

        policy_snapshot = _policy_snapshot(validated, path_pairs)
        reason_codes = _full_rebuild_reasons(
            policy_snapshot,
            validated.prior_accepted_snapshot,
        )
        if reason_codes and validated.build_mode == "incremental":
            raise FullRebuildRequiredError(
                "index policy state requires a full rebuild: " + ", ".join(reason_codes)
            )
        full_rebuild = validated.build_mode == "full"
        points = _vector_points(validated, candidate_result, path_pairs)
        lookup_documents = _lookup_documents(
            validated,
            candidate_result,
            path_pairs,
        )
        expected_index_projections = build_index_projection_manifests(
            request=validated,
            points=points,
            full_rebuild=full_rebuild,
        )
        expected_lookup_projections = build_lookup_projection_manifests(
            request=validated,
            documents=lookup_documents,
            full_rebuild=full_rebuild,
        )
        actual = self._materializer.materialize(
            request=validated,
            points=points,
            lookup_documents=lookup_documents,
            expected_index_projections=expected_index_projections,
            expected_lookup_projections=expected_lookup_projections,
        )
        if (
            actual.index_projections != expected_index_projections
            or actual.lookup_projections != expected_lookup_projections
        ):
            raise IndexProjectionIntegrityError(
                "isolated lookup/vector readback differs from expected build"
            )
        rebuild_decisions = _rebuild_decisions(
            release_id=validated.candidate_projection_result.release_id,
            reason_codes=reason_codes,
            affected_projection_ids=tuple(
                item.projection_id
                for item in (
                    *expected_index_projections,
                    *expected_lookup_projections,
                )
            ),
        )
        values = {
            "release_id": validated.candidate_projection_result.release_id,
            "points": points,
            "lookup_documents": lookup_documents,
            "expected_index_projections": expected_index_projections,
            "actual_index_projections": actual.index_projections,
            "expected_lookup_projections": expected_lookup_projections,
            "actual_lookup_projections": actual.lookup_projections,
            "rebuild_decisions": rebuild_decisions,
            "policy_snapshot": policy_snapshot,
        }
        provisional = IndexProjectionResult.model_construct(
            **values,
            content_sha256="0" * 64,
        )
        payload = cast(
            JsonValue,
            provisional.model_dump(mode="json", exclude={"content_sha256"}),
        )
        return IndexProjectionResult(
            **values,
            content_sha256=_canonical_sha256(payload),
        )


def create_ephemeral_index_projection_builder() -> IndexProjectionBuilder:
    """Create the deterministic package-internal no-I/O adapter."""

    return IndexProjectionBuilder()


def _canonical_sha256(value: JsonValue) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}:sha256:{_sha256_text('|'.join(parts))}"


def _validate_owner(
    scope: ProjectionScope,
    domain: PublicProjectionDomain | None,
    reference_type: InternalReferenceType | None,
) -> None:
    if scope is ProjectionScope.public_domain:
        if domain is None or reference_type is not None:
            raise ValueError("public projection requires a public domain only")
        return
    if domain is not None or reference_type is None:
        raise ValueError("internal projection requires an internal reference type only")


def _replay_candidate_projection(
    request: IndexProjectionRequest,
) -> CandidateProjectionResult:
    try:
        replayed = compose_candidate_projections(request.candidate_projection_request)
    except (
        AttributeError,
        CandidateProjectionIntegrityError,
        TypeError,
        ValueError,
        ValidationError,
    ) as exc:
        raise IndexProjectionIntegrityError(
            "candidate projection request failed exact replay"
        ) from exc
    if replayed != request.candidate_projection_result:
        raise IndexProjectionIntegrityError(
            "candidate projection result differs from exact replay"
        )
    return replayed


def _projection_assertion_map(
    projection: PublicDomainProjection,
) -> dict[str, tuple[str, ...]]:
    return {
        lineage.field_path: lineage.supporting_assertion_ids
        for lineage in projection.field_lineage
    }


def _replay_path_eligibility(
    request: IndexProjectionRequest,
    candidate_result: CandidateProjectionResult,
) -> dict[str, tuple[PathEligibilityRequest, PathEligibilityResult]]:
    requests = request.public_path_eligibility_requests
    results = request.public_path_eligibility_results
    if len(requests) != len(results):
        raise IndexProjectionIntegrityError(
            "path eligibility request/result pairing differs"
        )
    pairs: dict[str, tuple[PathEligibilityRequest, PathEligibilityResult]] = {}
    exact_inclusions = {
        decision.subject_identity_id: decision
        for decision in request.candidate_projection_request.internal_reference_projection_request.public_domain_projection_result.inclusion_decisions
    }
    for path_request, supplied_result in zip(requests, results, strict=True):
        try:
            replayed = PathEligibilityEngine().evaluate(path_request)
        except (
            AttributeError,
            PathEligibilityIntegrityError,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            raise IndexProjectionIntegrityError(
                "path eligibility request failed exact replay"
            ) from exc
        if replayed != supplied_result:
            raise IndexProjectionIntegrityError(
                "path eligibility result differs from exact replay"
            )
        projection = path_request.projection
        if projection is None:
            raise IndexProjectionIntegrityError(
                "public path eligibility requires one typed projection"
            )
        identity_id = projection.canonical_identity_id
        if identity_id in pairs:
            raise IndexProjectionIntegrityError(
                "public path eligibility identities must be unique"
            )
        pairs[identity_id] = (path_request, replayed)

    candidates = {
        item.canonical_identity_id: item
        for item in candidate_result.public_domain_projections
    }
    if set(pairs) != set(candidates):
        raise IndexProjectionIntegrityError(
            "path eligibility population differs from public candidate projection"
        )
    for identity_id, candidate in candidates.items():
        path_request, path_result = pairs[identity_id]
        typed = path_request.projection
        assert typed is not None
        exact_inclusion = exact_inclusions.get(identity_id)
        if (
            exact_inclusion is None
            or path_request.inclusion_decision != exact_inclusion
            or path_result.inclusion_decision_id != exact_inclusion.decision_id
            or candidate.inclusion_decision_id != exact_inclusion.decision_id
        ):
            raise IndexProjectionIntegrityError(
                "path eligibility does not bind the exact candidate inclusion decision"
            )
        if (
            path_request.release_id != candidate_result.release_id
            or path_result.release_id != candidate_result.release_id
            or typed.release_id != candidate_result.release_id
            or typed.domain != candidate.entity_type
            or path_result.subject_identity_id != identity_id
            or typed.field_assertion_ids != _projection_assertion_map(candidate)
            or typed.usable_field_paths
            != tuple(sorted(item.field_path for item in candidate.field_lineage))
            or path_result.projection_id != typed.projection_id
        ):
            raise IndexProjectionIntegrityError(
                "path eligibility pair does not bind its exact public projection"
            )
    return pairs


def _decision(
    pair: tuple[PathEligibilityRequest, PathEligibilityResult],
    path: str,
):
    return next(item for item in pair[1].decisions if item.path == path)


def _is_eligible(outcome: PolicyOutcome) -> bool:
    return outcome in {PolicyOutcome.admitted, PolicyOutcome.limited}


def _public_evidence_ids(
    pair: tuple[PathEligibilityRequest, PathEligibilityResult],
    path: str,
) -> tuple[str, ...]:
    decision = _decision(pair, path)
    return tuple(sorted({decision.decision_id, *decision.supporting_assertion_ids}))


def _internal_evidence_ids(
    projection: PersonProjection
    | TechnologyConceptProjection
    | TechnologyRouteProjection,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                *projection.source_anchor_ids,
                *projection.supporting_assertion_ids,
                projection.identity_decision_id,
            }
        )
    )


def _public_embedded_content(
    projection: PublicDomainProjection,
    view: ProjectionView,
) -> str:
    if isinstance(projection, ProfessorProjection):
        if view is ProjectionView.identity:
            content: JsonValue = {
                "name": projection.name,
                "canonical_name_zh": projection.canonical_name_zh,
                "canonical_name_en": projection.canonical_name_en,
                "aliases": list(projection.aliases),
                "institution": projection.institution,
                "department": projection.department.name,
                "title": projection.title,
            }
        elif view is ProjectionView.research:
            content = {
                "profile_summary": projection.profile_summary,
                "paper_summary": projection.paper_summary,
                "patent_summary": projection.patent_summary,
                "research_directions": [
                    item.model_dump(mode="json")
                    for item in projection.research_directions
                ],
                "projects": [
                    item.model_dump(mode="json") for item in projection.projects
                ],
            }
        else:
            raise IndexProjectionIntegrityError(
                "Professor vector projection requires a typed intent view"
            )
        return json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    if view is not ProjectionView.default:
        raise IndexProjectionIntegrityError(
            "non-Professor vector projection requires the default view"
        )
    if isinstance(projection, CompanyProjection):
        content = {
            "name": projection.name,
            "aliases": list(projection.aliases),
            "profile_summary": projection.profile_summary,
            "product_description": projection.product_description,
            "technology_route_summary": projection.technology_route_summary,
            "industry": (
                projection.industry.model_dump(mode="json")
                if projection.industry is not None
                else None
            ),
            "tech_tags": [
                item.model_dump(mode="json") for item in projection.tech_tags
            ],
        }
    elif isinstance(projection, PaperProjection):
        content = {
            "title": projection.title,
            "title_zh": projection.title_zh,
            "abstract": projection.abstract,
            "summary_text": projection.summary_text,
            "summary_zh": projection.summary_zh,
            "tldr": projection.tldr,
            "keywords": list(projection.keywords),
            "fields_of_study": [
                item.model_dump(mode="json") for item in projection.fields_of_study
            ],
        }
    elif isinstance(projection, PatentProjection):
        content = {
            "title": projection.title,
            "title_en": projection.title_en,
            "abstract": projection.abstract,
            "summary_text": projection.summary_text,
            "technology_effect": projection.technology_effect,
            "ipc_codes": [
                item.model_dump(mode="json") for item in projection.ipc_codes
            ],
        }
    else:
        raise IndexProjectionIntegrityError("unknown public projection type")
    return json.dumps(
        cast(JsonValue, content),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _internal_embedded_content(
    projection: PersonProjection
    | TechnologyConceptProjection
    | TechnologyRouteProjection,
) -> str:
    if isinstance(projection, PersonProjection):
        content: JsonValue = {
            "display_name": projection.display_name,
            "aliases": list(projection.aliases),
            "source_public_domains": list(projection.source_public_domains),
            "references": [
                {
                    "name": item.name,
                    "source_kind": item.source_kind,
                }
                for item in projection.references
            ],
        }
    elif isinstance(projection, TechnologyConceptProjection):
        content = {
            "preferred_name": projection.preferred_name,
            "aliases": list(projection.aliases),
            "definition": projection.definition,
            "parent_concept_ids": list(projection.parent_concept_ids),
        }
    elif isinstance(projection, TechnologyRouteProjection):
        content = {
            "preferred_name": projection.preferred_name,
            "aliases": list(projection.aliases),
            "definition": projection.definition,
            "concept_ids": list(projection.concept_ids),
        }
    else:
        raise IndexProjectionIntegrityError("unknown internal projection type")
    return json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _public_vector_specs(
    projection: PublicDomainProjection,
) -> tuple[tuple[ProjectionView, str], ...]:
    if isinstance(projection, ProfessorProjection):
        return (
            (ProjectionView.identity, _vector_projection_id("professor", "identity")),
            (ProjectionView.research, _vector_projection_id("professor", "research")),
        )
    return (
        (
            ProjectionView.default,
            _vector_projection_id(projection.entity_type, "default"),
        ),
    )


def _vector_projection_id(owner: str, view: str) -> str:
    return f"index:semantic-recall:{owner}:{view}"


def _lookup_projection_id(owner: str) -> str:
    return f"lookup:exact-lookup:{owner}"


def _vector_points(
    request: IndexProjectionRequest,
    candidate_result: CandidateProjectionResult,
    path_pairs: dict[str, tuple[PathEligibilityRequest, PathEligibilityResult]],
) -> tuple[IndexProjectionPoint, ...]:
    points: list[IndexProjectionPoint] = []
    for projection in candidate_result.public_domain_projections:
        pair = path_pairs[projection.canonical_identity_id]
        semantic = _decision(pair, _VECTOR_PATH)
        if not _is_eligible(semantic.outcome):
            continue
        eligibility_outcome: Literal["admitted", "limited"] = (
            "admitted" if semantic.outcome is PolicyOutcome.admitted else "limited"
        )
        for view, projection_id in _public_vector_specs(projection):
            content = _public_embedded_content(projection, view)
            points.append(
                IndexProjectionPoint(
                    point_id=_stable_id(
                        "index-point",
                        projection_id,
                        projection.canonical_identity_id,
                        view.value,
                    ),
                    canonical_object_id=projection.canonical_identity_id,
                    release_id=candidate_result.release_id,
                    projection_id=projection_id,
                    projection_scope=ProjectionScope.public_domain,
                    domain=projection.entity_type,
                    reference_type=None,
                    projection_view=view,
                    projection_version=request.index_projection_version,
                    schema_version=request.vector_schema_version,
                    embedding_model=request.embedding_model,
                    eligibility_policy_version=semantic.policy.policy_version,
                    eligibility_decision_id=semantic.decision_id,
                    eligibility_outcome=eligibility_outcome,
                    eligibility_limitations=semantic.limitations,
                    source_projection_content_sha256=projection.content_sha256,
                    embedded_content=content,
                    embedded_content_sha256=_sha256_text(content),
                    source_evidence_ids=_public_evidence_ids(pair, _VECTOR_PATH),
                )
            )
    internal_groups: tuple[
        tuple[
            PersonProjection | TechnologyConceptProjection | TechnologyRouteProjection,
            ...,
        ],
        ...,
    ] = (
        candidate_result.person_projections,
        candidate_result.technology_concept_projections,
        candidate_result.technology_route_projections,
    )
    for group in internal_groups:
        for projection in group:
            owner = projection.reference_type
            projection_id = _vector_projection_id(owner, "default")
            content = _internal_embedded_content(projection)
            object_id = (
                projection.canonical_person_identity_id
                if isinstance(projection, PersonProjection)
                else projection.canonical_technology_identity_id
            )
            points.append(
                IndexProjectionPoint(
                    point_id=_stable_id(
                        "index-point",
                        projection_id,
                        object_id,
                        ProjectionView.default.value,
                    ),
                    canonical_object_id=object_id,
                    release_id=candidate_result.release_id,
                    projection_id=projection_id,
                    projection_scope=ProjectionScope.internal_auxiliary,
                    domain=None,
                    reference_type=owner,
                    projection_view=ProjectionView.default,
                    projection_version=request.index_projection_version,
                    schema_version=request.vector_schema_version,
                    embedding_model=request.embedding_model,
                    eligibility_policy_version=(
                        request.internal_auxiliary_policy_version
                    ),
                    eligibility_decision_id=None,
                    eligibility_outcome="admitted",
                    eligibility_limitations=(),
                    source_projection_content_sha256=projection.content_sha256,
                    embedded_content=content,
                    embedded_content_sha256=_sha256_text(content),
                    source_evidence_ids=_internal_evidence_ids(projection),
                )
            )
    return tuple(
        sorted(points, key=lambda item: (item.projection_id, item.canonical_object_id))
    )


def _lookup_documents(
    request: IndexProjectionRequest,
    candidate_result: CandidateProjectionResult,
    path_pairs: dict[str, tuple[PathEligibilityRequest, PathEligibilityResult]],
) -> tuple[LookupProjectionDocument, ...]:
    documents: list[LookupProjectionDocument] = []
    for projection in candidate_result.public_domain_projections:
        pair = path_pairs[projection.canonical_identity_id]
        lookup = _decision(pair, _LOOKUP_PATH)
        if not _is_eligible(lookup.outcome):
            continue
        eligibility_outcome: Literal["admitted", "limited"] = (
            "admitted" if lookup.outcome is PolicyOutcome.admitted else "limited"
        )
        projection_id = _lookup_projection_id(projection.entity_type)
        content = projection.model_dump_json()
        view = (
            ProjectionView.identity
            if isinstance(projection, ProfessorProjection)
            else ProjectionView.default
        )
        documents.append(
            LookupProjectionDocument(
                document_id=_stable_id(
                    "lookup-document",
                    projection_id,
                    projection.canonical_identity_id,
                    view.value,
                ),
                canonical_object_id=projection.canonical_identity_id,
                release_id=candidate_result.release_id,
                projection_id=projection_id,
                projection_scope=ProjectionScope.public_domain,
                domain=projection.entity_type,
                reference_type=None,
                projection_view=view,
                eligibility_policy_version=lookup.policy.policy_version,
                eligibility_decision_id=lookup.decision_id,
                eligibility_outcome=eligibility_outcome,
                eligibility_limitations=lookup.limitations,
                source_projection_content_sha256=projection.content_sha256,
                lookup_content=content,
                lookup_content_sha256=_sha256_text(content),
                source_evidence_ids=_public_evidence_ids(pair, _LOOKUP_PATH),
            )
        )
    internal_groups: tuple[
        tuple[
            PersonProjection | TechnologyConceptProjection | TechnologyRouteProjection,
            ...,
        ],
        ...,
    ] = (
        candidate_result.person_projections,
        candidate_result.technology_concept_projections,
        candidate_result.technology_route_projections,
    )
    for group in internal_groups:
        for projection in group:
            owner = projection.reference_type
            projection_id = _lookup_projection_id(owner)
            object_id = (
                projection.canonical_person_identity_id
                if isinstance(projection, PersonProjection)
                else projection.canonical_technology_identity_id
            )
            content = projection.model_dump_json()
            documents.append(
                LookupProjectionDocument(
                    document_id=_stable_id(
                        "lookup-document",
                        projection_id,
                        object_id,
                        ProjectionView.default.value,
                    ),
                    canonical_object_id=object_id,
                    release_id=candidate_result.release_id,
                    projection_id=projection_id,
                    projection_scope=ProjectionScope.internal_auxiliary,
                    domain=None,
                    reference_type=owner,
                    projection_view=ProjectionView.default,
                    eligibility_policy_version=(
                        request.internal_auxiliary_policy_version
                    ),
                    eligibility_decision_id=None,
                    eligibility_outcome="admitted",
                    eligibility_limitations=(),
                    source_projection_content_sha256=projection.content_sha256,
                    lookup_content=content,
                    lookup_content_sha256=_sha256_text(content),
                    source_evidence_ids=_internal_evidence_ids(projection),
                )
            )
    return tuple(
        sorted(
            documents,
            key=lambda item: (item.projection_id, item.canonical_object_id),
        )
    )


def _entity_ids_sha256(ids: Iterable[str]) -> str:
    return _sha256_text("|".join(sorted(ids)))


def index_point_content_sha256(points: Iterable[IndexProjectionPoint]) -> str:
    return _sha256_text(
        "|".join(
            sorted(
                _canonical_sha256(cast(JsonValue, item.model_dump(mode="json")))
                for item in points
            )
        )
    )


def _document_content_sha256(documents: Iterable[LookupProjectionDocument]) -> str:
    return _sha256_text(
        "|".join(
            sorted(
                _canonical_sha256(cast(JsonValue, item.model_dump(mode="json")))
                for item in documents
            )
        )
    )


def _vector_manifest_specs() -> tuple[
    tuple[
        str,
        ProjectionScope,
        PublicProjectionDomain | None,
        InternalReferenceType | None,
    ],
    ...,
]:
    return (
        (
            _vector_projection_id("company", "default"),
            ProjectionScope.public_domain,
            "company",
            None,
        ),
        (
            _vector_projection_id("paper", "default"),
            ProjectionScope.public_domain,
            "paper",
            None,
        ),
        (
            _vector_projection_id("patent", "default"),
            ProjectionScope.public_domain,
            "patent",
            None,
        ),
        (
            _vector_projection_id("professor", "identity"),
            ProjectionScope.public_domain,
            "professor",
            None,
        ),
        (
            _vector_projection_id("professor", "research"),
            ProjectionScope.public_domain,
            "professor",
            None,
        ),
        (
            _vector_projection_id("person", "default"),
            ProjectionScope.internal_auxiliary,
            None,
            "person",
        ),
        (
            _vector_projection_id("technology_concept", "default"),
            ProjectionScope.internal_auxiliary,
            None,
            "technology_concept",
        ),
        (
            _vector_projection_id("technology_route", "default"),
            ProjectionScope.internal_auxiliary,
            None,
            "technology_route",
        ),
    )


def build_index_projection_manifests(
    *,
    request: IndexProjectionRequest,
    points: tuple[IndexProjectionPoint, ...],
    full_rebuild: bool,
) -> tuple[IndexProjectionManifest, ...]:
    manifests: list[IndexProjectionManifest] = []
    public_policy_versions = {
        item.policy.policy_version
        for result in request.public_path_eligibility_results
        for item in result.decisions
        if item.path == _VECTOR_PATH
    }
    if len(public_policy_versions) != 1:
        raise IndexProjectionIntegrityError(
            "public semantic projection requires one policy version"
        )
    public_policy_version = next(iter(public_policy_versions))
    for projection_id, scope, domain, reference_type in _vector_manifest_specs():
        owned = tuple(item for item in points if item.projection_id == projection_id)
        policy_version = (
            public_policy_version
            if scope is ProjectionScope.public_domain
            else request.internal_auxiliary_policy_version
        )
        manifests.append(
            IndexProjectionManifest(
                projection_id=projection_id,
                release_id=request.candidate_projection_result.release_id,
                projection_scope=scope,
                domain=domain,
                reference_type=reference_type,
                path=_VECTOR_PATH,
                projection_version=request.index_projection_version,
                schema_version=request.vector_schema_version,
                embedding_model=request.embedding_model,
                eligibility_policy_version=policy_version,
                point_count=len(owned),
                entity_ids_sha256=_entity_ids_sha256(
                    item.canonical_object_id for item in owned
                ),
                content_sha256=index_point_content_sha256(owned),
                full_rebuild=full_rebuild,
            )
        )
    return tuple(manifests)


def _lookup_manifest_specs() -> tuple[
    tuple[
        str,
        ProjectionScope,
        PublicProjectionDomain | None,
        InternalReferenceType | None,
    ],
    ...,
]:
    return (
        (
            _lookup_projection_id("company"),
            ProjectionScope.public_domain,
            "company",
            None,
        ),
        (_lookup_projection_id("paper"), ProjectionScope.public_domain, "paper", None),
        (
            _lookup_projection_id("patent"),
            ProjectionScope.public_domain,
            "patent",
            None,
        ),
        (
            _lookup_projection_id("professor"),
            ProjectionScope.public_domain,
            "professor",
            None,
        ),
        (
            _lookup_projection_id("person"),
            ProjectionScope.internal_auxiliary,
            None,
            "person",
        ),
        (
            _lookup_projection_id("technology_concept"),
            ProjectionScope.internal_auxiliary,
            None,
            "technology_concept",
        ),
        (
            _lookup_projection_id("technology_route"),
            ProjectionScope.internal_auxiliary,
            None,
            "technology_route",
        ),
    )


def build_lookup_projection_manifests(
    *,
    request: IndexProjectionRequest,
    documents: tuple[LookupProjectionDocument, ...],
    full_rebuild: bool,
) -> tuple[LookupProjectionManifest, ...]:
    public_policy_versions = {
        item.policy.policy_version
        for result in request.public_path_eligibility_results
        for item in result.decisions
        if item.path == _LOOKUP_PATH
    }
    if len(public_policy_versions) != 1:
        raise IndexProjectionIntegrityError(
            "public lookup projection requires one policy version"
        )
    public_policy_version = next(iter(public_policy_versions))
    manifests: list[LookupProjectionManifest] = []
    for projection_id, scope, domain, reference_type in _lookup_manifest_specs():
        owned = tuple(item for item in documents if item.projection_id == projection_id)
        manifests.append(
            LookupProjectionManifest(
                projection_id=projection_id,
                release_id=request.candidate_projection_result.release_id,
                projection_scope=scope,
                domain=domain,
                reference_type=reference_type,
                eligibility_policy_version=(
                    public_policy_version
                    if scope is ProjectionScope.public_domain
                    else request.internal_auxiliary_policy_version
                ),
                document_count=len(owned),
                entity_ids_sha256=_entity_ids_sha256(
                    item.canonical_object_id for item in owned
                ),
                content_sha256=_document_content_sha256(owned),
                full_rebuild=full_rebuild,
            )
        )
    return tuple(manifests)


def _policy_snapshot(
    request: IndexProjectionRequest,
    path_pairs: dict[str, tuple[PathEligibilityRequest, PathEligibilityResult]],
) -> IndexProjectionPolicySnapshot:
    policy_versions = tuple(
        sorted(
            {
                decision.policy.policy_version
                for _, result in path_pairs.values()
                for decision in result.decisions
            }
        )
    )
    return IndexProjectionPolicySnapshot(
        release_id=request.candidate_projection_result.release_id,
        index_projection_version=request.index_projection_version,
        vector_schema_version=request.vector_schema_version,
        embedding_model=request.embedding_model,
        public_path_policy_versions=policy_versions,
        internal_auxiliary_policy_version=(request.internal_auxiliary_policy_version),
    )


def _full_rebuild_reasons(
    current: IndexProjectionPolicySnapshot,
    prior: IndexProjectionPolicySnapshot | None,
) -> tuple[
    Literal[
        "initial_release",
        "schema_version_changed",
        "embedding_model_changed",
        "eligibility_changed",
    ],
    ...,
]:
    if prior is None:
        return ("initial_release",)
    reasons: list[
        Literal[
            "initial_release",
            "schema_version_changed",
            "embedding_model_changed",
            "eligibility_changed",
        ]
    ] = []
    if (
        current.vector_schema_version != prior.vector_schema_version
        or current.lookup_schema_version != prior.lookup_schema_version
    ):
        reasons.append("schema_version_changed")
    if current.embedding_model != prior.embedding_model:
        reasons.append("embedding_model_changed")
    if (
        current.public_path_policy_versions != prior.public_path_policy_versions
        or current.internal_auxiliary_policy_version
        != prior.internal_auxiliary_policy_version
    ):
        reasons.append("eligibility_changed")
    return tuple(sorted(reasons))


def _rebuild_decisions(
    *,
    release_id: str,
    reason_codes: tuple[str, ...],
    affected_projection_ids: tuple[str, ...],
) -> tuple[IndexProjectionRebuildDecision, ...]:
    if not reason_codes:
        return ()
    sorted_reasons = tuple(sorted(reason_codes))
    sorted_projection_ids = tuple(sorted(affected_projection_ids))
    decision_id = _stable_id(
        "index-rebuild-decision",
        release_id,
        *sorted_reasons,
        *sorted_projection_ids,
    )
    return (
        IndexProjectionRebuildDecision(
            decision_id=decision_id,
            release_id=release_id,
            reason_codes=cast(
                tuple[
                    Literal[
                        "initial_release",
                        "schema_version_changed",
                        "embedding_model_changed",
                        "eligibility_changed",
                    ],
                    ...,
                ],
                sorted_reasons,
            ),
            affected_projection_ids=sorted_projection_ids,
        ),
    )


__all__ = [
    "FullRebuildRequiredError",
    "IndexProjectionActualState",
    "IndexProjectionBuilder",
    "IndexProjectionIntegrityError",
    "IndexProjectionManifest",
    "IndexProjectionMaterializationReceipt",
    "IndexProjectionPoint",
    "IndexProjectionPolicySnapshot",
    "IndexProjectionRebuildDecision",
    "IndexProjectionRequest",
    "IndexProjectionResult",
    "LOOKUP_PROJECTION_VERSION",
    "LOOKUP_SCHEMA_VERSION",
    "LookupProjectionDocument",
    "LookupProjectionManifest",
    "ProjectionView",
    "build_index_projection_manifests",
    "build_lookup_projection_manifests",
    "create_ephemeral_index_projection_builder",
]
