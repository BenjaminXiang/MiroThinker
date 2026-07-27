"""Offline, evidence-bound canonical identity resolution for Canonical V2 builds."""

from __future__ import annotations

from abc import ABC, abstractmethod
import base64
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol, cast
import unicodedata

from pydantic import (
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from src.data_agents.canonical_v2.contracts import (
    CanonicalDatetime,
    CanonicalIdentity,
    CanonicalIdentityState,
    Confidence,
    ContractModel,
    DecisionMethod,
    HumanReviewOutcome,
    HumanReviewResolution,
    IdentityAction,
    IdentityDecision,
    LLMDecisionTrace,
    NonEmptyStr,
    PolicyKind,
    PolicyReference,
    ReviewCase,
    ReviewFamily,
    Sha256,
    SourceAssertion,
    SourceIdentity,
    SourceIdentityState,
    create_review_case,
    create_human_review_resolution,
)


class CanonicalIdentityResolutionError(RuntimeError):
    """Base error for invalid or unsafe identity resolution."""


class IdentityResolutionIntegrityError(CanonicalIdentityResolutionError):
    """Raised when typed identity state is incomplete or content changes."""


class IdentityAdjudicationIntegrityError(CanonicalIdentityResolutionError):
    """Raised when recorded adjudication is not bound to exact evidence."""


class IdentityAdjudicationOutputError(CanonicalIdentityResolutionError):
    """Raised when structured adjudication output violates its schema."""


class IdentityCandidateOutcome(str, Enum):
    same_entity = "same_entity"
    different_entities = "different_entities"
    unresolved = "unresolved"


def _require_unique(values: Iterable[str], label: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must not contain duplicates")
    return normalized


def _supporting_record_ids(
    sources: Iterable[SourceIdentity],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                record_id
                for source in sources
                for record_id in source.source_record_ids
            }
        )
    )


def _canonical_json(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _content_sha256(value: JsonValue) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, JsonValue]],
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _models_json(values: Iterable[ContractModel], id_field: str) -> list[JsonValue]:
    return [
        cast(JsonValue, value.model_dump(mode="json"))
        for value in sorted(values, key=lambda item: str(getattr(item, id_field)))
    ]


class SourceIdentityAssignment(ContractModel):
    release_id: NonEmptyStr
    source_identity_id: NonEmptyStr
    canonical_identity_id: NonEmptyStr
    identity_decision_id: NonEmptyStr


class IdentityResolutionRequest(ContractModel):
    release_id: NonEmptyStr
    decision_run_id: NonEmptyStr
    identity_method_version: NonEmptyStr
    as_of: CanonicalDatetime
    policy: PolicyReference
    source_identities: tuple[SourceIdentity, ...]
    identity_assertions: tuple[SourceAssertion, ...]
    current_canonical_identities: tuple[CanonicalIdentity, ...] = ()
    current_source_identity_assignments: tuple[SourceIdentityAssignment, ...] = ()
    canonical_identity_history: tuple[CanonicalIdentity, ...] = ()
    prior_identity_decisions: tuple[IdentityDecision, ...] = ()
    prior_decision_contexts: tuple[IdentityDecisionContext, ...] = ()
    human_review_resolutions: tuple[HumanReviewResolution, ...] = ()

    @field_validator("source_identities")
    @classmethod
    def normalize_source_identities(
        cls, values: tuple[SourceIdentity, ...]
    ) -> tuple[SourceIdentity, ...]:
        normalized = tuple(
            SourceIdentity(
                **{
                    **value.model_dump(mode="python"),
                    "source_record_ids": tuple(sorted(value.source_record_ids)),
                }
            )
            for value in values
        )
        _require_unique(
            (value.source_identity_id for value in normalized),
            "source identity IDs",
        )
        return tuple(sorted(normalized, key=lambda value: value.source_identity_id))

    @field_validator("identity_assertions")
    @classmethod
    def normalize_identity_assertions(
        cls, values: tuple[SourceAssertion, ...]
    ) -> tuple[SourceAssertion, ...]:
        _require_unique(
            (value.assertion_id for value in values), "identity assertion IDs"
        )
        return tuple(sorted(values, key=lambda value: value.assertion_id))

    @field_validator("current_canonical_identities", "canonical_identity_history")
    @classmethod
    def normalize_canonical_identities(
        cls, values: tuple[CanonicalIdentity, ...]
    ) -> tuple[CanonicalIdentity, ...]:
        normalized = tuple(
            CanonicalIdentity(
                **{
                    **value.model_dump(mode="python"),
                    "source_identity_ids": tuple(sorted(value.source_identity_ids)),
                    "predecessor_identity_ids": tuple(
                        sorted(value.predecessor_identity_ids)
                    ),
                    "successor_identity_ids": tuple(
                        sorted(value.successor_identity_ids)
                    ),
                }
            )
            for value in values
        )
        _require_unique(
            (value.canonical_identity_id for value in normalized),
            "canonical identity IDs",
        )
        return tuple(sorted(normalized, key=lambda value: value.canonical_identity_id))

    @field_validator("prior_identity_decisions")
    @classmethod
    def normalize_prior_decisions(
        cls, values: tuple[IdentityDecision, ...]
    ) -> tuple[IdentityDecision, ...]:
        _require_unique(
            (value.decision_id for value in values), "prior identity decision IDs"
        )
        return tuple(sorted(values, key=lambda value: value.decision_id))

    @field_validator("prior_decision_contexts")
    @classmethod
    def normalize_prior_contexts(
        cls, values: tuple[IdentityDecisionContext, ...]
    ) -> tuple[IdentityDecisionContext, ...]:
        _require_unique(
            (value.decision_id for value in values),
            "prior identity decision context IDs",
        )
        return tuple(sorted(values, key=lambda value: value.decision_id))

    @field_validator("current_source_identity_assignments")
    @classmethod
    def normalize_current_assignments(
        cls, values: tuple[SourceIdentityAssignment, ...]
    ) -> tuple[SourceIdentityAssignment, ...]:
        _require_unique(
            (value.source_identity_id for value in values),
            "current source assignment IDs",
        )
        return tuple(sorted(values, key=lambda value: value.source_identity_id))

    @field_validator("human_review_resolutions")
    @classmethod
    def normalize_human_review_resolutions(
        cls, values: tuple[HumanReviewResolution, ...]
    ) -> tuple[HumanReviewResolution, ...]:
        _require_unique(
            (value.resolution_id for value in values),
            "identity human review resolution IDs",
        )
        _require_unique(
            (value.review_case.review_case_id for value in values),
            "identity human review case IDs",
        )
        return tuple(sorted(values, key=lambda value: value.resolution_id))

    @model_validator(mode="after")
    def validate_request(self) -> IdentityResolutionRequest:
        if self.policy.policy_kind is not PolicyKind.identity:
            raise ValueError("identity resolution requires an identity policy")
        if (
            any(source.entity_type == "person" for source in self.source_identities)
            and self.identity_method_version != PERSON_IDENTITY_METHOD_VERSION
        ):
            raise ValueError(
                "Person identity resolution requires its versioned Person rule set"
            )
        if (
            any(
                source.entity_type in {"technology_concept", "technology_route"}
                for source in self.source_identities
            )
            and self.identity_method_version != TECHNOLOGY_IDENTITY_METHOD_VERSION
        ):
            raise ValueError(
                "Technology identity resolution requires its versioned Technology "
                "rule set"
            )
        if self.identity_method_version == PERSON_IDENTITY_METHOD_VERSION and any(
            source.entity_type != "person" for source in self.source_identities
        ):
            raise ValueError("the Person identity method only accepts Person sources")
        if self.identity_method_version == TECHNOLOGY_IDENTITY_METHOD_VERSION and any(
            source.entity_type not in {"technology_concept", "technology_route"}
            for source in self.source_identities
        ):
            raise ValueError(
                "the Technology identity method only accepts Technology sources"
            )
        source_by_id = {
            value.source_identity_id: value for value in self.source_identities
        }
        if any(
            source.state is not SourceIdentityState.active
            for source in source_by_id.values()
        ):
            raise ValueError("identity-resolution source identities must be active")
        assertion_ids_by_source: dict[str, set[str]] = {
            source_id: set() for source_id in source_by_id
        }
        for assertion in self.identity_assertions:
            source = source_by_id.get(assertion.source_identity_id)
            if source is None:
                raise ValueError(
                    "identity assertion references an unknown source identity"
                )
            if assertion.source_record_id not in source.source_record_ids:
                raise ValueError(
                    "identity assertion record must belong to its source identity"
                )
            if assertion.subject_entity_type != source.entity_type:
                raise ValueError(
                    "identity assertion entity type must match its source identity"
                )
            assertion_ids_by_source[source.source_identity_id].add(
                assertion.assertion_id
            )
        if any(not values for values in assertion_ids_by_source.values()):
            raise ValueError("every source identity requires identity evidence")

        current_ids = {
            value.canonical_identity_id for value in self.current_canonical_identities
        }
        history_ids = {
            value.canonical_identity_id for value in self.canonical_identity_history
        }
        if current_ids & history_ids:
            raise ValueError("current and terminal identity IDs must be disjoint")
        current_owner: dict[str, str] = {}
        for identity in self.current_canonical_identities:
            if identity.release_id != self.release_id:
                raise ValueError("current identity release must match the request")
            if identity.state is not CanonicalIdentityState.active:
                raise ValueError("current canonical identities must be active")
            for source_id in identity.source_identity_ids:
                if source_id not in source_by_id:
                    raise ValueError("current identity references an unknown source")
                if identity.entity_type != source_by_id[source_id].entity_type:
                    raise ValueError(
                        "canonical identity entity type must match every source"
                    )
                prior_owner = current_owner.setdefault(
                    source_id, identity.canonical_identity_id
                )
                if prior_owner != identity.canonical_identity_id:
                    raise ValueError(
                        "one source identity cannot have two current owners"
                    )
        prior_decision_by_id = {
            decision.decision_id: decision for decision in self.prior_identity_decisions
        }
        prior_decision_ids = set(prior_decision_by_id)
        prior_context_by_id = {
            context.decision_id: context for context in self.prior_decision_contexts
        }
        if set(prior_context_by_id) != prior_decision_ids or any(
            context.release_id != self.release_id
            or context.decision != prior_decision_by_id[decision_id]
            for decision_id, context in prior_context_by_id.items()
        ):
            raise ValueError(
                "every prior identity decision requires its exact decision-time context"
            )
        assignments = {
            value.source_identity_id: value
            for value in self.current_source_identity_assignments
        }
        if set(assignments) != set(current_owner):
            raise ValueError(
                "current source assignments must exactly equal current membership"
            )
        for source_id, assignment in assignments.items():
            if assignment.release_id != self.release_id:
                raise ValueError("current source assignment release mismatch")
            if assignment.canonical_identity_id != current_owner[source_id]:
                raise ValueError(
                    "current source assignment must target its exact current owner"
                )
            if assignment.identity_decision_id not in prior_decision_ids:
                raise ValueError(
                    "current source assignment must reference a supplied prior decision"
                )
            provenance_decision = prior_decision_by_id[assignment.identity_decision_id]
            if (
                source_id not in provenance_decision.source_identity_ids
                or assignment.canonical_identity_id
                not in provenance_decision.output_canonical_identity_ids
            ):
                raise ValueError(
                    "current assignment decision provenance must bind its source "
                    "and canonical owner"
                )
        for identity in self.canonical_identity_history:
            if identity.release_id != self.release_id:
                raise ValueError("history identity release must match the request")
            if identity.state is CanonicalIdentityState.active:
                raise ValueError("canonical identity history must be terminal")
            for source_id in identity.source_identity_ids:
                if source_id not in source_by_id:
                    raise ValueError("history identity references an unknown source")
                if identity.entity_type != source_by_id[source_id].entity_type:
                    raise ValueError(
                        "canonical identity entity type must match every source"
                    )

        for identity in (
            *self.current_canonical_identities,
            *self.canonical_identity_history,
        ):
            if identity.identity_decision_id not in prior_decision_ids:
                raise ValueError(
                    "existing identity must reference a supplied prior decision"
                )
        known_canonical_ids = current_ids | history_ids
        for identity in (
            *self.current_canonical_identities,
            *self.canonical_identity_history,
        ):
            lineage_ids = set(identity.predecessor_identity_ids) | set(
                identity.successor_identity_ids
            )
            if not lineage_ids <= known_canonical_ids:
                raise ValueError(
                    "canonical identity references an unknown canonical lineage endpoint"
                )
        reviewed_source_ids: set[str] = set()
        assertion_ids_by_source = {
            source_id: {
                assertion.assertion_id
                for assertion in self.identity_assertions
                if assertion.source_identity_id == source_id
            }
            for source_id in source_by_id
        }
        for resolution in self.human_review_resolutions:
            case = resolution.review_case
            case_source_ids = set(case.source_identity_ids)
            expected_assertion_ids = {
                assertion_id
                for source_id in case_source_ids
                for assertion_id in assertion_ids_by_source.get(source_id, set())
            }
            if (
                case.family is not ReviewFamily.identity
                or case.policy != self.policy
                or case.release_id == self.release_id
                or resolution.reviewed_at > self.as_of
                or not case_source_ids <= set(source_by_id)
                or reviewed_source_ids & case_source_ids
                or set(case.candidate_evidence_ids) != expected_assertion_ids
            ):
                raise ValueError(
                    "identity human review must bind one prior exact component"
                )
            reviewed_source_ids.update(case_source_ids)
        return self


class IdentityCandidateVerdict(ContractModel):
    verdict_id: NonEmptyStr
    component_id: NonEmptyStr
    component_input_sha256: Sha256
    verdict: IdentityCandidateOutcome
    proposed_outcome: IdentityCandidateOutcome | None = None
    source_identity_ids: tuple[NonEmptyStr, ...] = Field(min_length=2)
    source_identity_groups: tuple[tuple[NonEmptyStr, ...], ...] = Field(min_length=1)
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    reason_codes: tuple[NonEmptyStr, ...] = Field(min_length=1)
    method: DecisionMethod
    confidence: Confidence
    rationale: NonEmptyStr
    uncertainty: NonEmptyStr
    llm_trace: LLMDecisionTrace | None = None
    human_review_resolution: HumanReviewResolution | None = None

    @field_validator("source_identity_ids", "supporting_assertion_ids", "reason_codes")
    @classmethod
    def normalize_tuple(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(values, "candidate verdict values")
        return tuple(sorted(values))

    @field_validator("source_identity_groups")
    @classmethod
    def normalize_source_identity_groups(
        cls, groups: tuple[tuple[str, ...], ...]
    ) -> tuple[tuple[str, ...], ...]:
        normalized = tuple(tuple(sorted(group)) for group in groups)
        if any(not group for group in normalized):
            raise ValueError("candidate verdict source groups cannot be empty")
        _require_unique(
            (source_id for group in normalized for source_id in group),
            "candidate verdict grouped source IDs",
        )
        return tuple(sorted(normalized))

    @model_validator(mode="after")
    def validate_trace(self) -> IdentityCandidateVerdict:
        grouped_source_ids = tuple(
            source_id for group in self.source_identity_groups for source_id in group
        )
        if set(grouped_source_ids) != set(self.source_identity_ids):
            raise ValueError(
                "candidate verdict groups must partition the exact component sources"
            )
        semantic_outcome = self.proposed_outcome or self.verdict
        if (
            semantic_outcome is IdentityCandidateOutcome.same_entity
            and len(self.source_identity_groups) != 1
        ):
            raise ValueError("same_entity candidate verdict requires one source group")
        if (
            semantic_outcome is IdentityCandidateOutcome.different_entities
            and len(self.source_identity_groups) < 2
        ):
            raise ValueError(
                "different_entities candidate verdict requires multiple source groups"
            )
        if self.method is DecisionMethod.structured_llm:
            if self.llm_trace is None:
                raise ValueError("structured LLM verdict requires an LLM trace")
            if self.proposed_outcome is None:
                raise ValueError("structured LLM verdict requires its proposed outcome")
            if set(self.llm_trace.input_evidence_ids) != set(
                self.supporting_assertion_ids
            ):
                raise ValueError(
                    "LLM verdict evidence must match supporting assertions"
                )
            if (
                self.llm_trace.validated_output.get("verdict")
                != self.proposed_outcome.value
                or tuple(
                    sorted(
                        tuple(sorted(cast(list[str], group)))
                        for group in cast(
                            list[list[str]],
                            self.llm_trace.validated_output.get(
                                "source_identity_groups", []
                            ),
                        )
                    )
                )
                != self.source_identity_groups
            ):
                raise ValueError(
                    "LLM verdict proposal and source groups must match its trace"
                )
        elif self.llm_trace is not None or self.proposed_outcome is not None:
            raise ValueError(
                "non-LLM verdict cannot carry an LLM trace or proposed outcome"
            )
        if self.method is DecisionMethod.human_review:
            resolution = self.human_review_resolution
            if resolution is None:
                raise ValueError("human review verdict requires its bound resolution")
            expected_outcome = {
                HumanReviewOutcome.same_entity: IdentityCandidateOutcome.same_entity,
                HumanReviewOutcome.different_entities: (
                    IdentityCandidateOutcome.different_entities
                ),
            }.get(resolution.outcome)
            if (
                resolution.review_case.family is not ReviewFamily.identity
                or expected_outcome is not self.verdict
                or resolution.source_identity_groups != self.source_identity_groups
                or resolution.review_case.source_identity_ids
                != self.source_identity_ids
                or resolution.review_case.candidate_evidence_ids
                != self.supporting_assertion_ids
            ):
                raise ValueError(
                    "human review identity verdict must exactly apply its resolution"
                )
        elif self.human_review_resolution is not None:
            raise ValueError(
                "non-human identity verdict cannot carry a review resolution"
            )
        return self


class IdentityDecisionManifest(ContractModel):
    release_id: NonEmptyStr
    decision_id: NonEmptyStr
    candidate_verdict_id: NonEmptyStr | None = None
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    input_content_sha256: Sha256

    @field_validator("supporting_assertion_ids")
    @classmethod
    def normalize_assertion_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(values, "manifest supporting assertion IDs")
        return tuple(sorted(values))


class IdentityDecisionOutputAllocation(ContractModel):
    canonical_identity_id: NonEmptyStr
    source_identity_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("source_identity_ids")
    @classmethod
    def normalize_source_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(values, "identity decision allocation source IDs")
        return tuple(sorted(values))


class _IdentityDecisionContextContent(ContractModel):
    release_id: NonEmptyStr
    decision_id: NonEmptyStr
    decision: IdentityDecision
    candidate_verdict: IdentityCandidateVerdict | None = None
    source_identities: tuple[SourceIdentity, ...] = Field(min_length=1)
    identity_assertions: tuple[SourceAssertion, ...] = Field(min_length=1)
    input_canonical_identities: tuple[CanonicalIdentity, ...] = ()
    output_canonical_identities: tuple[CanonicalIdentity, ...] = ()
    input_source_assignments: tuple[SourceIdentityAssignment, ...] = ()
    referenced_prior_decision_ids: tuple[NonEmptyStr, ...] = ()
    output_allocations: tuple[IdentityDecisionOutputAllocation, ...] = ()
    rule_set_content_sha256: Sha256
    decision_content_sha256: Sha256

    @field_validator("source_identities")
    @classmethod
    def normalize_context_sources(
        cls, values: tuple[SourceIdentity, ...]
    ) -> tuple[SourceIdentity, ...]:
        _require_unique(
            (value.source_identity_id for value in values),
            "identity context source IDs",
        )
        return tuple(sorted(values, key=lambda value: value.source_identity_id))

    @field_validator("identity_assertions")
    @classmethod
    def normalize_context_assertions(
        cls, values: tuple[SourceAssertion, ...]
    ) -> tuple[SourceAssertion, ...]:
        _require_unique(
            (value.assertion_id for value in values),
            "identity context assertion IDs",
        )
        return tuple(sorted(values, key=lambda value: value.assertion_id))

    @field_validator("input_canonical_identities", "output_canonical_identities")
    @classmethod
    def normalize_context_identities(
        cls, values: tuple[CanonicalIdentity, ...]
    ) -> tuple[CanonicalIdentity, ...]:
        _require_unique(
            (value.canonical_identity_id for value in values),
            "identity context canonical IDs",
        )
        return tuple(sorted(values, key=lambda value: value.canonical_identity_id))

    @field_validator("input_source_assignments")
    @classmethod
    def normalize_context_assignments(
        cls, values: tuple[SourceIdentityAssignment, ...]
    ) -> tuple[SourceIdentityAssignment, ...]:
        _require_unique(
            (value.source_identity_id for value in values),
            "identity context input assignment source IDs",
        )
        return tuple(sorted(values, key=lambda value: value.source_identity_id))

    @field_validator("referenced_prior_decision_ids")
    @classmethod
    def normalize_prior_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(values, "identity context prior decision IDs")
        return tuple(sorted(values))

    @field_validator("output_allocations")
    @classmethod
    def normalize_allocations(
        cls, values: tuple[IdentityDecisionOutputAllocation, ...]
    ) -> tuple[IdentityDecisionOutputAllocation, ...]:
        _require_unique(
            (value.canonical_identity_id for value in values),
            "identity context allocation output IDs",
        )
        return tuple(sorted(values, key=lambda value: value.canonical_identity_id))

    @model_validator(mode="after")
    def validate_context_content(self) -> _IdentityDecisionContextContent:
        if self.decision_id != self.decision.decision_id:
            raise ValueError("identity context decision ID mismatch")
        if self.decision_content_sha256 != _content_sha256(
            cast(JsonValue, self.decision.model_dump(mode="json"))
        ):
            raise ValueError("identity context decision content hash mismatch")
        source_by_id = {
            source.source_identity_id: source for source in self.source_identities
        }
        if set(source_by_id) != set(self.decision.source_identity_ids):
            raise ValueError("identity context must retain the exact decision sources")
        assertion_by_id = {
            assertion.assertion_id: assertion for assertion in self.identity_assertions
        }
        if any(
            assertion.source_identity_id not in source_by_id
            or assertion.source_record_id not in self.decision.supporting_record_ids
            for assertion in assertion_by_id.values()
        ):
            raise ValueError("identity context assertion evidence is cross-wired")
        input_by_id = {
            identity.canonical_identity_id: identity
            for identity in self.input_canonical_identities
        }
        output_by_id = {
            identity.canonical_identity_id: identity
            for identity in self.output_canonical_identities
        }
        if set(input_by_id) != set(self.decision.input_canonical_identity_ids):
            raise ValueError("identity context input topology mismatch")
        if set(output_by_id) != set(self.decision.output_canonical_identity_ids):
            raise ValueError("identity context output topology mismatch")
        if any(
            assignment.release_id != self.release_id
            or assignment.source_identity_id not in source_by_id
            or assignment.canonical_identity_id not in input_by_id
            for assignment in self.input_source_assignments
        ):
            raise ValueError("identity context input assignment is cross-wired")
        allocation_by_output = {
            allocation.canonical_identity_id: set(allocation.source_identity_ids)
            for allocation in self.output_allocations
        }
        if set(allocation_by_output) != set(output_by_id):
            raise ValueError("identity context output allocation is incomplete")
        allocated_sources = [
            source_id
            for allocation in self.output_allocations
            for source_id in allocation.source_identity_ids
        ]
        if self.decision.action is IdentityAction.reject:
            invalid_allocation = bool(allocated_sources or allocation_by_output)
        else:
            invalid_allocation = (
                len(allocated_sources) != len(set(allocated_sources))
                or set(allocated_sources) != set(source_by_id)
                or any(
                    allocation_by_output[canonical_id]
                    != set(output_by_id[canonical_id].source_identity_ids)
                    for canonical_id in output_by_id
                )
            )
        if invalid_allocation:
            raise ValueError(
                "identity context output allocation must partition exact sources"
            )
        if self.candidate_verdict is not None and not set(
            self.decision.source_identity_ids
        ) <= set(self.candidate_verdict.source_identity_ids):
            raise ValueError("identity context candidate verdict is cross-wired")
        return self


class IdentityDecisionContext(_IdentityDecisionContextContent):
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_context_hash(self) -> IdentityDecisionContext:
        if identity_decision_context_sha256(self) != self.content_sha256:
            raise ValueError("identity decision context content hash mismatch")
        return self


IdentityResolutionRequest.model_rebuild()


class RecordedIdentityAdjudication(ContractModel):
    input_source_identity_ids: tuple[NonEmptyStr, ...] = Field(min_length=2)
    input_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    input_content_sha256: Sha256
    raw_output: bytes = Field(min_length=2)
    expected_output_sha256: Sha256

    @field_validator("input_source_identity_ids", "input_assertion_ids")
    @classmethod
    def normalize_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(values, "recorded identity adjudication IDs")
        return tuple(sorted(values))


class _StructuredIdentityAdjudicationOutput(ContractModel):
    verdict: IdentityCandidateOutcome
    source_identity_groups: tuple[tuple[NonEmptyStr, ...], ...] = Field(min_length=1)
    confidence: Confidence
    rationale: NonEmptyStr
    uncertainty: NonEmptyStr

    @field_validator("source_identity_groups")
    @classmethod
    def normalize_groups(
        cls, groups: tuple[tuple[str, ...], ...]
    ) -> tuple[tuple[str, ...], ...]:
        normalized: list[tuple[str, ...]] = []
        for group in groups:
            if not group:
                raise ValueError("identity adjudication groups cannot be empty")
            _require_unique(group, "identity adjudication group source IDs")
            normalized.append(tuple(sorted(group)))
        _require_unique(
            (source_id for group in normalized for source_id in group),
            "identity adjudication source IDs",
        )
        return tuple(sorted(normalized))


class _IdentityAdjudicationRequest(ContractModel):
    source_identity_ids: tuple[NonEmptyStr, ...] = Field(min_length=2)
    assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    input_content_sha256: Sha256


class _ValidatedIdentityAdjudication(ContractModel):
    output: _StructuredIdentityAdjudicationOutput
    llm_trace: LLMDecisionTrace


def _parse_identity_adjudication_output(
    raw_output: bytes,
    *,
    source_identity_ids: tuple[str, ...],
) -> tuple[_StructuredIdentityAdjudicationOutput, dict[str, JsonValue]]:
    try:
        parsed = json.loads(
            raw_output.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_non_finite_json,
        )
        if not isinstance(parsed, dict):
            raise ValueError("identity adjudication output must be a JSON object")
        output = _StructuredIdentityAdjudicationOutput.model_validate(parsed)
    except (UnicodeError, ValueError, ValidationError) as exc:
        raise IdentityAdjudicationOutputError(
            "identity adjudication output is not valid structured JSON"
        ) from exc
    flattened = tuple(
        source_id for group in output.source_identity_groups for source_id in group
    )
    if set(flattened) != set(source_identity_ids) or len(flattened) != len(
        source_identity_ids
    ):
        raise IdentityAdjudicationOutputError(
            "identity adjudication groups must partition the exact candidate sources"
        )
    if (
        output.verdict is IdentityCandidateOutcome.same_entity
        and len(output.source_identity_groups) != 1
    ):
        raise IdentityAdjudicationOutputError(
            "same_entity adjudication requires one source group"
        )
    if (
        output.verdict is IdentityCandidateOutcome.different_entities
        and len(output.source_identity_groups) < 2
    ):
        raise IdentityAdjudicationOutputError(
            "different_entities adjudication requires at least two source groups"
        )
    return output, cast(dict[str, JsonValue], parsed)


class _IdentityResolutionContent(ContractModel):
    release_id: NonEmptyStr
    decision_run_id: NonEmptyStr
    identity_method_version: NonEmptyStr
    as_of: CanonicalDatetime
    policy: PolicyReference
    source_identities: tuple[SourceIdentity, ...]
    identity_assertions: tuple[SourceAssertion, ...]
    candidate_verdicts: tuple[IdentityCandidateVerdict, ...]
    identity_decisions: tuple[IdentityDecision, ...]
    current_canonical_identities: tuple[CanonicalIdentity, ...]
    canonical_identity_history: tuple[CanonicalIdentity, ...]
    source_identity_assignments: tuple[SourceIdentityAssignment, ...]
    decision_manifests: tuple[IdentityDecisionManifest, ...]
    decision_contexts: tuple[IdentityDecisionContext, ...] = ()
    review_cases: tuple[ReviewCase, ...] = ()

    @field_validator("review_cases")
    @classmethod
    def normalize_review_cases(
        cls, cases: tuple[ReviewCase, ...]
    ) -> tuple[ReviewCase, ...]:
        _require_unique(
            (case.review_case_id for case in cases), "identity review case IDs"
        )
        return tuple(sorted(cases, key=lambda case: case.review_case_id))


def _identity_review_cases(
    *,
    release_id: str,
    decision_run_id: str,
    identity_method_version: str,
    as_of: CanonicalDatetime,
    policy: PolicyReference,
    verdicts: Iterable[IdentityCandidateVerdict],
) -> tuple[ReviewCase, ...]:
    cases = tuple(
        create_review_case(
            family=ReviewFamily.identity,
            release_id=release_id,
            decision_run_id=decision_run_id,
            subject_id=verdict.component_id,
            path="canonical_identity",
            originating_record_id=verdict.verdict_id,
            candidate_evidence_ids=verdict.supporting_assertion_ids,
            conflicting_evidence_ids=verdict.supporting_assertion_ids,
            source_identity_ids=verdict.source_identity_ids,
            policy=policy,
            method=verdict.method,
            method_version=identity_method_version,
            confidence=verdict.confidence,
            rationale=verdict.rationale,
            uncertainty=verdict.uncertainty,
            reason_codes=verdict.reason_codes,
            trace_content_sha256=(
                verdict.llm_trace.output_sha256
                if verdict.llm_trace is not None
                else None
            ),
            input_content_sha256=verdict.component_input_sha256,
            created_at=as_of,
        )
        for verdict in verdicts
        if verdict.verdict is IdentityCandidateOutcome.unresolved
    )
    return tuple(sorted(cases, key=lambda case: case.review_case_id))


class IdentityResolutionResult(_IdentityResolutionContent):
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_result(self) -> IdentityResolutionResult:
        if canonical_identity_resolution_result_sha256(self) != self.content_sha256:
            raise ValueError("identity resolution content hash mismatch")

        expected_review_cases = _identity_review_cases(
            release_id=self.release_id,
            decision_run_id=self.decision_run_id,
            identity_method_version=self.identity_method_version,
            as_of=self.as_of,
            policy=self.policy,
            verdicts=self.candidate_verdicts,
        )
        if self.review_cases != expected_review_cases:
            raise ValueError(
                "identity review cases must exactly cover unresolved candidate verdicts"
            )

        source_ids = [value.source_identity_id for value in self.source_identities]
        _require_unique(source_ids, "result source identity IDs")
        assertion_ids = [value.assertion_id for value in self.identity_assertions]
        _require_unique(assertion_ids, "result identity assertion IDs")
        decision_ids = [value.decision_id for value in self.identity_decisions]
        _require_unique(decision_ids, "result identity decision IDs")
        manifest_ids = [value.decision_id for value in self.decision_manifests]
        context_ids = [value.decision_id for value in self.decision_contexts]
        _require_unique(manifest_ids, "result manifest decision IDs")
        if set(decision_ids) != set(manifest_ids):
            raise ValueError("every identity decision requires exactly one manifest")
        _require_unique(context_ids, "result decision context IDs")
        if set(decision_ids) != set(context_ids):
            raise ValueError("every identity decision requires exactly one context")

        current_by_id = {
            value.canonical_identity_id: value
            for value in self.current_canonical_identities
        }
        if len(current_by_id) != len(self.current_canonical_identities):
            raise ValueError("current canonical identity IDs must be unique")
        history_ids = [
            value.canonical_identity_id for value in self.canonical_identity_history
        ]
        _require_unique(history_ids, "history canonical identity IDs")
        if set(current_by_id) & set(history_ids):
            raise ValueError("current and history canonical IDs must be disjoint")
        if any(
            identity.state is not CanonicalIdentityState.active
            for identity in current_by_id.values()
        ):
            raise ValueError("current canonical identities must be active")
        if any(
            identity.state is CanonicalIdentityState.active
            for identity in self.canonical_identity_history
        ):
            raise ValueError("canonical identity history must be terminal")

        membership: dict[str, str] = {}
        for identity in current_by_id.values():
            for source_id in identity.source_identity_ids:
                if source_id in membership:
                    raise ValueError(
                        "one source identity cannot have two current owners"
                    )
                membership[source_id] = identity.canonical_identity_id
        assignments: dict[str, SourceIdentityAssignment] = {}
        for assignment in self.source_identity_assignments:
            if assignment.release_id != self.release_id:
                raise ValueError("source assignment release mismatch")
            if assignment.source_identity_id in assignments:
                raise ValueError("source assignment IDs must be unique")
            assignments[assignment.source_identity_id] = assignment
        assignment_source_ids = set(assignments)
        source_id_set = set(source_ids)
        if assignment_source_ids != source_id_set:
            if not assignment_source_ids <= source_id_set:
                raise ValueError(
                    "every source identity requires one current assignment"
                )
            allowed_unassigned_source_ids = {
                source_id
                for decision in self.identity_decisions
                if decision.action is IdentityAction.reject
                for source_id in decision.source_identity_ids
            }
            if self.identity_method_version in {
                PERSON_IDENTITY_METHOD_VERSION,
                TECHNOLOGY_IDENTITY_METHOD_VERSION,
            }:
                verdict_source_ids = {
                    source_id
                    for verdict in self.candidate_verdicts
                    for source_id in verdict.source_identity_ids
                }
                allowed_unassigned_source_ids.update(
                    source_id
                    for verdict in self.candidate_verdicts
                    if verdict.verdict is IdentityCandidateOutcome.unresolved
                    for source_id in verdict.source_identity_ids
                )
                allowed_unassigned_source_ids.update(
                    source.source_identity_id
                    for source in self.source_identities
                    if source.source_identity_id not in verdict_source_ids
                    and not _has_evidence_bound_internal_identifier(
                        source=source,
                        assertions=self.identity_assertions,
                        method_version=self.identity_method_version,
                    )
                )
            if (source_id_set - assignment_source_ids) - (
                allowed_unassigned_source_ids
            ):
                message = (
                    "resolved internal-reference sources require current assignments"
                    if self.identity_method_version
                    in {
                        PERSON_IDENTITY_METHOD_VERSION,
                        TECHNOLOGY_IDENTITY_METHOD_VERSION,
                    }
                    else "every source identity requires one current assignment"
                )
                raise ValueError(message)
        if {
            source_id: assignment.canonical_identity_id
            for source_id, assignment in assignments.items()
        } != membership:
            raise ValueError(
                "source assignments must equal current identity membership"
            )
        decision_by_id = {
            decision.decision_id: decision for decision in self.identity_decisions
        }
        manifest_by_decision_id = {
            manifest.decision_id: manifest for manifest in self.decision_manifests
        }
        if self.identity_method_version in {
            PERSON_IDENTITY_METHOD_VERSION,
            TECHNOLOGY_IDENTITY_METHOD_VERSION,
        }:
            unresolved_verdict_ids = {
                verdict.verdict_id
                for verdict in self.candidate_verdicts
                if verdict.verdict is IdentityCandidateOutcome.unresolved
            }
            source_by_id = {
                source.source_identity_id: source for source in self.source_identities
            }
            unresolved_source_ids = {
                source_id
                for verdict in self.candidate_verdicts
                if verdict.verdict is IdentityCandidateOutcome.unresolved
                for source_id in verdict.source_identity_ids
            }
            for decision in self.identity_decisions:
                manifest = manifest_by_decision_id[decision.decision_id]
                if (
                    manifest.candidate_verdict_id in unresolved_verdict_ids
                    or set(decision.source_identity_ids) & unresolved_source_ids
                ):
                    raise ValueError(
                        "unresolved internal references cannot create identity decisions"
                    )
                if (
                    decision.action is IdentityAction.create
                    and manifest.candidate_verdict_id is None
                    and (
                        bool(set(decision.source_identity_ids) - set(source_by_id))
                        or any(
                            not _has_evidence_bound_internal_identifier(
                                source=source_by_id[source_id],
                                assertions=self.identity_assertions,
                                method_version=self.identity_method_version,
                            )
                            for source_id in decision.source_identity_ids
                        )
                    )
                ):
                    raise ValueError(
                        "internal-reference singleton identity requires an "
                        "evidence-bound stable identifier"
                    )
        for assignment in assignments.values():
            provenance_decision = decision_by_id.get(assignment.identity_decision_id)
            if provenance_decision is None:
                continue
            if (
                assignment.source_identity_id
                not in provenance_decision.source_identity_ids
                or assignment.canonical_identity_id
                not in provenance_decision.output_canonical_identity_ids
            ):
                raise ValueError(
                    "source assignment decision provenance must bind its source "
                    "and canonical owner"
                )
        return self


def canonical_identity_adjudication_input_sha256(
    *,
    source_identities: Iterable[SourceIdentity],
    identity_assertions: Iterable[SourceAssertion],
    current_canonical_identities: Iterable[CanonicalIdentity],
    canonical_identity_history: Iterable[CanonicalIdentity],
    policy: PolicyReference,
    current_source_identity_assignments: Iterable[SourceIdentityAssignment] = (),
    prior_identity_decisions: Iterable[IdentityDecision] = (),
    prior_decision_contexts: Iterable[IdentityDecisionContext] = (),
) -> str:
    payload = cast(
        JsonValue,
        {
            "source_identities": _models_json(source_identities, "source_identity_id"),
            "identity_assertions": _models_json(identity_assertions, "assertion_id"),
            "current_canonical_identities": _models_json(
                current_canonical_identities, "canonical_identity_id"
            ),
            "canonical_identity_history": _models_json(
                canonical_identity_history, "canonical_identity_id"
            ),
            "current_source_identity_assignments": _models_json(
                current_source_identity_assignments, "source_identity_id"
            ),
            "prior_identity_decisions": _models_json(
                prior_identity_decisions, "decision_id"
            ),
            "prior_decision_contexts": _models_json(
                prior_decision_contexts, "decision_id"
            ),
            "policy": policy.model_dump(mode="json"),
        },
    )
    return _content_sha256(payload)


def canonical_identity_component_id(
    *,
    request: IdentityResolutionRequest,
    source_identity_ids: Iterable[str],
) -> str:
    normalized_source_ids = tuple(sorted(source_identity_ids))
    source_id_set = set(normalized_source_ids)
    payload = cast(
        JsonValue,
        {
            "release_id": request.release_id,
            "identity_method_version": request.identity_method_version,
            "entity_type": next(
                source.entity_type
                for source in request.source_identities
                if source.source_identity_id in source_id_set
            ),
            "source_identity_ids": normalized_source_ids,
        },
    )
    return f"identity-component:{_content_sha256(payload)}"


def canonical_identity_decision_input_sha256(
    *,
    request: IdentityResolutionRequest,
    decision: IdentityDecision,
    supporting_assertion_ids: Iterable[str],
) -> str:
    return _IdentityDecisionInputHasher(request).hexdigest(
        decision=decision,
        supporting_assertion_ids=supporting_assertion_ids,
    )


class _IdentityDecisionInputHasher:
    """Reuse exact canonical request bytes across a batch of decision hashes."""

    def __init__(self, request: IdentityResolutionRequest) -> None:
        self._request_json = _canonical_json(
            cast(JsonValue, request.model_dump(mode="json"))
        )

    def hexdigest(
        self,
        *,
        decision: IdentityDecision,
        supporting_assertion_ids: Iterable[str],
    ) -> str:
        digest = hashlib.sha256()
        # These fragments reproduce _canonical_json() exactly. sort_keys=True orders
        # the three payload fields as decision, request, supporting_assertion_ids.
        digest.update(b'{"decision":')
        digest.update(
            _canonical_json(cast(JsonValue, decision.model_dump(mode="json")))
        )
        digest.update(b',"request":')
        digest.update(self._request_json)
        digest.update(b',"supporting_assertion_ids":')
        digest.update(
            _canonical_json(cast(JsonValue, sorted(supporting_assertion_ids)))
        )
        digest.update(b"}")
        return digest.hexdigest()


def canonical_identity_applied_decision_id(
    *,
    decision: IdentityDecision,
    candidate_verdict_id: str | None,
) -> str:
    decision_content = decision.model_dump(mode="json")
    decision_content.pop("decision_id", None)
    return "identity-decision:" + _content_sha256(
        cast(
            JsonValue,
            {
                "candidate_verdict_id": candidate_verdict_id,
                "decision": decision_content,
            },
        )
    )


def canonical_identity_rule_set_sha256(method_version: str) -> str:
    thresholds = _LLM_AUTO_ACTION_THRESHOLDS.get(method_version, {})
    strong_identifier_keys, candidate_recall_keys, high_confidence_composites = (
        _identity_rule_maps(method_version)
    )
    payload = cast(
        JsonValue,
        {
            "context_schema_version": "identity-decision-context-v1",
            "method_version": method_version,
            "strong_identifier_keys": strong_identifier_keys,
            "candidate_recall_keys": candidate_recall_keys,
            "high_confidence_composites": high_confidence_composites,
            "llm_auto_action_thresholds": {
                outcome.value: threshold for outcome, threshold in thresholds.items()
            },
        },
    )
    return _content_sha256(payload)


def identity_decision_context_sha256(
    context: IdentityDecisionContext | _IdentityDecisionContextContent,
) -> str:
    payload = context.model_dump(mode="json")
    payload.pop("content_sha256", None)
    return _content_sha256(cast(JsonValue, payload))


def create_identity_decision_context(
    *,
    release_id: str,
    decision: IdentityDecision,
    candidate_verdict: IdentityCandidateVerdict | None,
    source_identities: Iterable[SourceIdentity],
    identity_assertions: Iterable[SourceAssertion],
    input_canonical_identities: Iterable[CanonicalIdentity] = (),
    output_canonical_identities: Iterable[CanonicalIdentity] = (),
    input_source_assignments: Iterable[SourceIdentityAssignment] = (),
    referenced_prior_decision_ids: Iterable[str] = (),
    output_allocations: Iterable[IdentityDecisionOutputAllocation] = (),
) -> IdentityDecisionContext:
    content = _IdentityDecisionContextContent(
        release_id=release_id,
        decision_id=decision.decision_id,
        decision=decision,
        candidate_verdict=candidate_verdict,
        source_identities=tuple(source_identities),
        identity_assertions=tuple(identity_assertions),
        input_canonical_identities=tuple(input_canonical_identities),
        output_canonical_identities=tuple(output_canonical_identities),
        input_source_assignments=tuple(input_source_assignments),
        referenced_prior_decision_ids=tuple(referenced_prior_decision_ids),
        output_allocations=tuple(output_allocations),
        rule_set_content_sha256=canonical_identity_rule_set_sha256(
            decision.method_version
        ),
        decision_content_sha256=_content_sha256(
            cast(JsonValue, decision.model_dump(mode="json"))
        ),
    )
    return IdentityDecisionContext(
        **content.model_dump(mode="python"),
        content_sha256=identity_decision_context_sha256(content),
    )


def _bind_applied_decision_id(
    decision: IdentityDecision,
    *,
    candidate_verdict_id: str | None,
) -> IdentityDecision:
    return decision.model_copy(
        update={
            "decision_id": canonical_identity_applied_decision_id(
                decision=decision,
                candidate_verdict_id=candidate_verdict_id,
            )
        }
    )


def _build_decision_contexts(
    *,
    request: IdentityResolutionRequest,
    decisions: Iterable[IdentityDecision],
    manifests: Iterable[IdentityDecisionManifest],
    candidate_verdicts: Iterable[IdentityCandidateVerdict],
    current_canonical_identities: Iterable[CanonicalIdentity],
    canonical_identity_history: Iterable[CanonicalIdentity],
) -> tuple[IdentityDecisionContext, ...]:
    manifest_by_id = {manifest.decision_id: manifest for manifest in manifests}
    verdict_by_id = {verdict.verdict_id: verdict for verdict in candidate_verdicts}
    source_by_id = {
        source.source_identity_id: source for source in request.source_identities
    }
    assertion_by_id = {
        assertion.assertion_id: assertion for assertion in request.identity_assertions
    }
    request_identity_by_id = {
        identity.canonical_identity_id: identity
        for identity in request.current_canonical_identities
    }
    result_identity_by_id = {
        identity.canonical_identity_id: identity
        for identity in (
            *tuple(current_canonical_identities),
            *tuple(canonical_identity_history),
        )
    }
    contexts: list[IdentityDecisionContext] = []
    for decision in decisions:
        manifest = manifest_by_id[decision.decision_id]
        input_identities = tuple(
            request_identity_by_id[canonical_id]
            for canonical_id in decision.input_canonical_identity_ids
        )
        output_identities = tuple(
            result_identity_by_id[canonical_id]
            for canonical_id in decision.output_canonical_identity_ids
        )
        input_assignments = tuple(
            assignment
            for assignment in request.current_source_identity_assignments
            if assignment.source_identity_id in decision.source_identity_ids
            and assignment.canonical_identity_id
            in decision.input_canonical_identity_ids
        )
        referenced_prior_ids = {
            identity.identity_decision_id for identity in input_identities
        } | {assignment.identity_decision_id for assignment in input_assignments}
        if decision.reversal_of_decision_id is not None:
            referenced_prior_ids.add(decision.reversal_of_decision_id)
        contexts.append(
            create_identity_decision_context(
                release_id=request.release_id,
                decision=decision,
                candidate_verdict=(
                    verdict_by_id[manifest.candidate_verdict_id]
                    if manifest.candidate_verdict_id is not None
                    else None
                ),
                source_identities=tuple(
                    source_by_id[source_id]
                    for source_id in decision.source_identity_ids
                ),
                identity_assertions=tuple(
                    assertion_by_id[assertion_id]
                    for assertion_id in manifest.supporting_assertion_ids
                ),
                input_canonical_identities=input_identities,
                output_canonical_identities=output_identities,
                input_source_assignments=input_assignments,
                referenced_prior_decision_ids=tuple(sorted(referenced_prior_ids)),
                output_allocations=tuple(
                    IdentityDecisionOutputAllocation(
                        canonical_identity_id=identity.canonical_identity_id,
                        source_identity_ids=tuple(
                            source_id
                            for source_id in identity.source_identity_ids
                            if source_id in decision.source_identity_ids
                        ),
                    )
                    for identity in output_identities
                ),
            )
        )
    return tuple(sorted(contexts, key=lambda context: context.decision_id))


def _finalize_identity_result(
    request: IdentityResolutionRequest,
    content: _IdentityResolutionContent,
) -> IdentityResolutionResult:
    contexts = _build_decision_contexts(
        request=request,
        decisions=content.identity_decisions,
        manifests=content.decision_manifests,
        candidate_verdicts=content.candidate_verdicts,
        current_canonical_identities=content.current_canonical_identities,
        canonical_identity_history=content.canonical_identity_history,
    )
    review_cases = _identity_review_cases(
        release_id=content.release_id,
        decision_run_id=content.decision_run_id,
        identity_method_version=content.identity_method_version,
        as_of=content.as_of,
        policy=content.policy,
        verdicts=content.candidate_verdicts,
    )
    finalized = content.model_copy(
        update={"decision_contexts": contexts, "review_cases": review_cases}
    )
    return IdentityResolutionResult(
        **finalized.model_dump(mode="python"),
        content_sha256=canonical_identity_resolution_result_sha256(finalized),
    )


def canonical_identity_resolution_result_sha256(
    result: IdentityResolutionResult | _IdentityResolutionContent,
) -> str:
    payload = result.model_dump(mode="json")
    payload.pop("content_sha256", None)
    return _content_sha256(cast(JsonValue, payload))


def canonical_identity_resolution_request_sha256(
    request: IdentityResolutionRequest,
) -> str:
    return _content_sha256(cast(JsonValue, request.model_dump(mode="json")))


def canonical_identity_candidate_verdict_id(
    *,
    request: IdentityResolutionRequest,
    verdict: IdentityCandidateVerdict,
) -> str:
    verdict_content = verdict.model_dump(mode="json")
    verdict_content.pop("verdict_id", None)
    payload = cast(
        JsonValue,
        {
            "release_id": request.release_id,
            "decision_run_id": request.decision_run_id,
            "identity_method_version": request.identity_method_version,
            "as_of": request.as_of.isoformat(),
            "policy": request.policy.model_dump(mode="json"),
            "verdict": verdict_content,
        },
    )
    return f"identity-verdict:{_content_sha256(payload)}"


def _expected_identity_history(
    request: IdentityResolutionRequest,
    decisions: tuple[IdentityDecision, ...],
) -> tuple[CanonicalIdentity, ...]:
    expected_by_id = {
        identity.canonical_identity_id: identity
        for identity in request.canonical_identity_history
    }
    current_by_id = {
        identity.canonical_identity_id: identity
        for identity in request.current_canonical_identities
    }
    owner_by_source = {
        source_id: identity.canonical_identity_id
        for identity in request.current_canonical_identities
        for source_id in identity.source_identity_ids
    }
    used_input_ids: set[str] = set()
    for decision in decisions:
        input_ids = decision.input_canonical_identity_ids
        output_ids = decision.output_canonical_identity_ids
        decision_source_ids = set(decision.source_identity_ids)
        expected_input_ids = {
            owner_by_source[source_id]
            for source_id in decision_source_ids
            if source_id in owner_by_source
        }
        if (
            set(input_ids) != expected_input_ids
            or used_input_ids & set(input_ids)
            or any(
                not set(current_by_id[canonical_identity_id].source_identity_ids)
                <= decision_source_ids
                for canonical_identity_id in input_ids
            )
        ):
            raise IdentityResolutionIntegrityError(
                "identity decision inputs do not match owned decision sources"
            )
        used_input_ids.update(input_ids)
        if decision.action is IdentityAction.create:
            if input_ids:
                raise IdentityResolutionIntegrityError(
                    "create identity decision cannot consume a request owner"
                )
            continue
        if decision.action is IdentityAction.link:
            if len(input_ids) != 1 or output_ids != input_ids:
                raise IdentityResolutionIntegrityError(
                    "link identity decision must update one exact request owner"
                )
            continue
        if decision.action is IdentityAction.merge:
            terminal_state = CanonicalIdentityState.merged
            successor_ids = output_ids
        elif decision.action in {
            IdentityAction.split_identity,
            IdentityAction.reverse,
        }:
            terminal_state = CanonicalIdentityState.split_identity
            successor_ids = output_ids
        elif decision.action is IdentityAction.reject:
            terminal_state = CanonicalIdentityState.rejected
            successor_ids = ()
        else:  # pragma: no cover - enum exhaustiveness guard
            raise IdentityResolutionIntegrityError(
                "unsupported identity transition action"
            )
        for canonical_identity_id in input_ids:
            input_identity = current_by_id.get(canonical_identity_id)
            if input_identity is None or canonical_identity_id in expected_by_id:
                raise IdentityResolutionIntegrityError(
                    "identity transition does not consume one exact current owner"
                )
            expected_by_id[canonical_identity_id] = CanonicalIdentity(
                **{
                    **input_identity.model_dump(mode="python"),
                    "state": terminal_state,
                    "identity_decision_id": decision.decision_id,
                    "successor_identity_ids": successor_ids,
                }
            )
    return tuple(
        sorted(expected_by_id.values(), key=lambda value: value.canonical_identity_id)
    )


def _expected_identity_decision_outputs(
    *,
    request: IdentityResolutionRequest,
    decision: IdentityDecision,
    context: IdentityDecisionContext,
    candidate_verdict: IdentityCandidateVerdict | None,
) -> tuple[tuple[CanonicalIdentity, ...], tuple[SourceIdentityAssignment, ...]]:
    if decision.action is IdentityAction.reject:
        return (), ()
    source_by_id = {
        source.source_identity_id: source for source in request.source_identities
    }
    request_identity_by_id = {
        identity.canonical_identity_id: identity
        for identity in request.current_canonical_identities
    }
    request_assignment_by_source = {
        assignment.source_identity_id: assignment
        for assignment in request.current_source_identity_assignments
    }
    allocation_by_output = {
        allocation.canonical_identity_id: allocation.source_identity_ids
        for allocation in context.output_allocations
    }
    if set(allocation_by_output) != set(decision.output_canonical_identity_ids):
        raise IdentityResolutionIntegrityError(
            "identity decision output allocation is incomplete"
        )

    expected_outputs: list[CanonicalIdentity] = []
    expected_assignments: list[SourceIdentityAssignment] = []
    for output_id in decision.output_canonical_identity_ids:
        allocation = allocation_by_output[output_id]
        try:
            group_sources = tuple(source_by_id[source_id] for source_id in allocation)
        except KeyError as exc:
            raise IdentityResolutionIntegrityError(
                "identity decision output allocation references an unknown source"
            ) from exc
        entity_types = {source.entity_type for source in group_sources}
        if not group_sources or len(entity_types) != 1:
            raise IdentityResolutionIntegrityError(
                "identity decision output must allocate one exact entity type"
            )
        entity_type = group_sources[0].entity_type
        if decision.action is IdentityAction.link:
            input_id = decision.input_canonical_identity_ids[0]
            input_identity = request_identity_by_id[input_id]
            expected_output_id = input_id
            output = CanonicalIdentity(
                **{
                    **input_identity.model_dump(mode="python"),
                    "source_identity_ids": allocation,
                    "identity_decision_id": decision.decision_id,
                }
            )
        else:
            if decision.action is IdentityAction.create:
                predecessor_ids: tuple[str, ...] = ()
                if candidate_verdict is None:
                    if len(allocation) != 1:
                        raise IdentityResolutionIntegrityError(
                            "singleton create must allocate exactly one source"
                        )
                    generation_key = f"singleton:{request.decision_run_id}"
                elif candidate_verdict.verdict is IdentityCandidateOutcome.unresolved:
                    generation_key = f"unresolved:{candidate_verdict.verdict_id}"
                elif (
                    candidate_verdict.verdict
                    is IdentityCandidateOutcome.different_entities
                ):
                    generation_key = f"separate:{candidate_verdict.verdict_id}"
                else:
                    generation_key = f"create:{candidate_verdict.verdict_id}"
            elif decision.action is IdentityAction.merge:
                if candidate_verdict is None:
                    raise IdentityResolutionIntegrityError(
                        "merge identity decision requires a candidate verdict"
                    )
                predecessor_ids = decision.input_canonical_identity_ids
                generation_key = (
                    "merge:"
                    + ",".join(sorted(predecessor_ids))
                    + f":{candidate_verdict.verdict_id}"
                )
            elif decision.action is IdentityAction.reverse:
                if (
                    candidate_verdict is None
                    or decision.reversal_of_decision_id is None
                ):
                    raise IdentityResolutionIntegrityError(
                        "reverse identity decision requires exact verdict lineage"
                    )
                predecessor_ids = decision.input_canonical_identity_ids
                generation_key = (
                    f"reverse:{decision.reversal_of_decision_id}:"
                    f"{candidate_verdict.verdict_id}"
                )
            elif decision.action is IdentityAction.split_identity:
                if candidate_verdict is None:
                    raise IdentityResolutionIntegrityError(
                        "split identity decision requires a candidate verdict"
                    )
                predecessor_ids = decision.input_canonical_identity_ids
                generation_key = (
                    f"split:{predecessor_ids[0]}:{candidate_verdict.verdict_id}"
                )
            else:  # pragma: no cover - enum exhaustiveness guard
                raise IdentityResolutionIntegrityError(
                    "unsupported identity output action"
                )
            expected_output_id = _canonical_identity_id(
                request.release_id,
                entity_type,
                allocation,
                generation_key=generation_key,
            )
            output = CanonicalIdentity(
                canonical_identity_id=expected_output_id,
                entity_type=entity_type,
                state=CanonicalIdentityState.active,
                display_name=_display_name(group_sources),
                source_identity_ids=allocation,
                identity_decision_id=decision.decision_id,
                predecessor_identity_ids=predecessor_ids,
                release_id=request.release_id,
            )
        if output_id != expected_output_id:
            raise IdentityResolutionIntegrityError(
                "identity decision output ID does not match exact transition"
            )
        expected_outputs.append(output)
        expected_assignments.extend(
            SourceIdentityAssignment(
                release_id=request.release_id,
                source_identity_id=source_id,
                canonical_identity_id=output_id,
                identity_decision_id=(
                    request_assignment_by_source[source_id].identity_decision_id
                    if decision.action is IdentityAction.link
                    and source_id in request_assignment_by_source
                    else decision.decision_id
                ),
            )
            for source_id in allocation
        )
    return (
        tuple(
            sorted(
                expected_outputs,
                key=lambda identity: identity.canonical_identity_id,
            )
        ),
        tuple(
            sorted(
                expected_assignments,
                key=lambda assignment: assignment.source_identity_id,
            )
        ),
    )


def validate_identity_resolution_result(
    request: IdentityResolutionRequest,
    result: IdentityResolutionResult,
) -> IdentityResolutionResult:
    """Revalidate a result against the exact immutable resolution request."""

    try:
        validated_request = IdentityResolutionRequest.model_validate(
            request.model_dump(mode="python")
        )
        validated_result = IdentityResolutionResult.model_validate(
            result.model_dump(mode="python")
        )
    except (AttributeError, ValueError, ValidationError) as exc:
        raise IdentityResolutionIntegrityError(
            "identity resolution request, verdict/review case, or result content is invalid"
        ) from exc
    if (
        validated_result.release_id != validated_request.release_id
        or validated_result.decision_run_id != validated_request.decision_run_id
        or validated_result.identity_method_version
        != validated_request.identity_method_version
        or validated_result.as_of != validated_request.as_of
        or validated_result.policy != validated_request.policy
    ):
        raise IdentityResolutionIntegrityError(
            "identity resolution result context does not match its request"
        )
    if validated_result.source_identities != validated_request.source_identities:
        raise IdentityResolutionIntegrityError(
            "identity resolution result changed retained source identities"
        )
    if validated_result.identity_assertions != validated_request.identity_assertions:
        raise IdentityResolutionIntegrityError(
            "identity resolution result changed retained identity assertions"
        )

    source_by_id = {
        source.source_identity_id: source
        for source in validated_request.source_identities
    }
    source_ids = set(source_by_id)
    assertion_by_id = {
        assertion.assertion_id: assertion
        for assertion in validated_request.identity_assertions
    }
    verdict_source_ids: set[str] = set()
    for verdict in validated_result.candidate_verdicts:
        current_verdict_source_ids = set(verdict.source_identity_ids)
        component_sources = tuple(
            source
            for source in validated_request.source_identities
            if source.source_identity_id in current_verdict_source_ids
        )
        component_request = _component_request(validated_request, component_sources)
        expected_assertion_ids = {
            assertion.assertion_id
            for assertion in validated_request.identity_assertions
            if assertion.source_identity_id in current_verdict_source_ids
        }
        if (
            not current_verdict_source_ids <= source_ids
            or verdict_source_ids & current_verdict_source_ids
            or set(verdict.supporting_assertion_ids) != expected_assertion_ids
        ):
            raise IdentityResolutionIntegrityError(
                "identity candidate verdict must bind one disjoint exact component"
            )
        verdict_source_ids.update(current_verdict_source_ids)
        if (
            verdict.component_id
            != canonical_identity_component_id(
                request=component_request,
                source_identity_ids=verdict.source_identity_ids,
            )
            or verdict.component_input_sha256
            != canonical_identity_adjudication_input_sha256(
                source_identities=component_request.source_identities,
                identity_assertions=component_request.identity_assertions,
                current_canonical_identities=(
                    component_request.current_canonical_identities
                ),
                canonical_identity_history=(
                    component_request.canonical_identity_history
                ),
                current_source_identity_assignments=(
                    component_request.current_source_identity_assignments
                ),
                prior_identity_decisions=(component_request.prior_identity_decisions),
                prior_decision_contexts=(component_request.prior_decision_contexts),
                policy=component_request.policy,
            )
        ):
            raise IdentityResolutionIntegrityError(
                "identity candidate component content binding mismatch"
            )
        if verdict.verdict_id != canonical_identity_candidate_verdict_id(
            request=validated_request,
            verdict=verdict,
        ):
            raise IdentityResolutionIntegrityError(
                "identity candidate verdict content binding mismatch"
            )
    expected_verdict_components = tuple(
        sorted(
            tuple(source.source_identity_id for source in component)
            for component in _candidate_components(validated_request)
            if len(component) > 1
        )
    )
    actual_verdict_components = tuple(
        sorted(
            verdict.source_identity_ids
            for verdict in validated_result.candidate_verdicts
        )
    )
    if actual_verdict_components != expected_verdict_components:
        raise IdentityResolutionIntegrityError(
            "candidate verdicts must exactly cover recalled multi-source components"
        )
    applied_review_resolutions = tuple(
        verdict.human_review_resolution
        for verdict in validated_result.candidate_verdicts
        if verdict.human_review_resolution is not None
    )
    if applied_review_resolutions != validated_request.human_review_resolutions:
        raise IdentityResolutionIntegrityError(
            "identity result must apply every exact human review resolution once"
        )
    manifest_by_decision_id = {
        manifest.decision_id: manifest
        for manifest in validated_result.decision_manifests
    }
    context_by_decision_id = {
        context.decision_id: context for context in validated_result.decision_contexts
    }
    verdict_by_id = {
        verdict.verdict_id: verdict for verdict in validated_result.candidate_verdicts
    }
    result_identity_by_id = {
        identity.canonical_identity_id: identity
        for identity in (
            *validated_result.current_canonical_identities,
            *validated_result.canonical_identity_history,
        )
    }
    request_current_ids = {
        identity.canonical_identity_id
        for identity in validated_request.current_canonical_identities
    }
    request_current_by_id = {
        identity.canonical_identity_id: identity
        for identity in validated_request.current_canonical_identities
    }
    decision_output_ids = {
        canonical_identity_id
        for decision in validated_result.identity_decisions
        for canonical_identity_id in decision.output_canonical_identity_ids
    }
    decision_input_ids = {
        canonical_identity_id
        for decision in validated_result.identity_decisions
        for canonical_identity_id in decision.input_canonical_identity_ids
    }
    if validated_result.canonical_identity_history != _expected_identity_history(
        validated_request, validated_result.identity_decisions
    ):
        raise IdentityResolutionIntegrityError(
            "canonical identity history does not match exact request transitions"
        )
    result_current_by_id = {
        identity.canonical_identity_id: identity
        for identity in validated_result.current_canonical_identities
    }
    if any(
        canonical_identity_id not in decision_input_ids
        and result_current_by_id.get(canonical_identity_id) != identity
        for canonical_identity_id, identity in request_current_by_id.items()
    ):
        raise IdentityResolutionIntegrityError(
            "identity result dropped unconsumed request identity or assignment"
        )
    for identity in validated_result.current_canonical_identities:
        if identity.canonical_identity_id in decision_output_ids:
            continue
        if request_current_by_id.get(identity.canonical_identity_id) != identity:
            raise IdentityResolutionIntegrityError(
                "current identity is neither an exact request owner nor a decision output"
            )
    request_assignment_by_source = {
        assignment.source_identity_id: assignment
        for assignment in validated_request.current_source_identity_assignments
    }
    prior_decision_ids = {
        decision.decision_id for decision in validated_request.prior_identity_decisions
    }
    decision_source_ids = {
        source_id
        for decision in validated_result.identity_decisions
        for source_id in decision.source_identity_ids
    }
    result_assignment_by_source = {
        assignment.source_identity_id: assignment
        for assignment in validated_result.source_identity_assignments
    }
    if any(
        source_id not in decision_source_ids
        and result_assignment_by_source.get(source_id) != assignment
        for source_id, assignment in request_assignment_by_source.items()
    ):
        raise IdentityResolutionIntegrityError(
            "identity result dropped unconsumed request identity or assignment"
        )
    for assignment in validated_result.source_identity_assignments:
        if assignment.source_identity_id in decision_source_ids:
            continue
        if (
            request_assignment_by_source.get(assignment.source_identity_id)
            != assignment
        ):
            raise IdentityResolutionIntegrityError(
                "source assignment is neither exact request state nor decision output"
            )
    decision_input_hasher = _IdentityDecisionInputHasher(validated_request)
    rule_set_sha256_by_method_version: dict[str, str] = {}
    for decision in validated_result.identity_decisions:
        manifest = manifest_by_decision_id[decision.decision_id]
        context = context_by_decision_id[decision.decision_id]
        decision_source_id_set = set(decision.source_identity_ids)
        decision_input_id_set = set(decision.input_canonical_identity_ids)
        if decision.decision_id != canonical_identity_applied_decision_id(
            decision=decision,
            candidate_verdict_id=manifest.candidate_verdict_id,
        ):
            raise IdentityResolutionIntegrityError(
                "identity applied decision content binding mismatch"
            )
        if manifest.candidate_verdict_id is not None:
            linked_verdict = verdict_by_id.get(manifest.candidate_verdict_id)
            if linked_verdict is None or not set(decision.source_identity_ids) <= set(
                linked_verdict.source_identity_ids
            ):
                raise IdentityResolutionIntegrityError(
                    "identity decision candidate verdict link is cross-wired"
                )
        else:
            linked_verdict = None
        expected_outputs, expected_assignments = _expected_identity_decision_outputs(
            request=validated_request,
            decision=decision,
            context=context,
            candidate_verdict=linked_verdict,
        )
        if context.output_canonical_identities != expected_outputs:
            raise IdentityResolutionIntegrityError(
                "identity decision output payload does not match exact transition"
            )
        actual_assignments = tuple(
            sorted(
                (
                    result_assignment_by_source[source_id]
                    for source_id in decision.source_identity_ids
                    if source_id in result_assignment_by_source
                ),
                key=lambda assignment: assignment.source_identity_id,
            )
        )
        if actual_assignments != expected_assignments:
            raise IdentityResolutionIntegrityError(
                "identity decision output assignment does not match exact transition"
            )
        try:
            bound_output_identities = tuple(
                result_identity_by_id[canonical_identity_id]
                for canonical_identity_id in decision.output_canonical_identity_ids
            )
        except KeyError as exc:
            raise IdentityResolutionIntegrityError(
                "identity decision output references an unknown canonical identity"
            ) from exc
        if any(
            identity.identity_decision_id != decision.decision_id
            for identity in bound_output_identities
        ):
            raise IdentityResolutionIntegrityError(
                "canonical output decision provenance is cross-wired"
            )
        expected_context_sources = {
            source_id: source_by_id[source_id]
            for source_id in decision.source_identity_ids
            if source_id in source_by_id
        }
        expected_context_assertions = {
            assertion_id: assertion_by_id[assertion_id]
            for assertion_id in manifest.supporting_assertion_ids
            if assertion_id in assertion_by_id
        }
        expected_input_identities = tuple(
            sorted(
                (
                    request_current_by_id[canonical_identity_id]
                    for canonical_identity_id in decision.input_canonical_identity_ids
                    if canonical_identity_id in request_current_by_id
                ),
                key=lambda identity: identity.canonical_identity_id,
            )
        )
        expected_input_assignments = tuple(
            sorted(
                (
                    request_assignment_by_source[source_id]
                    for source_id in decision.source_identity_ids
                    if source_id in request_assignment_by_source
                    and request_assignment_by_source[source_id].canonical_identity_id
                    in decision_input_id_set
                ),
                key=lambda assignment: assignment.source_identity_id,
            )
        )
        if decision.method_version not in rule_set_sha256_by_method_version:
            rule_set_sha256_by_method_version[decision.method_version] = (
                canonical_identity_rule_set_sha256(decision.method_version)
            )
        expected_rule_set_sha256 = rule_set_sha256_by_method_version[
            decision.method_version
        ]
        if (
            context.release_id != validated_request.release_id
            or context.decision != decision
            or context.candidate_verdict != linked_verdict
            or {
                source.source_identity_id: source
                for source in context.source_identities
            }
            != expected_context_sources
            or {
                assertion.assertion_id: assertion
                for assertion in context.identity_assertions
            }
            != expected_context_assertions
            or context.rule_set_content_sha256 != expected_rule_set_sha256
            or context.input_canonical_identities != expected_input_identities
            or context.output_canonical_identities
            != tuple(
                sorted(
                    (
                        result_identity_by_id[canonical_id]
                        for canonical_id in decision.output_canonical_identity_ids
                    ),
                    key=lambda identity: identity.canonical_identity_id,
                )
            )
            or context.input_source_assignments != expected_input_assignments
            or not set(context.referenced_prior_decision_ids) <= prior_decision_ids
        ):
            raise IdentityResolutionIntegrityError(
                "identity decision-time context does not match the exact request"
            )
        if (
            decision.policy != validated_request.policy
            or decision.method_version != validated_request.identity_method_version
            or decision.decision_run_id != validated_request.decision_run_id
            or decision.decided_at != validated_request.as_of
        ):
            raise IdentityResolutionIntegrityError(
                "identity decision context does not match its request"
            )
        if not decision_input_id_set <= request_current_ids:
            raise IdentityResolutionIntegrityError(
                "identity decision input does not name an exact current request owner"
            )
        try:
            output_identities = tuple(
                result_identity_by_id[canonical_identity_id]
                for canonical_identity_id in decision.output_canonical_identity_ids
            )
        except KeyError as exc:
            raise IdentityResolutionIntegrityError(
                "identity decision output references an unknown canonical identity"
            ) from exc
        if any(
            identity.identity_decision_id != decision.decision_id
            for identity in output_identities
        ):
            raise IdentityResolutionIntegrityError(
                "canonical output decision provenance is cross-wired"
            )
        output_source_ids = {
            source_id
            for identity in output_identities
            for source_id in identity.source_identity_ids
        }
        expected_output_source_ids = (
            set()
            if decision.action is IdentityAction.reject
            else set(decision.source_identity_ids)
        )
        if output_source_ids != expected_output_source_ids:
            raise IdentityResolutionIntegrityError(
                "identity decision output allocation must cover its exact sources"
            )
        try:
            supporting_assertions = tuple(
                assertion_by_id[assertion_id]
                for assertion_id in manifest.supporting_assertion_ids
            )
        except KeyError as exc:
            raise IdentityResolutionIntegrityError(
                "identity decision manifest references unknown evidence"
            ) from exc
        if {
            assertion.source_identity_id for assertion in supporting_assertions
        } - decision_source_id_set:
            raise IdentityResolutionIntegrityError(
                "identity decision manifest evidence is cross-wired"
            )
        expected_manifest_sha256 = decision_input_hasher.hexdigest(
            decision=decision,
            supporting_assertion_ids=manifest.supporting_assertion_ids,
        )
        if manifest.input_content_sha256 != expected_manifest_sha256:
            raise IdentityResolutionIntegrityError(
                "identity decision manifest content hash mismatch"
            )
    for verdict in validated_result.candidate_verdicts:
        if verdict.verdict not in {
            IdentityCandidateOutcome.same_entity,
            IdentityCandidateOutcome.different_entities,
        }:
            continue
        verdict_sources = set(verdict.source_identity_ids)
        accepted_materialized_groups: list[tuple[str, ...]] = []
        for identity in validated_result.current_canonical_identities:
            membership = set(identity.source_identity_ids)
            if not membership & verdict_sources:
                continue
            if not membership <= verdict_sources:
                raise IdentityResolutionIntegrityError(
                    "accepted identity verdict spans another candidate component"
                )
            accepted_materialized_groups.append(tuple(sorted(membership)))
        if (
            tuple(sorted(accepted_materialized_groups))
            != verdict.source_identity_groups
        ):
            raise IdentityResolutionIntegrityError(
                "accepted identity verdict does not match materialized groups"
            )
    for verdict in validated_result.candidate_verdicts:
        if verdict.human_review_resolution is None:
            continue
        linked_decisions = tuple(
            decision
            for decision in validated_result.identity_decisions
            if manifest_by_decision_id[decision.decision_id].candidate_verdict_id
            == verdict.verdict_id
        )
        if linked_decisions:
            materialized_groups = tuple(
                sorted(
                    tuple(sorted(result_identity_by_id[output_id].source_identity_ids))
                    for decision in linked_decisions
                    for output_id in decision.output_canonical_identity_ids
                )
            )
        else:
            verdict_sources = set(verdict.source_identity_ids)
            materialized_groups = tuple(
                sorted(
                    tuple(sorted(identity.source_identity_ids))
                    for identity in validated_result.current_canonical_identities
                    if set(identity.source_identity_ids) <= verdict_sources
                    and set(identity.source_identity_ids)
                )
            )
        if materialized_groups != verdict.source_identity_groups:
            raise IdentityResolutionIntegrityError(
                "identity human review output groups must exactly apply its resolution"
            )
    return validated_result


def _canonical_identity_id(
    release_id: str,
    entity_type: str,
    source_identity_ids: Iterable[str],
    *,
    generation_key: str,
) -> str:
    digest = _content_sha256(
        cast(
            JsonValue,
            {
                "release_id": release_id,
                "entity_type": entity_type,
                "source_identity_ids": sorted(source_identity_ids),
                "generation_key": generation_key,
            },
        )
    )
    return f"{entity_type}-c-{digest[:24]}"


def _decision_id(
    *,
    request: IdentityResolutionRequest,
    action: IdentityAction,
    source_identity_ids: Iterable[str],
    input_canonical_identity_ids: Iterable[str],
    output_canonical_identity_ids: Iterable[str],
    reversal_of_decision_id: str | None,
    verdict: IdentityCandidateVerdict,
) -> str:
    digest = _content_sha256(
        cast(
            JsonValue,
            {
                "release_id": request.release_id,
                "decision_run_id": request.decision_run_id,
                "identity_method_version": request.identity_method_version,
                "as_of": request.as_of.isoformat(),
                "policy": request.policy.model_dump(mode="json"),
                "action": action.value,
                "source_identity_ids": sorted(source_identity_ids),
                "input_canonical_identity_ids": sorted(input_canonical_identity_ids),
                "output_canonical_identity_ids": sorted(output_canonical_identity_ids),
                "reversal_of_decision_id": reversal_of_decision_id,
                "verdict": verdict.model_dump(mode="json"),
            },
        )
    )
    return f"identity-decision:{digest}"


_STRONG_IDENTIFIER_KEYS = {
    "professor": ("orcid",),
    "company": ("unified_social_credit_code",),
    "paper": ("doi",),
    "patent": ("publication_number",),
}

_CANDIDATE_RECALL_KEYS = {
    "professor": ("name_key",),
    "company": ("name_key",),
    "paper": ("title_key",),
    "patent": ("title_key", "application_number"),
}

_HIGH_CONFIDENCE_COMPOSITES = {
    "professor": (("name_key", "institution_key", "department_key"),),
    "company": (("name_key", "registered_address_key"),),
    "paper": (("title_key", "publication_year", "first_author_key"),),
    "patent": (("title_key", "applicant_key", "filing_date"),),
}

CANONICAL_IDENTITY_METHOD_VERSION_V2 = "canonical-identity-resolution-v2"
_V2_HIGH_CONFIDENCE_COMPOSITES = {
    **_HIGH_CONFIDENCE_COMPOSITES,
    "professor": (
        ("name_key", "institution_key", "email_key"),
        ("name_key", "institution_key", "homepage_key"),
        *_HIGH_CONFIDENCE_COMPOSITES["professor"],
    ),
}

PERSON_IDENTITY_METHOD_VERSION = "canonical-identity-resolution-person-v1"
_PERSON_STRONG_IDENTIFIER_KEYS = {
    **_STRONG_IDENTIFIER_KEYS,
    "person": ("orcid",),
}
_PERSON_CANDIDATE_RECALL_KEYS = {
    **_CANDIDATE_RECALL_KEYS,
    "person": ("name_key",),
}
_PERSON_HIGH_CONFIDENCE_COMPOSITES = {
    **_HIGH_CONFIDENCE_COMPOSITES,
    "person": (),
}

TECHNOLOGY_IDENTITY_METHOD_VERSION = "canonical-identity-resolution-technology-v1"
_TECHNOLOGY_STRONG_IDENTIFIER_KEYS = {
    **_STRONG_IDENTIFIER_KEYS,
    "technology_concept": ("technology_id",),
    "technology_route": ("technology_id",),
}
_TECHNOLOGY_CANDIDATE_RECALL_KEYS = {
    **_CANDIDATE_RECALL_KEYS,
    "technology_concept": ("name_key",),
    "technology_route": ("name_key",),
}
_TECHNOLOGY_HIGH_CONFIDENCE_COMPOSITES = {
    **_HIGH_CONFIDENCE_COMPOSITES,
    "technology_concept": (),
    "technology_route": (),
}


def _identity_rule_maps(
    method_version: str,
) -> tuple[
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
    dict[str, tuple[tuple[str, ...], ...]],
]:
    if method_version == PERSON_IDENTITY_METHOD_VERSION:
        return (
            _PERSON_STRONG_IDENTIFIER_KEYS,
            _PERSON_CANDIDATE_RECALL_KEYS,
            _PERSON_HIGH_CONFIDENCE_COMPOSITES,
        )
    if method_version == TECHNOLOGY_IDENTITY_METHOD_VERSION:
        return (
            _TECHNOLOGY_STRONG_IDENTIFIER_KEYS,
            _TECHNOLOGY_CANDIDATE_RECALL_KEYS,
            _TECHNOLOGY_HIGH_CONFIDENCE_COMPOSITES,
        )
    if method_version == CANONICAL_IDENTITY_METHOD_VERSION_V2:
        return (
            _STRONG_IDENTIFIER_KEYS,
            _CANDIDATE_RECALL_KEYS,
            _V2_HIGH_CONFIDENCE_COMPOSITES,
        )
    return (
        _STRONG_IDENTIFIER_KEYS,
        _CANDIDATE_RECALL_KEYS,
        _HIGH_CONFIDENCE_COMPOSITES,
    )


_LLM_AUTO_ACTION_THRESHOLDS = {
    "canonical-identity-resolution-v1": {
        IdentityCandidateOutcome.same_entity: 0.90,
        IdentityCandidateOutcome.different_entities: 0.85,
    },
    CANONICAL_IDENTITY_METHOD_VERSION_V2: {
        IdentityCandidateOutcome.same_entity: 0.90,
        IdentityCandidateOutcome.different_entities: 0.85,
    },
    PERSON_IDENTITY_METHOD_VERSION: {
        IdentityCandidateOutcome.same_entity: 0.90,
        IdentityCandidateOutcome.different_entities: 0.85,
    },
    TECHNOLOGY_IDENTITY_METHOD_VERSION: {
        IdentityCandidateOutcome.same_entity: 0.90,
        IdentityCandidateOutcome.different_entities: 0.85,
    },
}


def _normalize_key_value(key: str, value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if key == "doi":
        normalized = re.sub(
            r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", normalized
        )
    if key == "orcid":
        normalized = re.sub(r"^https?://orcid\.org/", "", normalized)
    if key in {
        "orcid",
        "publication_number",
        "application_number",
        "unified_social_credit_code",
    }:
        normalized = re.sub(r"[^0-9a-z]", "", normalized)
    else:
        normalized = re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)
    return normalized or None


def normalize_identity_key_value(key: str, value: str | None) -> str | None:
    """Return the version-stable normalized value used by identity rules."""

    return _normalize_key_value(key, value)


def _has_evidence_bound_internal_identifier(
    *,
    source: SourceIdentity,
    assertions: Iterable[SourceAssertion],
    method_version: str,
) -> bool:
    identity_spec = {
        PERSON_IDENTITY_METHOD_VERSION: {
            "person": ("orcid", "identity.orcid"),
        },
        TECHNOLOGY_IDENTITY_METHOD_VERSION: {
            "technology_concept": (
                "technology_id",
                "identity.technology_id",
            ),
            "technology_route": (
                "technology_id",
                "identity.technology_id",
            ),
        },
    }.get(method_version, {})
    key_and_path = identity_spec.get(source.entity_type)
    if key_and_path is None:
        return False
    key, field_path = key_and_path
    normalized_identifier = _normalize_key_value(key, source.normalized_keys.get(key))
    if normalized_identifier is None:
        return False
    identifier_assertions = tuple(
        assertion
        for assertion in assertions
        if assertion.source_identity_id == source.source_identity_id
        and assertion.field_path == field_path
    )
    return bool(identifier_assertions) and all(
        isinstance(assertion.value, str)
        and _normalize_key_value(key, assertion.value) == normalized_identifier
        for assertion in identifier_assertions
    )


def _normalized_source_key(source: SourceIdentity, key: str) -> str | None:
    return _normalize_key_value(key, source.normalized_keys.get(key))


def _matching_composite_keys(
    sources: tuple[SourceIdentity, ...],
    *,
    method_version: str,
) -> tuple[str, ...] | None:
    if not sources or len({source.entity_type for source in sources}) != 1:
        return None
    _, _, composites = _identity_rule_maps(method_version)
    for keys in composites.get(sources[0].entity_type, ()):
        values_by_key = [
            tuple(_normalized_source_key(source, key) for source in sources)
            for key in keys
        ]
        if all(all(values) and len(set(values)) == 1 for values in values_by_key):
            return keys
    return None


def _sources_are_recall_candidates(
    left: SourceIdentity,
    right: SourceIdentity,
    *,
    method_version: str,
) -> bool:
    if left.entity_type != right.entity_type:
        return False
    strong_keys, recall_keys, _ = _identity_rule_maps(method_version)
    keys = (
        *strong_keys.get(left.entity_type, ()),
        *recall_keys.get(left.entity_type, ()),
    )
    return any(
        (left_value := _normalized_source_key(left, key)) is not None
        and left_value == _normalized_source_key(right, key)
        for key in keys
    )


def _candidate_components(
    request: IdentityResolutionRequest,
) -> tuple[tuple[SourceIdentity, ...], ...]:
    sources = request.source_identities
    parent = {
        source.source_identity_id: source.source_identity_id for source in sources
    }

    def find(source_id: str) -> str:
        while parent[source_id] != source_id:
            parent[source_id] = parent[parent[source_id]]
            source_id = parent[source_id]
        return source_id

    def union(left_id: str, right_id: str) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root == right_root:
            return
        lower, higher = sorted((left_root, right_root))
        parent[higher] = lower

    strong_keys, recall_keys, _ = _identity_rule_maps(
        request.identity_method_version
    )
    first_source_id_by_recall_key: dict[tuple[str, str, str], str] = {}
    for source in sources:
        keys = dict.fromkeys(
            (
                *strong_keys.get(source.entity_type, ()),
                *recall_keys.get(source.entity_type, ()),
            )
        )
        for key in keys:
            normalized_value = _normalized_source_key(source, key)
            if normalized_value is None:
                continue
            recall_key = (source.entity_type, key, normalized_value)
            first_source_id = first_source_id_by_recall_key.setdefault(
                recall_key, source.source_identity_id
            )
            union(first_source_id, source.source_identity_id)
    for identity in (
        *request.current_canonical_identities,
        *request.canonical_identity_history,
    ):
        for source_id in identity.source_identity_ids[1:]:
            union(identity.source_identity_ids[0], source_id)
    for decision in request.prior_identity_decisions:
        for source_id in decision.source_identity_ids[1:]:
            union(decision.source_identity_ids[0], source_id)

    grouped: dict[str, list[SourceIdentity]] = {}
    for source in sources:
        grouped.setdefault(find(source.source_identity_id), []).append(source)
    return tuple(
        tuple(sorted(component, key=lambda source: source.source_identity_id))
        for component in sorted(
            grouped.values(),
            key=lambda values: min(source.source_identity_id for source in values),
        )
    )


def _matching_strong_key(
    sources: tuple[SourceIdentity, ...], *, method_version: str
) -> str | None:
    if not sources or len({source.entity_type for source in sources}) != 1:
        return None
    strong_keys, _, _ = _identity_rule_maps(method_version)
    keys = strong_keys.get(sources[0].entity_type, ())
    for key in keys:
        values = [_normalized_source_key(source, key) for source in sources]
        if all(values) and len(set(values)) == 1:
            return key
    return None


def _conflicting_strong_key(
    sources: tuple[SourceIdentity, ...], *, method_version: str
) -> str | None:
    if not sources or len({source.entity_type for source in sources}) != 1:
        return None
    strong_keys, _, _ = _identity_rule_maps(method_version)
    keys = strong_keys.get(sources[0].entity_type, ())
    for key in keys:
        values = [_normalized_source_key(source, key) for source in sources]
        if all(values) and len(set(values)) > 1:
            return key
    return None


def _strong_identifier_groups(
    sources: tuple[SourceIdentity, ...],
    key: str,
) -> tuple[tuple[str, ...], ...]:
    grouped: dict[str, list[str]] = {}
    for source in sources:
        value = _normalized_source_key(source, key)
        if value is None:
            raise IdentityResolutionIntegrityError(
                "strong-identifier grouping requires complete normalized values"
            )
        grouped.setdefault(value, []).append(source.source_identity_id)
    return tuple(sorted(tuple(sorted(source_ids)) for source_ids in grouped.values()))


def _display_name(sources: Iterable[SourceIdentity]) -> str:
    for source in sorted(sources, key=lambda item: item.source_identity_id):
        for key in ("name_key", "title_key", "doi", "publication_number"):
            value = source.normalized_keys.get(key)
            if value:
                return value
    return sorted(sources, key=lambda item: item.source_identity_id)[0].source_key


def _unresolved_identity_result(
    request: IdentityResolutionRequest,
    verdict: IdentityCandidateVerdict,
) -> IdentityResolutionResult:
    """Keep existing ownership and isolate only sources that have no current owner."""

    if request.identity_method_version in {
        PERSON_IDENTITY_METHOD_VERSION,
        TECHNOLOGY_IDENTITY_METHOD_VERSION,
    }:
        content = _IdentityResolutionContent(
            release_id=request.release_id,
            decision_run_id=request.decision_run_id,
            identity_method_version=request.identity_method_version,
            as_of=request.as_of,
            policy=request.policy,
            source_identities=request.source_identities,
            identity_assertions=request.identity_assertions,
            candidate_verdicts=(verdict,),
            identity_decisions=(),
            current_canonical_identities=request.current_canonical_identities,
            canonical_identity_history=request.canonical_identity_history,
            source_identity_assignments=(request.current_source_identity_assignments),
            decision_manifests=(),
        )
        return _finalize_identity_result(request, content)

    owned_source_ids = {
        source_id
        for identity in request.current_canonical_identities
        for source_id in identity.source_identity_ids
    }
    assertions_by_source = {
        source.source_identity_id: tuple(
            assertion
            for assertion in request.identity_assertions
            if assertion.source_identity_id == source.source_identity_id
        )
        for source in request.source_identities
    }
    decisions: list[IdentityDecision] = []
    new_current: list[CanonicalIdentity] = []
    new_assignments: list[SourceIdentityAssignment] = []
    manifests: list[IdentityDecisionManifest] = []
    for source in request.source_identities:
        if source.source_identity_id in owned_source_ids:
            continue
        source_ids = (source.source_identity_id,)
        output_id = _canonical_identity_id(
            request.release_id,
            source.entity_type,
            source_ids,
            generation_key=f"unresolved:{verdict.verdict_id}",
        )
        decision_id = _decision_id(
            request=request,
            action=IdentityAction.create,
            source_identity_ids=source_ids,
            input_canonical_identity_ids=(),
            output_canonical_identity_ids=(output_id,),
            reversal_of_decision_id=None,
            verdict=verdict,
        )
        decision = IdentityDecision(
            decision_id=decision_id,
            action=IdentityAction.create,
            source_identity_ids=source_ids,
            output_canonical_identity_ids=(output_id,),
            supporting_record_ids=source.source_record_ids,
            policy=request.policy,
            method=(
                DecisionMethod.composite
                if verdict.method is DecisionMethod.structured_llm
                else verdict.method
            ),
            method_version=request.identity_method_version,
            decision_run_id=request.decision_run_id,
            confidence=verdict.confidence,
            rationale=(
                "Created a separate provisional canonical owner while the candidate "
                "identity remains unresolved."
            ),
            decided_at=request.as_of,
            llm_trace=None,
            human_review_resolution=verdict.human_review_resolution,
        )
        decision = _bind_applied_decision_id(
            decision, candidate_verdict_id=verdict.verdict_id
        )
        decision_id = decision.decision_id
        supporting_assertion_ids = tuple(
            assertion.assertion_id
            for assertion in assertions_by_source[source.source_identity_id]
        )
        decisions.append(decision)
        new_current.append(
            CanonicalIdentity(
                canonical_identity_id=output_id,
                entity_type=source.entity_type,
                state=CanonicalIdentityState.active,
                display_name=_display_name((source,)),
                source_identity_ids=source_ids,
                identity_decision_id=decision_id,
                release_id=request.release_id,
            )
        )
        new_assignments.append(
            SourceIdentityAssignment(
                release_id=request.release_id,
                source_identity_id=source.source_identity_id,
                canonical_identity_id=output_id,
                identity_decision_id=decision_id,
            )
        )
        manifests.append(
            IdentityDecisionManifest(
                release_id=request.release_id,
                decision_id=decision_id,
                candidate_verdict_id=verdict.verdict_id,
                supporting_assertion_ids=supporting_assertion_ids,
                input_content_sha256=canonical_identity_decision_input_sha256(
                    request=request,
                    decision=decision,
                    supporting_assertion_ids=supporting_assertion_ids,
                ),
            )
        )
    content = _IdentityResolutionContent(
        release_id=request.release_id,
        decision_run_id=request.decision_run_id,
        identity_method_version=request.identity_method_version,
        as_of=request.as_of,
        policy=request.policy,
        source_identities=request.source_identities,
        identity_assertions=request.identity_assertions,
        candidate_verdicts=(verdict,),
        identity_decisions=tuple(
            sorted(decisions, key=lambda value: value.decision_id)
        ),
        current_canonical_identities=tuple(
            sorted(
                (*request.current_canonical_identities, *new_current),
                key=lambda value: value.canonical_identity_id,
            )
        ),
        canonical_identity_history=request.canonical_identity_history,
        source_identity_assignments=tuple(
            sorted(
                (*request.current_source_identity_assignments, *new_assignments),
                key=lambda value: value.source_identity_id,
            )
        ),
        decision_manifests=tuple(
            sorted(manifests, key=lambda value: value.decision_id)
        ),
    )
    return _finalize_identity_result(request, content)


def _different_new_entities_result(
    request: IdentityResolutionRequest,
    verdict: IdentityCandidateVerdict,
) -> IdentityResolutionResult:
    if request.current_canonical_identities:
        return _different_existing_owner_result(request, verdict)
    source_by_id = {
        source.source_identity_id: source for source in request.source_identities
    }

    decisions: list[IdentityDecision] = []
    current: list[CanonicalIdentity] = []
    assignments: list[SourceIdentityAssignment] = []
    manifests: list[IdentityDecisionManifest] = []
    for source_ids in verdict.source_identity_groups:
        group_sources = tuple(source_by_id[source_id] for source_id in source_ids)
        output_id = _canonical_identity_id(
            request.release_id,
            group_sources[0].entity_type,
            source_ids,
            generation_key=f"separate:{verdict.verdict_id}",
        )
        decision_id = _decision_id(
            request=request,
            action=IdentityAction.create,
            source_identity_ids=source_ids,
            input_canonical_identity_ids=(),
            output_canonical_identity_ids=(output_id,),
            reversal_of_decision_id=None,
            verdict=verdict,
        )
        decision = IdentityDecision(
            decision_id=decision_id,
            action=IdentityAction.create,
            source_identity_ids=source_ids,
            output_canonical_identity_ids=(output_id,),
            supporting_record_ids=_supporting_record_ids(group_sources),
            policy=request.policy,
            method=(
                DecisionMethod.composite
                if verdict.method is DecisionMethod.structured_llm
                else verdict.method
            ),
            method_version=request.identity_method_version,
            decision_run_id=request.decision_run_id,
            confidence=verdict.confidence,
            rationale=(
                "Materialized one source-local canonical owner under the recorded "
                "candidate separation verdict."
                if verdict.method is DecisionMethod.structured_llm
                else verdict.rationale
            ),
            decided_at=request.as_of,
            llm_trace=None,
            human_review_resolution=verdict.human_review_resolution,
        )
        decision = _bind_applied_decision_id(
            decision, candidate_verdict_id=verdict.verdict_id
        )
        decision_id = decision.decision_id
        output = CanonicalIdentity(
            canonical_identity_id=output_id,
            entity_type=group_sources[0].entity_type,
            state=CanonicalIdentityState.active,
            display_name=_display_name(group_sources),
            source_identity_ids=source_ids,
            identity_decision_id=decision_id,
            release_id=request.release_id,
        )
        supporting_assertion_ids = tuple(
            assertion.assertion_id
            for assertion in request.identity_assertions
            if assertion.source_identity_id in source_ids
        )
        decisions.append(decision)
        current.append(output)
        assignments.extend(
            SourceIdentityAssignment(
                release_id=request.release_id,
                source_identity_id=source_id,
                canonical_identity_id=output_id,
                identity_decision_id=decision_id,
            )
            for source_id in source_ids
        )
        manifests.append(
            IdentityDecisionManifest(
                release_id=request.release_id,
                decision_id=decision_id,
                candidate_verdict_id=verdict.verdict_id,
                supporting_assertion_ids=supporting_assertion_ids,
                input_content_sha256=canonical_identity_decision_input_sha256(
                    request=request,
                    decision=decision,
                    supporting_assertion_ids=supporting_assertion_ids,
                ),
            )
        )
    content = _IdentityResolutionContent(
        release_id=request.release_id,
        decision_run_id=request.decision_run_id,
        identity_method_version=request.identity_method_version,
        as_of=request.as_of,
        policy=request.policy,
        source_identities=request.source_identities,
        identity_assertions=request.identity_assertions,
        candidate_verdicts=(verdict,),
        identity_decisions=tuple(
            sorted(decisions, key=lambda value: value.decision_id)
        ),
        current_canonical_identities=tuple(
            sorted(current, key=lambda value: value.canonical_identity_id)
        ),
        canonical_identity_history=request.canonical_identity_history,
        source_identity_assignments=tuple(
            sorted(assignments, key=lambda value: value.source_identity_id)
        ),
        decision_manifests=tuple(
            sorted(manifests, key=lambda value: value.decision_id)
        ),
    )
    return _finalize_identity_result(request, content)


def _different_existing_owner_result(
    request: IdentityResolutionRequest,
    verdict: IdentityCandidateVerdict,
) -> IdentityResolutionResult:
    if len(request.current_canonical_identities) != 1:
        raise IdentityResolutionIntegrityError(
            "candidate separation requires exactly one combined current owner"
        )
    predecessor = request.current_canonical_identities[0]
    if set(predecessor.source_identity_ids) != {
        source.source_identity_id for source in request.source_identities
    }:
        raise IdentityResolutionIntegrityError(
            "combined current owner must contain the exact candidate sources"
        )
    prior_by_id = {
        decision.decision_id: decision for decision in request.prior_identity_decisions
    }
    reversed_decision = prior_by_id.get(predecessor.identity_decision_id)
    named_reversal = (
        reversed_decision is not None
        and reversed_decision.action is IdentityAction.merge
    )
    if named_reversal:
        assert reversed_decision is not None
        action = IdentityAction.reverse
        reversal_of_decision_id = reversed_decision.decision_id
        generation_prefix = f"reverse:{reversal_of_decision_id}"
    else:
        action = IdentityAction.split_identity
        reversal_of_decision_id = None
        generation_prefix = f"split:{predecessor.canonical_identity_id}"

    source_by_id = {
        source.source_identity_id: source for source in request.source_identities
    }
    output_specs = tuple(
        (
            source_ids,
            tuple(source_by_id[source_id] for source_id in source_ids),
            _canonical_identity_id(
                request.release_id,
                source_by_id[source_ids[0]].entity_type,
                source_ids,
                generation_key=(f"{generation_prefix}:{verdict.verdict_id}"),
            ),
        )
        for source_ids in verdict.source_identity_groups
    )
    output_ids = tuple(output_id for _, _, output_id in output_specs)
    source_ids = tuple(
        source.source_identity_id for source in request.source_identities
    )
    decision_id = _decision_id(
        request=request,
        action=action,
        source_identity_ids=source_ids,
        input_canonical_identity_ids=(predecessor.canonical_identity_id,),
        output_canonical_identity_ids=output_ids,
        reversal_of_decision_id=reversal_of_decision_id,
        verdict=verdict,
    )
    decision = IdentityDecision(
        decision_id=decision_id,
        action=action,
        source_identity_ids=source_ids,
        input_canonical_identity_ids=(predecessor.canonical_identity_id,),
        output_canonical_identity_ids=output_ids,
        supporting_record_ids=_supporting_record_ids(request.source_identities),
        policy=request.policy,
        method=verdict.method,
        method_version=request.identity_method_version,
        decision_run_id=request.decision_run_id,
        confidence=verdict.confidence,
        rationale=verdict.rationale,
        decided_at=request.as_of,
        reversal_of_decision_id=reversal_of_decision_id,
        llm_trace=verdict.llm_trace,
        human_review_resolution=verdict.human_review_resolution,
    )
    decision = _bind_applied_decision_id(
        decision, candidate_verdict_id=verdict.verdict_id
    )
    decision_id = decision.decision_id
    outputs = tuple(
        CanonicalIdentity(
            canonical_identity_id=output_id,
            entity_type=group_sources[0].entity_type,
            state=CanonicalIdentityState.active,
            display_name=_display_name(group_sources),
            source_identity_ids=source_ids,
            identity_decision_id=decision_id,
            predecessor_identity_ids=(predecessor.canonical_identity_id,),
            release_id=request.release_id,
        )
        for source_ids, group_sources, output_id in output_specs
    )
    corrected_predecessor = CanonicalIdentity(
        **{
            **predecessor.model_dump(mode="python"),
            "state": CanonicalIdentityState.split_identity,
            "identity_decision_id": decision_id,
            "successor_identity_ids": output_ids,
        }
    )
    assignments = tuple(
        SourceIdentityAssignment(
            release_id=request.release_id,
            source_identity_id=source_identity_id,
            canonical_identity_id=output_id,
            identity_decision_id=decision_id,
        )
        for source_ids, _, output_id in output_specs
        for source_identity_id in source_ids
    )
    supporting_assertion_ids = tuple(
        assertion.assertion_id for assertion in request.identity_assertions
    )
    manifest = IdentityDecisionManifest(
        release_id=request.release_id,
        decision_id=decision_id,
        candidate_verdict_id=verdict.verdict_id,
        supporting_assertion_ids=supporting_assertion_ids,
        input_content_sha256=canonical_identity_decision_input_sha256(
            request=request,
            decision=decision,
            supporting_assertion_ids=supporting_assertion_ids,
        ),
    )
    content = _IdentityResolutionContent(
        release_id=request.release_id,
        decision_run_id=request.decision_run_id,
        identity_method_version=request.identity_method_version,
        as_of=request.as_of,
        policy=request.policy,
        source_identities=request.source_identities,
        identity_assertions=request.identity_assertions,
        candidate_verdicts=(verdict,),
        identity_decisions=(decision,),
        current_canonical_identities=tuple(
            sorted(outputs, key=lambda value: value.canonical_identity_id)
        ),
        canonical_identity_history=tuple(
            sorted(
                (*request.canonical_identity_history, corrected_predecessor),
                key=lambda value: value.canonical_identity_id,
            )
        ),
        source_identity_assignments=tuple(
            sorted(assignments, key=lambda value: value.source_identity_id)
        ),
        decision_manifests=(manifest,),
    )
    return _finalize_identity_result(request, content)


class StructuredIdentityAdjudicator(Protocol):
    """Internal seam for schema-validated identity candidate adjudication."""

    def adjudicate(
        self, request: _IdentityAdjudicationRequest, /
    ) -> _ValidatedIdentityAdjudication: ...


class _RecordedStructuredIdentityAdjudicator:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        schema_version: str,
        responses: Mapping[
            tuple[tuple[str, ...], tuple[str, ...], str],
            RecordedIdentityAdjudication,
        ],
    ) -> None:
        self._provider = provider
        self._model = model
        self._prompt_version = prompt_version
        self._schema_version = schema_version
        self._responses = MappingProxyType(dict(responses))

    def adjudicate(
        self, request: _IdentityAdjudicationRequest, /
    ) -> _ValidatedIdentityAdjudication:
        response = self._responses.get(
            (
                request.source_identity_ids,
                request.assertion_ids,
                request.input_content_sha256,
            )
        )
        if response is None:
            raise IdentityAdjudicationIntegrityError(
                "no recorded identity adjudication is bound to the exact input content"
            )
        actual_output_sha256 = hashlib.sha256(response.raw_output).hexdigest()
        if actual_output_sha256 != response.expected_output_sha256:
            raise IdentityAdjudicationIntegrityError(
                "recorded identity adjudication output hash does not match raw bytes"
            )
        output, validated_output = _parse_identity_adjudication_output(
            response.raw_output,
            source_identity_ids=request.source_identity_ids,
        )
        trace = LLMDecisionTrace(
            provider=self._provider,
            model=self._model,
            prompt_version=self._prompt_version,
            schema_version=self._schema_version,
            input_evidence_ids=request.assertion_ids,
            raw_output_base64=base64.b64encode(response.raw_output).decode("ascii"),
            output_sha256=actual_output_sha256,
            validated_output=validated_output,
        )
        return _ValidatedIdentityAdjudication(output=output, llm_trace=trace)


def create_recorded_structured_identity_adjudicator(
    *,
    provider: str,
    model: str,
    prompt_version: str,
    schema_version: str,
    responses: Iterable[RecordedIdentityAdjudication],
) -> StructuredIdentityAdjudicator:
    """Create a deterministic adapter over exact recorded provider bytes."""

    if not all(
        (
            provider.strip(),
            model.strip(),
            prompt_version.strip(),
            schema_version.strip(),
        )
    ):
        raise IdentityAdjudicationIntegrityError(
            "recorded identity adjudicator configuration cannot be empty"
        )
    response_map: dict[
        tuple[tuple[str, ...], tuple[str, ...], str], RecordedIdentityAdjudication
    ] = {}
    try:
        validated_responses = tuple(
            RecordedIdentityAdjudication.model_validate(
                response.model_dump(mode="python")
            )
            for response in responses
        )
    except (AttributeError, ValidationError) as exc:
        raise IdentityAdjudicationIntegrityError(
            "recorded identity adjudication response is invalid"
        ) from exc
    for response in validated_responses:
        key = (
            response.input_source_identity_ids,
            response.input_assertion_ids,
            response.input_content_sha256,
        )
        if key in response_map:
            raise IdentityAdjudicationIntegrityError(
                "duplicate recorded identity adjudication input is ambiguous"
            )
        response_map[key] = response
    return _RecordedStructuredIdentityAdjudicator(
        provider=provider.strip(),
        model=model.strip(),
        prompt_version=prompt_version.strip(),
        schema_version=schema_version.strip(),
        responses=response_map,
    )


def _component_request(
    request: IdentityResolutionRequest,
    sources: tuple[SourceIdentity, ...],
) -> IdentityResolutionRequest:
    source_ids = {source.source_identity_id for source in sources}

    def identity_is_in_component(identity: CanonicalIdentity) -> bool:
        membership = set(identity.source_identity_ids)
        if membership & source_ids and not membership <= source_ids:
            raise IdentityResolutionIntegrityError(
                "one canonical identity cannot span recalled candidate components"
            )
        return bool(membership) and membership <= source_ids

    current = tuple(
        identity
        for identity in request.current_canonical_identities
        if identity_is_in_component(identity)
    )
    history = tuple(
        identity
        for identity in request.canonical_identity_history
        if identity_is_in_component(identity)
    )
    decisions = tuple(
        decision
        for decision in request.prior_identity_decisions
        if set(decision.source_identity_ids) <= source_ids
    )
    decision_ids = {decision.decision_id for decision in decisions}
    return IdentityResolutionRequest(
        release_id=request.release_id,
        decision_run_id=request.decision_run_id,
        identity_method_version=request.identity_method_version,
        as_of=request.as_of,
        policy=request.policy,
        source_identities=sources,
        identity_assertions=tuple(
            assertion
            for assertion in request.identity_assertions
            if assertion.source_identity_id in source_ids
        ),
        current_canonical_identities=current,
        current_source_identity_assignments=tuple(
            assignment
            for assignment in request.current_source_identity_assignments
            if assignment.source_identity_id in source_ids
        ),
        canonical_identity_history=history,
        prior_identity_decisions=decisions,
        prior_decision_contexts=tuple(
            context
            for context in request.prior_decision_contexts
            if context.decision_id in decision_ids
        ),
        human_review_resolutions=tuple(
            resolution
            for resolution in request.human_review_resolutions
            if set(resolution.review_case.source_identity_ids) == source_ids
        ),
    )


def _singleton_component_result(
    request: IdentityResolutionRequest,
) -> IdentityResolutionResult:
    source = request.source_identities[0]
    if request.current_canonical_identities:
        if len(
            request.current_canonical_identities
        ) != 1 or request.current_canonical_identities[0].source_identity_ids != (
            source.source_identity_id,
        ):
            raise IdentityResolutionIntegrityError(
                "a singleton candidate has ambiguous current ownership"
            )
        content = _IdentityResolutionContent(
            release_id=request.release_id,
            decision_run_id=request.decision_run_id,
            identity_method_version=request.identity_method_version,
            as_of=request.as_of,
            policy=request.policy,
            source_identities=request.source_identities,
            identity_assertions=request.identity_assertions,
            candidate_verdicts=(),
            identity_decisions=(),
            current_canonical_identities=request.current_canonical_identities,
            canonical_identity_history=request.canonical_identity_history,
            source_identity_assignments=request.current_source_identity_assignments,
            decision_manifests=(),
        )
        return _finalize_identity_result(request, content)

    if request.identity_method_version in {
        PERSON_IDENTITY_METHOD_VERSION,
        TECHNOLOGY_IDENTITY_METHOD_VERSION,
    } and not _has_evidence_bound_internal_identifier(
        source=source,
        assertions=request.identity_assertions,
        method_version=request.identity_method_version,
    ):
        content = _IdentityResolutionContent(
            release_id=request.release_id,
            decision_run_id=request.decision_run_id,
            identity_method_version=request.identity_method_version,
            as_of=request.as_of,
            policy=request.policy,
            source_identities=request.source_identities,
            identity_assertions=request.identity_assertions,
            candidate_verdicts=(),
            identity_decisions=(),
            current_canonical_identities=(),
            canonical_identity_history=request.canonical_identity_history,
            source_identity_assignments=(),
            decision_manifests=(),
        )
        return _finalize_identity_result(request, content)

    output_id = _canonical_identity_id(
        request.release_id,
        source.entity_type,
        (source.source_identity_id,),
        generation_key=f"singleton:{request.decision_run_id}",
    )
    decision_id = "identity-decision:" + _content_sha256(
        cast(
            JsonValue,
            {
                "release_id": request.release_id,
                "decision_run_id": request.decision_run_id,
                "identity_method_version": request.identity_method_version,
                "policy": request.policy.model_dump(mode="json"),
                "action": IdentityAction.create.value,
                "source_identity_id": source.source_identity_id,
                "output_canonical_identity_id": output_id,
            },
        )
    )
    decision = IdentityDecision(
        decision_id=decision_id,
        action=IdentityAction.create,
        source_identity_ids=(source.source_identity_id,),
        output_canonical_identity_ids=(output_id,),
        supporting_record_ids=source.source_record_ids,
        policy=request.policy,
        method=DecisionMethod.deterministic,
        method_version=request.identity_method_version,
        decision_run_id=request.decision_run_id,
        confidence=1.0,
        rationale=(
            "Created an isolated canonical owner because candidate recall found no "
            "other plausible source identity."
        ),
        decided_at=request.as_of,
    )
    decision = _bind_applied_decision_id(decision, candidate_verdict_id=None)
    decision_id = decision.decision_id
    output = CanonicalIdentity(
        canonical_identity_id=output_id,
        entity_type=source.entity_type,
        state=CanonicalIdentityState.active,
        display_name=_display_name((source,)),
        source_identity_ids=(source.source_identity_id,),
        identity_decision_id=decision_id,
        release_id=request.release_id,
    )
    supporting_assertion_ids = tuple(
        assertion.assertion_id for assertion in request.identity_assertions
    )
    manifest = IdentityDecisionManifest(
        release_id=request.release_id,
        decision_id=decision_id,
        supporting_assertion_ids=supporting_assertion_ids,
        input_content_sha256=canonical_identity_decision_input_sha256(
            request=request,
            decision=decision,
            supporting_assertion_ids=supporting_assertion_ids,
        ),
    )
    content = _IdentityResolutionContent(
        release_id=request.release_id,
        decision_run_id=request.decision_run_id,
        identity_method_version=request.identity_method_version,
        as_of=request.as_of,
        policy=request.policy,
        source_identities=request.source_identities,
        identity_assertions=request.identity_assertions,
        candidate_verdicts=(),
        identity_decisions=(decision,),
        current_canonical_identities=(output,),
        canonical_identity_history=request.canonical_identity_history,
        source_identity_assignments=(
            SourceIdentityAssignment(
                release_id=request.release_id,
                source_identity_id=source.source_identity_id,
                canonical_identity_id=output_id,
                identity_decision_id=decision_id,
            ),
        ),
        decision_manifests=(manifest,),
    )
    return _finalize_identity_result(request, content)


def _combine_component_results(
    request: IdentityResolutionRequest,
    results: tuple[IdentityResolutionResult, ...],
) -> IdentityResolutionResult:
    decisions = tuple(
        sorted(
            (decision for result in results for decision in result.identity_decisions),
            key=lambda decision: decision.decision_id,
        )
    )
    component_manifests = {
        manifest.decision_id: manifest
        for result in results
        for manifest in result.decision_manifests
    }
    decision_input_hasher = _IdentityDecisionInputHasher(request)
    content = _IdentityResolutionContent(
        release_id=request.release_id,
        decision_run_id=request.decision_run_id,
        identity_method_version=request.identity_method_version,
        as_of=request.as_of,
        policy=request.policy,
        source_identities=request.source_identities,
        identity_assertions=request.identity_assertions,
        candidate_verdicts=tuple(
            sorted(
                (
                    verdict
                    for result in results
                    for verdict in result.candidate_verdicts
                ),
                key=lambda verdict: verdict.verdict_id,
            )
        ),
        identity_decisions=decisions,
        current_canonical_identities=tuple(
            sorted(
                (
                    identity
                    for result in results
                    for identity in result.current_canonical_identities
                ),
                key=lambda identity: identity.canonical_identity_id,
            )
        ),
        canonical_identity_history=tuple(
            sorted(
                (
                    identity
                    for result in results
                    for identity in result.canonical_identity_history
                ),
                key=lambda identity: identity.canonical_identity_id,
            )
        ),
        source_identity_assignments=tuple(
            sorted(
                (
                    assignment
                    for result in results
                    for assignment in result.source_identity_assignments
                ),
                key=lambda assignment: assignment.source_identity_id,
            )
        ),
        decision_manifests=tuple(
            IdentityDecisionManifest(
                **{
                    **component_manifests[decision.decision_id].model_dump(
                        mode="python"
                    ),
                    "input_content_sha256": decision_input_hasher.hexdigest(
                        decision=decision,
                        supporting_assertion_ids=component_manifests[
                            decision.decision_id
                        ].supporting_assertion_ids,
                    ),
                }
            )
            for decision in decisions
        ),
    )
    result = _finalize_identity_result(request, content)
    return validate_identity_resolution_result(request, result)


def _no_action_component_result(
    request: IdentityResolutionRequest,
    verdict: IdentityCandidateVerdict,
) -> IdentityResolutionResult:
    content = _IdentityResolutionContent(
        release_id=request.release_id,
        decision_run_id=request.decision_run_id,
        identity_method_version=request.identity_method_version,
        as_of=request.as_of,
        policy=request.policy,
        source_identities=request.source_identities,
        identity_assertions=request.identity_assertions,
        candidate_verdicts=(verdict,),
        identity_decisions=(),
        current_canonical_identities=request.current_canonical_identities,
        canonical_identity_history=request.canonical_identity_history,
        source_identity_assignments=request.current_source_identity_assignments,
        decision_manifests=(),
    )
    result = _finalize_identity_result(request, content)
    return validate_identity_resolution_result(request, result)


class CanonicalIdentityResolutionEngine(ABC):
    @abstractmethod
    def resolve(self, request: IdentityResolutionRequest) -> IdentityResolutionResult:
        """Resolve a versioned offline identity batch without durable side effects."""


class _EphemeralCanonicalIdentityResolutionEngine(CanonicalIdentityResolutionEngine):
    def __init__(self, *, adjudicator: StructuredIdentityAdjudicator | None) -> None:
        self._adjudicator = adjudicator

    def resolve(self, request: IdentityResolutionRequest) -> IdentityResolutionResult:
        try:
            validated = IdentityResolutionRequest.model_validate(
                request.model_dump(mode="python")
            )
        except (AttributeError, ValueError) as exc:
            raise IdentityResolutionIntegrityError(
                "identity resolution request is invalid"
            ) from exc
        component_results = tuple(
            (
                _singleton_component_result(component_request)
                if len(component) == 1
                else self._resolve_component(component_request)
            )
            for component in _candidate_components(validated)
            for component_request in (_component_request(validated, component),)
        )
        return _combine_component_results(validated, component_results)

    def _resolve_component(
        self, request: IdentityResolutionRequest
    ) -> IdentityResolutionResult:
        try:
            validated = IdentityResolutionRequest.model_validate(
                request.model_dump(mode="python")
            )
        except (AttributeError, ValueError) as exc:
            raise IdentityResolutionIntegrityError(
                "identity resolution request is invalid"
            ) from exc
        sources = validated.source_identities
        if len(sources) < 2 or len({source.entity_type for source in sources}) != 1:
            raise IdentityResolutionIntegrityError(
                "one recalled identity component requires same-type source identities"
            )

        source_ids = tuple(source.source_identity_id for source in sources)
        assertion_ids = tuple(
            assertion.assertion_id for assertion in validated.identity_assertions
        )
        try:
            llm_thresholds = _LLM_AUTO_ACTION_THRESHOLDS[
                validated.identity_method_version
            ]
        except KeyError as exc:
            raise IdentityResolutionIntegrityError(
                "identity resolution method version has no accepted rule set"
            ) from exc
        component_input_sha256 = canonical_identity_adjudication_input_sha256(
            source_identities=sources,
            identity_assertions=validated.identity_assertions,
            current_canonical_identities=validated.current_canonical_identities,
            canonical_identity_history=validated.canonical_identity_history,
            current_source_identity_assignments=(
                validated.current_source_identity_assignments
            ),
            prior_identity_decisions=validated.prior_identity_decisions,
            prior_decision_contexts=validated.prior_decision_contexts,
            policy=validated.policy,
        )
        human_review_resolution = next(iter(validated.human_review_resolutions), None)
        if len(validated.human_review_resolutions) > 1:
            raise IdentityResolutionIntegrityError(
                "one identity component cannot apply multiple human reviews"
            )
        proposed_outcome: IdentityCandidateOutcome | None = None
        matching_strong_key = _matching_strong_key(
            sources, method_version=validated.identity_method_version
        )
        conflicting_strong_key = _conflicting_strong_key(
            sources, method_version=validated.identity_method_version
        )
        matching_composite_keys = _matching_composite_keys(
            sources, method_version=validated.identity_method_version
        )
        if conflicting_strong_key is not None:
            candidate_outcome = IdentityCandidateOutcome.different_entities
            target_groups = _strong_identifier_groups(sources, conflicting_strong_key)
            verdict_groups = target_groups
            reason_codes = ("conflicting_strong_identifier",)
            verdict_method = DecisionMethod.deterministic
            verdict_confidence = 1.0
            verdict_rationale = (
                "Conflicting normalized strong identifiers prove distinct identities."
            )
            verdict_uncertainty = "No material separation uncertainty remains."
            verdict_trace = None
        elif matching_strong_key is not None:
            candidate_outcome = IdentityCandidateOutcome.same_entity
            target_groups = (source_ids,)
            verdict_groups = target_groups
            reason_codes = ("matching_strong_identifier",)
            verdict_method = DecisionMethod.deterministic
            verdict_confidence = 1.0
            verdict_rationale = (
                "Matching normalized strong identifiers prove one identity."
            )
            verdict_uncertainty = "No material identity uncertainty remains."
            verdict_trace = None
        elif matching_composite_keys is not None:
            if human_review_resolution is not None:
                raise IdentityResolutionIntegrityError(
                    "human review cannot override a deterministic identity outcome"
                )
            candidate_outcome = IdentityCandidateOutcome.same_entity
            target_groups = (source_ids,)
            verdict_groups = target_groups
            reason_codes = ("matching_high_confidence_composite",)
            verdict_method = DecisionMethod.composite
            verdict_confidence = 0.99
            verdict_rationale = (
                "The policy-versioned normalized composite identity keys match "
                "exactly across the recalled sources."
            )
            verdict_uncertainty = (
                "No strong public identifier is present; the accepted composite "
                "rule supplies the identity evidence."
            )
            verdict_trace = None
        elif human_review_resolution is not None:
            candidate_outcome = {
                HumanReviewOutcome.same_entity: IdentityCandidateOutcome.same_entity,
                HumanReviewOutcome.different_entities: (
                    IdentityCandidateOutcome.different_entities
                ),
            }[human_review_resolution.outcome]
            target_groups = human_review_resolution.source_identity_groups
            verdict_groups = target_groups
            reason_codes = ("human_review_resolution",)
            verdict_method = DecisionMethod.human_review
            verdict_confidence = human_review_resolution.confidence
            verdict_rationale = human_review_resolution.rationale
            verdict_uncertainty = (
                human_review_resolution.review_case.uncertainty
                or "The named human reviewer resolved the material identity ambiguity."
            )
            verdict_trace = None
        else:
            if self._adjudicator is None:
                candidate_outcome = IdentityCandidateOutcome.unresolved
                target_groups = tuple((source_id,) for source_id in source_ids)
                verdict_groups = target_groups
                reason_codes = ("structured_adjudication_unavailable",)
                verdict_method = DecisionMethod.deterministic
                verdict_confidence = 0.0
                verdict_rationale = (
                    "No strong deterministic identifier or structured adjudication "
                    "was available; candidate identity remains unresolved."
                )
                verdict_uncertainty = (
                    "The sources may represent one entity or distinct entities."
                )
                verdict_trace = None
            else:
                adjudication_request = _IdentityAdjudicationRequest(
                    source_identity_ids=source_ids,
                    assertion_ids=assertion_ids,
                    input_content_sha256=component_input_sha256,
                )
                adjudication = self._adjudicator.adjudicate(adjudication_request)
                proposed_outcome = adjudication.output.verdict
                verdict_groups = adjudication.output.source_identity_groups
                threshold = llm_thresholds.get(proposed_outcome)
                if threshold is not None and adjudication.output.confidence < threshold:
                    candidate_outcome = IdentityCandidateOutcome.unresolved
                    target_groups = tuple((source_id,) for source_id in source_ids)
                    reason_codes = ("below_auto_action_threshold",)
                else:
                    candidate_outcome = proposed_outcome
                    target_groups = verdict_groups
                    reason_codes = ("structured_llm_adjudication",)
                verdict_method = DecisionMethod.structured_llm
                verdict_confidence = adjudication.output.confidence
                verdict_rationale = adjudication.output.rationale
                verdict_uncertainty = adjudication.output.uncertainty
                verdict_trace = adjudication.llm_trace
        provisional_verdict = IdentityCandidateVerdict(
            verdict_id="pending-content-binding",
            component_id=canonical_identity_component_id(
                request=validated,
                source_identity_ids=source_ids,
            ),
            component_input_sha256=component_input_sha256,
            verdict=candidate_outcome,
            proposed_outcome=proposed_outcome,
            source_identity_ids=source_ids,
            source_identity_groups=verdict_groups,
            supporting_assertion_ids=assertion_ids,
            reason_codes=reason_codes,
            method=verdict_method,
            confidence=verdict_confidence,
            rationale=verdict_rationale,
            uncertainty=verdict_uncertainty,
            llm_trace=verdict_trace,
            human_review_resolution=human_review_resolution,
        )
        verdict = provisional_verdict.model_copy(
            update={
                "verdict_id": canonical_identity_candidate_verdict_id(
                    request=validated,
                    verdict=provisional_verdict,
                )
            }
        )
        current_groups = tuple(
            sorted(
                tuple(sorted(identity.source_identity_ids))
                for identity in validated.current_canonical_identities
            )
        )
        if current_groups and current_groups == tuple(sorted(target_groups)):
            return _no_action_component_result(validated, verdict)
        if verdict.verdict is IdentityCandidateOutcome.different_entities:
            return validate_identity_resolution_result(
                validated, _different_new_entities_result(validated, verdict)
            )
        if verdict.verdict is IdentityCandidateOutcome.unresolved:
            return validate_identity_resolution_result(
                validated, _unresolved_identity_result(validated, verdict)
            )

        input_ids = tuple(
            identity.canonical_identity_id
            for identity in validated.current_canonical_identities
        )
        if len(input_ids) == 0:
            action = IdentityAction.create
            output_id = _canonical_identity_id(
                validated.release_id,
                sources[0].entity_type,
                source_ids,
                generation_key=f"create:{verdict.verdict_id}",
            )
        elif len(input_ids) == 1:
            action = IdentityAction.link
            output_id = input_ids[0]
            existing_source_ids = set(
                validated.current_canonical_identities[0].source_identity_ids
            )
            if not existing_source_ids < set(source_ids):
                raise IdentityResolutionIntegrityError(
                    "link requires at least one newly assigned source identity"
                )
        else:
            action = IdentityAction.merge
            output_id = _canonical_identity_id(
                validated.release_id,
                sources[0].entity_type,
                source_ids,
                generation_key=(
                    "merge:" + ",".join(sorted(input_ids)) + f":{verdict.verdict_id}"
                ),
            )
        entity_type = sources[0].entity_type
        decision_id = _decision_id(
            request=validated,
            action=action,
            source_identity_ids=source_ids,
            input_canonical_identity_ids=input_ids,
            output_canonical_identity_ids=(output_id,),
            reversal_of_decision_id=None,
            verdict=verdict,
        )
        record_ids = _supporting_record_ids(sources)
        decision = IdentityDecision(
            decision_id=decision_id,
            action=action,
            source_identity_ids=source_ids,
            input_canonical_identity_ids=input_ids,
            output_canonical_identity_ids=(output_id,),
            supporting_record_ids=record_ids,
            policy=validated.policy,
            method=verdict.method,
            method_version=validated.identity_method_version,
            decision_run_id=validated.decision_run_id,
            confidence=verdict.confidence,
            rationale=verdict.rationale,
            decided_at=validated.as_of,
            llm_trace=verdict.llm_trace,
            human_review_resolution=verdict.human_review_resolution,
        )
        decision = _bind_applied_decision_id(
            decision, candidate_verdict_id=verdict.verdict_id
        )
        decision_id = decision.decision_id
        if action is IdentityAction.link:
            existing = validated.current_canonical_identities[0]
            output = CanonicalIdentity(
                **{
                    **existing.model_dump(mode="python"),
                    "source_identity_ids": source_ids,
                    "identity_decision_id": decision_id,
                }
            )
        else:
            output = CanonicalIdentity(
                canonical_identity_id=output_id,
                entity_type=entity_type,
                state=CanonicalIdentityState.active,
                display_name=_display_name(sources),
                source_identity_ids=source_ids,
                identity_decision_id=decision_id,
                predecessor_identity_ids=input_ids,
                release_id=validated.release_id,
            )
        terminal_history = (
            tuple(
                CanonicalIdentity(
                    **{
                        **identity.model_dump(mode="python"),
                        "state": CanonicalIdentityState.merged,
                        "identity_decision_id": decision_id,
                        "successor_identity_ids": (output_id,),
                    }
                )
                for identity in validated.current_canonical_identities
            )
            if action is IdentityAction.merge
            else ()
        )
        supporting_assertion_ids = tuple(sorted(assertion_ids))
        manifest = IdentityDecisionManifest(
            release_id=validated.release_id,
            decision_id=decision_id,
            candidate_verdict_id=verdict.verdict_id,
            supporting_assertion_ids=supporting_assertion_ids,
            input_content_sha256=canonical_identity_decision_input_sha256(
                request=validated,
                decision=decision,
                supporting_assertion_ids=supporting_assertion_ids,
            ),
        )
        prior_assignment_by_source = {
            assignment.source_identity_id: assignment
            for assignment in validated.current_source_identity_assignments
        }
        assignments = tuple(
            SourceIdentityAssignment(
                release_id=validated.release_id,
                source_identity_id=source_id,
                canonical_identity_id=output_id,
                identity_decision_id=(
                    prior_assignment_by_source[source_id].identity_decision_id
                    if action is IdentityAction.link
                    and source_id in prior_assignment_by_source
                    else decision_id
                ),
            )
            for source_id in source_ids
        )
        content = _IdentityResolutionContent(
            release_id=validated.release_id,
            decision_run_id=validated.decision_run_id,
            identity_method_version=validated.identity_method_version,
            as_of=validated.as_of,
            policy=validated.policy,
            source_identities=sources,
            identity_assertions=validated.identity_assertions,
            candidate_verdicts=(verdict,),
            identity_decisions=(decision,),
            current_canonical_identities=(output,),
            canonical_identity_history=tuple(
                sorted(
                    (*validated.canonical_identity_history, *terminal_history),
                    key=lambda value: value.canonical_identity_id,
                )
            ),
            source_identity_assignments=tuple(
                sorted(assignments, key=lambda value: value.source_identity_id)
            ),
            decision_manifests=(manifest,),
        )
        result = _finalize_identity_result(validated, content)
        return validate_identity_resolution_result(validated, result)


def create_ephemeral_canonical_identity_resolution_engine(
    *, adjudicator: StructuredIdentityAdjudicator | None = None
) -> CanonicalIdentityResolutionEngine:
    """Compose the pure offline identity engine with an optional adjudicator."""

    return _EphemeralCanonicalIdentityResolutionEngine(adjudicator=adjudicator)


__all__ = [
    "CANONICAL_IDENTITY_METHOD_VERSION_V2",
    "CanonicalIdentity",
    "CanonicalIdentityResolutionEngine",
    "CanonicalIdentityResolutionError",
    "IdentityAction",
    "IdentityAdjudicationIntegrityError",
    "IdentityAdjudicationOutputError",
    "IdentityCandidateOutcome",
    "IdentityCandidateVerdict",
    "IdentityDecision",
    "IdentityDecisionContext",
    "IdentityDecisionManifest",
    "IdentityDecisionOutputAllocation",
    "IdentityResolutionIntegrityError",
    "IdentityResolutionRequest",
    "IdentityResolutionResult",
    "PERSON_IDENTITY_METHOD_VERSION",
    "TECHNOLOGY_IDENTITY_METHOD_VERSION",
    "normalize_identity_key_value",
    "HumanReviewOutcome",
    "HumanReviewResolution",
    "PolicyReference",
    "RecordedIdentityAdjudication",
    "ReviewCase",
    "SourceAssertion",
    "SourceIdentity",
    "SourceIdentityAssignment",
    "StructuredIdentityAdjudicator",
    "canonical_identity_adjudication_input_sha256",
    "canonical_identity_applied_decision_id",
    "canonical_identity_candidate_verdict_id",
    "canonical_identity_component_id",
    "canonical_identity_decision_input_sha256",
    "canonical_identity_resolution_result_sha256",
    "canonical_identity_resolution_request_sha256",
    "canonical_identity_rule_set_sha256",
    "create_ephemeral_canonical_identity_resolution_engine",
    "create_human_review_resolution",
    "create_identity_decision_context",
    "create_recorded_structured_identity_adjudicator",
    "identity_decision_context_sha256",
    "validate_identity_resolution_result",
]
