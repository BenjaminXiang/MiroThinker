"""Deterministic, evidence-bound relationship projection for Canonical V2.

This package-internal deep module keeps catalog loading, retained-input closure,
typed endpoint validation, and relationship decision construction behind one
pure projection interface. Persistence and path eligibility are separate seams.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from functools import lru_cache
import hashlib
from importlib.resources import files
import json
from typing import Any, Literal, cast

from pydantic import (
    Field,
    JsonValue,
    ValidationInfo,
    field_validator,
    model_validator,
)

from .contracts import (
    CanonicalDatetime,
    Confidence,
    ContractModel,
    DecisionMethod,
    NonEmptyStr,
    PolicyReference,
    RelationshipAssertion,
    RelationshipDecision,
    RelationshipDecisionState,
    RelationshipLayer,
    RelationshipRole,
    RelationshipType,
    Sha256,
    TemporalComparisonContext,
    TemporalDateValue,
    TemporalInstantValue,
    TemporalRelation,
    TemporalValue,
    compare_temporal_values,
)
from .domain_catalog import (
    CATALOG_CONTENT_SHA256,
    CATALOG_RESOURCE,
    CATALOG_SCHEMA_VERSION,
    CATALOG_VERSION,
    PACKAGED_CATALOG,
)
from .domain_projection_models import (
    DOMAIN_SUBOBJECT_ATTRIBUTES,
    CompanyProjection,
    PaperProjection,
    PatentProjection,
    ProfessorProjection,
)


DomainProjection = (
    CompanyProjection | PaperProjection | PatentProjection | ProfessorProjection
)
EndpointReferenceKind = Literal[
    "canonical_identity", "registry_entity", "typed_subobject", "lineage_record"
]
DecisionStateValue = Literal["accepted", "unresolved", "rejected", "superseded"]
SourcePotentialOutcome = Literal["supported", "insufficient_evidence", "absent"]
CurrentProjectionState = Literal[
    "current", "not_current", "indeterminate", "not_applicable"
]


class RelationshipProjectionIntegrityError(ValueError):
    """The request envelope or installed catalog identity is not trustworthy."""


def _unique(values: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(values)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must not contain duplicates")
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


def _index_unique[T](values: Iterable[T], attribute: str, label: str) -> dict[str, T]:
    result: dict[str, T] = {}
    for value in values:
        identity = cast(str, getattr(value, attribute))
        if identity in result:
            raise RelationshipProjectionIntegrityError(f"duplicate {label}: {identity}")
        result[identity] = value
    return result


def _validate_temporal_interval(
    valid_from: TemporalDateValue | TemporalInstantValue | None,
    valid_to: TemporalDateValue | TemporalInstantValue | None,
) -> None:
    if valid_from is None or valid_to is None:
        return
    if type(valid_from) is not type(valid_to):
        raise ValueError(
            "valid_from and valid_to must have the same temporal precision"
        )
    if compare_temporal_values(valid_from, valid_to) is TemporalRelation.after:
        raise ValueError("valid_from must not be after valid_to")


class RelationshipCatalogIdentity(ContractModel):
    schema_version: NonEmptyStr
    catalog_version: NonEmptyStr
    content_sha256: Sha256


class RelationshipEndpointReference(ContractModel):
    reference_kind: EndpointReferenceKind
    endpoint_type: NonEmptyStr
    stable_reference: NonEmptyStr
    canonical_identity_id: NonEmptyStr | None = None
    parent_canonical_identity_ref: NonEmptyStr | None = None
    lineage_family: NonEmptyStr | None = None
    subject_reference: NonEmptyStr | None = None
    subject_entity_type: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_reference_shape(self) -> RelationshipEndpointReference:
        if self.reference_kind == "canonical_identity":
            if (
                self.canonical_identity_id is None
                or self.parent_canonical_identity_ref is not None
            ):
                raise ValueError(
                    "canonical endpoint requires only canonical_identity_id"
                )
        elif self.reference_kind == "typed_subobject":
            if (
                self.canonical_identity_id is not None
                or self.parent_canonical_identity_ref is None
            ):
                raise ValueError(
                    "typed subobject requires only parent_canonical_identity_ref"
                )
        elif (
            self.canonical_identity_id is not None
            or self.parent_canonical_identity_ref is not None
        ):
            raise ValueError(
                "registry and lineage endpoints cannot masquerade as canonical identities"
            )
        if self.reference_kind != "lineage_record" and any(
            value is not None
            for value in (
                self.lineage_family,
                self.subject_reference,
                self.subject_entity_type,
            )
        ):
            raise ValueError("lineage metadata belongs only to lineage endpoints")
        return self


class RetainedArtifactReference(ContractModel):
    reference_id: NonEmptyStr
    artifact_id: NonEmptyStr
    content_sha256: Sha256


class RetainedAssertionReference(ContractModel):
    reference_id: NonEmptyStr
    assertion_id: NonEmptyStr
    source_record_ref: NonEmptyStr
    artifact_refs: tuple[NonEmptyStr, ...] = ()

    @field_validator("artifact_refs")
    @classmethod
    def validate_artifact_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique(values, "artifact_refs")


class RetainedEvidenceBinding(ContractModel):
    evidence_kind: NonEmptyStr
    assertion_refs: tuple[NonEmptyStr, ...] = ()
    artifact_refs: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> RetainedEvidenceBinding:
        _unique(self.assertion_refs, "assertion_refs")
        _unique(self.artifact_refs, "artifact_refs")
        if not self.assertion_refs and not self.artifact_refs:
            raise ValueError("retained evidence binding requires a retained reference")
        return self


class SourceCanonicalAssignment(ContractModel):
    assignment_id: NonEmptyStr
    source_identity_id: NonEmptyStr
    canonical_identity_id: NonEmptyStr
    entity_type: NonEmptyStr
    source_record_refs: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("source_record_refs")
    @classmethod
    def validate_source_records(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _unique(values, "source_record_refs")


class TypedRelationshipAssertionInput(ContractModel):
    assertion_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    relationship_type_version: NonEmptyStr
    source_record_ref: NonEmptyStr
    source_endpoint: RelationshipEndpointReference
    target_endpoint: RelationshipEndpointReference
    attributes: dict[NonEmptyStr, JsonValue]
    evidence_bindings: tuple[RetainedEvidenceBinding, ...]
    observed_at: CanonicalDatetime
    source_event_time: CanonicalDatetime | None = None
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    assertion_run_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_interval(self) -> TypedRelationshipAssertionInput:
        _validate_temporal_interval(self.valid_from, self.valid_to)
        return self


class RelationshipDecisionInput(ContractModel):
    decision_input_id: NonEmptyStr
    decision_id: NonEmptyStr
    canonical_relationship_id: NonEmptyStr
    state: DecisionStateValue
    candidate_assertion_ids: tuple[NonEmptyStr, ...]
    selected_assertion_ids: tuple[NonEmptyStr, ...] = ()
    conflicting_assertion_ids: tuple[NonEmptyStr, ...] = ()
    role_bindings: dict[NonEmptyStr, NonEmptyStr]
    selected_evidence_refs: tuple[NonEmptyStr, ...] = ()
    policy: PolicyReference
    method: DecisionMethod
    method_version: NonEmptyStr
    confidence: Confidence
    rationale: NonEmptyStr
    supersedes_decision_id: NonEmptyStr | None = None


class RelationshipProjectionCandidate(ContractModel):
    candidate_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    relationship_type_version: NonEmptyStr
    source_endpoint: RelationshipEndpointReference
    target_endpoint: RelationshipEndpointReference
    role_bindings: dict[NonEmptyStr, NonEmptyStr]
    evidence_metadata: dict[NonEmptyStr, JsonValue] = Field(default_factory=dict)
    requested_paths: tuple[NonEmptyStr, ...] = ()
    catalog_scenario_id: NonEmptyStr | None = None
    observed_at: CanonicalDatetime
    source_event_time: CanonicalDatetime | None = None
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    evidence_bindings: tuple[RetainedEvidenceBinding, ...]
    assertion_input_id: NonEmptyStr | None = None
    assertion_input_kind: (
        Literal["shared_source_relationship_assertion", "typed_relationship_assertion"]
        | None
    ) = None
    decision_input_id: NonEmptyStr | None = None

    @field_validator("evidence_metadata", mode="before")
    @classmethod
    def normalize_json_metadata(cls, value: object) -> object:
        """Normalize tuple-shaped fixture/input values to strict JSON arrays."""
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))

    @model_validator(mode="after")
    def validate_interval(self) -> RelationshipProjectionCandidate:
        _validate_temporal_interval(self.valid_from, self.valid_to)
        return self


class RelationshipDirectionProbe(ContractModel):
    probe_id: NonEmptyStr
    scenario_id: NonEmptyStr
    source_endpoint: RelationshipEndpointReference
    target_endpoint: RelationshipEndpointReference
    relationship_type_ids: tuple[NonEmptyStr, ...]
    retained_relationship_refs: tuple[NonEmptyStr, ...]


class RelationshipLayerProbe(ContractModel):
    layer: Literal["canonical", "derived", "session"]
    stable_reference: NonEmptyStr
    attempt_canonical_projection: bool
    evidence_bindings: tuple[RetainedEvidenceBinding, ...]


class RelationshipProjectionRequest(ContractModel):
    catalog: RelationshipCatalogIdentity
    release_id: NonEmptyStr
    projection_run_id: NonEmptyStr
    as_of: CanonicalDatetime
    temporal_comparison_context: TemporalComparisonContext | None = None
    decision_policy: PolicyReference
    domain_projections: tuple[DomainProjection, ...]
    candidates: tuple[RelationshipProjectionCandidate, ...]
    relationship_assertions: tuple[RelationshipAssertion, ...]
    typed_relationship_assertions: tuple[TypedRelationshipAssertionInput, ...]
    source_canonical_assignments: tuple[SourceCanonicalAssignment, ...]
    decision_inputs: tuple[RelationshipDecisionInput, ...]
    direction_probes: tuple[RelationshipDirectionProbe, ...] = ()
    layer_probes: tuple[RelationshipLayerProbe, ...] = ()
    retained_assertions: tuple[RetainedAssertionReference, ...]
    retained_artifacts: tuple[RetainedArtifactReference, ...]


class TypedRelationshipDecision(ContractModel):
    decision_id: NonEmptyStr
    canonical_relationship_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    relationship_type_version: NonEmptyStr
    source_endpoint: RelationshipEndpointReference
    target_endpoint: RelationshipEndpointReference
    state: DecisionStateValue
    candidate_assertion_ids: tuple[NonEmptyStr, ...]
    selected_assertion_ids: tuple[NonEmptyStr, ...]
    conflicting_assertion_ids: tuple[NonEmptyStr, ...]
    role_bindings: dict[NonEmptyStr, NonEmptyStr]
    selected_evidence_refs: tuple[NonEmptyStr, ...]
    policy: PolicyReference
    method: DecisionMethod
    method_version: NonEmptyStr
    decision_run_id: NonEmptyStr
    confidence: Confidence
    rationale: NonEmptyStr
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    release_id: NonEmptyStr
    decided_at: CanonicalDatetime
    supersedes_decision_id: NonEmptyStr | None = None


class CurrentRelationshipProjection(ContractModel):
    canonical_relationship_id: NonEmptyStr
    decision_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    relationship_type_version: NonEmptyStr
    source_endpoint: RelationshipEndpointReference
    target_endpoint: RelationshipEndpointReference
    role_bindings: dict[NonEmptyStr, NonEmptyStr]
    selected_evidence_refs: tuple[NonEmptyStr, ...]
    effective_time_semantics: NonEmptyStr
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    release_id: NonEmptyStr
    projected_at: CanonicalDatetime


class RelationshipCandidateOutcome(ContractModel):
    candidate_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    admitted: bool
    reason_codes: tuple[NonEmptyStr, ...]
    decision_state: DecisionStateValue | None = None
    retained_assertion_id: NonEmptyStr | None = None
    decision_id: NonEmptyStr | None = None
    projected_relationship_id: NonEmptyStr | None = None
    selected_evidence_refs: tuple[NonEmptyStr, ...] = ()
    source_reference_kind: EndpointReferenceKind
    target_reference_kind: EndpointReferenceKind
    source_canonical_identity_id: NonEmptyStr | None = None
    target_canonical_identity_id: NonEmptyStr | None = None
    source_parent_canonical_identity_ref: NonEmptyStr | None = None
    target_parent_canonical_identity_ref: NonEmptyStr | None = None
    effective_time_semantics: NonEmptyStr | None = None
    source_potential_outcome: SourcePotentialOutcome | None = None
    current_projection_state: CurrentProjectionState = "not_applicable"
    current_projection_reason_codes: tuple[NonEmptyStr, ...] = ()


class RelationshipDirectionOutcome(ContractModel):
    probe_id: NonEmptyStr
    scenario_id: NonEmptyStr
    orientation_valid: bool
    source_potential_outcome: SourcePotentialOutcome
    available: bool
    projected_relationship_ids: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...]


class RelationshipLayerOutcome(ContractModel):
    layer: Literal["canonical", "derived", "session"]
    stable_reference: NonEmptyStr
    canonical_projection_allowed: bool
    reason_codes: tuple[NonEmptyStr, ...]


class RelationshipProjectionResult(ContractModel):
    release_id: NonEmptyStr
    projection_run_id: NonEmptyStr
    as_of: CanonicalDatetime
    catalog: RelationshipCatalogIdentity
    relationship_types: tuple[RelationshipType, ...]
    candidate_outcomes: tuple[RelationshipCandidateOutcome, ...]
    retained_assertion_refs: tuple[NonEmptyStr, ...]
    retained_artifact_refs: tuple[NonEmptyStr, ...]
    retained_relationship_assertions: tuple[RelationshipAssertion, ...]
    typed_relationship_assertions: tuple[TypedRelationshipAssertionInput, ...]
    relationship_decisions: tuple[RelationshipDecision, ...]
    typed_relationship_decisions: tuple[TypedRelationshipDecision, ...]
    current_relationships: tuple[CurrentRelationshipProjection, ...]
    direction_outcomes: tuple[RelationshipDirectionOutcome, ...]
    layer_outcomes: tuple[RelationshipLayerOutcome, ...]
    identity_state_changes: tuple[NonEmptyStr, ...] = ()
    inferred_relationship_type_ids: tuple[NonEmptyStr, ...] = ()
    path_eligibility_results: tuple[NonEmptyStr, ...] = ()
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_content_hash(
        self, info: ValidationInfo
    ) -> RelationshipProjectionResult:
        if not (info.context or {}).get("allow_unbound_content_hash"):
            payload = cast(
                JsonValue,
                self.model_dump(mode="json", exclude={"content_sha256"}),
            )
            if self.content_sha256 != _canonical_sha256(payload):
                raise ValueError("content_sha256 must bind the relationship result")
        return self


@lru_cache(maxsize=1)
def _installed_catalog_payload() -> dict[str, Any]:
    # Importing domain_catalog already verifies the exact packaged file and content
    # hashes. This module consumes that installed resource, never the review artifact.
    if (
        PACKAGED_CATALOG.schema_version,
        PACKAGED_CATALOG.catalog_version,
        PACKAGED_CATALOG.content_sha256,
    ) != (CATALOG_SCHEMA_VERSION, CATALOG_VERSION, CATALOG_CONTENT_SHA256):
        raise RelationshipProjectionIntegrityError(
            "installed relationship catalog identity mismatch"
        )
    value = json.loads(files(__package__).joinpath(CATALOG_RESOURCE).read_text("utf-8"))
    if not isinstance(value, dict):
        raise RelationshipProjectionIntegrityError(
            "installed relationship catalog must be an object"
        )
    return cast(dict[str, Any], value)


@lru_cache(maxsize=1)
def _installed_relationship_types() -> tuple[RelationshipType, ...]:
    rows = cast(list[dict[str, Any]], _installed_catalog_payload()["relationships"])
    return tuple(
        RelationshipType.model_validate(
            {
                "relationship_type_id": row["relationship_type_id"],
                "version": row["version"],
                "layer": RelationshipLayer.canonical,
                "source_entity_types": row["source_entity_types"],
                "target_entity_types": row["target_entity_types"],
                "direction": row["direction"],
                "roles": row["roles"],
                "required_evidence_kinds": row["required_evidence_kinds"],
                "time_semantics": row["time_semantics"],
                "allowed_states": row["allowed_states"],
                "eligible_paths": row["eligible_paths"],
            }
        )
        for row in rows
    )


def _reason(reasons: list[str], code: str, condition: bool) -> None:
    if condition and code not in reasons:
        reasons.append(code)


def _valid_time_shape(
    candidate: RelationshipProjectionCandidate, semantics: str
) -> bool:
    if semantics == "event_time":
        return (
            candidate.source_event_time is not None
            and candidate.valid_from is None
            and candidate.valid_to is None
        )
    if semantics == "validity_interval":
        return candidate.source_event_time is None
    if semantics in {"none", "observed_at"}:
        return (
            candidate.source_event_time is None
            and candidate.valid_from is None
            and candidate.valid_to is None
        )
    return False


def _current_projection_state(
    candidate: RelationshipProjectionCandidate,
    as_of: CanonicalDatetime,
    context: TemporalComparisonContext | None,
) -> tuple[CurrentProjectionState, tuple[str, ...]]:
    as_of_value = TemporalInstantValue(value=as_of)
    if candidate.valid_from is not None:
        relation = compare_temporal_values(
            as_of_value,
            candidate.valid_from,
            context=context,
        )
        if relation is TemporalRelation.indeterminate:
            return "indeterminate", ("explicit_calendar_context_required",)
        if relation is TemporalRelation.before:
            return "not_current", ("validity_has_not_started",)
    if candidate.valid_to is not None:
        relation = compare_temporal_values(
            as_of_value,
            candidate.valid_to,
            context=context,
        )
        if relation is TemporalRelation.indeterminate:
            return "indeterminate", ("explicit_calendar_context_required",)
        if relation in {TemporalRelation.equal, TemporalRelation.after}:
            return "not_current", ("validity_has_ended",)
    return "current", ()


def _projection_registries(
    projections: tuple[DomainProjection, ...],
) -> tuple[set[tuple[str, str]], dict[str, tuple[str, str]]]:
    canonical: set[tuple[str, str]] = set()
    subobjects: dict[str, tuple[str, str]] = {}
    for projection in projections:
        key = (projection.entity_type, projection.canonical_identity_id)
        if key in canonical:
            raise RelationshipProjectionIntegrityError(
                f"duplicate domain projection endpoint: {key}"
            )
        canonical.add(key)
        for subobject_type, attribute in DOMAIN_SUBOBJECT_ATTRIBUTES[
            projection.entity_type
        ].items():
            for subobject in cast(tuple[Any, ...], getattr(projection, attribute)):
                if subobject.subobject_id in subobjects:
                    raise RelationshipProjectionIntegrityError(
                        f"duplicate typed subobject endpoint: {subobject.subobject_id}"
                    )
                subobjects[subobject.subobject_id] = (
                    (
                        f"canonical:{projection.entity_type}:"
                        f"{projection.canonical_identity_id}"
                    ),
                    subobject_type,
                )
    return canonical, subobjects


def _scenario_outcomes() -> dict[str, SourcePotentialOutcome]:
    scenarios = _scenario_rows().values()
    return {
        cast(str, row["scenario_id"]): cast(
            SourcePotentialOutcome, row["evidence_outcome"]
        )
        for row in scenarios
    }


def _scenario_rows() -> dict[str, dict[str, Any]]:
    scenarios = cast(
        list[dict[str, Any]], _installed_catalog_payload()["scenario_accounting"]
    )
    return {cast(str, row["scenario_id"]): row for row in scenarios}


def _decision_input_shape_is_valid(
    candidate: RelationshipProjectionCandidate,
    decision: RelationshipDecisionInput,
) -> bool:
    candidate_ids = decision.candidate_assertion_ids
    selected_ids = decision.selected_assertion_ids
    conflicting_ids = decision.conflicting_assertion_ids
    if (
        len(candidate_ids) != len(set(candidate_ids))
        or len(selected_ids) != len(set(selected_ids))
        or len(conflicting_ids) != len(set(conflicting_ids))
        or not set(selected_ids) <= set(candidate_ids)
        or not set(conflicting_ids) <= set(candidate_ids)
        or set(selected_ids) & set(conflicting_ids)
        or candidate.assertion_input_id not in candidate_ids
    ):
        return False
    if decision.state == "accepted":
        return bool(selected_ids)
    if decision.state == "unresolved":
        return not selected_ids and len(conflicting_ids) >= 2
    if decision.state == "rejected":
        return not selected_ids
    return (
        not selected_ids
        and not conflicting_ids
        and not decision.role_bindings
        and decision.supersedes_decision_id is not None
    )


class RelationshipProjection(ABC):
    @abstractmethod
    def project(
        self, request: RelationshipProjectionRequest
    ) -> RelationshipProjectionResult:
        """Validate and project one closed relationship candidate batch."""


class _EphemeralRelationshipProjection(RelationshipProjection):
    def project(
        self, request: RelationshipProjectionRequest
    ) -> RelationshipProjectionResult:
        expected_catalog = (
            CATALOG_SCHEMA_VERSION,
            CATALOG_VERSION,
            CATALOG_CONTENT_SHA256,
        )
        supplied_catalog = (
            request.catalog.schema_version,
            request.catalog.catalog_version,
            request.catalog.content_sha256,
        )
        if supplied_catalog != expected_catalog:
            raise RelationshipProjectionIntegrityError(
                "request catalog identity does not match the installed catalog"
            )
        if request.decision_policy.policy_kind.value != "relationship":
            raise RelationshipProjectionIntegrityError(
                "relationship projection requires a relationship decision policy"
            )
        if request.decision_policy.effective_at > request.as_of:
            raise RelationshipProjectionIntegrityError(
                "relationship decision policy cannot be effective after projection as_of"
            )
        if any(
            projection.release_id != request.release_id
            or projection.as_of > request.as_of
            or (
                projection.catalog_schema_version,
                projection.catalog_version,
                projection.catalog_content_sha256,
            )
            != expected_catalog
            for projection in request.domain_projections
        ):
            raise RelationshipProjectionIntegrityError(
                "domain projections must bind this release, as_of, and installed catalog"
            )

        relationship_types = _installed_relationship_types()
        type_by_id = {
            relationship.relationship_type_id: relationship
            for relationship in relationship_types
        }
        canonical_registry, subobject_registry = _projection_registries(
            request.domain_projections
        )
        retained_assertions = _index_unique(
            request.retained_assertions, "reference_id", "retained assertion reference"
        )
        retained_artifacts = _index_unique(
            request.retained_artifacts, "reference_id", "retained artifact reference"
        )
        if any(
            artifact_ref not in retained_artifacts
            for retained_assertion in retained_assertions.values()
            for artifact_ref in retained_assertion.artifact_refs
        ):
            raise RelationshipProjectionIntegrityError(
                "retained assertion references an unknown retained artifact"
            )
        shared_assertions = _index_unique(
            request.relationship_assertions, "assertion_id", "relationship assertion"
        )
        typed_assertions = _index_unique(
            request.typed_relationship_assertions,
            "assertion_id",
            "typed relationship assertion",
        )
        assignments = _index_unique(
            request.source_canonical_assignments,
            "source_identity_id",
            "source canonical assignment",
        )
        decision_inputs = _index_unique(
            request.decision_inputs, "decision_input_id", "relationship decision input"
        )
        _index_unique(
            request.decision_inputs,
            "decision_id",
            "relationship decision ID",
        )
        _index_unique(
            request.decision_inputs,
            "canonical_relationship_id",
            "canonical relationship ID",
        )
        _index_unique(request.candidates, "candidate_id", "relationship candidate")
        _index_unique(
            request.direction_probes, "probe_id", "relationship direction probe"
        )
        scenario_rows = _scenario_rows()
        scenario_outcomes = _scenario_outcomes()

        candidate_outcomes: list[RelationshipCandidateOutcome] = []
        canonical_decisions: list[RelationshipDecision] = []
        typed_decisions: list[TypedRelationshipDecision] = []
        current_relationships: list[CurrentRelationshipProjection] = []

        for candidate in request.candidates:
            relationship_type = type_by_id.get(candidate.relationship_type_id)
            reasons: list[str] = []
            source_potential = (
                scenario_outcomes.get(candidate.catalog_scenario_id)
                if candidate.catalog_scenario_id is not None
                else None
            )
            _reason(
                reasons,
                "observation_after_projection_as_of",
                candidate.observed_at > request.as_of,
            )
            if candidate.catalog_scenario_id is not None:
                scenario = scenario_rows.get(candidate.catalog_scenario_id)
                _reason(
                    reasons,
                    "catalog_scenario_not_registered",
                    scenario is None,
                )
                _reason(
                    reasons,
                    "catalog_scenario_relationship_type_mismatch",
                    scenario is not None
                    and candidate.relationship_type_id
                    not in cast(list[str], scenario["relationship_type_ids"]),
                )
            if relationship_type is None:
                reasons.append("relationship_type_not_registered")
            else:
                _reason(
                    reasons,
                    "relationship_type_version_not_registered",
                    candidate.relationship_type_version != relationship_type.version,
                )
                _reason(
                    reasons,
                    "endpoint_type_not_allowed",
                    candidate.source_endpoint.endpoint_type
                    not in relationship_type.source_entity_types
                    or candidate.target_endpoint.endpoint_type
                    not in relationship_type.target_entity_types,
                )
                self._validate_endpoint_registry(
                    candidate.source_endpoint,
                    canonical_registry,
                    subobject_registry,
                    reasons,
                )
                self._validate_endpoint_registry(
                    candidate.target_endpoint,
                    canonical_registry,
                    subobject_registry,
                    reasons,
                )
                self._validate_relationship_semantics(
                    candidate, relationship_type, reasons
                )
                self._validate_evidence(
                    candidate,
                    relationship_type,
                    retained_assertions,
                    retained_artifacts,
                    reasons,
                )

            decision_input = (
                decision_inputs.get(candidate.decision_input_id)
                if candidate.decision_input_id is not None
                else None
            )
            input_assertion = self._validate_retained_inputs(
                candidate,
                request,
                shared_assertions,
                typed_assertions,
                assignments,
                decision_input,
                reasons,
            )
            if relationship_type is not None and decision_input is not None:
                _reason(
                    reasons,
                    "state_not_allowed",
                    decision_input.state not in relationship_type.allowed_states,
                )
            if source_potential is not None and candidate.evidence_bindings == ():
                _reason(
                    reasons,
                    "source_potential_is_not_accepted_evidence",
                    True,
                )

            admitted = not reasons
            decision_id = (
                decision_input.decision_id
                if admitted and decision_input is not None
                else None
            )
            relationship_id = (
                decision_input.canonical_relationship_id
                if admitted and decision_input is not None
                else None
            )
            projected_relationship_id: str | None = None
            selected_evidence_refs: tuple[str, ...] = ()
            decision_state: DecisionStateValue | None = None
            current_projection_state: CurrentProjectionState = "not_applicable"
            current_projection_reason_codes: tuple[str, ...] = ()
            if (
                admitted
                and relationship_type is not None
                and decision_input is not None
                and input_assertion is not None
                and decision_id is not None
                and relationship_id is not None
            ):
                decision_state = decision_input.state
                selected_evidence_refs = decision_input.selected_evidence_refs
                if (
                    candidate.assertion_input_kind
                    == "shared_source_relationship_assertion"
                ):
                    source_id = cast(
                        str, candidate.source_endpoint.canonical_identity_id
                    )
                    target_id = cast(
                        str, candidate.target_endpoint.canonical_identity_id
                    )
                    canonical_decisions.append(
                        RelationshipDecision(
                            decision_id=decision_id,
                            canonical_relationship_id=relationship_id,
                            relationship_type_id=candidate.relationship_type_id,
                            relationship_type_version=candidate.relationship_type_version,
                            source_canonical_identity_id=source_id,
                            target_canonical_identity_id=target_id,
                            state=RelationshipDecisionState(decision_input.state),
                            candidate_assertion_ids=decision_input.candidate_assertion_ids,
                            selected_assertion_ids=decision_input.selected_assertion_ids,
                            conflicting_assertion_ids=(
                                decision_input.conflicting_assertion_ids
                            ),
                            role_bindings=decision_input.role_bindings,
                            policy=request.decision_policy,
                            method=decision_input.method,
                            method_version=decision_input.method_version,
                            decision_run_id=request.projection_run_id,
                            confidence=decision_input.confidence,
                            rationale=decision_input.rationale,
                            valid_from=candidate.valid_from,
                            valid_to=candidate.valid_to,
                            release_id=request.release_id,
                            decided_at=request.as_of,
                            supersedes_decision_id=(
                                decision_input.supersedes_decision_id
                            ),
                        )
                    )
                else:
                    typed_decisions.append(
                        TypedRelationshipDecision(
                            decision_id=decision_id,
                            canonical_relationship_id=relationship_id,
                            relationship_type_id=candidate.relationship_type_id,
                            relationship_type_version=candidate.relationship_type_version,
                            source_endpoint=candidate.source_endpoint,
                            target_endpoint=candidate.target_endpoint,
                            state=decision_input.state,
                            candidate_assertion_ids=decision_input.candidate_assertion_ids,
                            selected_assertion_ids=decision_input.selected_assertion_ids,
                            conflicting_assertion_ids=(
                                decision_input.conflicting_assertion_ids
                            ),
                            role_bindings=decision_input.role_bindings,
                            selected_evidence_refs=decision_input.selected_evidence_refs,
                            policy=request.decision_policy,
                            method=decision_input.method,
                            method_version=decision_input.method_version,
                            decision_run_id=request.projection_run_id,
                            confidence=decision_input.confidence,
                            rationale=decision_input.rationale,
                            valid_from=candidate.valid_from,
                            valid_to=candidate.valid_to,
                            release_id=request.release_id,
                            decided_at=request.as_of,
                            supersedes_decision_id=(
                                decision_input.supersedes_decision_id
                            ),
                        )
                    )
                if decision_input.state == "accepted":
                    (
                        current_projection_state,
                        current_projection_reason_codes,
                    ) = _current_projection_state(
                        candidate,
                        request.as_of,
                        request.temporal_comparison_context,
                    )
                if current_projection_state == "current":
                    projected_relationship_id = relationship_id
                    current_relationships.append(
                        CurrentRelationshipProjection(
                            canonical_relationship_id=relationship_id,
                            decision_id=decision_id,
                            relationship_type_id=candidate.relationship_type_id,
                            relationship_type_version=(
                                candidate.relationship_type_version
                            ),
                            source_endpoint=candidate.source_endpoint,
                            target_endpoint=candidate.target_endpoint,
                            role_bindings=candidate.role_bindings,
                            selected_evidence_refs=selected_evidence_refs,
                            effective_time_semantics=(
                                relationship_type.time_semantics.value
                            ),
                            valid_from=candidate.valid_from,
                            valid_to=candidate.valid_to,
                            release_id=request.release_id,
                            projected_at=request.as_of,
                        )
                    )

            candidate_outcomes.append(
                RelationshipCandidateOutcome(
                    candidate_id=candidate.candidate_id,
                    relationship_type_id=candidate.relationship_type_id,
                    admitted=admitted,
                    reason_codes=tuple(sorted(reasons)),
                    decision_state=decision_state,
                    retained_assertion_id=(
                        candidate.assertion_input_id if admitted else None
                    ),
                    decision_id=decision_id,
                    projected_relationship_id=projected_relationship_id,
                    selected_evidence_refs=selected_evidence_refs,
                    source_reference_kind=candidate.source_endpoint.reference_kind,
                    target_reference_kind=candidate.target_endpoint.reference_kind,
                    source_canonical_identity_id=(
                        candidate.source_endpoint.canonical_identity_id
                    ),
                    target_canonical_identity_id=(
                        candidate.target_endpoint.canonical_identity_id
                    ),
                    source_parent_canonical_identity_ref=(
                        candidate.source_endpoint.parent_canonical_identity_ref
                    ),
                    target_parent_canonical_identity_ref=(
                        candidate.target_endpoint.parent_canonical_identity_ref
                    ),
                    effective_time_semantics=(
                        relationship_type.time_semantics.value
                        if relationship_type is not None
                        else None
                    ),
                    source_potential_outcome=source_potential,
                    current_projection_state=current_projection_state,
                    current_projection_reason_codes=(current_projection_reason_codes),
                )
            )

        direction_outcomes = self._project_direction_probes(
            request.direction_probes,
            current_relationships,
            scenario_rows,
            canonical_registry,
        )
        layer_outcomes = self._project_layer_probes(request.layer_probes)
        provisional = RelationshipProjectionResult.model_validate(
            {
                "release_id": request.release_id,
                "projection_run_id": request.projection_run_id,
                "as_of": request.as_of,
                "catalog": request.catalog,
                "relationship_types": relationship_types,
                "candidate_outcomes": tuple(candidate_outcomes),
                "retained_assertion_refs": tuple(sorted(retained_assertions)),
                "retained_artifact_refs": tuple(sorted(retained_artifacts)),
                "retained_relationship_assertions": tuple(
                    sorted(
                        request.relationship_assertions,
                        key=lambda item: item.assertion_id,
                    )
                ),
                "typed_relationship_assertions": tuple(
                    sorted(
                        request.typed_relationship_assertions,
                        key=lambda item: item.assertion_id,
                    )
                ),
                "relationship_decisions": tuple(
                    sorted(canonical_decisions, key=lambda item: item.decision_id)
                ),
                "typed_relationship_decisions": tuple(
                    sorted(typed_decisions, key=lambda item: item.decision_id)
                ),
                "current_relationships": tuple(
                    sorted(
                        current_relationships,
                        key=lambda item: item.canonical_relationship_id,
                    )
                ),
                "direction_outcomes": direction_outcomes,
                "layer_outcomes": layer_outcomes,
                "content_sha256": "0" * 64,
            },
            context={"allow_unbound_content_hash": True},
        )
        payload = cast(
            JsonValue,
            provisional.model_dump(mode="json", exclude={"content_sha256"}),
        )
        return RelationshipProjectionResult.model_validate(
            {
                **provisional.model_dump(mode="python"),
                "content_sha256": _canonical_sha256(payload),
            }
        )

    @staticmethod
    def _validate_endpoint_registry(
        endpoint: RelationshipEndpointReference,
        canonical_registry: set[tuple[str, str]],
        subobject_registry: dict[str, tuple[str, str]],
        reasons: list[str],
    ) -> None:
        if endpoint.reference_kind == "canonical_identity":
            key = (endpoint.endpoint_type, cast(str, endpoint.canonical_identity_id))
            _reason(
                reasons,
                "canonical_endpoint_not_in_domain_projection",
                key not in canonical_registry,
            )
            _reason(
                reasons,
                "canonical_endpoint_reference_mismatch",
                endpoint.stable_reference
                != (
                    f"canonical:{endpoint.endpoint_type}:"
                    f"{endpoint.canonical_identity_id}"
                ),
            )
        elif endpoint.reference_kind == "typed_subobject":
            parent_reference = cast(str, endpoint.parent_canonical_identity_ref)
            registry_value = subobject_registry.get(endpoint.stable_reference)
            _reason(
                reasons,
                "typed_subobject_not_in_domain_projection",
                registry_value is None
                or registry_value[0] != parent_reference
                or registry_value[1] != endpoint.endpoint_type,
            )

    @staticmethod
    def _validate_relationship_semantics(
        candidate: RelationshipProjectionCandidate,
        relationship_type: RelationshipType,
        reasons: list[str],
    ) -> None:
        relationship_id = candidate.relationship_type_id
        if relationship_id in {
            "canonical_identity_merged_into",
            "canonical_identity_split_from",
        }:
            _reason(
                reasons,
                "source_and_target_entity_types_must_match",
                candidate.source_endpoint.endpoint_type
                != candidate.target_endpoint.endpoint_type,
            )
        if relationship_id == "source_identity_resolves_to_canonical_identity":
            _reason(
                reasons,
                "source_and_target_entity_types_must_match",
                candidate.source_endpoint.subject_entity_type
                != candidate.target_endpoint.endpoint_type,
            )
        if relationship_id in {
            "identity_decision_supersedes_identity_decision",
            "identity_decision_reverses_identity_decision",
        }:
            _reason(
                reasons,
                "identity_decision_subjects_must_match",
                candidate.source_endpoint.subject_reference
                != candidate.target_endpoint.subject_reference,
            )
        if relationship_id == "canonical_decision_selects_assertion":
            _reason(
                reasons,
                "decision_and_assertion_families_and_subjects_must_match",
                candidate.source_endpoint.lineage_family
                != candidate.target_endpoint.lineage_family
                or candidate.source_endpoint.subject_reference
                != candidate.target_endpoint.subject_reference,
            )
        if relationship_id == "professor_held_role_at_non_company_organization":
            _reason(
                reasons,
                "company_targets_require_professor_company_role",
                candidate.target_endpoint.endpoint_type == "company",
            )
        if relationship_id == "professor_attributed_to_paper":
            _reason(
                reasons,
                "attribution_basis_is_evidence_metadata_not_business_role",
                bool(candidate.role_bindings),
            )
        if relationship_id == "patent_has_applicant":
            _reason(
                reasons,
                "applicant_not_owner_or_assignee",
                bool({"owner", "assignee"} & set(candidate.role_bindings)),
            )
            _reason(
                reasons,
                "company_paths_require_target_type_company_and_accepted_company_identity",
                bool(
                    {"company_to_patent", "patent_to_company"}
                    & set(candidate.requested_paths)
                )
                and (
                    candidate.target_endpoint.endpoint_type != "company"
                    or candidate.target_endpoint.reference_kind != "canonical_identity"
                ),
            )
        if relationship_id == "patent_has_inventor":
            _reason(
                reasons,
                "professor_paths_require_target_type_professor_and_accepted_professor_identity",
                bool(
                    {"patent_to_professor", "professor_to_patent"}
                    & set(candidate.requested_paths)
                )
                and (
                    candidate.target_endpoint.endpoint_type != "professor"
                    or candidate.target_endpoint.reference_kind != "canonical_identity"
                ),
            )

        role_by_id: dict[str, RelationshipRole] = {
            role.role_id: role for role in relationship_type.roles
        }
        unknown_roles = set(candidate.role_bindings) - set(role_by_id)
        if relationship_id == "professor_company_role" and unknown_roles:
            _reason(
                reasons,
                "generic_association_without_a_supported_role_is_not_accepted",
                True,
            )
        elif unknown_roles:
            _reason(reasons, "role_not_registered", True)
        for role in relationship_type.roles:
            if role.required:
                _reason(
                    reasons,
                    "missing_required_role",
                    role.role_id not in candidate.role_bindings,
                )
            if role.role_id not in candidate.role_bindings:
                continue
            expected_owner = {
                "source": candidate.source_endpoint.stable_reference,
                "target": candidate.target_endpoint.stable_reference,
                "relationship": candidate.candidate_id,
            }[role.applies_to.value]
            _reason(
                reasons,
                "role_ownership_mismatch",
                candidate.role_bindings[role.role_id] != expected_owner,
            )
        _reason(
            reasons,
            "invalid_time_semantics",
            not _valid_time_shape(candidate, relationship_type.time_semantics.value),
        )

    @staticmethod
    def _validate_evidence(
        candidate: RelationshipProjectionCandidate,
        relationship_type: RelationshipType,
        retained_assertions: dict[str, RetainedAssertionReference],
        retained_artifacts: dict[str, RetainedArtifactReference],
        reasons: list[str],
    ) -> None:
        supplied_kinds = {
            binding.evidence_kind for binding in candidate.evidence_bindings
        }
        required_kinds = set(relationship_type.required_evidence_kinds)
        _reason(
            reasons,
            "missing_required_evidence_kind",
            not required_kinds <= supplied_kinds,
        )
        _reason(
            reasons,
            "unsupported_evidence_kind",
            not supplied_kinds <= required_kinds,
        )
        unresolved = any(
            reference not in retained_assertions
            for binding in candidate.evidence_bindings
            for reference in binding.assertion_refs
        ) or any(
            reference not in retained_artifacts
            for binding in candidate.evidence_bindings
            for reference in binding.artifact_refs
        )
        _reason(reasons, "unresolved_retained_evidence_reference", unresolved)

    @staticmethod
    def _validate_retained_inputs(
        candidate: RelationshipProjectionCandidate,
        request: RelationshipProjectionRequest,
        shared_assertions: dict[str, RelationshipAssertion],
        typed_assertions: dict[str, TypedRelationshipAssertionInput],
        assignments: dict[str, SourceCanonicalAssignment],
        decision_input: RelationshipDecisionInput | None,
        reasons: list[str],
    ) -> RelationshipAssertion | TypedRelationshipAssertionInput | None:
        assertion: RelationshipAssertion | TypedRelationshipAssertionInput | None = None
        if candidate.assertion_input_id is None:
            _reason(reasons, "missing_relationship_assertion_input", True)
        elif candidate.assertion_input_kind == "shared_source_relationship_assertion":
            assertion = shared_assertions.get(candidate.assertion_input_id)
            _reason(
                reasons, "unresolved_relationship_assertion_input", assertion is None
            )
            if isinstance(assertion, RelationshipAssertion):
                source_assignment = assignments.get(
                    assertion.source_endpoint.identity_id
                )
                target_assignment = assignments.get(
                    assertion.target_endpoint.identity_id
                )
                continuity_broken = (
                    assertion.relationship_type_id != candidate.relationship_type_id
                    or assertion.relationship_type_version
                    != candidate.relationship_type_version
                    or source_assignment is None
                    or target_assignment is None
                    or source_assignment.entity_type
                    != candidate.source_endpoint.endpoint_type
                    or target_assignment.entity_type
                    != candidate.target_endpoint.endpoint_type
                    or source_assignment.canonical_identity_id
                    != candidate.source_endpoint.canonical_identity_id
                    or target_assignment.canonical_identity_id
                    != candidate.target_endpoint.canonical_identity_id
                    or assertion.source_record_id
                    not in source_assignment.source_record_refs
                    or assertion.source_record_id
                    not in target_assignment.source_record_refs
                )
                _reason(
                    reasons,
                    "source_canonical_assignment_continuity_mismatch",
                    continuity_broken,
                )
                evidence_refs = tuple(
                    sorted(
                        {
                            reference
                            for binding in candidate.evidence_bindings
                            for reference in (
                                *binding.assertion_refs,
                                *binding.artifact_refs,
                            )
                        }
                    )
                )
                expected_attributes: dict[str, JsonValue] = {
                    "candidate_id": candidate.candidate_id,
                    "evidence_refs": list(evidence_refs),
                    "evidence_metadata": cast(
                        JsonValue,
                        json.loads(
                            json.dumps(
                                candidate.evidence_metadata,
                                ensure_ascii=False,
                                allow_nan=False,
                            )
                        ),
                    ),
                    "role_bindings": cast(JsonValue, dict(candidate.role_bindings)),
                }
                _reason(
                    reasons,
                    "source_relationship_assertion_continuity_mismatch",
                    assertion.attributes != expected_attributes
                    or assertion.observed_at != candidate.observed_at
                    or assertion.source_event_time != candidate.source_event_time
                    or assertion.valid_from != candidate.valid_from
                    or assertion.valid_to != candidate.valid_to,
                )
        elif candidate.assertion_input_kind == "typed_relationship_assertion":
            assertion = typed_assertions.get(candidate.assertion_input_id)
            _reason(
                reasons, "unresolved_relationship_assertion_input", assertion is None
            )
            if isinstance(assertion, TypedRelationshipAssertionInput):
                _reason(
                    reasons,
                    "typed_relationship_assertion_continuity_mismatch",
                    assertion.relationship_type_id != candidate.relationship_type_id
                    or assertion.relationship_type_version
                    != candidate.relationship_type_version
                    or assertion.source_endpoint != candidate.source_endpoint
                    or assertion.target_endpoint != candidate.target_endpoint
                    or assertion.evidence_bindings != candidate.evidence_bindings
                    or assertion.observed_at != candidate.observed_at
                    or assertion.source_event_time != candidate.source_event_time
                    or assertion.valid_from != candidate.valid_from
                    or assertion.valid_to != candidate.valid_to
                    or assertion.attributes.get("candidate_id")
                    != candidate.candidate_id
                    or assertion.attributes.get("evidence_metadata")
                    != candidate.evidence_metadata
                    or assertion.attributes.get("role_bindings")
                    != candidate.role_bindings,
                )
        else:
            _reason(reasons, "relationship_assertion_input_kind_mismatch", True)

        if decision_input is None:
            _reason(reasons, "unresolved_relationship_decision_input", True)
        else:
            exact_evidence_refs = tuple(
                sorted(
                    {
                        reference
                        for binding in candidate.evidence_bindings
                        for reference in (
                            *binding.assertion_refs,
                            *binding.artifact_refs,
                        )
                    }
                )
            )
            expected_selected = (
                exact_evidence_refs if decision_input.state == "accepted" else ()
            )
            _reason(
                reasons,
                "relationship_decision_input_continuity_mismatch",
                candidate.assertion_input_id
                not in decision_input.candidate_assertion_ids
                or not _decision_input_shape_is_valid(candidate, decision_input)
                or decision_input.role_bindings != candidate.role_bindings
                or decision_input.policy != request.decision_policy
                or decision_input.selected_evidence_refs != expected_selected,
            )
        return assertion

    @staticmethod
    def _project_direction_probes(
        probes: tuple[RelationshipDirectionProbe, ...],
        current_relationships: list[CurrentRelationshipProjection],
        scenario_rows: dict[str, dict[str, Any]],
        canonical_registry: set[tuple[str, str]],
    ) -> tuple[RelationshipDirectionOutcome, ...]:
        current_by_id = {
            relationship.canonical_relationship_id: relationship
            for relationship in current_relationships
        }
        outcomes: list[RelationshipDirectionOutcome] = []
        for probe in probes:
            row = scenario_rows[probe.scenario_id]
            scenario = probe.scenario_id.removeprefix("traversal_scenario.")
            source_type, separator, target_type = scenario.partition("_to_")
            type_orientation_valid = bool(separator) and (
                probe.source_endpoint.endpoint_type,
                probe.target_endpoint.endpoint_type,
            ) == (source_type, target_type)
            endpoints_registered = all(
                endpoint.reference_kind == "canonical_identity"
                and (
                    endpoint.endpoint_type,
                    cast(str, endpoint.canonical_identity_id),
                )
                in canonical_registry
                for endpoint in (probe.source_endpoint, probe.target_endpoint)
            )
            type_ids_valid = tuple(probe.relationship_type_ids) == tuple(
                row["relationship_type_ids"]
            )
            orientation_valid = (
                type_orientation_valid and endpoints_registered and type_ids_valid
            )
            reasons: list[str] = []
            _reason(
                reasons,
                "direction_orientation_mismatch",
                not type_orientation_valid,
            )
            _reason(
                reasons,
                "canonical_endpoint_not_in_domain_projection",
                not endpoints_registered,
            )
            _reason(
                reasons,
                "direction_relationship_types_mismatch",
                not type_ids_valid,
            )
            projected_ids = tuple(
                sorted(
                    reference
                    for reference in probe.retained_relationship_refs
                    if reference in current_by_id
                )
            )
            outcomes.append(
                RelationshipDirectionOutcome(
                    probe_id=probe.probe_id,
                    scenario_id=probe.scenario_id,
                    orientation_valid=orientation_valid,
                    source_potential_outcome=cast(
                        SourcePotentialOutcome, row["evidence_outcome"]
                    ),
                    available=orientation_valid and bool(projected_ids),
                    projected_relationship_ids=projected_ids,
                    reason_codes=tuple(reasons),
                )
            )
        return tuple(outcomes)

    @staticmethod
    def _project_layer_probes(
        probes: tuple[RelationshipLayerProbe, ...],
    ) -> tuple[RelationshipLayerOutcome, ...]:
        return tuple(
            RelationshipLayerOutcome(
                layer=probe.layer,
                stable_reference=probe.stable_reference,
                canonical_projection_allowed=(
                    probe.layer == "canonical" and bool(probe.evidence_bindings)
                ),
                reason_codes=(
                    ("noncanonical_layer_cannot_project_canonical_fact",)
                    if probe.layer in {"derived", "session"}
                    and probe.attempt_canonical_projection
                    else ()
                ),
            )
            for probe in probes
        )


def create_ephemeral_relationship_projection() -> RelationshipProjection:
    """Return the pure in-process adapter used by builds and contract tests."""
    return _EphemeralRelationshipProjection()


__all__ = [
    "RelationshipAssertion",
    "RelationshipCatalogIdentity",
    "RelationshipDecision",
    "RelationshipDecisionInput",
    "RelationshipDirectionProbe",
    "RelationshipEndpointReference",
    "RelationshipLayerProbe",
    "RelationshipProjection",
    "RelationshipProjectionCandidate",
    "RelationshipProjectionIntegrityError",
    "RelationshipProjectionRequest",
    "RelationshipProjectionResult",
    "RelationshipType",
    "RetainedArtifactReference",
    "RetainedAssertionReference",
    "RetainedEvidenceBinding",
    "SourceCanonicalAssignment",
    "TypedRelationshipAssertionInput",
    "create_ephemeral_relationship_projection",
]
