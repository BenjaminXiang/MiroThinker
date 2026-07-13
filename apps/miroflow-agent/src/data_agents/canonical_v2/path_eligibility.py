"""Deterministic per-path eligibility policy for Canonical V2 candidates.

This package-internal deep module consumes already validated inclusion,
projection, identity, and relationship decisions.  It never reads provider or
query-time state and deliberately has no global ``ready`` compatibility seam.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
import hashlib
from importlib.resources import files
import json
from typing import Any, Literal, cast

from pydantic import Field, JsonValue, ValidationError, field_validator, model_validator

from .contracts import (
    CanonicalDatetime,
    CanonicalIdentityState,
    ContractModel,
    IdentityAction,
    IdentityDecision,
    NonEmptyStr,
    PolicyDecision,
    PolicyKind,
    PolicyOutcome,
    PolicyReference,
    RelationshipDecision,
    RelationshipDecisionState,
    Sha256,
)
from .domain_catalog import CATALOG_CONTENT_SHA256, CATALOG_RESOURCE, PACKAGED_CATALOG


Domain = Literal["company", "paper", "patent", "professor"]
PublishedPath = Literal[
    "exact_lookup",
    "structured_filter",
    "verified_relationship_traversal",
    "semantic_recall",
    "recommendation",
    "ranking",
]
PaperIdentityStatus = Literal["confirmed", "unverified", "rejected", "merged"]
GapKind = Literal["quality", "hard_invariant", "relationship"]

PUBLISHED_USER_PATHS: tuple[PublishedPath, ...] = (
    "exact_lookup",
    "structured_filter",
    "verified_relationship_traversal",
    "semantic_recall",
    "recommendation",
    "ranking",
)
_EXPECTED_TRAVERSAL_DIRECTIONS = frozenset(
    {
        "company_to_patent",
        "company_to_professor",
        "paper_to_professor",
        "patent_to_company",
        "patent_to_professor",
        "professor_to_company",
        "professor_to_paper",
        "professor_to_patent",
    }
)


class PathEligibilityIntegrityError(ValueError):
    """The supplied offline path-policy request is internally inconsistent."""


def _unique(values: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(values)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return result


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


class QualitySignal(ContractModel):
    code: NonEmptyStr
    affected_paths: tuple[PublishedPath, ...] = Field(min_length=1)
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("affected_paths", "supporting_assertion_ids")
    @classmethod
    def validate_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(_unique(values, "quality signal values")))


class HardInvariantDecisionInput(ContractModel):
    decision_id: NonEmptyStr
    code: NonEmptyStr
    affected_paths: tuple[PublishedPath, ...] = Field(min_length=1)
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    release_id: NonEmptyStr

    @field_validator("affected_paths", "supporting_assertion_ids")
    @classmethod
    def validate_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(_unique(values, "hard invariant values")))


class TypedProjectionInput(ContractModel):
    projection_id: NonEmptyStr
    canonical_identity_id: NonEmptyStr
    domain: Domain
    release_id: NonEmptyStr
    canonical_identity_state: CanonicalIdentityState
    domain_identity_status: PaperIdentityStatus | None = None
    usable_field_paths: tuple[NonEmptyStr, ...]
    field_assertion_ids: dict[NonEmptyStr, tuple[NonEmptyStr, ...]]
    quality_signals: tuple[QualitySignal, ...] = ()
    diagnostic_metadata: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)

    @field_validator("usable_field_paths")
    @classmethod
    def validate_field_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(_unique(values, "usable projection field paths")))

    @model_validator(mode="after")
    def validate_projection(self) -> TypedProjectionInput:
        if self.canonical_identity_state is not CanonicalIdentityState.active:
            raise ValueError("a current path projection requires an active identity")
        if self.domain == "paper":
            if self.domain_identity_status not in {"confirmed", "unverified"}:
                raise ValueError(
                    "a current Paper projection requires confirmed or unverified status"
                )
        elif self.domain_identity_status is not None:
            raise ValueError("domain identity status belongs only to Paper projections")
        if set(self.field_assertion_ids) != set(self.usable_field_paths):
            raise ValueError(
                "usable projection fields must exactly match field assertion lineage"
            )
        assertion_ids = {
            assertion_id
            for field_ids in self.field_assertion_ids.values()
            for assertion_id in field_ids
        }
        if any(not field_ids for field_ids in self.field_assertion_ids.values()):
            raise ValueError("every usable field requires source assertion lineage")
        _unique(
            tuple(signal.code for signal in self.quality_signals),
            "projection quality signal codes",
        )
        if any(
            not set(signal.supporting_assertion_ids) <= assertion_ids
            for signal in self.quality_signals
        ):
            raise ValueError("quality signals require projection assertion lineage")
        return self


class IdentityRedirect(ContractModel):
    source_identity_id: NonEmptyStr
    survivor_identity_id: NonEmptyStr
    identity_decision_id: NonEmptyStr


class PathEligibilityGap(ContractModel):
    code: NonEmptyStr
    gap_kind: GapKind
    affected_paths: tuple[PublishedPath, ...] = Field(min_length=1)
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("affected_paths", "supporting_assertion_ids")
    @classmethod
    def validate_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(_unique(values, "path gap values")))


class PathEligibilityRequest(ContractModel):
    release_id: NonEmptyStr
    policy: PolicyReference
    projection: TypedProjectionInput | None = None
    related_projections: tuple[TypedProjectionInput, ...] = ()
    inclusion_decision: PolicyDecision
    relationship_decisions: tuple[RelationshipDecision, ...]
    hard_invariant_decisions: tuple[HardInvariantDecisionInput, ...] = ()
    identity_redirect_decision: IdentityDecision | None = None
    referenced_identity_id: NonEmptyStr | None = None
    requested_traversal_direction: NonEmptyStr | None = None
    published_paths: tuple[PublishedPath, ...]
    evaluated_at: CanonicalDatetime

    @model_validator(mode="after")
    def validate_request(self) -> PathEligibilityRequest:
        if self.policy.policy_kind is not PolicyKind.path_eligibility:
            raise ValueError("path eligibility requires a path-eligibility policy")
        if self.policy.effective_at > self.evaluated_at:
            raise ValueError("path policy cannot become effective after evaluation")
        if self.published_paths != PUBLISHED_USER_PATHS:
            raise ValueError("published paths must equal the complete ordered registry")
        if (
            self.inclusion_decision.policy.policy_kind is not PolicyKind.inclusion
            or self.inclusion_decision.path is not None
        ):
            raise ValueError(
                "path eligibility consumes one separate inclusion decision"
            )
        if self.inclusion_decision.release_id != self.release_id:
            raise ValueError("inclusion decision release does not match path request")
        if not self.inclusion_decision.supporting_assertion_ids:
            raise ValueError("inclusion decision requires evidence")
        if self.inclusion_decision.evaluated_at > self.evaluated_at:
            raise ValueError("inclusion decision cannot postdate path evaluation")
        projections = tuple(
            projection
            for projection in (self.projection, *self.related_projections)
            if projection is not None
        )
        _unique(
            tuple(projection.projection_id for projection in projections),
            "path projection IDs",
        )
        _unique(
            tuple(projection.canonical_identity_id for projection in projections),
            "path projection identity IDs",
        )
        if any(projection.release_id != self.release_id for projection in projections):
            raise ValueError("path projection release does not match request")
        for projection in projections:
            assertion_ids = _projection_assertions(projection)
            if any(
                not set(signal.supporting_assertion_ids) <= assertion_ids
                for signal in projection.quality_signals
            ):
                raise ValueError("quality signals require projection assertion lineage")
        quality_codes = tuple(
            signal.code
            for projection in projections
            for signal in projection.quality_signals
        )
        _unique(quality_codes, "path request quality signal codes")
        _unique(
            tuple(decision.decision_id for decision in self.relationship_decisions),
            "relationship decision IDs",
        )
        if any(
            decision.release_id != self.release_id
            for decision in self.relationship_decisions
        ):
            raise ValueError("relationship decision release does not match request")
        _unique(
            tuple(decision.decision_id for decision in self.hard_invariant_decisions),
            "hard invariant decision IDs",
        )
        if any(
            decision.release_id != self.release_id
            for decision in self.hard_invariant_decisions
        ):
            raise ValueError("hard invariant release does not match request")
        invariant_codes = tuple(
            decision.code for decision in self.hard_invariant_decisions
        )
        _unique(invariant_codes, "hard invariant codes")
        if set(quality_codes) & set(invariant_codes):
            raise ValueError("quality and hard invariant codes must be distinct")
        if self.requested_traversal_direction is None and (
            self.related_projections or self.relationship_decisions
        ):
            raise ValueError(
                "related projections and relationships require a requested traversal"
            )

        if self.identity_redirect_decision is not None:
            redirect = self.identity_redirect_decision
            if (
                redirect.action is not IdentityAction.merge
                or self.referenced_identity_id is None
                or self.referenced_identity_id
                not in redirect.input_canonical_identity_ids
                or len(redirect.output_canonical_identity_ids) != 1
                or self.projection is None
                or redirect.output_canonical_identity_ids[0]
                != self.projection.canonical_identity_id
            ):
                raise ValueError("identity redirect must bind one exact merge survivor")
        elif (
            self.referenced_identity_id is not None
            and self.projection is not None
            and self.referenced_identity_id != self.projection.canonical_identity_id
        ):
            raise ValueError("referenced identity does not own the current projection")

        resolved_identity_id = (
            self.projection.canonical_identity_id
            if self.projection is not None
            else self.referenced_identity_id
        )
        if resolved_identity_id is None:
            raise ValueError(
                "path request requires a projection or referenced identity"
            )
        if self.inclusion_decision.subject_identity_id != resolved_identity_id:
            raise ValueError(
                "inclusion decision does not belong to the resolved identity"
            )
        if self.requested_traversal_direction is not None:
            _validate_traversal(self)
        return self


class PathEligibilityResult(ContractModel):
    release_id: NonEmptyStr
    subject_identity_id: NonEmptyStr
    projection_id: NonEmptyStr | None
    resolved_projection_id: NonEmptyStr | None
    inclusion_decision_id: NonEmptyStr
    relationship_decision_ids: tuple[NonEmptyStr, ...]
    traversal_directions: tuple[NonEmptyStr, ...]
    decisions: tuple[PolicyDecision, ...]
    gaps: tuple[PathEligibilityGap, ...]
    redirect: IdentityRedirect | None = None
    result_identity_ids: tuple[NonEmptyStr, ...]
    evaluated_at: CanonicalDatetime
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_result(self) -> PathEligibilityResult:
        if tuple(decision.path for decision in self.decisions) != PUBLISHED_USER_PATHS:
            raise ValueError(
                "result must contain one ordered decision per published path"
            )
        if any(
            decision.release_id != self.release_id
            or decision.policy.policy_kind is not PolicyKind.path_eligibility
            or decision.subject_identity_id != self.subject_identity_id
            or decision.evaluated_at != self.evaluated_at
            or not decision.supporting_assertion_ids
            for decision in self.decisions
        ):
            raise ValueError(
                "path decision subject, release, policy, time, or evidence is invalid"
            )
        policy_identities = {
            (
                decision.policy.policy_id,
                decision.policy.policy_version,
                decision.policy.content_sha256,
                decision.policy.effective_at,
            )
            for decision in self.decisions
        }
        if len(policy_identities) != 1:
            raise ValueError("all path decisions require one exact versioned policy")
        if self.projection_id != self.resolved_projection_id:
            raise ValueError("path result projection identity is cross-wired")
        expected_identity_ids = (
            (self.subject_identity_id,) if self.projection_id is not None else ()
        )
        if self.result_identity_ids != expected_identity_ids:
            raise ValueError("path result identity set does not match its projection")
        if self.redirect is not None and (
            self.redirect.survivor_identity_id != self.subject_identity_id
            or self.redirect.source_identity_id == self.subject_identity_id
        ):
            raise ValueError("path redirect does not bind the resolved survivor")
        _unique(self.relationship_decision_ids, "result relationship decision IDs")
        _unique(self.traversal_directions, "result traversal directions")
        _unique(self.result_identity_ids, "result identity IDs")
        _unique(tuple(gap.code for gap in self.gaps), "result gap codes")
        payload = cast(
            JsonValue,
            self.model_dump(mode="json", exclude={"content_sha256"}),
        )
        if self.content_sha256 != _canonical_sha256(payload):
            raise ValueError("content_sha256 must bind the path eligibility result")
        return self


@lru_cache(maxsize=1)
def _catalog_rules() -> tuple[
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]],
]:
    if PACKAGED_CATALOG.content_sha256 != CATALOG_CONTENT_SHA256:
        raise PathEligibilityIntegrityError("installed catalog identity is invalid")
    payload = json.loads(
        files(__package__).joinpath(CATALOG_RESOURCE).read_text("utf-8")
    )
    relationships = {
        row["relationship_type_id"]: (
            row["version"],
            tuple(row["source_entity_types"]),
            tuple(row["target_entity_types"]),
        )
        for row in payload["relationships"]
    }
    directions = {
        row["traversal_direction"]: tuple(row["relationship_type_ids"])
        for row in payload["scenario_accounting"]
        if row["scenario_kind"] == "traversal_direction"
    }
    if set(directions) != _EXPECTED_TRAVERSAL_DIRECTIONS:
        raise PathEligibilityIntegrityError(
            "installed catalog traversal-direction registry is incomplete"
        )
    return directions, relationships


def _validate_traversal(request: PathEligibilityRequest) -> None:
    direction = cast(str, request.requested_traversal_direction)
    directions, relationships = _catalog_rules()
    allowed_types = directions.get(direction)
    if allowed_types is None:
        raise ValueError("requested traversal direction is not registered")
    if request.projection is None or not request.related_projections:
        raise ValueError("relationship traversal requires both endpoint projections")
    direction_parts = direction.split("_to_", maxsplit=1)
    if len(direction_parts) != 2 or direction_parts[0] != request.projection.domain:
        raise ValueError(
            "requested traversal direction does not start at the projection"
        )
    targets = tuple(
        projection
        for projection in request.related_projections
        if projection.domain == direction_parts[1]
    )
    if len(targets) != 1:
        raise ValueError("requested traversal direction requires one exact target")
    if len(request.relationship_decisions) != 1:
        raise ValueError("requested traversal requires one exact relationship decision")
    relationship = request.relationship_decisions[0]
    if relationship.relationship_type_id not in allowed_types:
        raise ValueError("relationship type is not registered for traversal direction")
    rule = relationships.get(relationship.relationship_type_id)
    if rule is None:
        raise ValueError("relationship type is absent from installed catalog")
    version, source_domains, target_domains = rule
    if relationship.relationship_type_version != version:
        raise ValueError("relationship type version is not installed")
    endpoint_projections = {
        projection.canonical_identity_id: projection
        for projection in (request.projection, targets[0])
    }
    source = endpoint_projections.get(relationship.source_canonical_identity_id)
    target = endpoint_projections.get(relationship.target_canonical_identity_id)
    if (
        source is None
        or target is None
        or source.domain not in source_domains
        or target.domain not in target_domains
    ):
        raise ValueError("relationship endpoints do not match catalog orientation")


def _projection_assertions(projection: TypedProjectionInput | None) -> set[str]:
    if projection is None:
        return set()
    return {
        assertion_id
        for assertion_ids in projection.field_assertion_ids.values()
        for assertion_id in assertion_ids
    }


def _path_decision(
    *,
    policy: PolicyReference,
    subject_identity_id: str,
    release_id: str,
    path: PublishedPath,
    outcome: PolicyOutcome,
    limitations: tuple[str, ...],
    hard_exclusion_codes: tuple[str, ...],
    supporting_assertion_ids: tuple[str, ...],
    evaluated_at: CanonicalDatetime,
) -> PolicyDecision:
    provisional = PolicyDecision(
        decision_id="path-eligibility:pending-content-identity",
        policy=policy,
        subject_identity_id=subject_identity_id,
        release_id=release_id,
        path=path,
        outcome=outcome,
        score=None,
        limitations=limitations,
        hard_exclusion_codes=hard_exclusion_codes,
        supporting_assertion_ids=supporting_assertion_ids,
        evaluated_at=evaluated_at,
    )
    content_sha256 = _canonical_sha256(
        cast(
            JsonValue,
            provisional.model_dump(mode="json", exclude={"decision_id"}),
        )
    )
    return PolicyDecision.model_validate(
        {
            **provisional.model_dump(mode="python"),
            "decision_id": f"path-eligibility:sha256:{content_sha256}",
        }
    )


class PathEligibilityEngine:
    """Evaluate all published paths independently for one resolved identity."""

    def evaluate(self, request: PathEligibilityRequest) -> PathEligibilityResult:
        if not isinstance(request, PathEligibilityRequest):
            raise PathEligibilityIntegrityError(
                "evaluate requires one typed PathEligibilityRequest"
            )
        try:
            validated = PathEligibilityRequest.model_validate(
                request.model_dump(mode="python")
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise PathEligibilityIntegrityError(
                "path eligibility request failed typed integrity validation"
            ) from exc
        projection = validated.projection
        resolved_identity_id = (
            projection.canonical_identity_id
            if projection is not None
            else cast(str, validated.referenced_identity_id)
        )
        all_projections = tuple(
            item
            for item in (projection, *validated.related_projections)
            if item is not None
        )
        signal_by_code = {
            signal.code: signal
            for item in all_projections
            for signal in item.quality_signals
        }
        if projection is not None and projection.domain_identity_status == "unverified":
            evidence = tuple(sorted(_projection_assertions(projection)))
            if evidence and "identity_unverified" not in signal_by_code:
                signal_by_code["identity_unverified"] = QualitySignal(
                    code="identity_unverified",
                    affected_paths=PUBLISHED_USER_PATHS,
                    supporting_assertion_ids=evidence,
                )
        hard_invariants = tuple(validated.hard_invariant_decisions)
        relationship = (
            validated.relationship_decisions[0]
            if validated.requested_traversal_direction is not None
            else None
        )
        decisions: list[PolicyDecision] = []
        gaps: dict[str, PathEligibilityGap] = {
            signal.code: PathEligibilityGap(
                code=signal.code,
                gap_kind="quality",
                affected_paths=signal.affected_paths,
                supporting_assertion_ids=signal.supporting_assertion_ids,
            )
            for signal in signal_by_code.values()
        }
        for code in validated.inclusion_decision.hard_exclusion_codes:
            gaps[code] = PathEligibilityGap(
                code=code,
                gap_kind="hard_invariant",
                affected_paths=PUBLISHED_USER_PATHS,
                supporting_assertion_ids=(
                    validated.inclusion_decision.supporting_assertion_ids
                ),
            )
        base_evidence = set(validated.inclusion_decision.supporting_assertion_ids)
        base_evidence.update(_projection_assertions(projection))

        for path in PUBLISHED_USER_PATHS:
            limitations = {
                signal.code
                for signal in signal_by_code.values()
                if path in signal.affected_paths
            }
            limitations.update(validated.inclusion_decision.limitations)
            hard_codes = {
                invariant.code
                for invariant in hard_invariants
                if path in invariant.affected_paths
            }
            evidence = set(base_evidence)
            for signal in signal_by_code.values():
                if path in signal.affected_paths:
                    evidence.update(signal.supporting_assertion_ids)
            for invariant in hard_invariants:
                if path in invariant.affected_paths:
                    evidence.update(invariant.supporting_assertion_ids)
                    gaps.setdefault(
                        invariant.code,
                        PathEligibilityGap(
                            code=invariant.code,
                            gap_kind="hard_invariant",
                            affected_paths=invariant.affected_paths,
                            supporting_assertion_ids=(
                                invariant.supporting_assertion_ids
                            ),
                        ),
                    )
            if validated.inclusion_decision.outcome is PolicyOutcome.excluded:
                hard_codes.update(validated.inclusion_decision.hard_exclusion_codes)
                evidence.update(validated.inclusion_decision.supporting_assertion_ids)
            if path == "verified_relationship_traversal" and relationship is not None:
                evidence.update(relationship.candidate_assertion_ids)
                target_domain = cast(
                    str, validated.requested_traversal_direction
                ).split("_to_", maxsplit=1)[1]
                target_projection = next(
                    item
                    for item in validated.related_projections
                    if item.domain == target_domain
                )
                evidence.update(_projection_assertions(target_projection))
                if relationship.state is not RelationshipDecisionState.accepted:
                    hard_codes.add("relationship_not_accepted")
                    gaps.setdefault(
                        "relationship_not_accepted",
                        PathEligibilityGap(
                            code="relationship_not_accepted",
                            gap_kind="relationship",
                            affected_paths=("verified_relationship_traversal",),
                            supporting_assertion_ids=(
                                relationship.candidate_assertion_ids
                            ),
                        ),
                    )
                else:
                    evidence.update(relationship.selected_assertion_ids)
            if hard_codes:
                outcome = PolicyOutcome.excluded
                limitations = set()
            elif validated.inclusion_decision.outcome is PolicyOutcome.review:
                outcome = PolicyOutcome.review
            elif validated.inclusion_decision.outcome is PolicyOutcome.limited:
                outcome = PolicyOutcome.limited
            else:
                outcome = PolicyOutcome.admitted
            decisions.append(
                _path_decision(
                    policy=validated.policy,
                    subject_identity_id=resolved_identity_id,
                    release_id=validated.release_id,
                    path=path,
                    outcome=outcome,
                    limitations=tuple(sorted(limitations)),
                    hard_exclusion_codes=tuple(sorted(hard_codes)),
                    supporting_assertion_ids=tuple(sorted(evidence)),
                    evaluated_at=validated.evaluated_at,
                )
            )

        redirect = None
        if validated.identity_redirect_decision is not None:
            redirect = IdentityRedirect(
                source_identity_id=cast(str, validated.referenced_identity_id),
                survivor_identity_id=resolved_identity_id,
                identity_decision_id=validated.identity_redirect_decision.decision_id,
            )
        provisional_values: dict[str, Any] = {
            "release_id": validated.release_id,
            "subject_identity_id": resolved_identity_id,
            "projection_id": projection.projection_id
            if projection is not None
            else None,
            "resolved_projection_id": (
                projection.projection_id if projection is not None else None
            ),
            "inclusion_decision_id": validated.inclusion_decision.decision_id,
            "relationship_decision_ids": tuple(
                decision.decision_id for decision in validated.relationship_decisions
            ),
            "traversal_directions": (
                (cast(str, validated.requested_traversal_direction),)
                if validated.requested_traversal_direction is not None
                else ()
            ),
            "decisions": tuple(decisions),
            "gaps": tuple(sorted(gaps.values(), key=lambda gap: gap.code)),
            "redirect": redirect,
            "result_identity_ids": (
                (resolved_identity_id,) if projection is not None else ()
            ),
            "evaluated_at": validated.evaluated_at,
        }
        content_sha256 = _canonical_sha256(
            cast(
                JsonValue,
                PathEligibilityResult.model_construct(
                    **provisional_values,
                    content_sha256="0" * 64,
                ).model_dump(mode="json", exclude={"content_sha256"}),
            )
        )
        return PathEligibilityResult.model_validate(
            {**provisional_values, "content_sha256": content_sha256}
        )


__all__ = [
    "HardInvariantDecisionInput",
    "IdentityRedirect",
    "PUBLISHED_USER_PATHS",
    "PathEligibilityEngine",
    "PathEligibilityGap",
    "PathEligibilityIntegrityError",
    "PathEligibilityRequest",
    "PathEligibilityResult",
    "PolicyDecision",
    "PolicyReference",
    "QualitySignal",
    "TypedProjectionInput",
]
