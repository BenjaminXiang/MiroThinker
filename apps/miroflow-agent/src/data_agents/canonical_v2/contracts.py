"""Storage-independent shared contracts for the Canonical V2 knowledge platform."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import math
from enum import Enum
from typing import Annotated, NoReturn, cast

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


def _canonical_utc_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


CanonicalDatetime = Annotated[
    AwareDatetime,
    AfterValidator(_canonical_utc_datetime),
]


class ContractModel(BaseModel):
    """Strict immutable value at the shared Canonical V2 seam."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class ParseStatus(str, Enum):
    parsed = "parsed"
    partial = "partial"
    quarantined = "quarantined"
    unsupported = "unsupported"
    corrupt = "corrupt"


class SourceErrorKind(str, Enum):
    unsupported_format = "unsupported_format"
    corrupt_content = "corrupt_content"
    missing_external_content = "missing_external_content"
    parse_error = "parse_error"
    schema_mismatch = "schema_mismatch"


class DecisionState(str, Enum):
    selected = "selected"
    unresolved = "unresolved"
    rejected = "rejected"
    superseded = "superseded"


class DecisionMethod(str, Enum):
    deterministic = "deterministic"
    structured_llm = "structured_llm"
    human_review = "human_review"
    composite = "composite"


class SourceIdentityState(str, Enum):
    active = "active"
    superseded = "superseded"
    rejected = "rejected"


class CanonicalIdentityState(str, Enum):
    active = "active"
    merged = "merged"
    split_identity = "split"
    rejected = "rejected"


class IdentityAction(str, Enum):
    create = "create"
    link = "link"
    merge = "merge"
    split_identity = "split"
    reject = "reject"
    reverse = "reverse"


class IdentitySpace(str, Enum):
    source = "source"
    canonical = "canonical"


class RelationshipLayer(str, Enum):
    canonical = "canonical"
    derived = "derived"
    session = "session"


class RelationshipDirection(str, Enum):
    directed = "directed"
    undirected = "undirected"


class RoleAppliesTo(str, Enum):
    source = "source"
    target = "target"
    relationship = "relationship"


class TimeSemantics(str, Enum):
    none = "none"
    observed_at = "observed_at"
    event_time = "event_time"
    validity_interval = "validity_interval"
    computed_at = "computed_at"
    session_lifetime = "session_lifetime"


class RelationshipDecisionState(str, Enum):
    accepted = "accepted"
    unresolved = "unresolved"
    rejected = "rejected"
    superseded = "superseded"


class PolicyKind(str, Enum):
    inclusion = "inclusion"
    path_eligibility = "path_eligibility"
    identity = "identity"
    field_selection = "field_selection"
    relationship = "relationship"
    publication = "publication"
    gap = "gap"


class PolicyOutcome(str, Enum):
    admitted = "admitted"
    limited = "limited"
    excluded = "excluded"
    review = "review"


class GapClass(str, Enum):
    knowledge_coverage = "knowledge_coverage"
    identity = "identity"
    source_conflict_freshness = "source_conflict_freshness"
    relationship = "relationship"
    path_reach = "path_reach"
    retrieval_precision = "retrieval_precision"
    context = "context"
    synthesis = "synthesis"
    index_parity = "index_parity"
    provider_availability = "provider_availability"


class GapStatus(str, Enum):
    open = "open"
    in_review = "in_review"
    planned = "planned"
    resolved = "resolved"
    dismissed = "dismissed"


class ReviewState(str, Enum):
    unreviewed = "unreviewed"
    in_review = "in_review"
    accepted = "accepted"
    rejected = "rejected"


class ReviewFamily(str, Enum):
    field = "field"
    relationship = "relationship"
    identity = "identity"


class HumanReviewOutcome(str, Enum):
    selected = "selected"
    accepted = "accepted"
    rejected = "rejected"
    same_entity = "same_entity"
    different_entities = "different_entities"


class GapSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ReleaseState(str, Enum):
    candidate = "candidate"
    verified = "verified"
    accepted = "accepted"
    rejected = "rejected"
    active = "active"
    rolled_back = "rolled_back"
    retired = "retired"


def _validate_interval(
    valid_from: CanonicalDatetime | None,
    valid_to: CanonicalDatetime | None,
) -> None:
    if valid_from is not None and valid_to is not None and valid_from > valid_to:
        raise ValueError("valid_from must not be after valid_to")


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicates")


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, JsonValue]],
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON object keys must be unique; duplicate key: {key!r}")
        result[key] = value
    return result


def _reject_non_finite_json_constant(value: str) -> NoReturn:
    raise ValueError(f"JSON numbers must be finite; {value} is forbidden")


def _require_finite_json(value: JsonValue) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite; NaN and Infinity are forbidden")
    if isinstance(value, list):
        for item in value:
            _require_finite_json(item)
    elif isinstance(value, dict):
        for item in value.values():
            _require_finite_json(item)


def _strict_json_equal(left: JsonValue, right: JsonValue) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _strict_json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _strict_json_equal(left[key], right[key]) for key in left
        )
    return left == right


def _canonical_content_sha256(value: JsonValue) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class EvidenceArtifact(ContractModel):
    artifact_id: NonEmptyStr
    source_kind: NonEmptyStr
    source_locator: NonEmptyStr
    content_sha256: Sha256
    byte_size: NonNegativeInt
    acquired_at: CanonicalDatetime
    run_id: NonEmptyStr
    parent_artifact_id: NonEmptyStr | None = None
    parent_content_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def validate_parent_lineage(self) -> EvidenceArtifact:
        if (self.parent_artifact_id is None) != (self.parent_content_sha256 is None):
            raise ValueError(
                "parent_artifact_id and parent_content_sha256 must be provided together"
            )
        if self.parent_artifact_id == self.artifact_id:
            raise ValueError("parent artifact cannot be the artifact itself")
        return self


class SourceError(ContractModel):
    error_code: NonEmptyStr
    error_kind: SourceErrorKind
    message: NonEmptyStr
    field_path: NonEmptyStr | None = None
    recoverable: bool


class SourceRecord(ContractModel):
    record_id: NonEmptyStr
    artifact_id: NonEmptyStr
    source_batch_id: NonEmptyStr
    record_locator: NonEmptyStr
    parser_name: NonEmptyStr
    parser_version: NonEmptyStr
    schema_version: NonEmptyStr
    parse_run_id: NonEmptyStr
    parse_status: ParseStatus
    payload: dict[NonEmptyStr, JsonValue]
    errors: tuple[SourceError, ...] = ()
    parsed_at: CanonicalDatetime

    @model_validator(mode="after")
    def validate_parse_outcome(self) -> SourceRecord:
        if self.parse_status is not ParseStatus.parsed and not self.errors:
            raise ValueError(
                "a non-parsed source record requires at least one typed error"
            )
        return self


class SourceAssertion(ContractModel):
    assertion_id: NonEmptyStr
    source_record_id: NonEmptyStr
    source_identity_id: NonEmptyStr
    subject_entity_type: NonEmptyStr
    field_path: NonEmptyStr
    value: JsonValue
    observed_at: CanonicalDatetime
    source_event_time: CanonicalDatetime | None = None
    valid_from: CanonicalDatetime | None = None
    valid_to: CanonicalDatetime | None = None
    assertion_run_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_validity(self) -> SourceAssertion:
        _validate_interval(self.valid_from, self.valid_to)
        return self


class PolicyReference(ContractModel):
    policy_id: NonEmptyStr
    policy_version: NonEmptyStr
    policy_kind: PolicyKind
    content_sha256: Sha256
    effective_at: CanonicalDatetime


class LLMDecisionTrace(ContractModel):
    provider: NonEmptyStr
    model: NonEmptyStr
    prompt_version: NonEmptyStr
    schema_version: NonEmptyStr
    input_evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    raw_output_base64: Annotated[str, Field(min_length=1)]
    output_sha256: Sha256
    validated_output: dict[NonEmptyStr, JsonValue]

    @model_validator(mode="after")
    def validate_trace_integrity(self) -> LLMDecisionTrace:
        _require_unique(self.input_evidence_ids, "input_evidence_ids")
        if any(character in " \t\n\v\f\r" for character in self.raw_output_base64):
            raise ValueError("raw_output_base64 must not contain ASCII whitespace")
        try:
            raw_output = base64.b64decode(self.raw_output_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("raw_output_base64 must be valid base64") from exc
        if base64.b64encode(raw_output).decode("ascii") != self.raw_output_base64:
            raise ValueError("raw_output_base64 must use canonical base64 padding")
        if hashlib.sha256(raw_output).hexdigest() != self.output_sha256:
            raise ValueError(
                "output_sha256 must be the SHA-256 of the exact raw output"
            )
        try:
            raw_text = raw_output.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("raw output must be strict UTF-8") from exc
        try:
            parsed_output: JsonValue = json.loads(
                raw_text,
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_non_finite_json_constant,
            )
        except json.JSONDecodeError as exc:
            raise ValueError("raw output must be valid JSON") from exc
        if not isinstance(parsed_output, dict):
            raise ValueError("raw output JSON must be an object")
        _require_finite_json(self.validated_output)
        if not _strict_json_equal(parsed_output, self.validated_output):
            raise ValueError("decoded raw output must equal validated_output")
        return self


class _ReviewCaseContent(ContractModel):
    family: ReviewFamily
    release_id: NonEmptyStr
    decision_run_id: NonEmptyStr
    subject_id: NonEmptyStr
    path: NonEmptyStr
    originating_record_id: NonEmptyStr
    candidate_evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    conflicting_evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=2)
    source_identity_ids: tuple[NonEmptyStr, ...] = ()
    policy: PolicyReference
    method: DecisionMethod
    method_version: NonEmptyStr
    confidence: Confidence
    rationale: NonEmptyStr
    uncertainty: NonEmptyStr | None = None
    reason_codes: tuple[NonEmptyStr, ...] = ()
    trace_content_sha256: Sha256 | None = None
    input_content_sha256: Sha256
    created_at: CanonicalDatetime

    @field_validator("confidence")
    @classmethod
    def normalize_confidence_zero(cls, value: float) -> float:
        return 0.0 if value == 0.0 else value

    @field_validator(
        "candidate_evidence_ids",
        "conflicting_evidence_ids",
        "source_identity_ids",
        "reason_codes",
    )
    @classmethod
    def normalize_review_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(values, "review case values")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_review_shape(self) -> _ReviewCaseContent:
        if not set(self.conflicting_evidence_ids) <= set(self.candidate_evidence_ids):
            raise ValueError(
                "review case conflicting evidence must be candidate evidence"
            )
        expected_policy_kind = {
            ReviewFamily.field: PolicyKind.field_selection,
            ReviewFamily.relationship: PolicyKind.relationship,
            ReviewFamily.identity: PolicyKind.identity,
        }[self.family]
        if self.policy.policy_kind is not expected_policy_kind:
            raise ValueError("review case family must match its policy kind")
        if self.family is ReviewFamily.identity:
            if len(self.source_identity_ids) < 2:
                raise ValueError(
                    "identity review case requires multiple source identities"
                )
        elif self.source_identity_ids:
            raise ValueError(
                "field and relationship review cases cannot carry source identities"
            )
        if self.method is DecisionMethod.structured_llm:
            if self.trace_content_sha256 is None:
                raise ValueError(
                    "structured LLM review case requires its trace content hash"
                )
        elif self.trace_content_sha256 is not None:
            raise ValueError(
                "non-LLM review case cannot carry a structured trace content hash"
            )
        return self


class ReviewCase(_ReviewCaseContent):
    review_case_id: NonEmptyStr
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_content_binding(self) -> ReviewCase:
        expected = review_case_content_sha256(self)
        if self.content_sha256 != expected:
            raise ValueError("review case content hash mismatch")
        if self.review_case_id != f"review-case:sha256:{expected}":
            raise ValueError("review case ID must bind its exact content hash")
        return self


def review_case_content_sha256(case: ReviewCase | _ReviewCaseContent) -> str:
    payload = case.model_dump(mode="json")
    payload.pop("review_case_id", None)
    payload.pop("content_sha256", None)
    return _canonical_content_sha256(cast(JsonValue, payload))


def create_review_case(**values: object) -> ReviewCase:
    content = _ReviewCaseContent.model_validate(values)
    content_sha256 = review_case_content_sha256(content)
    return ReviewCase(
        **content.model_dump(mode="python"),
        review_case_id=f"review-case:sha256:{content_sha256}",
        content_sha256=content_sha256,
    )


class _HumanReviewResolutionContent(ContractModel):
    review_case: ReviewCase
    outcome: HumanReviewOutcome
    selected_evidence_ids: tuple[NonEmptyStr, ...] = ()
    role_bindings: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)
    source_identity_groups: tuple[tuple[NonEmptyStr, ...], ...] = ()
    reviewer_id: NonEmptyStr
    review_policy_id: NonEmptyStr
    review_policy_version: NonEmptyStr
    review_policy_content_sha256: Sha256
    reviewed_at: CanonicalDatetime
    rationale: NonEmptyStr
    confidence: Confidence

    @field_validator("confidence")
    @classmethod
    def normalize_confidence_zero(cls, value: float) -> float:
        return 0.0 if value == 0.0 else value

    @field_validator("selected_evidence_ids")
    @classmethod
    def normalize_selected_evidence_ids(
        cls, values: tuple[str, ...]
    ) -> tuple[str, ...]:
        _require_unique(values, "human review selected evidence IDs")
        return tuple(sorted(values))

    @field_validator("source_identity_groups")
    @classmethod
    def normalize_source_identity_groups(
        cls, groups: tuple[tuple[str, ...], ...]
    ) -> tuple[tuple[str, ...], ...]:
        normalized = tuple(tuple(sorted(group)) for group in groups)
        if any(not group for group in normalized):
            raise ValueError("human review source identity groups cannot be empty")
        flattened = tuple(source_id for group in normalized for source_id in group)
        _require_unique(flattened, "human review grouped source identity IDs")
        return tuple(sorted(normalized))

    @field_validator("role_bindings")
    @classmethod
    def normalize_role_bindings(cls, values: dict[str, str]) -> dict[str, str]:
        return {key: values[key] for key in sorted(values)}

    @model_validator(mode="after")
    def validate_review_outcome(self) -> _HumanReviewResolutionContent:
        if self.reviewed_at < self.review_case.created_at:
            raise ValueError("human review cannot predate its review case")
        if not set(self.selected_evidence_ids) <= set(
            self.review_case.candidate_evidence_ids
        ):
            raise ValueError(
                "human review may select only exact review-case candidate evidence"
            )
        if self.review_case.family is ReviewFamily.field:
            if self.outcome not in {
                HumanReviewOutcome.selected,
                HumanReviewOutcome.rejected,
            }:
                raise ValueError("field review requires selected or rejected outcome")
            if self.outcome is HumanReviewOutcome.selected:
                if not self.selected_evidence_ids:
                    raise ValueError("selected field review requires evidence")
            elif self.selected_evidence_ids:
                raise ValueError("rejected field review cannot select evidence")
            if self.role_bindings or self.source_identity_groups:
                raise ValueError(
                    "field review cannot carry roles or source identity groups"
                )
        elif self.review_case.family is ReviewFamily.relationship:
            if self.outcome not in {
                HumanReviewOutcome.accepted,
                HumanReviewOutcome.rejected,
            }:
                raise ValueError(
                    "relationship review requires accepted or rejected outcome"
                )
            if self.outcome is HumanReviewOutcome.accepted:
                if not self.selected_evidence_ids or not self.role_bindings:
                    raise ValueError(
                        "accepted relationship review requires evidence and roles"
                    )
            elif self.selected_evidence_ids or self.role_bindings:
                raise ValueError(
                    "rejected relationship review cannot select evidence or roles"
                )
            if self.source_identity_groups:
                raise ValueError(
                    "relationship review cannot carry source identity groups"
                )
        else:
            if self.outcome not in {
                HumanReviewOutcome.same_entity,
                HumanReviewOutcome.different_entities,
            }:
                raise ValueError(
                    "identity review requires same_entity or different_entities outcome"
                )
            if self.selected_evidence_ids or self.role_bindings:
                raise ValueError(
                    "identity review cannot carry selected field evidence or roles"
                )
            flattened = tuple(
                source_id
                for group in self.source_identity_groups
                for source_id in group
            )
            if set(flattened) != set(self.review_case.source_identity_ids):
                raise ValueError(
                    "identity review groups must partition the exact case sources"
                )
            if (
                self.outcome is HumanReviewOutcome.same_entity
                and len(self.source_identity_groups) != 1
            ):
                raise ValueError("same_entity review requires one source group")
            if (
                self.outcome is HumanReviewOutcome.different_entities
                and len(self.source_identity_groups) < 2
            ):
                raise ValueError(
                    "different_entities review requires multiple source groups"
                )
        return self


class HumanReviewResolution(_HumanReviewResolutionContent):
    resolution_id: NonEmptyStr
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_content_binding(self) -> HumanReviewResolution:
        expected = human_review_resolution_content_sha256(self)
        if self.content_sha256 != expected:
            raise ValueError("human review resolution content hash mismatch")
        if self.resolution_id != f"human-review-resolution:sha256:{expected}":
            raise ValueError(
                "human review resolution ID must bind its exact content hash"
            )
        return self


def human_review_resolution_content_sha256(
    resolution: HumanReviewResolution | _HumanReviewResolutionContent,
) -> str:
    payload = resolution.model_dump(mode="json")
    payload.pop("resolution_id", None)
    payload.pop("content_sha256", None)
    return _canonical_content_sha256(cast(JsonValue, payload))


def create_human_review_resolution(**values: object) -> HumanReviewResolution:
    content = _HumanReviewResolutionContent.model_validate(values)
    content_sha256 = human_review_resolution_content_sha256(content)
    return HumanReviewResolution(
        **content.model_dump(mode="python"),
        resolution_id=f"human-review-resolution:sha256:{content_sha256}",
        content_sha256=content_sha256,
    )


class CanonicalDecision(ContractModel):
    decision_id: NonEmptyStr
    canonical_identity_id: NonEmptyStr
    field_path: NonEmptyStr
    state: DecisionState
    candidate_assertion_ids: tuple[NonEmptyStr, ...]
    selected_assertion_ids: tuple[NonEmptyStr, ...] = ()
    conflicting_assertion_ids: tuple[NonEmptyStr, ...] = ()
    policy: PolicyReference
    method: DecisionMethod
    method_version: NonEmptyStr
    decision_run_id: NonEmptyStr
    confidence: Confidence
    rationale: NonEmptyStr
    llm_trace: LLMDecisionTrace | None = None
    release_id: NonEmptyStr
    decided_at: CanonicalDatetime
    supersedes_decision_id: NonEmptyStr | None = None
    human_review_resolution: HumanReviewResolution | None = None

    @model_validator(mode="after")
    def validate_decision_evidence(self) -> CanonicalDecision:
        candidates = set(self.candidate_assertion_ids)
        _require_unique(self.candidate_assertion_ids, "candidate_assertion_ids")
        _require_unique(self.selected_assertion_ids, "selected_assertion_ids")
        _require_unique(self.conflicting_assertion_ids, "conflicting_assertion_ids")
        if set(self.selected_assertion_ids) & set(self.conflicting_assertion_ids):
            raise ValueError("selected and conflicting assertion IDs must be disjoint")
        if not set(self.selected_assertion_ids) <= candidates:
            raise ValueError("selected assertion IDs must be candidate assertions")
        if not set(self.conflicting_assertion_ids) <= candidates:
            raise ValueError("conflicting assertion IDs must be candidate assertions")
        if not self.candidate_assertion_ids:
            if (
                self.state is not DecisionState.unresolved
                or self.method is not DecisionMethod.deterministic
                or self.selected_assertion_ids
                or self.conflicting_assertion_ids
                or self.llm_trace is not None
            ):
                raise ValueError(
                    "empty candidates require an unresolved deterministic decision "
                    "with no selected/conflicting assertions or LLM trace"
                )
        if self.state is DecisionState.selected and not self.selected_assertion_ids:
            raise ValueError("selected decision requires a selected assertion")
        if self.state is DecisionState.unresolved:
            if self.selected_assertion_ids:
                raise ValueError(
                    "unresolved decision cannot select a canonical assertion"
                )
            if self.candidate_assertion_ids and len(self.conflicting_assertion_ids) < 2:
                raise ValueError(
                    "unresolved decision requires at least two conflicting assertions"
                )
        if self.state is DecisionState.rejected and self.selected_assertion_ids:
            raise ValueError("rejected decision cannot select an assertion")
        if self.state is DecisionState.superseded:
            if (
                self.selected_assertion_ids
                or self.conflicting_assertion_ids
                or self.supersedes_decision_id is None
            ):
                raise ValueError(
                    "superseded withdrawal requires prior lineage and no selected or "
                    "conflicting evidence"
                )
        if self.policy.policy_kind is not PolicyKind.field_selection:
            raise ValueError("canonical decision requires a field-selection policy")
        if self.method is DecisionMethod.structured_llm:
            if self.llm_trace is None:
                raise ValueError(
                    "structured_llm decision requires an LLM decision trace"
                )
            if not self.candidate_assertion_ids:
                raise ValueError(
                    "structured_llm decision requires candidate assertions"
                )
            if self.llm_trace.input_evidence_ids != self.candidate_assertion_ids:
                raise ValueError(
                    "LLM trace input_evidence_ids must exactly equal candidate_assertion_ids"
                )
        if self.supersedes_decision_id == self.decision_id:
            raise ValueError("canonical decision cannot supersede itself")
        if self.method is DecisionMethod.human_review:
            resolution = self.human_review_resolution
            if resolution is None:
                raise ValueError(
                    "human_review canonical decision requires a bound resolution"
                )
            if (
                resolution.review_case.family is not ReviewFamily.field
                or self.supersedes_decision_id
                != resolution.review_case.originating_record_id
                or self.selected_assertion_ids != resolution.selected_evidence_ids
                or (
                    resolution.outcome is HumanReviewOutcome.selected
                    and self.state is not DecisionState.selected
                )
                or (
                    resolution.outcome is HumanReviewOutcome.rejected
                    and self.state is not DecisionState.rejected
                )
            ):
                raise ValueError(
                    "human review field decision must exactly apply its resolution"
                )
            if self.llm_trace is not None:
                raise ValueError("human review decision cannot carry an LLM trace")
        elif self.human_review_resolution is not None:
            raise ValueError(
                "non-human canonical decision cannot carry a review resolution"
            )
        return self


class SourceIdentity(ContractModel):
    source_identity_id: NonEmptyStr
    source_system: NonEmptyStr
    source_key: NonEmptyStr
    entity_type: NonEmptyStr
    source_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    normalized_keys: dict[NonEmptyStr, NonEmptyStr]
    first_observed_at: CanonicalDatetime
    last_observed_at: CanonicalDatetime
    state: SourceIdentityState

    @model_validator(mode="after")
    def validate_observation_window(self) -> SourceIdentity:
        if self.first_observed_at > self.last_observed_at:
            raise ValueError("first_observed_at must not be after last_observed_at")
        _require_unique(self.source_record_ids, "source_record_ids")
        return self


class CanonicalIdentity(ContractModel):
    canonical_identity_id: NonEmptyStr
    entity_type: NonEmptyStr
    state: CanonicalIdentityState
    display_name: NonEmptyStr | None = None
    source_identity_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    identity_decision_id: NonEmptyStr
    predecessor_identity_ids: tuple[NonEmptyStr, ...] = ()
    successor_identity_ids: tuple[NonEmptyStr, ...] = ()
    release_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_lifecycle_lineage(self) -> CanonicalIdentity:
        _require_unique(self.source_identity_ids, "source_identity_ids")
        _require_unique(self.predecessor_identity_ids, "predecessor_identity_ids")
        _require_unique(self.successor_identity_ids, "successor_identity_ids")
        if (
            self.state is CanonicalIdentityState.merged
            and not self.successor_identity_ids
        ):
            raise ValueError("merged identity requires successor identity lineage")
        if (
            self.state is CanonicalIdentityState.split_identity
            and len(self.successor_identity_ids) < 2
        ):
            raise ValueError(
                "split identity requires at least two successor identities"
            )
        return self


class IdentityDecision(ContractModel):
    decision_id: NonEmptyStr
    action: IdentityAction
    source_identity_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    input_canonical_identity_ids: tuple[NonEmptyStr, ...] = ()
    output_canonical_identity_ids: tuple[NonEmptyStr, ...] = ()
    supporting_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    policy: PolicyReference
    method: DecisionMethod
    method_version: NonEmptyStr
    decision_run_id: NonEmptyStr
    confidence: Confidence
    rationale: NonEmptyStr
    decided_at: CanonicalDatetime
    reversal_of_decision_id: NonEmptyStr | None = None
    llm_trace: LLMDecisionTrace | None = None
    human_review_resolution: HumanReviewResolution | None = None

    @model_validator(mode="after")
    def validate_action_shape(self) -> IdentityDecision:
        _require_unique(self.source_identity_ids, "source_identity_ids")
        _require_unique(
            self.input_canonical_identity_ids, "input_canonical_identity_ids"
        )
        _require_unique(
            self.output_canonical_identity_ids, "output_canonical_identity_ids"
        )
        _require_unique(self.supporting_record_ids, "supporting_record_ids")
        if self.policy.policy_kind is not PolicyKind.identity:
            raise ValueError("identity decision requires an identity policy")
        if self.action in {IdentityAction.create, IdentityAction.link}:
            if len(self.output_canonical_identity_ids) != 1:
                raise ValueError(f"{self.action.value} requires one output identity")
        elif self.action is IdentityAction.merge:
            if len(self.input_canonical_identity_ids) < 2:
                raise ValueError(
                    "merge requires at least two input canonical identities"
                )
            if len(self.output_canonical_identity_ids) != 1:
                raise ValueError("merge requires exactly one output canonical identity")
        elif self.action is IdentityAction.split_identity:
            if len(self.input_canonical_identity_ids) != 1:
                raise ValueError("split requires exactly one input canonical identity")
            if len(self.output_canonical_identity_ids) < 2:
                raise ValueError(
                    "split requires at least two output canonical identities"
                )
        elif self.action is IdentityAction.reject:
            if self.output_canonical_identity_ids:
                raise ValueError("reject cannot create an output canonical identity")
        elif self.action is IdentityAction.reverse:
            if self.reversal_of_decision_id is None:
                raise ValueError("reverse requires reversal_of_decision_id")
            if (
                not self.input_canonical_identity_ids
                or not self.output_canonical_identity_ids
            ):
                raise ValueError("reverse requires input and output identity lineage")
        if self.method is DecisionMethod.structured_llm and self.llm_trace is None:
            raise ValueError("structured_llm identity decision requires an LLM trace")
        if self.reversal_of_decision_id == self.decision_id:
            raise ValueError("identity decision cannot reverse itself")
        if self.method is DecisionMethod.human_review:
            resolution = self.human_review_resolution
            if resolution is None:
                raise ValueError(
                    "human_review identity decision requires a bound resolution"
                )
            decision_sources = tuple(sorted(self.source_identity_ids))
            exact_sources = resolution.review_case.source_identity_ids
            applies_exact_partition = (
                resolution.outcome is HumanReviewOutcome.same_entity
                and decision_sources == exact_sources
                and self.action
                in {IdentityAction.create, IdentityAction.link, IdentityAction.merge}
            ) or (
                resolution.outcome is HumanReviewOutcome.different_entities
                and (
                    (
                        self.action is IdentityAction.create
                        and decision_sources in resolution.source_identity_groups
                    )
                    or (
                        self.action
                        in {IdentityAction.split_identity, IdentityAction.reverse}
                        and decision_sources == exact_sources
                    )
                )
            )
            if (
                resolution.review_case.family is not ReviewFamily.identity
                or not applies_exact_partition
                or self.llm_trace is not None
            ):
                raise ValueError(
                    "human review identity decision must exactly apply its resolution"
                )
        elif self.human_review_resolution is not None:
            raise ValueError(
                "non-human identity decision cannot carry a review resolution"
            )
        return self


class RelationshipRole(ContractModel):
    role_id: NonEmptyStr
    applies_to: RoleAppliesTo
    description: NonEmptyStr
    required: bool


class RelationshipType(ContractModel):
    relationship_type_id: NonEmptyStr
    version: NonEmptyStr
    layer: RelationshipLayer
    source_entity_types: tuple[NonEmptyStr, ...] = Field(min_length=1)
    target_entity_types: tuple[NonEmptyStr, ...] = Field(min_length=1)
    direction: RelationshipDirection
    roles: tuple[RelationshipRole, ...] = ()
    required_evidence_kinds: tuple[NonEmptyStr, ...] = ()
    time_semantics: TimeSemantics
    allowed_states: tuple[NonEmptyStr, ...] = Field(min_length=1)
    eligible_paths: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_layer_evidence(self) -> RelationshipType:
        _require_unique(self.source_entity_types, "source_entity_types")
        _require_unique(self.target_entity_types, "target_entity_types")
        _require_unique(self.required_evidence_kinds, "required_evidence_kinds")
        _require_unique(self.allowed_states, "allowed_states")
        _require_unique(self.eligible_paths, "eligible_paths")
        if (
            self.layer is RelationshipLayer.canonical
            and not self.required_evidence_kinds
        ):
            raise ValueError("canonical relationship type requires source evidence")
        if (
            self.layer in {RelationshipLayer.derived, RelationshipLayer.session}
            and self.required_evidence_kinds
        ):
            raise ValueError(
                f"{self.layer.value} relationship type cannot require source evidence"
            )
        return self


class IdentityReference(ContractModel):
    identity_id: NonEmptyStr
    identity_space: IdentitySpace
    entity_type: NonEmptyStr


class RelationshipAssertion(ContractModel):
    assertion_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    relationship_type_version: NonEmptyStr
    source_record_id: NonEmptyStr
    source_endpoint: IdentityReference
    target_endpoint: IdentityReference
    attributes: dict[NonEmptyStr, JsonValue]
    observed_at: CanonicalDatetime
    source_event_time: CanonicalDatetime | None = None
    valid_from: CanonicalDatetime | None = None
    valid_to: CanonicalDatetime | None = None
    assertion_run_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_validity(self) -> RelationshipAssertion:
        if (
            self.source_endpoint.identity_space is not IdentitySpace.source
            or self.target_endpoint.identity_space is not IdentitySpace.source
        ):
            raise ValueError(
                "source-grounded relationship assertions require source identities"
            )
        _validate_interval(self.valid_from, self.valid_to)
        return self


class RelationshipDecision(ContractModel):
    decision_id: NonEmptyStr
    canonical_relationship_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    relationship_type_version: NonEmptyStr
    source_canonical_identity_id: NonEmptyStr
    target_canonical_identity_id: NonEmptyStr
    state: RelationshipDecisionState
    candidate_assertion_ids: tuple[NonEmptyStr, ...]
    selected_assertion_ids: tuple[NonEmptyStr, ...] = ()
    conflicting_assertion_ids: tuple[NonEmptyStr, ...] = ()
    role_bindings: dict[NonEmptyStr, NonEmptyStr]
    policy: PolicyReference
    method: DecisionMethod
    method_version: NonEmptyStr
    decision_run_id: NonEmptyStr
    confidence: Confidence
    rationale: NonEmptyStr
    valid_from: CanonicalDatetime | None = None
    valid_to: CanonicalDatetime | None = None
    release_id: NonEmptyStr
    decided_at: CanonicalDatetime
    supersedes_decision_id: NonEmptyStr | None = None
    llm_trace: LLMDecisionTrace | None = None
    human_review_resolution: HumanReviewResolution | None = None

    @model_validator(mode="after")
    def validate_decision_evidence(self) -> RelationshipDecision:
        candidates = set(self.candidate_assertion_ids)
        _require_unique(self.candidate_assertion_ids, "candidate_assertion_ids")
        _require_unique(self.selected_assertion_ids, "selected_assertion_ids")
        _require_unique(self.conflicting_assertion_ids, "conflicting_assertion_ids")
        if set(self.selected_assertion_ids) & set(self.conflicting_assertion_ids):
            raise ValueError(
                "selected and conflicting relationship assertion IDs must be disjoint"
            )
        if not set(self.selected_assertion_ids) <= candidates:
            raise ValueError("selected relationship assertions must be candidates")
        if not set(self.conflicting_assertion_ids) <= candidates:
            raise ValueError("conflicting relationship assertions must be candidates")
        if not self.candidate_assertion_ids:
            if (
                self.state is not RelationshipDecisionState.unresolved
                or self.method is not DecisionMethod.deterministic
                or self.selected_assertion_ids
                or self.conflicting_assertion_ids
                or self.role_bindings
                or self.llm_trace is not None
            ):
                raise ValueError(
                    "empty candidates require an unresolved deterministic relationship "
                    "with no roles, selected/conflicting assertions, or LLM trace"
                )
        if (
            self.state is RelationshipDecisionState.accepted
            and not self.selected_assertion_ids
        ):
            raise ValueError("accepted relationship requires a selected assertion")
        if self.state is RelationshipDecisionState.unresolved:
            if self.selected_assertion_ids:
                raise ValueError("unresolved relationship cannot select an assertion")
            if self.candidate_assertion_ids and len(self.conflicting_assertion_ids) < 2:
                raise ValueError(
                    "unresolved relationship requires at least two conflicting assertions"
                )
        if (
            self.state is RelationshipDecisionState.rejected
            and self.selected_assertion_ids
        ):
            raise ValueError("rejected relationship cannot select an assertion")
        if self.state is RelationshipDecisionState.superseded:
            if (
                self.selected_assertion_ids
                or self.conflicting_assertion_ids
                or self.role_bindings
                or self.valid_from is not None
                or self.valid_to is not None
                or self.supersedes_decision_id is None
            ):
                raise ValueError(
                    "superseded relationship withdrawal requires prior lineage and no "
                    "selected evidence, conflicts, roles, or validity"
                )
        if self.policy.policy_kind is not PolicyKind.relationship:
            raise ValueError("relationship decision requires a relationship policy")
        if self.method is DecisionMethod.structured_llm:
            if self.llm_trace is None:
                raise ValueError(
                    "structured_llm relationship decision requires an LLM trace"
                )
            if not self.candidate_assertion_ids:
                raise ValueError(
                    "structured_llm relationship decision requires candidate assertions"
                )
            if self.llm_trace.input_evidence_ids != self.candidate_assertion_ids:
                raise ValueError(
                    "LLM trace input_evidence_ids must exactly equal candidate_assertion_ids"
                )
        if self.supersedes_decision_id == self.decision_id:
            raise ValueError("relationship decision cannot supersede itself")
        if self.method is DecisionMethod.human_review:
            resolution = self.human_review_resolution
            if resolution is None:
                raise ValueError(
                    "human_review relationship decision requires a bound resolution"
                )
            if (
                resolution.review_case.family is not ReviewFamily.relationship
                or self.supersedes_decision_id
                != resolution.review_case.originating_record_id
                or self.selected_assertion_ids != resolution.selected_evidence_ids
                or self.role_bindings != resolution.role_bindings
                or (
                    resolution.outcome is HumanReviewOutcome.accepted
                    and self.state is not RelationshipDecisionState.accepted
                )
                or (
                    resolution.outcome is HumanReviewOutcome.rejected
                    and self.state is not RelationshipDecisionState.rejected
                )
            ):
                raise ValueError(
                    "human review relationship decision must exactly apply its resolution"
                )
            if self.llm_trace is not None:
                raise ValueError("human review decision cannot carry an LLM trace")
        elif self.human_review_resolution is not None:
            raise ValueError(
                "non-human relationship decision cannot carry a review resolution"
            )
        _validate_interval(self.valid_from, self.valid_to)
        return self


class DerivedRelationship(ContractModel):
    derived_relationship_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    release_id: NonEmptyStr
    source_canonical_identity_id: NonEmptyStr
    target_canonical_identity_id: NonEmptyStr
    computation_version: NonEmptyStr
    input_content_sha256: tuple[Sha256, ...] = Field(min_length=1)
    score: float | None = None
    computed_at: CanonicalDatetime


class SessionRelationship(ContractModel):
    session_relationship_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    session_id: NonEmptyStr
    turn_id: NonEmptyStr
    release_id: NonEmptyStr
    source_reference: NonEmptyStr
    target_reference: NonEmptyStr
    created_at: CanonicalDatetime
    expires_at: CanonicalDatetime | None = None

    @model_validator(mode="after")
    def validate_lifetime(self) -> SessionRelationship:
        if self.expires_at is not None and self.created_at > self.expires_at:
            raise ValueError("created_at must not be after expires_at")
        return self


class PolicyDecision(ContractModel):
    decision_id: NonEmptyStr
    policy: PolicyReference
    subject_identity_id: NonEmptyStr
    release_id: NonEmptyStr
    path: NonEmptyStr | None = None
    outcome: PolicyOutcome
    score: Confidence | None = None
    limitations: tuple[NonEmptyStr, ...] = ()
    hard_exclusion_codes: tuple[NonEmptyStr, ...] = ()
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = ()
    evaluated_at: CanonicalDatetime

    @model_validator(mode="after")
    def validate_policy_effect(self) -> PolicyDecision:
        _require_unique(self.limitations, "limitations")
        _require_unique(self.hard_exclusion_codes, "hard_exclusion_codes")
        _require_unique(self.supporting_assertion_ids, "supporting_assertion_ids")
        if self.policy.policy_kind is PolicyKind.path_eligibility and self.path is None:
            raise ValueError("path eligibility decision requires a named path")
        if self.policy.policy_kind is PolicyKind.inclusion and self.path is not None:
            raise ValueError("inclusion decision must not be a path decision")
        if self.outcome is PolicyOutcome.limited and not self.limitations:
            raise ValueError("limited policy decision requires a visible limitation")
        if self.outcome is PolicyOutcome.excluded and not self.hard_exclusion_codes:
            raise ValueError("excluded policy decision requires a named hard exclusion")
        if self.outcome is not PolicyOutcome.excluded and self.hard_exclusion_codes:
            raise ValueError("only excluded policy decisions may carry hard exclusions")
        return self


class KnowledgeGap(ContractModel):
    gap_id: NonEmptyStr
    gap_class: GapClass
    status: GapStatus
    release_id: NonEmptyStr
    affected_domains: tuple[NonEmptyStr, ...] = Field(min_length=1)
    affected_paths: tuple[NonEmptyStr, ...] = ()
    query_trace_id: NonEmptyStr | None = None
    answer_trace_id: NonEmptyStr | None = None
    benchmark_case_id: NonEmptyStr | None = None
    telemetry_key: NonEmptyStr | None = None
    observed_symptom: NonEmptyStr
    evidence_ids: tuple[NonEmptyStr, ...] = ()
    classification_confidence: Confidence
    review_state: ReviewState
    proposed_owner: NonEmptyStr
    proposed_remediation: NonEmptyStr
    demand_count: NonNegativeInt
    scenario_families: tuple[NonEmptyStr, ...] = ()
    severity: GapSeverity
    created_at: CanonicalDatetime
    updated_at: CanonicalDatetime
    resolved_release_id: NonEmptyStr | None = None
    resolved_release_state: ReleaseState | None = None
    resolution_verification_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_gap_lifecycle(self) -> KnowledgeGap:
        if not any(
            (
                self.query_trace_id,
                self.answer_trace_id,
                self.benchmark_case_id,
                self.telemetry_key,
            )
        ):
            raise ValueError(
                "knowledge gap requires a query, answer, benchmark, or telemetry trace"
            )
        if self.created_at > self.updated_at:
            raise ValueError("created_at must not be after updated_at")
        _require_unique(self.affected_domains, "affected_domains")
        _require_unique(self.affected_paths, "affected_paths")
        _require_unique(self.evidence_ids, "evidence_ids")
        _require_unique(self.scenario_families, "scenario_families")
        _require_unique(self.resolution_verification_ids, "resolution_verification_ids")
        if self.status is GapStatus.resolved:
            if (
                self.resolved_release_id is None
                or self.resolved_release_state
                not in {ReleaseState.accepted, ReleaseState.active}
                or not self.resolution_verification_ids
                or self.review_state is not ReviewState.accepted
            ):
                raise ValueError(
                    "resolved knowledge gap requires an accepted release and "
                    "verification evidence"
                )
        elif (
            self.resolved_release_id is not None
            or self.resolved_release_state is not None
            or self.resolution_verification_ids
        ):
            raise ValueError(
                "unresolved knowledge gap cannot carry resolution evidence"
            )
        return self


class ManifestSection(ContractModel):
    section_id: NonEmptyStr
    release_id: NonEmptyStr
    version: NonEmptyStr
    record_count: NonNegativeInt
    content_sha256: Sha256


class ProjectionManifest(ContractModel):
    projection_id: NonEmptyStr
    release_id: NonEmptyStr
    projection_kind: NonEmptyStr
    domain: NonEmptyStr
    path: NonEmptyStr | None = None
    projection_version: NonEmptyStr
    record_count: NonNegativeInt
    content_sha256: Sha256


class IndexProjectionManifest(ContractModel):
    projection_id: NonEmptyStr
    release_id: NonEmptyStr
    domain: NonEmptyStr
    path: NonEmptyStr
    projection_version: NonEmptyStr
    schema_version: NonEmptyStr
    embedding_model: NonEmptyStr
    eligibility_policy_version: NonEmptyStr
    point_count: NonNegativeInt
    entity_ids_sha256: Sha256
    content_sha256: Sha256
    full_rebuild: bool


class BuildManifest(ContractModel):
    manifest_version: NonEmptyStr
    release_id: NonEmptyStr
    build_run_id: NonEmptyStr
    source_batch_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_batches_sha256: Sha256
    parser_versions: dict[NonEmptyStr, NonEmptyStr] = Field(min_length=1)
    policy_versions: dict[NonEmptyStr, NonEmptyStr] = Field(min_length=1)
    model_versions: dict[NonEmptyStr, NonEmptyStr]
    decision_set: ManifestSection
    object_sets: tuple[ManifestSection, ...] = Field(min_length=1)
    relationship_set: ManifestSection
    eligibility_sets: tuple[ManifestSection, ...] = Field(min_length=1)
    published_projections: tuple[ProjectionManifest, ...] = Field(min_length=1)
    expected_index_projections: tuple[IndexProjectionManifest, ...] = Field(
        min_length=1
    )
    created_at: CanonicalDatetime
    manifest_sha256: Sha256

    @model_validator(mode="after")
    def validate_one_release(self) -> BuildManifest:
        _require_unique(self.source_batch_ids, "source_batch_ids")
        sections: tuple[
            ManifestSection | ProjectionManifest | IndexProjectionManifest, ...
        ] = (
            self.decision_set,
            *self.object_sets,
            self.relationship_set,
            *self.eligibility_sets,
            *self.published_projections,
            *self.expected_index_projections,
        )
        if any(section.release_id != self.release_id for section in sections):
            raise ValueError("all manifest sections must identify one release")
        projection_ids = tuple(
            projection.projection_id
            for projection in (
                *self.published_projections,
                *self.expected_index_projections,
            )
        )
        _require_unique(projection_ids, "projection_ids")
        return self


class CandidateRelease(ContractModel):
    release_id: NonEmptyStr
    run_id: NonEmptyStr
    state: ReleaseState
    source_batch_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    parser_versions: dict[NonEmptyStr, NonEmptyStr] = Field(min_length=1)
    policy_versions: dict[NonEmptyStr, NonEmptyStr] = Field(min_length=1)
    model_versions: dict[NonEmptyStr, NonEmptyStr]
    manifest_sha256: Sha256
    object_counts: dict[NonEmptyStr, NonNegativeInt] = Field(min_length=1)
    relationship_count: NonNegativeInt
    active_release_changed: bool

    @model_validator(mode="after")
    def validate_candidate_isolation(self) -> CandidateRelease:
        if self.state not in {
            ReleaseState.candidate,
            ReleaseState.verified,
            ReleaseState.accepted,
            ReleaseState.rejected,
        }:
            raise ValueError("candidate release has an invalid pre-publication state")
        if self.active_release_changed:
            raise ValueError("candidate construction cannot change the active release")
        _require_unique(self.source_batch_ids, "source_batch_ids")
        return self


class ReleaseVerification(ContractModel):
    candidate_release_id: NonEmptyStr
    manifest_sha256: Sha256
    accepted: bool
    canonical_index_parity: bool
    missing_points: NonNegativeInt
    extra_points: NonNegativeInt
    stale_points: NonNegativeInt
    cross_release_points: NonNegativeInt
    evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    verified_at: CanonicalDatetime

    @model_validator(mode="after")
    def validate_acceptance_parity(self) -> ReleaseVerification:
        deviations = (
            self.missing_points,
            self.extra_points,
            self.stale_points,
            self.cross_release_points,
        )
        if self.accepted and (
            not self.canonical_index_parity or any(value != 0 for value in deviations)
        ):
            raise ValueError(
                "accepted release verification requires exact parity and zero deviations"
            )
        _require_unique(self.evidence_ids, "evidence_ids")
        return self


class PublishedRelease(ContractModel):
    release_id: NonEmptyStr
    previous_release_id: NonEmptyStr | None = None
    canonical_release_id: NonEmptyStr
    published_projection_release_id: NonEmptyStr
    index_release_id: NonEmptyStr
    state: ReleaseState
    changed_at: CanonicalDatetime
    verification_evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_release_parity(self) -> PublishedRelease:
        if self.state not in {ReleaseState.active, ReleaseState.rolled_back}:
            raise ValueError("published release must be active or rolled_back")
        release_ids = {
            self.release_id,
            self.canonical_release_id,
            self.published_projection_release_id,
            self.index_release_id,
        }
        if len(release_ids) != 1:
            raise ValueError(
                "canonical, published projection, and index must use the same release"
            )
        if self.previous_release_id == self.release_id:
            raise ValueError("previous_release_id must differ from the active release")
        _require_unique(self.verification_evidence_ids, "verification_evidence_ids")
        return self
