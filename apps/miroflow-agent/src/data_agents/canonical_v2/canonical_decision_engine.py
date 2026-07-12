"""Reproducible, storage-independent Canonical V2 decision core.

The module keeps deterministic filtering, recorded structured adjudication, and
generic current selections behind one :class:`CanonicalDecisionEngine` seam.
Durable history and typed domain projections are separate adapters/slices.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
import base64
import hashlib
import json
import math
from types import MappingProxyType
from typing import Annotated, Literal, NoReturn, Protocol, cast

from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from .contracts import (
    CanonicalDecision,
    CanonicalIdentity,
    CanonicalIdentityState,
    Confidence,
    ContractModel,
    DecisionMethod,
    DecisionState,
    IdentityReference,
    LLMDecisionTrace,
    NonEmptyStr,
    PolicyKind,
    PolicyReference,
    RelationshipAssertion,
    RelationshipDecision,
    RelationshipDecisionState,
    Sha256,
    SourceAssertion,
    SourceIdentity,
    SourceIdentityState,
)


class CanonicalDecisionEngineError(RuntimeError):
    """Base error for fail-closed canonical decision processing."""


class DecisionBatchIntegrityError(CanonicalDecisionEngineError):
    """A decision batch or derived result violates an integrity invariant."""


class AdjudicationIntegrityError(CanonicalDecisionEngineError):
    """Recorded adjudication bytes do not match their declared identity."""


class AdjudicationOutputError(CanonicalDecisionEngineError):
    """Structured adjudication output is invalid or unsafe to project."""


def _canonical_json_bytes(value: JsonValue) -> bytes:
    """Encode the one canonical JSON representation used for IDs and hashes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _content_sha256(value: JsonValue) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _stable_content_id(prefix: str, value: JsonValue) -> str:
    return f"{prefix}:sha256:{_content_sha256(value)}"


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicates")


def _field_group_key(canonical_identity_id: str, field_path: str) -> str:
    return _stable_content_id(
        "field-group",
        cast(
            JsonValue,
            {
                "canonical_identity_id": canonical_identity_id,
                "field_path": field_path,
            },
        ),
    )


def _relationship_group_key(
    canonical_relationship_id: str,
    relationship_type_id: str,
    relationship_type_version: str,
) -> str:
    return _stable_content_id(
        "relationship-group",
        cast(
            JsonValue,
            {
                "canonical_relationship_id": canonical_relationship_id,
                "relationship_type_id": relationship_type_id,
                "relationship_type_version": relationship_type_version,
            },
        ),
    )


def _decision_group_key(
    decision: CanonicalDecision | RelationshipDecision,
) -> str:
    if isinstance(decision, CanonicalDecision):
        return _field_group_key(
            decision.canonical_identity_id,
            decision.field_path,
        )
    return _relationship_group_key(
        decision.canonical_relationship_id,
        decision.relationship_type_id,
        decision.relationship_type_version,
    )


def _decision_group_manifest_content_sha256(
    *,
    group_key: str,
    assertions: Iterable[SourceAssertion | RelationshipAssertion],
) -> str:
    ordered_assertions = tuple(
        sorted(assertions, key=lambda assertion: assertion.assertion_id)
    )
    return _content_sha256(
        cast(
            JsonValue,
            {
                "group_key": group_key,
                "assertions": [
                    assertion.model_dump(mode="json")
                    for assertion in ordered_assertions
                ],
            },
        )
    )


def _manifest_bound_decision_id(
    *,
    prefix: Literal["field-decision", "relationship-decision"],
    manifest_content_sha256: str,
    seed: JsonValue,
) -> str:
    return (
        f"{prefix}:manifest-sha256:{manifest_content_sha256}:"
        f"seed-sha256:{_content_sha256(seed)}"
    )


def canonical_adjudication_input_sha256(
    *,
    decision_kind: Literal["field", "relationship"],
    subject_id: str,
    path: str,
    assertions: Iterable[SourceAssertion | RelationshipAssertion],
) -> str:
    """Bind adjudication to complete, ordered candidate assertion content."""
    if decision_kind not in {"field", "relationship"}:
        raise DecisionBatchIntegrityError("unsupported adjudication decision kind")
    if not subject_id or subject_id != subject_id.strip():
        raise DecisionBatchIntegrityError("adjudication subject_id must be non-empty")
    if not path or path != path.strip():
        raise DecisionBatchIntegrityError("adjudication path must be non-empty")
    assertion_values = tuple(assertions)
    expected_type = (
        SourceAssertion if decision_kind == "field" else RelationshipAssertion
    )
    if not assertion_values or any(
        not isinstance(assertion, expected_type) for assertion in assertion_values
    ):
        raise DecisionBatchIntegrityError(
            f"{decision_kind} adjudication received the wrong assertion kind"
        )
    assertion_ids = tuple(assertion.assertion_id for assertion in assertion_values)
    if len(assertion_ids) != len(set(assertion_ids)):
        raise DecisionBatchIntegrityError(
            "adjudication assertions contain duplicate assertion IDs"
        )
    ordered_assertions = tuple(
        sorted(assertion_values, key=lambda assertion: assertion.assertion_id)
    )
    payload = cast(
        JsonValue,
        {
            "decision_kind": decision_kind,
            "subject_id": subject_id,
            "path": path,
            "assertions": [
                assertion.model_dump(mode="json") for assertion in ordered_assertions
            ],
        },
    )
    try:
        return _content_sha256(payload)
    except (TypeError, UnicodeError, ValueError) as exc:
        raise DecisionBatchIntegrityError(
            "adjudication assertion content is not canonical JSON"
        ) from exc


def _canonical_decision_input_sha256(
    *,
    decision_kind: Literal["field", "relationship"],
    subject_id: str,
    path: str,
    assertions: tuple[SourceAssertion, ...] | tuple[RelationshipAssertion, ...],
    canonical_identities: tuple[CanonicalIdentityConstraintContext, ...],
    source_identities: Mapping[str, SourceIdentity],
) -> str:
    if decision_kind == "field":
        field_assertions = cast(tuple[SourceAssertion, ...], assertions)
        referenced_source_ids = {
            assertion.source_identity_id for assertion in field_assertions
        }
    else:
        relationship_assertions = cast(tuple[RelationshipAssertion, ...], assertions)
        referenced_source_ids = {
            identity_id
            for assertion in relationship_assertions
            for identity_id in (
                assertion.source_endpoint.identity_id,
                assertion.target_endpoint.identity_id,
            )
        }
    payload = cast(
        JsonValue,
        {
            "adjudication_input_sha256": canonical_adjudication_input_sha256(
                decision_kind=decision_kind,
                subject_id=subject_id,
                path=path,
                assertions=assertions,
            ),
            "canonical_identities": [
                identity.model_dump(mode="json")
                for identity in sorted(
                    canonical_identities,
                    key=lambda identity: identity.canonical_identity_id,
                )
            ],
            "source_identities": [
                source_identities[source_identity_id].model_dump(mode="json")
                for source_identity_id in sorted(referenced_source_ids)
                if source_identity_id in source_identities
            ],
        },
    )
    return _content_sha256(payload)


class CanonicalIdentityConstraintContext(ContractModel):
    """Minimal canonical identity snapshot needed by deterministic constraints."""

    canonical_identity_id: NonEmptyStr
    entity_type: NonEmptyStr
    state: CanonicalIdentityState
    source_identity_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("source_identity_ids")
    @classmethod
    def normalize_source_identity_ids(
        cls, source_identity_ids: tuple[str, ...]
    ) -> tuple[str, ...]:
        _require_unique(source_identity_ids, "canonical context source identity IDs")
        return tuple(sorted(source_identity_ids))


def _canonical_constraint_context(
    identity: CanonicalIdentity,
) -> CanonicalIdentityConstraintContext:
    return CanonicalIdentityConstraintContext(
        canonical_identity_id=identity.canonical_identity_id,
        entity_type=identity.entity_type,
        state=identity.state,
        source_identity_ids=identity.source_identity_ids,
    )


class FieldAssertionGroup(ContractModel):
    canonical_identity_id: NonEmptyStr
    field_path: NonEmptyStr
    assertions: tuple[SourceAssertion, ...] = Field(min_length=1)
    policy: PolicyReference

    @field_validator("assertions")
    @classmethod
    def sort_assertions(
        cls, assertions: tuple[SourceAssertion, ...]
    ) -> tuple[SourceAssertion, ...]:
        _require_unique(
            tuple(assertion.assertion_id for assertion in assertions),
            "field assertion IDs",
        )
        return tuple(sorted(assertions, key=lambda assertion: assertion.assertion_id))

    @model_validator(mode="after")
    def validate_policy(self) -> FieldAssertionGroup:
        if self.policy.policy_kind is not PolicyKind.field_selection:
            raise ValueError("field assertion group requires a field-selection policy")
        return self


class RelationshipAssertionGroup(ContractModel):
    canonical_relationship_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    relationship_type_version: NonEmptyStr
    source_canonical_identity_id: NonEmptyStr
    target_canonical_identity_id: NonEmptyStr
    assertions: tuple[RelationshipAssertion, ...] = Field(min_length=1)
    policy: PolicyReference

    @field_validator("assertions")
    @classmethod
    def sort_assertions(
        cls, assertions: tuple[RelationshipAssertion, ...]
    ) -> tuple[RelationshipAssertion, ...]:
        _require_unique(
            tuple(assertion.assertion_id for assertion in assertions),
            "relationship assertion IDs",
        )
        return tuple(sorted(assertions, key=lambda assertion: assertion.assertion_id))

    @model_validator(mode="after")
    def validate_policy(self) -> RelationshipAssertionGroup:
        if self.policy.policy_kind is not PolicyKind.relationship:
            raise ValueError(
                "relationship assertion group requires a relationship policy"
            )
        return self


class DecisionBatchRequest(ContractModel):
    release_id: NonEmptyStr
    decision_run_id: NonEmptyStr
    decision_method_version: NonEmptyStr
    as_of: AwareDatetime
    source_identities: tuple[SourceIdentity, ...]
    canonical_identities: tuple[CanonicalIdentity, ...]
    field_groups: tuple[FieldAssertionGroup, ...] = ()
    relationship_groups: tuple[RelationshipAssertionGroup, ...] = ()

    @field_validator("source_identities")
    @classmethod
    def normalize_source_identities(
        cls, identities: tuple[SourceIdentity, ...]
    ) -> tuple[SourceIdentity, ...]:
        normalized = tuple(
            identity.model_copy(
                update={"source_record_ids": tuple(sorted(identity.source_record_ids))},
                deep=True,
            )
            for identity in identities
        )
        return tuple(
            sorted(normalized, key=lambda identity: identity.source_identity_id)
        )

    @field_validator("canonical_identities")
    @classmethod
    def normalize_canonical_identities(
        cls, identities: tuple[CanonicalIdentity, ...]
    ) -> tuple[CanonicalIdentity, ...]:
        normalized = tuple(
            identity.model_copy(
                update={
                    "source_identity_ids": tuple(sorted(identity.source_identity_ids)),
                    "predecessor_identity_ids": tuple(
                        sorted(identity.predecessor_identity_ids)
                    ),
                    "successor_identity_ids": tuple(
                        sorted(identity.successor_identity_ids)
                    ),
                },
                deep=True,
            )
            for identity in identities
        )
        return tuple(
            sorted(normalized, key=lambda identity: identity.canonical_identity_id)
        )

    @field_validator("field_groups")
    @classmethod
    def sort_field_groups(
        cls, groups: tuple[FieldAssertionGroup, ...]
    ) -> tuple[FieldAssertionGroup, ...]:
        return tuple(
            sorted(
                groups,
                key=lambda group: (group.canonical_identity_id, group.field_path),
            )
        )

    @field_validator("relationship_groups")
    @classmethod
    def sort_relationship_groups(
        cls, groups: tuple[RelationshipAssertionGroup, ...]
    ) -> tuple[RelationshipAssertionGroup, ...]:
        return tuple(sorted(groups, key=lambda group: group.canonical_relationship_id))

    @model_validator(mode="after")
    def validate_batch_integrity(self) -> DecisionBatchRequest:
        source_ids = tuple(
            identity.source_identity_id for identity in self.source_identities
        )
        canonical_ids = tuple(
            identity.canonical_identity_id for identity in self.canonical_identities
        )
        _require_unique(source_ids, "source identity IDs")
        _require_unique(canonical_ids, "canonical identity IDs")
        source_id_set = set(source_ids)
        owner_by_source_identity: dict[str, str] = {}
        for identity in self.canonical_identities:
            if identity.release_id != self.release_id:
                raise ValueError(
                    "canonical identity release_id must equal the decision batch release_id"
                )
            for source_identity_id in identity.source_identity_ids:
                if source_identity_id not in source_id_set:
                    raise ValueError(
                        "canonical identity references an unknown source identity: "
                        f"{source_identity_id}"
                    )
                prior_owner = owner_by_source_identity.setdefault(
                    source_identity_id, identity.canonical_identity_id
                )
                if prior_owner != identity.canonical_identity_id:
                    raise ValueError(
                        "a source identity cannot belong to multiple canonical identities"
                    )

        canonical_id_set = set(canonical_ids)
        field_group_keys = tuple(
            (group.canonical_identity_id, group.field_path)
            for group in self.field_groups
        )
        if len(field_group_keys) != len(set(field_group_keys)):
            raise ValueError(
                "field assertion groups must be unique by identity and path"
            )
        relationship_group_ids = tuple(
            group.canonical_relationship_id for group in self.relationship_groups
        )
        _require_unique(relationship_group_ids, "canonical relationship group IDs")

        assertion_ids: list[str] = []
        for group in self.field_groups:
            if group.canonical_identity_id not in canonical_id_set:
                raise ValueError(
                    "field assertion group references an unknown canonical identity"
                )
            assertion_ids.extend(
                assertion.assertion_id for assertion in group.assertions
            )
        for group in self.relationship_groups:
            if (
                group.source_canonical_identity_id not in canonical_id_set
                or group.target_canonical_identity_id not in canonical_id_set
            ):
                raise ValueError(
                    "relationship assertion group references an unknown canonical identity"
                )
            assertion_ids.extend(
                assertion.assertion_id for assertion in group.assertions
            )
        _require_unique(tuple(assertion_ids), "batch assertion IDs")
        return self


class ConstraintOutcome(ContractModel):
    release_id: NonEmptyStr
    decision_id: NonEmptyStr
    assertion_id: NonEmptyStr
    group_key: NonEmptyStr
    admitted: bool
    reason_codes: tuple[NonEmptyStr, ...]
    policy_version: NonEmptyStr

    @field_validator("reason_codes")
    @classmethod
    def sort_reason_codes(cls, reason_codes: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(reason_codes, "constraint reason codes")
        return tuple(sorted(reason_codes))

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> ConstraintOutcome:
        if self.admitted == bool(self.reason_codes):
            raise ValueError(
                "admitted outcomes require no reason code and rejected outcomes require one"
            )
        return self


class DecisionGroupManifest(ContractModel):
    decision_id: NonEmptyStr
    group_key: NonEmptyStr
    assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    content_sha256: Sha256

    @field_validator("assertion_ids")
    @classmethod
    def sort_assertion_ids(cls, assertion_ids: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(assertion_ids, "decision group manifest assertion IDs")
        return tuple(sorted(assertion_ids))


class CurrentFieldSelection(ContractModel):
    release_id: NonEmptyStr
    canonical_identity_id: NonEmptyStr
    field_path: NonEmptyStr
    value: JsonValue
    decision_id: NonEmptyStr
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    conflicting_assertion_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_roles(self) -> CurrentFieldSelection:
        _require_unique(self.supporting_assertion_ids, "supporting assertion IDs")
        _require_unique(self.conflicting_assertion_ids, "conflicting assertion IDs")
        if set(self.supporting_assertion_ids) & set(self.conflicting_assertion_ids):
            raise ValueError(
                "supporting and conflicting assertion IDs must be disjoint"
            )
        return self


class CurrentRelationshipSelection(ContractModel):
    release_id: NonEmptyStr
    canonical_relationship_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    relationship_type_version: NonEmptyStr
    source_canonical_identity_id: NonEmptyStr
    target_canonical_identity_id: NonEmptyStr
    role_bindings: dict[NonEmptyStr, NonEmptyStr]
    decision_id: NonEmptyStr
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    conflicting_assertion_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_roles(self) -> CurrentRelationshipSelection:
        _require_unique(self.supporting_assertion_ids, "supporting assertion IDs")
        _require_unique(self.conflicting_assertion_ids, "conflicting assertion IDs")
        if set(self.supporting_assertion_ids) & set(self.conflicting_assertion_ids):
            raise ValueError(
                "supporting and conflicting assertion IDs must be disjoint"
            )
        return self


class UnresolvedConflict(ContractModel):
    release_id: NonEmptyStr
    decision_id: NonEmptyStr
    subject_id: NonEmptyStr
    path: NonEmptyStr
    assertion_ids: tuple[NonEmptyStr, ...]

    @field_validator("assertion_ids")
    @classmethod
    def sort_assertion_ids(cls, assertion_ids: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(assertion_ids, "unresolved assertion IDs")
        return tuple(sorted(assertion_ids))


class _DecisionBatchContent(ContractModel):
    release_id: NonEmptyStr
    decision_run_id: NonEmptyStr
    as_of: AwareDatetime
    canonical_identity_contexts: tuple[CanonicalIdentityConstraintContext, ...]
    source_identity_contexts: tuple[SourceIdentity, ...]
    field_assertions: tuple[SourceAssertion, ...]
    relationship_assertions: tuple[RelationshipAssertion, ...]
    canonical_decisions: tuple[CanonicalDecision, ...]
    relationship_decisions: tuple[RelationshipDecision, ...]
    decision_group_manifests: tuple[DecisionGroupManifest, ...]
    constraint_outcomes: tuple[ConstraintOutcome, ...]
    current_fields: tuple[CurrentFieldSelection, ...]
    current_relationships: tuple[CurrentRelationshipSelection, ...]
    unresolved_conflicts: tuple[UnresolvedConflict, ...]

    @field_validator("canonical_identity_contexts")
    @classmethod
    def normalize_canonical_contexts(
        cls,
        contexts: tuple[CanonicalIdentityConstraintContext, ...],
    ) -> tuple[CanonicalIdentityConstraintContext, ...]:
        _require_unique(
            tuple(context.canonical_identity_id for context in contexts),
            "canonical identity context IDs",
        )
        return tuple(
            sorted(contexts, key=lambda context: context.canonical_identity_id)
        )

    @field_validator("source_identity_contexts")
    @classmethod
    def normalize_source_contexts(
        cls, contexts: tuple[SourceIdentity, ...]
    ) -> tuple[SourceIdentity, ...]:
        normalized = tuple(
            context.model_copy(
                update={"source_record_ids": tuple(sorted(context.source_record_ids))},
                deep=True,
            )
            for context in contexts
        )
        _require_unique(
            tuple(context.source_identity_id for context in normalized),
            "source identity context IDs",
        )
        return tuple(sorted(normalized, key=lambda context: context.source_identity_id))


def _validate_decision_assertion_families(
    *,
    field_assertions: Mapping[str, SourceAssertion],
    relationship_assertions: Mapping[str, RelationshipAssertion],
    field_decisions: Mapping[str, CanonicalDecision],
    relationship_decisions: Mapping[str, RelationshipDecision],
) -> None:
    for decision in field_decisions.values():
        evidence_ids = (
            *decision.candidate_assertion_ids,
            *decision.selected_assertion_ids,
            *decision.conflicting_assertion_ids,
        )
        if any(assertion_id not in field_assertions for assertion_id in evidence_ids):
            raise ValueError(
                "field decision evidence must reference retained field assertions"
            )
        if any(
            field_assertions[assertion_id].field_path != decision.field_path
            for assertion_id in decision.candidate_assertion_ids
        ):
            raise ValueError(
                "field decision candidates must match the decision field path"
            )
    for decision in relationship_decisions.values():
        evidence_ids = (
            *decision.candidate_assertion_ids,
            *decision.selected_assertion_ids,
            *decision.conflicting_assertion_ids,
        )
        if any(
            assertion_id not in relationship_assertions for assertion_id in evidence_ids
        ):
            raise ValueError(
                "relationship decision evidence must reference retained relationship "
                "assertions"
            )
        if any(
            relationship_assertions[assertion_id].relationship_type_id
            != decision.relationship_type_id
            or relationship_assertions[assertion_id].relationship_type_version
            != decision.relationship_type_version
            for assertion_id in decision.candidate_assertion_ids
        ):
            raise ValueError(
                "relationship decision candidates must match its type and version"
            )


def _validate_logical_decision_context(
    *,
    decision_run_id: str,
    as_of: datetime,
    field_decisions: tuple[CanonicalDecision, ...],
    relationship_decisions: tuple[RelationshipDecision, ...],
) -> None:
    field_keys = tuple(
        (decision.canonical_identity_id, decision.field_path)
        for decision in field_decisions
    )
    if len(field_keys) != len(set(field_keys)):
        raise ValueError(
            "logical field decisions must be unique by canonical identity and path"
        )
    relationship_keys = tuple(
        decision.canonical_relationship_id for decision in relationship_decisions
    )
    if len(relationship_keys) != len(set(relationship_keys)):
        raise ValueError(
            "logical relationship decisions must have unique canonical relationship IDs"
        )
    for decision in (*field_decisions, *relationship_decisions):
        if decision.decision_run_id != decision_run_id:
            raise ValueError("decision_run_id must exactly match the result batch run")
        if decision.decided_at != as_of:
            raise ValueError("decision decided_at must exactly match result as_of")


def _validated_trace_output(
    decision: CanonicalDecision | RelationshipDecision,
) -> _StructuredAdjudicationOutput:
    trace = decision.llm_trace
    if trace is None:
        raise ValueError("structured decision requires a content-bound trace")
    try:
        raw_output = base64.b64decode(trace.raw_output_base64, validate=True)
        output, _ = _parse_structured_output(raw_output)
        _validate_output_roles(output, decision.candidate_assertion_ids)
    except (CanonicalDecisionEngineError, ValueError) as exc:
        raise ValueError(
            "structured decision trace output failed strict semantic validation"
        ) from exc
    return output


def _validate_structured_trace_semantics(
    *,
    field_decisions: Mapping[str, CanonicalDecision],
    relationship_decisions: Mapping[str, RelationshipDecision],
) -> None:
    for decision in field_decisions.values():
        if decision.method is not DecisionMethod.structured_llm:
            continue
        output = _validated_trace_output(decision)
        expected_state = (
            DecisionState.selected
            if output.state == "selected"
            else DecisionState.unresolved
        )
        if decision.state is not expected_state:
            raise ValueError("structured field trace state must match its decision")
        if tuple(sorted(output.selected_assertion_ids)) != (
            decision.selected_assertion_ids
        ):
            raise ValueError(
                "structured field trace selected assertions must match its decision"
            )
        if tuple(sorted(output.conflicting_assertion_ids)) != (
            decision.conflicting_assertion_ids
        ):
            raise ValueError(
                "structured field trace conflicting assertions must match its decision"
            )
        if output.confidence != decision.confidence:
            raise ValueError(
                "structured field trace confidence must match its decision"
            )
        if output.rationale != decision.rationale:
            raise ValueError("structured field trace rationale must match its decision")
        if output.role_bindings is not None:
            raise ValueError("structured field trace cannot contain role bindings")

    for decision in relationship_decisions.values():
        if decision.method is not DecisionMethod.structured_llm:
            continue
        output = _validated_trace_output(decision)
        expected_state = (
            RelationshipDecisionState.accepted
            if output.state == "selected"
            else RelationshipDecisionState.unresolved
        )
        if decision.state is not expected_state:
            raise ValueError(
                "structured relationship trace state must match its decision"
            )
        if tuple(sorted(output.selected_assertion_ids)) != (
            decision.selected_assertion_ids
        ):
            raise ValueError(
                "structured relationship trace selected assertions must match its "
                "decision"
            )
        if tuple(sorted(output.conflicting_assertion_ids)) != (
            decision.conflicting_assertion_ids
        ):
            raise ValueError(
                "structured relationship trace conflicting assertions must match "
                "its decision"
            )
        if output.confidence != decision.confidence:
            raise ValueError(
                "structured relationship trace confidence must match its decision"
            )
        if output.rationale != decision.rationale:
            raise ValueError(
                "structured relationship trace rationale must match its decision"
            )
        if decision.state is RelationshipDecisionState.accepted:
            if output.role_bindings != decision.role_bindings:
                raise ValueError(
                    "structured relationship trace role bindings must match its "
                    "decision"
                )
        elif output.role_bindings not in (None, {}) or decision.role_bindings:
            raise ValueError(
                "structured unresolved relationship trace and decision require "
                "empty role bindings"
            )


def _validate_manifest_bound_decision_id(
    *,
    decision_id: str,
    decision_kind: Literal["field", "relationship"],
    manifest_content_sha256: str,
) -> None:
    prefix = "field-decision" if decision_kind == "field" else "relationship-decision"
    expected_prefix = f"{prefix}:manifest-sha256:{manifest_content_sha256}:seed-sha256:"
    if not decision_id.startswith(expected_prefix):
        raise ValueError(
            f"{decision_kind} decision ID must bind its group manifest content hash"
        )
    seed_sha256 = decision_id.removeprefix(expected_prefix)
    if len(seed_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in seed_sha256
    ):
        raise ValueError(
            f"{decision_kind} decision ID requires one canonical seed SHA-256"
        )


def _validate_decision_group_manifests(
    *,
    field_assertions: Mapping[str, SourceAssertion],
    relationship_assertions: Mapping[str, RelationshipAssertion],
    field_decisions: Mapping[str, CanonicalDecision],
    relationship_decisions: Mapping[str, RelationshipDecision],
    manifests: tuple[DecisionGroupManifest, ...],
) -> dict[str, DecisionGroupManifest]:
    manifest_decision_ids = tuple(manifest.decision_id for manifest in manifests)
    _require_unique(manifest_decision_ids, "decision group manifest decision IDs")
    all_decision_ids = set(field_decisions) | set(relationship_decisions)
    if set(manifest_decision_ids) != all_decision_ids:
        raise ValueError("every decision requires exactly one decision group manifest")

    manifest_assertion_ids = tuple(
        assertion_id
        for manifest in manifests
        for assertion_id in manifest.assertion_ids
    )
    all_assertion_ids = set(field_assertions) | set(relationship_assertions)
    if (
        len(manifest_assertion_ids) != len(set(manifest_assertion_ids))
        or set(manifest_assertion_ids) != all_assertion_ids
    ):
        raise ValueError(
            "decision group manifests must partition every retained assertion "
            "exactly once"
        )

    manifests_by_decision = {manifest.decision_id: manifest for manifest in manifests}
    for manifest in manifests:
        field_decision = field_decisions.get(manifest.decision_id)
        if field_decision is not None:
            decision: CanonicalDecision | RelationshipDecision = field_decision
            decision_kind: Literal["field", "relationship"] = "field"
            assertions: tuple[SourceAssertion | RelationshipAssertion, ...] = tuple(
                field_assertions[assertion_id]
                for assertion_id in manifest.assertion_ids
                if assertion_id in field_assertions
            )
            if len(assertions) != len(manifest.assertion_ids):
                raise ValueError(
                    "field decision group manifest may contain only field assertions"
                )
        else:
            decision = relationship_decisions[manifest.decision_id]
            decision_kind = "relationship"
            assertions = tuple(
                relationship_assertions[assertion_id]
                for assertion_id in manifest.assertion_ids
                if assertion_id in relationship_assertions
            )
            if len(assertions) != len(manifest.assertion_ids):
                raise ValueError(
                    "relationship decision group manifest may contain only "
                    "relationship assertions"
                )

        expected_group_key = _decision_group_key(decision)
        if manifest.group_key != expected_group_key:
            raise ValueError(
                f"{decision_kind} decision group manifest must match its decision "
                "group key and type"
            )
        _validate_manifest_bound_decision_id(
            decision_id=decision.decision_id,
            decision_kind=decision_kind,
            manifest_content_sha256=manifest.content_sha256,
        )
        expected_content_sha256 = _decision_group_manifest_content_sha256(
            group_key=manifest.group_key,
            assertions=assertions,
        )
        if manifest.content_sha256 != expected_content_sha256:
            raise ValueError(
                "decision group manifest content hash must bind its complete "
                "assertion models"
            )
    return manifests_by_decision


def _validate_constraint_outcome_links(
    *,
    field_assertions: Mapping[str, SourceAssertion],
    relationship_assertions: Mapping[str, RelationshipAssertion],
    field_decisions: Mapping[str, CanonicalDecision],
    relationship_decisions: Mapping[str, RelationshipDecision],
    manifests_by_decision: Mapping[str, DecisionGroupManifest],
    outcomes: tuple[ConstraintOutcome, ...],
) -> None:
    outcome_assertion_ids = tuple(outcome.assertion_id for outcome in outcomes)
    _require_unique(outcome_assertion_ids, "constraint outcome assertion IDs")
    all_assertion_ids = set(field_assertions) | set(relationship_assertions)
    if set(outcome_assertion_ids) != all_assertion_ids:
        raise ValueError("every retained assertion requires exactly one outcome")

    linked_decision_ids: set[str] = set()
    for outcome in outcomes:
        if outcome.assertion_id in field_assertions:
            decision = field_decisions.get(outcome.decision_id)
            if decision is None:
                raise ValueError(
                    "field outcome must link its assertion to a field decision"
                )
        else:
            decision = relationship_decisions.get(outcome.decision_id)
            if decision is None:
                raise ValueError(
                    "relationship outcome must link its assertion to a relationship "
                    "decision"
                )
        linked_decision_ids.add(decision.decision_id)
        manifest = manifests_by_decision[decision.decision_id]
        if outcome.assertion_id not in manifest.assertion_ids:
            raise ValueError(
                "outcome assertion must belong to its linked decision group manifest"
            )
        if (
            outcome.group_key != manifest.group_key
            or outcome.group_key != _decision_group_key(decision)
        ):
            raise ValueError(
                "outcome group_key must match its linked decision group manifest"
            )
        admitted_by_decision = outcome.assertion_id in decision.candidate_assertion_ids
        if outcome.admitted is not admitted_by_decision:
            raise ValueError(
                "outcome admitted state must exactly match decision candidate evidence"
            )
        if outcome.policy_version != decision.policy.policy_version:
            raise ValueError(
                "outcome policy_version must equal its linked decision policy version"
            )

    all_decision_ids = set(field_decisions) | set(relationship_decisions)
    if linked_decision_ids != all_decision_ids:
        raise ValueError("every decision requires at least one linked outcome")


def _validate_current_selections(
    *,
    field_assertions: Mapping[str, SourceAssertion],
    field_decisions: Mapping[str, CanonicalDecision],
    relationship_decisions: Mapping[str, RelationshipDecision],
    current_fields: tuple[CurrentFieldSelection, ...],
    current_relationships: tuple[CurrentRelationshipSelection, ...],
) -> None:
    current_decision_ids = tuple(
        current.decision_id for current in (*current_fields, *current_relationships)
    )
    _require_unique(current_decision_ids, "current selection decision IDs")

    expected_field_ids = {
        decision.decision_id
        for decision in field_decisions.values()
        if decision.state is DecisionState.selected
    }
    if {current.decision_id for current in current_fields} != expected_field_ids:
        raise ValueError(
            "selected field decisions and current field selections must match"
        )
    expected_relationship_ids = {
        decision.decision_id
        for decision in relationship_decisions.values()
        if decision.state is RelationshipDecisionState.accepted
    }
    if {
        current.decision_id for current in current_relationships
    } != expected_relationship_ids:
        raise ValueError(
            "accepted relationship decisions and current relationships must match"
        )

    for current in current_fields:
        decision = field_decisions.get(current.decision_id)
        if decision is None or decision.state is not DecisionState.selected:
            raise ValueError("current field must link a selected field decision")
        if (
            current.canonical_identity_id != decision.canonical_identity_id
            or current.field_path != decision.field_path
        ):
            raise ValueError(
                "current field subject and path must exactly match its decision"
            )
        if current.supporting_assertion_ids != decision.selected_assertion_ids:
            raise ValueError(
                "current field support must exactly match decision-selected assertions"
            )
        if current.conflicting_assertion_ids != decision.conflicting_assertion_ids:
            raise ValueError(
                "current field conflicts must exactly match decision conflicts"
            )
        selected_values = tuple(
            field_assertions[assertion_id].value
            for assertion_id in decision.selected_assertion_ids
        )
        if not selected_values or any(
            not _strict_json_equal(current.value, value) for value in selected_values
        ):
            raise ValueError(
                "current field value must strictly equal every selected assertion value"
            )

    for current in current_relationships:
        decision = relationship_decisions.get(current.decision_id)
        if decision is None or decision.state is not RelationshipDecisionState.accepted:
            raise ValueError(
                "current relationship must link an accepted relationship decision"
            )
        if (
            current.canonical_relationship_id != decision.canonical_relationship_id
            or current.relationship_type_id != decision.relationship_type_id
            or current.relationship_type_version != decision.relationship_type_version
            or current.source_canonical_identity_id
            != decision.source_canonical_identity_id
            or current.target_canonical_identity_id
            != decision.target_canonical_identity_id
        ):
            raise ValueError(
                "current relationship identity, type, version, and endpoints must "
                "exactly match its decision"
            )
        if current.role_bindings != decision.role_bindings:
            raise ValueError(
                "current relationship role bindings must exactly match its decision"
            )
        if current.supporting_assertion_ids != decision.selected_assertion_ids:
            raise ValueError(
                "current relationship support must exactly match decision-selected "
                "assertions"
            )
        if current.conflicting_assertion_ids != decision.conflicting_assertion_ids:
            raise ValueError(
                "current relationship conflicts must exactly match decision conflicts"
            )


def _validate_unresolved_conflicts(
    *,
    field_decisions: Mapping[str, CanonicalDecision],
    relationship_decisions: Mapping[str, RelationshipDecision],
    conflicts: tuple[UnresolvedConflict, ...],
) -> None:
    conflict_decision_ids = tuple(conflict.decision_id for conflict in conflicts)
    _require_unique(conflict_decision_ids, "unresolved conflict decision IDs")
    expected_ids = {
        decision.decision_id
        for decision in field_decisions.values()
        if decision.state is DecisionState.unresolved
    } | {
        decision.decision_id
        for decision in relationship_decisions.values()
        if decision.state is RelationshipDecisionState.unresolved
    }
    if set(conflict_decision_ids) != expected_ids:
        raise ValueError("every unresolved decision requires exactly one conflict")

    for conflict in conflicts:
        field_decision = field_decisions.get(conflict.decision_id)
        if field_decision is not None:
            if (
                conflict.subject_id != field_decision.canonical_identity_id
                or conflict.path != field_decision.field_path
            ):
                raise ValueError(
                    "field conflict subject and path must exactly match its decision"
                )
            expected_assertion_ids = field_decision.conflicting_assertion_ids
        else:
            relationship_decision = relationship_decisions[conflict.decision_id]
            if (
                conflict.subject_id != relationship_decision.canonical_relationship_id
                or conflict.path != relationship_decision.relationship_type_id
            ):
                raise ValueError(
                    "relationship conflict subject and path must exactly match its "
                    "decision"
                )
            expected_assertion_ids = relationship_decision.conflicting_assertion_ids
        if conflict.assertion_ids != expected_assertion_ids:
            raise ValueError(
                "unresolved conflict assertions must exactly match decision conflicts"
            )


def _validate_identity_contexts_and_determinism(
    *,
    as_of: datetime,
    canonical_contexts: tuple[CanonicalIdentityConstraintContext, ...],
    source_contexts: tuple[SourceIdentity, ...],
    field_assertions: Mapping[str, SourceAssertion],
    relationship_assertions: Mapping[str, RelationshipAssertion],
    field_decisions: Mapping[str, CanonicalDecision],
    relationship_decisions: Mapping[str, RelationshipDecision],
    manifests_by_decision: Mapping[str, DecisionGroupManifest],
    outcomes: tuple[ConstraintOutcome, ...],
) -> None:
    canonical_by_id = {
        context.canonical_identity_id: context for context in canonical_contexts
    }
    source_by_id = {context.source_identity_id: context for context in source_contexts}
    expected_canonical_ids = {
        decision.canonical_identity_id for decision in field_decisions.values()
    } | {
        canonical_identity_id
        for decision in relationship_decisions.values()
        for canonical_identity_id in (
            decision.source_canonical_identity_id,
            decision.target_canonical_identity_id,
        )
    }
    if set(canonical_by_id) != expected_canonical_ids:
        raise ValueError(
            "canonical identity contexts must exactly cover every decision subject "
            "and endpoint"
        )

    referenced_source_ids = {
        assertion.source_identity_id for assertion in field_assertions.values()
    } | {
        source_identity_id
        for assertion in relationship_assertions.values()
        for source_identity_id in (
            assertion.source_endpoint.identity_id,
            assertion.target_endpoint.identity_id,
        )
    }
    if not set(source_by_id) <= referenced_source_ids:
        raise ValueError(
            "source identity contexts may contain only assertion-referenced identities"
        )

    owner_by_source_id: dict[str, str] = {}
    for context in canonical_contexts:
        for source_identity_id in context.source_identity_ids:
            prior_owner = owner_by_source_id.setdefault(
                source_identity_id, context.canonical_identity_id
            )
            if prior_owner != context.canonical_identity_id:
                raise ValueError(
                    "identity context cannot assign one source identity to multiple "
                    "canonical owners"
                )

    outcomes_by_assertion = {outcome.assertion_id: outcome for outcome in outcomes}

    for decision in field_decisions.values():
        manifest = manifests_by_decision[decision.decision_id]
        assertions = tuple(
            field_assertions[assertion_id] for assertion_id in manifest.assertion_ids
        )
        canonical_context = canonical_by_id[decision.canonical_identity_id]
        group = FieldAssertionGroup(
            canonical_identity_id=decision.canonical_identity_id,
            field_path=decision.field_path,
            assertions=assertions,
            policy=decision.policy,
        )
        evaluations = tuple(
            _ConstraintEvaluation(
                assertion_id=assertion.assertion_id,
                admitted=(
                    reason := _field_rejection_reason(
                        assertion=assertion,
                        group=group,
                        canonical_identity=canonical_context,
                        source_identities=source_by_id,
                        as_of=as_of,
                    )
                )
                is None,
                reason_codes=() if reason is None else (reason,),
            )
            for assertion in assertions
        )
        _require_exact_deterministic_outcomes(
            evaluations=evaluations,
            outcomes_by_assertion=outcomes_by_assertion,
        )
        decision_input_sha256 = _canonical_decision_input_sha256(
            decision_kind="field",
            subject_id=decision.canonical_identity_id,
            path=decision.field_path,
            assertions=assertions,
            canonical_identities=(canonical_context,),
            source_identities=source_by_id,
        )
        expected_decision_id = _manifest_bound_decision_id(
            prefix="field-decision",
            manifest_content_sha256=manifest.content_sha256,
            seed=_decision_seed(
                decision=decision,
                evaluations=evaluations,
                decision_input_sha256=decision_input_sha256,
                manifest_content_sha256=manifest.content_sha256,
            ),
        )
        if decision.decision_id != expected_decision_id:
            raise ValueError(
                "field decision ID must equal its complete canonical seed hash"
            )

    for decision in relationship_decisions.values():
        manifest = manifests_by_decision[decision.decision_id]
        assertions = tuple(
            relationship_assertions[assertion_id]
            for assertion_id in manifest.assertion_ids
        )
        source_canonical_context = canonical_by_id[
            decision.source_canonical_identity_id
        ]
        target_canonical_context = canonical_by_id[
            decision.target_canonical_identity_id
        ]
        group = RelationshipAssertionGroup(
            canonical_relationship_id=decision.canonical_relationship_id,
            relationship_type_id=decision.relationship_type_id,
            relationship_type_version=decision.relationship_type_version,
            source_canonical_identity_id=decision.source_canonical_identity_id,
            target_canonical_identity_id=decision.target_canonical_identity_id,
            assertions=assertions,
            policy=decision.policy,
        )
        evaluations = tuple(
            _ConstraintEvaluation(
                assertion_id=assertion.assertion_id,
                admitted=(
                    reason := _relationship_rejection_reason(
                        assertion=assertion,
                        group=group,
                        source_canonical_identity=source_canonical_context,
                        target_canonical_identity=target_canonical_context,
                        source_identities=source_by_id,
                        as_of=as_of,
                    )
                )
                is None,
                reason_codes=() if reason is None else (reason,),
            )
            for assertion in assertions
        )
        _require_exact_deterministic_outcomes(
            evaluations=evaluations,
            outcomes_by_assertion=outcomes_by_assertion,
        )
        decision_input_sha256 = _canonical_decision_input_sha256(
            decision_kind="relationship",
            subject_id=decision.canonical_relationship_id,
            path=decision.relationship_type_id,
            assertions=assertions,
            canonical_identities=(
                source_canonical_context,
                target_canonical_context,
            ),
            source_identities=source_by_id,
        )
        expected_decision_id = _manifest_bound_decision_id(
            prefix="relationship-decision",
            manifest_content_sha256=manifest.content_sha256,
            seed=_decision_seed(
                decision=decision,
                evaluations=evaluations,
                decision_input_sha256=decision_input_sha256,
                manifest_content_sha256=manifest.content_sha256,
            ),
        )
        if decision.decision_id != expected_decision_id:
            raise ValueError(
                "relationship decision ID must equal its complete canonical seed hash"
            )


def _require_exact_deterministic_outcomes(
    *,
    evaluations: tuple[_ConstraintEvaluation, ...],
    outcomes_by_assertion: Mapping[str, ConstraintOutcome],
) -> None:
    for evaluation in evaluations:
        outcome = outcomes_by_assertion.get(evaluation.assertion_id)
        if outcome is None or (
            outcome.admitted is not evaluation.admitted
            or outcome.reason_codes != evaluation.reason_codes
        ):
            raise ValueError(
                "deterministic outcome must exactly match identity and constraint "
                "evaluation"
            )


class DecisionBatchResult(_DecisionBatchContent):
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_result_integrity(self) -> DecisionBatchResult:
        field_assertion_ids = tuple(
            assertion.assertion_id for assertion in self.field_assertions
        )
        relationship_assertion_ids = tuple(
            assertion.assertion_id for assertion in self.relationship_assertions
        )
        _require_unique(
            (*field_assertion_ids, *relationship_assertion_ids),
            "result assertion IDs",
        )
        field_assertions = {
            assertion.assertion_id: assertion for assertion in self.field_assertions
        }
        relationship_assertions = {
            assertion.assertion_id: assertion
            for assertion in self.relationship_assertions
        }
        decision_ids = tuple(
            decision.decision_id
            for decision in (*self.canonical_decisions, *self.relationship_decisions)
        )
        _require_unique(decision_ids, "result decision IDs")
        field_decisions = {
            decision.decision_id: decision for decision in self.canonical_decisions
        }
        relationship_decisions = {
            decision.decision_id: decision for decision in self.relationship_decisions
        }
        if any(
            item.release_id != self.release_id
            for item in (
                *self.canonical_decisions,
                *self.relationship_decisions,
                *self.constraint_outcomes,
                *self.current_fields,
                *self.current_relationships,
                *self.unresolved_conflicts,
            )
        ):
            raise ValueError("all decision result records must share one release_id")

        _validate_logical_decision_context(
            decision_run_id=self.decision_run_id,
            as_of=self.as_of,
            field_decisions=self.canonical_decisions,
            relationship_decisions=self.relationship_decisions,
        )

        _validate_decision_assertion_families(
            field_assertions=field_assertions,
            relationship_assertions=relationship_assertions,
            field_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
        )
        manifests_by_decision = _validate_decision_group_manifests(
            field_assertions=field_assertions,
            relationship_assertions=relationship_assertions,
            field_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
            manifests=self.decision_group_manifests,
        )
        _validate_structured_trace_semantics(
            field_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
        )
        _validate_identity_contexts_and_determinism(
            as_of=self.as_of,
            canonical_contexts=self.canonical_identity_contexts,
            source_contexts=self.source_identity_contexts,
            field_assertions=field_assertions,
            relationship_assertions=relationship_assertions,
            field_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
            manifests_by_decision=manifests_by_decision,
            outcomes=self.constraint_outcomes,
        )
        _validate_constraint_outcome_links(
            field_assertions=field_assertions,
            relationship_assertions=relationship_assertions,
            field_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
            manifests_by_decision=manifests_by_decision,
            outcomes=self.constraint_outcomes,
        )
        _validate_current_selections(
            field_assertions=field_assertions,
            field_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
            current_fields=self.current_fields,
            current_relationships=self.current_relationships,
        )
        _validate_unresolved_conflicts(
            field_decisions=field_decisions,
            relationship_decisions=relationship_decisions,
            conflicts=self.unresolved_conflicts,
        )

        expected_hash = _content_sha256(
            cast(
                JsonValue,
                self.model_dump(mode="json", exclude={"content_sha256"}),
            )
        )
        if self.content_sha256 != expected_hash:
            raise ValueError("content_sha256 must bind the complete decision result")
        return self


class RecordedAdjudication(ContractModel):
    input_evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    input_evidence_sha256: Sha256
    raw_output: Annotated[bytes, Field(min_length=1)]
    expected_output_sha256: Sha256

    @model_validator(mode="after")
    def validate_evidence_ids(self) -> RecordedAdjudication:
        _require_unique(self.input_evidence_ids, "recorded input evidence IDs")
        return self


class _StrictModel(ContractModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        strict=True,
    )


class _AdjudicationRequest(_StrictModel):
    decision_kind: Literal["field", "relationship"]
    subject_id: NonEmptyStr
    path: NonEmptyStr
    candidate_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=2)
    input_evidence_sha256: Sha256

    @model_validator(mode="after")
    def validate_candidate_ids(self) -> _AdjudicationRequest:
        _require_unique(self.candidate_assertion_ids, "adjudication candidate IDs")
        return self


class _StructuredAdjudicationOutput(_StrictModel):
    state: Literal["selected", "unresolved"]
    selected_assertion_ids: tuple[NonEmptyStr, ...]
    conflicting_assertion_ids: tuple[NonEmptyStr, ...]
    confidence: Confidence
    rationale: NonEmptyStr
    uncertainty: NonEmptyStr
    role_bindings: dict[NonEmptyStr, NonEmptyStr] | None = None


class _ValidatedAdjudication(_StrictModel):
    provider: NonEmptyStr
    model: NonEmptyStr
    prompt_version: NonEmptyStr
    schema_version: NonEmptyStr
    input_evidence_ids: tuple[NonEmptyStr, ...]
    input_evidence_sha256: Sha256
    raw_output: bytes
    output_sha256: Sha256
    validated_output: dict[NonEmptyStr, JsonValue]
    output: _StructuredAdjudicationOutput


class StructuredAdjudicator(Protocol):
    """Narrow true-external seam used only after deterministic filtering."""

    def adjudicate(self, request: _AdjudicationRequest, /) -> _ValidatedAdjudication:
        """Return one evidence-bound structured result for ordered candidates."""
        ...


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, JsonValue]],
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_non_finite_json_constant(value: str) -> NoReturn:
    raise ValueError(f"JSON number {value} is not finite")


def _require_finite_json(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, list):
        for item in value:
            _require_finite_json(item)
    elif isinstance(value, dict):
        for item in value.values():
            _require_finite_json(item)


def _strict_json_equal(left: object, right: object) -> bool:
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


def _strict_non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AdjudicationOutputError(f"{label} must be a non-empty exact string")
    return value


def _strict_id_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AdjudicationOutputError(f"{label} must be a JSON array")
    identifiers = tuple(
        _strict_non_empty_string(item, f"{label} item") for item in value
    )
    if len(identifiers) != len(set(identifiers)):
        raise AdjudicationOutputError(f"{label} must contain unique IDs")
    return identifiers


def _parse_structured_output(
    raw_output: bytes,
) -> tuple[_StructuredAdjudicationOutput, dict[NonEmptyStr, JsonValue]]:
    try:
        raw_text = raw_output.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AdjudicationOutputError(
            "adjudication output must be strict UTF-8"
        ) from exc
    try:
        parsed = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_non_finite_json_constant,
        )
        _require_finite_json(parsed)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AdjudicationOutputError(
            "adjudication output must be strict finite JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise AdjudicationOutputError("adjudication output JSON must be an object")

    required = {
        "state",
        "selected_assertion_ids",
        "conflicting_assertion_ids",
        "confidence",
        "rationale",
        "uncertainty",
    }
    allowed = required | {"role_bindings"}
    if set(parsed) != required and not (
        set(parsed) == allowed and "role_bindings" in parsed
    ):
        missing = sorted(required - set(parsed))
        extra = sorted(set(parsed) - allowed)
        raise AdjudicationOutputError(
            f"adjudication output schema mismatch; missing={missing}, extra={extra}"
        )
    state_value = parsed["state"]
    if not isinstance(state_value, str) or state_value not in {
        "selected",
        "unresolved",
    }:
        raise AdjudicationOutputError(
            "adjudication state must be selected or unresolved"
        )
    state = cast(Literal["selected", "unresolved"], state_value)
    confidence = parsed["confidence"]
    if (
        type(confidence) is not float
        or not math.isfinite(confidence)
        or not 0.0 <= confidence <= 1.0
    ):
        raise AdjudicationOutputError(
            "adjudication confidence must be a finite JSON float in [0, 1]"
        )
    role_bindings_value = parsed.get("role_bindings")
    role_bindings: dict[str, str] | None = None
    if "role_bindings" in parsed:
        if not isinstance(role_bindings_value, dict):
            raise AdjudicationOutputError("role_bindings must be a JSON object")
        role_bindings = {
            _strict_non_empty_string(key, "role binding key"): _strict_non_empty_string(
                value, "role binding value"
            )
            for key, value in role_bindings_value.items()
        }

    try:
        output = _StructuredAdjudicationOutput(
            state=state,
            selected_assertion_ids=_strict_id_array(
                parsed["selected_assertion_ids"], "selected_assertion_ids"
            ),
            conflicting_assertion_ids=_strict_id_array(
                parsed["conflicting_assertion_ids"],
                "conflicting_assertion_ids",
            ),
            confidence=confidence,
            rationale=_strict_non_empty_string(parsed["rationale"], "rationale"),
            uncertainty=_strict_non_empty_string(parsed["uncertainty"], "uncertainty"),
            role_bindings=role_bindings,
        )
    except ValidationError as exc:
        raise AdjudicationOutputError(
            "adjudication output failed its strict structured schema"
        ) from exc
    validated_output = cast(
        dict[NonEmptyStr, JsonValue],
        output.model_dump(mode="json", exclude_none=True),
    )
    if not _strict_json_equal(parsed, validated_output):
        raise AdjudicationOutputError(
            "validated adjudication output must exactly equal the decoded JSON object"
        )
    return output, validated_output


def _validate_output_roles(
    output: _StructuredAdjudicationOutput,
    candidate_assertion_ids: tuple[str, ...],
) -> None:
    selected = set(output.selected_assertion_ids)
    conflicting = set(output.conflicting_assertion_ids)
    candidates = set(candidate_assertion_ids)
    if selected & conflicting:
        raise AdjudicationOutputError(
            "selected and conflicting adjudication IDs must be disjoint"
        )
    if selected | conflicting != candidates:
        raise AdjudicationOutputError(
            "selected and conflicting IDs must cover every candidate exactly once"
        )
    if output.state == "selected" and not selected:
        raise AdjudicationOutputError(
            "selected adjudication requires selected evidence"
        )
    if output.state == "unresolved":
        if selected:
            raise AdjudicationOutputError(
                "unresolved adjudication cannot select evidence"
            )
        if len(conflicting) < 2:
            raise AdjudicationOutputError(
                "unresolved adjudication requires at least two conflicts"
            )


class _RecordedAdjudicatorConfig(_StrictModel):
    provider: NonEmptyStr
    model: NonEmptyStr
    prompt_version: NonEmptyStr
    schema_version: NonEmptyStr


class _RecordedStructuredAdjudicator:
    def __init__(
        self,
        *,
        config: _RecordedAdjudicatorConfig,
        responses_by_evidence_ids: Mapping[
            tuple[tuple[str, ...], str], RecordedAdjudication
        ],
    ) -> None:
        self._config = config
        self._responses_by_evidence_ids = MappingProxyType(
            dict(responses_by_evidence_ids)
        )

    def adjudicate(self, request: _AdjudicationRequest, /) -> _ValidatedAdjudication:
        response = self._responses_by_evidence_ids.get(
            (request.candidate_assertion_ids, request.input_evidence_sha256)
        )
        if response is None:
            raise AdjudicationIntegrityError(
                "no recorded adjudication response is bound to the exact ordered "
                "candidate IDs and input content hash"
            )
        actual_output_sha256 = hashlib.sha256(response.raw_output).hexdigest()
        if actual_output_sha256 != response.expected_output_sha256:
            raise AdjudicationIntegrityError(
                "recorded adjudication output hash does not match the exact raw bytes"
            )
        output, validated_output = _parse_structured_output(response.raw_output)
        _validate_output_roles(output, request.candidate_assertion_ids)
        return _ValidatedAdjudication(
            provider=self._config.provider,
            model=self._config.model,
            prompt_version=self._config.prompt_version,
            schema_version=self._config.schema_version,
            input_evidence_ids=request.candidate_assertion_ids,
            input_evidence_sha256=request.input_evidence_sha256,
            raw_output=response.raw_output,
            output_sha256=actual_output_sha256,
            validated_output=validated_output,
            output=output,
        )


def create_recorded_structured_adjudicator(
    provider: str,
    model: str,
    prompt_version: str,
    schema_version: str,
    responses: Iterable[RecordedAdjudication],
) -> StructuredAdjudicator:
    """Create a deterministic adapter over exact pre-recorded provider bytes."""
    try:
        config = _RecordedAdjudicatorConfig(
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            schema_version=schema_version,
        )
        validated_responses = tuple(
            RecordedAdjudication.model_validate(response.model_dump(mode="python"))
            for response in responses
        )
    except (AttributeError, ValidationError) as exc:
        raise AdjudicationIntegrityError(
            "recorded adjudicator configuration or response is invalid"
        ) from exc
    responses_by_evidence_ids: dict[
        tuple[tuple[str, ...], str], RecordedAdjudication
    ] = {}
    for response in validated_responses:
        key = (response.input_evidence_ids, response.input_evidence_sha256)
        if key in responses_by_evidence_ids:
            raise AdjudicationIntegrityError(
                "duplicate recorded candidate response keys are ambiguous"
            )
        responses_by_evidence_ids[key] = response
    return _RecordedStructuredAdjudicator(
        config=config,
        responses_by_evidence_ids=responses_by_evidence_ids,
    )


class CanonicalDecisionEngine(ABC):
    """Deep public seam for one immutable, reproducible decision batch."""

    @abstractmethod
    def decide(self, request: DecisionBatchRequest) -> DecisionBatchResult:
        """Filter, adjudicate, and derive generic current selections."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class _ConstraintEvaluation:
    assertion_id: str
    admitted: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _FieldGroupResult:
    assertions: tuple[SourceAssertion, ...]
    decision: CanonicalDecision
    manifest: DecisionGroupManifest
    outcomes: tuple[ConstraintOutcome, ...]
    current: CurrentFieldSelection | None
    conflict: UnresolvedConflict | None


@dataclass(frozen=True, slots=True)
class _RelationshipGroupResult:
    assertions: tuple[RelationshipAssertion, ...]
    decision: RelationshipDecision
    manifest: DecisionGroupManifest
    outcomes: tuple[ConstraintOutcome, ...]
    current: CurrentRelationshipSelection | None
    conflict: UnresolvedConflict | None


def _validated_request(request: DecisionBatchRequest) -> DecisionBatchRequest:
    if not isinstance(request, DecisionBatchRequest):
        raise DecisionBatchIntegrityError(
            "decide requires a validated DecisionBatchRequest"
        )
    try:
        return DecisionBatchRequest.model_validate(request.model_dump(mode="python"))
    except ValidationError as exc:
        raise DecisionBatchIntegrityError(
            "decision batch integrity check failed"
        ) from exc


def _source_state_reason(identity: SourceIdentity) -> str | None:
    if identity.state is SourceIdentityState.active:
        return None
    if identity.state is SourceIdentityState.rejected:
        return "source_identity_rejected"
    return "source_identity_superseded"


def _field_rejection_reason(
    *,
    assertion: SourceAssertion,
    group: FieldAssertionGroup,
    canonical_identity: CanonicalIdentityConstraintContext,
    source_identities: dict[str, SourceIdentity],
    as_of: datetime,
) -> str | None:
    source_identity = source_identities.get(assertion.source_identity_id)
    if source_identity is None:
        return "source_identity_missing"
    state_reason = _source_state_reason(source_identity)
    if state_reason is not None:
        return state_reason
    if (
        canonical_identity.state is not CanonicalIdentityState.active
        or assertion.source_identity_id not in canonical_identity.source_identity_ids
    ):
        return "identity_mismatch"
    if (
        assertion.subject_entity_type != canonical_identity.entity_type
        or source_identity.entity_type != canonical_identity.entity_type
    ):
        return "entity_type_mismatch"
    if assertion.field_path != group.field_path:
        return "field_mismatch"
    if assertion.source_record_id not in source_identity.source_record_ids:
        return "source_record_mismatch"
    if assertion.observed_at > as_of:
        return "observed_after_build"
    return None


def _relationship_rejection_reason(
    *,
    assertion: RelationshipAssertion,
    group: RelationshipAssertionGroup,
    source_canonical_identity: CanonicalIdentityConstraintContext,
    target_canonical_identity: CanonicalIdentityConstraintContext,
    source_identities: dict[str, SourceIdentity],
    as_of: datetime,
) -> str | None:
    if assertion.relationship_type_id != group.relationship_type_id:
        return "relationship_type_mismatch"
    if assertion.relationship_type_version != group.relationship_type_version:
        return "relationship_type_version_mismatch"

    source_identity = source_identities.get(assertion.source_endpoint.identity_id)
    if source_identity is None:
        return "source_identity_missing"
    state_reason = _source_state_reason(source_identity)
    if state_reason is not None:
        return state_reason
    target_identity = source_identities.get(assertion.target_endpoint.identity_id)
    if target_identity is None:
        return "source_identity_missing"
    state_reason = _source_state_reason(target_identity)
    if state_reason is not None:
        return state_reason

    if (
        source_canonical_identity.state is not CanonicalIdentityState.active
        or target_canonical_identity.state is not CanonicalIdentityState.active
        or assertion.source_endpoint.identity_id
        not in source_canonical_identity.source_identity_ids
        or assertion.target_endpoint.identity_id
        not in target_canonical_identity.source_identity_ids
    ):
        return "identity_mismatch"
    if (
        assertion.source_endpoint.entity_type != source_canonical_identity.entity_type
        or source_identity.entity_type != source_canonical_identity.entity_type
        or assertion.target_endpoint.entity_type
        != target_canonical_identity.entity_type
        or target_identity.entity_type != target_canonical_identity.entity_type
    ):
        return "entity_type_mismatch"
    if (
        assertion.source_record_id not in source_identity.source_record_ids
        and assertion.source_record_id not in target_identity.source_record_ids
    ):
        return "source_record_mismatch"
    if assertion.observed_at > as_of:
        return "observed_after_build"
    return None


def _validated_adjudication(
    adjudicator: StructuredAdjudicator,
    request: _AdjudicationRequest,
) -> _ValidatedAdjudication:
    try:
        result = adjudicator.adjudicate(request)
    except (AdjudicationIntegrityError, AdjudicationOutputError):
        raise
    except Exception as exc:
        raise AdjudicationIntegrityError(
            "structured adjudicator failed without a validated result"
        ) from exc
    if not isinstance(result, _ValidatedAdjudication):
        raise AdjudicationIntegrityError(
            "structured adjudicator returned an unsupported result type"
        )
    if result.input_evidence_ids != request.candidate_assertion_ids:
        raise AdjudicationIntegrityError(
            "adjudication result evidence IDs must exactly equal ordered candidates"
        )
    if result.input_evidence_sha256 != request.input_evidence_sha256:
        raise AdjudicationIntegrityError(
            "adjudication result input content hash differs from the request"
        )
    actual_output_sha256 = hashlib.sha256(result.raw_output).hexdigest()
    if actual_output_sha256 != result.output_sha256:
        raise AdjudicationIntegrityError(
            "adjudication result output hash does not match its exact raw bytes"
        )
    parsed_output, validated_output = _parse_structured_output(result.raw_output)
    if not _strict_json_equal(result.validated_output, validated_output):
        raise AdjudicationOutputError(
            "adjudication result validated output differs from its raw bytes"
        )
    if result.output != parsed_output:
        raise AdjudicationOutputError(
            "adjudication result typed output differs from its raw bytes"
        )
    _validate_output_roles(result.output, request.candidate_assertion_ids)
    return result


def _decision_trace(result: _ValidatedAdjudication) -> LLMDecisionTrace:
    try:
        return LLMDecisionTrace(
            provider=result.provider,
            model=result.model,
            prompt_version=result.prompt_version,
            schema_version=result.schema_version,
            input_evidence_ids=result.input_evidence_ids,
            raw_output_base64=base64.b64encode(result.raw_output).decode("ascii"),
            output_sha256=result.output_sha256,
            validated_output=result.validated_output,
        )
    except ValidationError as exc:
        raise AdjudicationOutputError(
            "adjudication output cannot form a content-bound decision trace"
        ) from exc


def _decision_seed(
    *,
    decision: CanonicalDecision | RelationshipDecision,
    evaluations: tuple[_ConstraintEvaluation, ...],
    decision_input_sha256: str,
    manifest_content_sha256: str,
) -> JsonValue:
    """Bind every persisted decision field and deterministic input to its ID."""
    return cast(
        JsonValue,
        {
            "decision": decision.model_dump(
                mode="json",
                exclude={"decision_id"},
            ),
            "constraint_outcomes": [
                {
                    "assertion_id": evaluation.assertion_id,
                    "admitted": evaluation.admitted,
                    "reason_codes": list(evaluation.reason_codes),
                }
                for evaluation in sorted(
                    evaluations, key=lambda evaluation: evaluation.assertion_id
                )
            ],
            "decision_input_sha256": decision_input_sha256,
            "group_manifest_sha256": manifest_content_sha256,
        },
    )


def _field_decision(
    *,
    request: DecisionBatchRequest,
    group: FieldAssertionGroup,
    state: DecisionState,
    candidate_assertion_ids: tuple[str, ...],
    selected_assertion_ids: tuple[str, ...],
    conflicting_assertion_ids: tuple[str, ...],
    method: DecisionMethod,
    confidence: float,
    rationale: str,
    llm_trace: LLMDecisionTrace | None,
    evaluations: tuple[_ConstraintEvaluation, ...],
    decision_input_sha256: str,
    manifest_content_sha256: str,
) -> CanonicalDecision:
    try:
        draft = CanonicalDecision(
            decision_id="pending-field-decision-id",
            canonical_identity_id=group.canonical_identity_id,
            field_path=group.field_path,
            state=state,
            candidate_assertion_ids=candidate_assertion_ids,
            selected_assertion_ids=selected_assertion_ids,
            conflicting_assertion_ids=conflicting_assertion_ids,
            policy=group.policy,
            method=method,
            method_version=request.decision_method_version,
            decision_run_id=request.decision_run_id,
            confidence=confidence,
            rationale=rationale,
            llm_trace=llm_trace,
            release_id=request.release_id,
            decided_at=request.as_of,
        )
        decision_id = _manifest_bound_decision_id(
            prefix="field-decision",
            manifest_content_sha256=manifest_content_sha256,
            seed=_decision_seed(
                decision=draft,
                evaluations=evaluations,
                decision_input_sha256=decision_input_sha256,
                manifest_content_sha256=manifest_content_sha256,
            ),
        )
        return CanonicalDecision.model_validate(
            {**draft.model_dump(mode="python"), "decision_id": decision_id}
        )
    except (UnicodeError, ValueError, ValidationError) as exc:
        raise DecisionBatchIntegrityError(
            "derived field decision violates the shared contract"
        ) from exc


def _field_group_result(
    *,
    request: DecisionBatchRequest,
    group: FieldAssertionGroup,
    canonical_identity: CanonicalIdentity,
    source_identities: dict[str, SourceIdentity],
    adjudicator: StructuredAdjudicator | None,
) -> _FieldGroupResult:
    canonical_context = _canonical_constraint_context(canonical_identity)
    evaluations = tuple(
        _ConstraintEvaluation(
            assertion_id=assertion.assertion_id,
            admitted=(
                reason := _field_rejection_reason(
                    assertion=assertion,
                    group=group,
                    canonical_identity=canonical_context,
                    source_identities=source_identities,
                    as_of=request.as_of,
                )
            )
            is None,
            reason_codes=() if reason is None else (reason,),
        )
        for assertion in group.assertions
    )
    admitted_ids = {
        evaluation.assertion_id for evaluation in evaluations if evaluation.admitted
    }
    candidates = tuple(
        assertion
        for assertion in group.assertions
        if assertion.assertion_id in admitted_ids
    )
    candidate_ids = tuple(assertion.assertion_id for assertion in candidates)
    decision_input_sha256 = _canonical_decision_input_sha256(
        decision_kind="field",
        subject_id=group.canonical_identity_id,
        path=group.field_path,
        assertions=group.assertions,
        canonical_identities=(canonical_context,),
        source_identities=source_identities,
    )
    group_key = _field_group_key(
        group.canonical_identity_id,
        group.field_path,
    )
    manifest_content_sha256 = _decision_group_manifest_content_sha256(
        group_key=group_key,
        assertions=group.assertions,
    )
    selected_ids: tuple[str, ...] = ()
    conflicting_ids: tuple[str, ...] = ()
    trace: LLMDecisionTrace | None = None

    if not candidates:
        state = DecisionState.unresolved
        method = DecisionMethod.deterministic
        confidence = 0.0
        rationale = "No field assertion survived deterministic constraints."
    elif len(candidates) == 1:
        state = DecisionState.selected
        method = DecisionMethod.deterministic
        selected_ids = candidate_ids
        confidence = 1.0
        rationale = "The sole surviving field assertion satisfies all constraints."
    elif all(
        _strict_json_equal(candidates[0].value, assertion.value)
        for assertion in candidates[1:]
    ):
        state = DecisionState.selected
        method = DecisionMethod.deterministic
        selected_ids = candidate_ids
        confidence = 1.0
        rationale = "All surviving field assertions have strictly equal values."
    elif adjudicator is None:
        state = DecisionState.unresolved
        method = DecisionMethod.deterministic
        conflicting_ids = candidate_ids
        confidence = 0.0
        rationale = (
            "Materially different field assertions require adjudication; "
            "no adjudicator was configured."
        )
    else:
        adjudication = _validated_adjudication(
            adjudicator,
            _AdjudicationRequest(
                decision_kind="field",
                subject_id=group.canonical_identity_id,
                path=group.field_path,
                candidate_assertion_ids=candidate_ids,
                input_evidence_sha256=canonical_adjudication_input_sha256(
                    decision_kind="field",
                    subject_id=group.canonical_identity_id,
                    path=group.field_path,
                    assertions=candidates,
                ),
            ),
        )
        output = adjudication.output
        if output.role_bindings is not None:
            raise AdjudicationOutputError(
                "field adjudication cannot emit relationship role_bindings"
            )
        state = (
            DecisionState.selected
            if output.state == "selected"
            else DecisionState.unresolved
        )
        method = DecisionMethod.structured_llm
        selected_ids = tuple(sorted(output.selected_assertion_ids))
        conflicting_ids = tuple(sorted(output.conflicting_assertion_ids))
        confidence = output.confidence
        rationale = output.rationale
        trace = _decision_trace(adjudication)
        if state is DecisionState.selected:
            by_id = {assertion.assertion_id: assertion for assertion in candidates}
            selected_values = tuple(by_id[item].value for item in selected_ids)
            if not all(
                _strict_json_equal(selected_values[0], value)
                for value in selected_values[1:]
            ):
                raise AdjudicationOutputError(
                    "selected field assertions must have strictly equal values"
                )

    decision = _field_decision(
        request=request,
        group=group,
        state=state,
        candidate_assertion_ids=candidate_ids,
        selected_assertion_ids=selected_ids,
        conflicting_assertion_ids=conflicting_ids,
        method=method,
        confidence=confidence,
        rationale=rationale,
        llm_trace=trace,
        evaluations=evaluations,
        decision_input_sha256=decision_input_sha256,
        manifest_content_sha256=manifest_content_sha256,
    )
    manifest = DecisionGroupManifest(
        decision_id=decision.decision_id,
        group_key=group_key,
        assertion_ids=tuple(assertion.assertion_id for assertion in group.assertions),
        content_sha256=manifest_content_sha256,
    )
    outcomes = tuple(
        ConstraintOutcome(
            release_id=request.release_id,
            decision_id=decision.decision_id,
            assertion_id=evaluation.assertion_id,
            group_key=group_key,
            admitted=evaluation.admitted,
            reason_codes=evaluation.reason_codes,
            policy_version=group.policy.policy_version,
        )
        for evaluation in evaluations
    )
    current: CurrentFieldSelection | None = None
    conflict: UnresolvedConflict | None = None
    if decision.state is DecisionState.selected:
        selected_assertion_id = next(iter(selected_ids), None)
        if selected_assertion_id is None:
            raise DecisionBatchIntegrityError(
                "a selected field decision lost its supporting assertion"
            )
        assertion_by_id = {
            assertion.assertion_id: assertion for assertion in candidates
        }
        current = CurrentFieldSelection(
            release_id=request.release_id,
            canonical_identity_id=group.canonical_identity_id,
            field_path=group.field_path,
            value=assertion_by_id[selected_assertion_id].value,
            decision_id=decision.decision_id,
            supporting_assertion_ids=selected_ids,
            conflicting_assertion_ids=conflicting_ids,
        )
    else:
        conflict = UnresolvedConflict(
            release_id=request.release_id,
            decision_id=decision.decision_id,
            subject_id=group.canonical_identity_id,
            path=group.field_path,
            assertion_ids=conflicting_ids,
        )
    return _FieldGroupResult(
        assertions=group.assertions,
        decision=decision,
        manifest=manifest,
        outcomes=outcomes,
        current=current,
        conflict=conflict,
    )


def _relationship_decision(
    *,
    request: DecisionBatchRequest,
    group: RelationshipAssertionGroup,
    state: RelationshipDecisionState,
    candidate_assertion_ids: tuple[str, ...],
    selected_assertion_ids: tuple[str, ...],
    conflicting_assertion_ids: tuple[str, ...],
    role_bindings: dict[str, str],
    method: DecisionMethod,
    confidence: float,
    rationale: str,
    llm_trace: LLMDecisionTrace | None,
    evaluations: tuple[_ConstraintEvaluation, ...],
    decision_input_sha256: str,
    manifest_content_sha256: str,
) -> RelationshipDecision:
    stable_role_bindings = {key: role_bindings[key] for key in sorted(role_bindings)}
    try:
        draft = RelationshipDecision(
            decision_id="pending-relationship-decision-id",
            canonical_relationship_id=group.canonical_relationship_id,
            relationship_type_id=group.relationship_type_id,
            relationship_type_version=group.relationship_type_version,
            source_canonical_identity_id=group.source_canonical_identity_id,
            target_canonical_identity_id=group.target_canonical_identity_id,
            state=state,
            candidate_assertion_ids=candidate_assertion_ids,
            selected_assertion_ids=selected_assertion_ids,
            conflicting_assertion_ids=conflicting_assertion_ids,
            role_bindings=stable_role_bindings,
            policy=group.policy,
            method=method,
            method_version=request.decision_method_version,
            decision_run_id=request.decision_run_id,
            confidence=confidence,
            rationale=rationale,
            valid_from=None,
            valid_to=None,
            release_id=request.release_id,
            decided_at=request.as_of,
            llm_trace=llm_trace,
        )
        decision_id = _manifest_bound_decision_id(
            prefix="relationship-decision",
            manifest_content_sha256=manifest_content_sha256,
            seed=_decision_seed(
                decision=draft,
                evaluations=evaluations,
                decision_input_sha256=decision_input_sha256,
                manifest_content_sha256=manifest_content_sha256,
            ),
        )
        return RelationshipDecision.model_validate(
            {**draft.model_dump(mode="python"), "decision_id": decision_id}
        )
    except (UnicodeError, ValueError, ValidationError) as exc:
        raise DecisionBatchIntegrityError(
            "derived relationship decision violates the shared contract"
        ) from exc


def _relationship_group_result(
    *,
    request: DecisionBatchRequest,
    group: RelationshipAssertionGroup,
    source_canonical_identity: CanonicalIdentity,
    target_canonical_identity: CanonicalIdentity,
    source_identities: dict[str, SourceIdentity],
    adjudicator: StructuredAdjudicator | None,
) -> _RelationshipGroupResult:
    source_canonical_context = _canonical_constraint_context(source_canonical_identity)
    target_canonical_context = _canonical_constraint_context(target_canonical_identity)
    evaluations = tuple(
        _ConstraintEvaluation(
            assertion_id=assertion.assertion_id,
            admitted=(
                reason := _relationship_rejection_reason(
                    assertion=assertion,
                    group=group,
                    source_canonical_identity=source_canonical_context,
                    target_canonical_identity=target_canonical_context,
                    source_identities=source_identities,
                    as_of=request.as_of,
                )
            )
            is None,
            reason_codes=() if reason is None else (reason,),
        )
        for assertion in group.assertions
    )
    admitted_ids = {
        evaluation.assertion_id for evaluation in evaluations if evaluation.admitted
    }
    candidates = tuple(
        assertion
        for assertion in group.assertions
        if assertion.assertion_id in admitted_ids
    )
    candidate_ids = tuple(assertion.assertion_id for assertion in candidates)
    decision_input_sha256 = _canonical_decision_input_sha256(
        decision_kind="relationship",
        subject_id=group.canonical_relationship_id,
        path=group.relationship_type_id,
        assertions=group.assertions,
        canonical_identities=(
            source_canonical_context,
            target_canonical_context,
        ),
        source_identities=source_identities,
    )
    group_key = _relationship_group_key(
        group.canonical_relationship_id,
        group.relationship_type_id,
        group.relationship_type_version,
    )
    manifest_content_sha256 = _decision_group_manifest_content_sha256(
        group_key=group_key,
        assertions=group.assertions,
    )
    selected_ids: tuple[str, ...] = ()
    conflicting_ids: tuple[str, ...] = ()
    role_bindings: dict[str, str] = {}
    trace: LLMDecisionTrace | None = None

    if not candidates:
        state = RelationshipDecisionState.unresolved
        method = DecisionMethod.deterministic
        confidence = 0.0
        rationale = "No relationship assertion survived deterministic constraints."
    elif len(candidates) == 1:
        state = RelationshipDecisionState.accepted
        method = DecisionMethod.deterministic
        selected_ids = candidate_ids
        confidence = 1.0
        rationale = (
            "The sole surviving relationship assertion satisfies all constraints."
        )
    elif all(
        _strict_json_equal(candidates[0].attributes, assertion.attributes)
        for assertion in candidates[1:]
    ):
        state = RelationshipDecisionState.accepted
        method = DecisionMethod.deterministic
        selected_ids = candidate_ids
        confidence = 1.0
        rationale = (
            "All surviving relationship assertions have strictly equal attributes."
        )
    elif adjudicator is None:
        state = RelationshipDecisionState.unresolved
        method = DecisionMethod.deterministic
        conflicting_ids = candidate_ids
        confidence = 0.0
        rationale = (
            "Materially different relationship assertions require adjudication; "
            "no adjudicator was configured."
        )
    else:
        adjudication = _validated_adjudication(
            adjudicator,
            _AdjudicationRequest(
                decision_kind="relationship",
                subject_id=group.canonical_relationship_id,
                path=group.relationship_type_id,
                candidate_assertion_ids=candidate_ids,
                input_evidence_sha256=canonical_adjudication_input_sha256(
                    decision_kind="relationship",
                    subject_id=group.canonical_relationship_id,
                    path=group.relationship_type_id,
                    assertions=candidates,
                ),
            ),
        )
        output = adjudication.output
        state = (
            RelationshipDecisionState.accepted
            if output.state == "selected"
            else RelationshipDecisionState.unresolved
        )
        if state is RelationshipDecisionState.accepted:
            if output.role_bindings is None:
                raise AdjudicationOutputError(
                    "selected relationship adjudication requires role_bindings"
                )
            role_bindings = dict(output.role_bindings)
        elif output.role_bindings is not None:
            raise AdjudicationOutputError(
                "unresolved relationship adjudication cannot emit role_bindings"
            )
        method = DecisionMethod.structured_llm
        selected_ids = tuple(sorted(output.selected_assertion_ids))
        conflicting_ids = tuple(sorted(output.conflicting_assertion_ids))
        confidence = output.confidence
        rationale = output.rationale
        trace = _decision_trace(adjudication)

    decision = _relationship_decision(
        request=request,
        group=group,
        state=state,
        candidate_assertion_ids=candidate_ids,
        selected_assertion_ids=selected_ids,
        conflicting_assertion_ids=conflicting_ids,
        role_bindings=role_bindings,
        method=method,
        confidence=confidence,
        rationale=rationale,
        llm_trace=trace,
        evaluations=evaluations,
        decision_input_sha256=decision_input_sha256,
        manifest_content_sha256=manifest_content_sha256,
    )
    manifest = DecisionGroupManifest(
        decision_id=decision.decision_id,
        group_key=group_key,
        assertion_ids=tuple(assertion.assertion_id for assertion in group.assertions),
        content_sha256=manifest_content_sha256,
    )
    outcomes = tuple(
        ConstraintOutcome(
            release_id=request.release_id,
            decision_id=decision.decision_id,
            assertion_id=evaluation.assertion_id,
            group_key=group_key,
            admitted=evaluation.admitted,
            reason_codes=evaluation.reason_codes,
            policy_version=group.policy.policy_version,
        )
        for evaluation in evaluations
    )
    current: CurrentRelationshipSelection | None = None
    conflict: UnresolvedConflict | None = None
    if decision.state is RelationshipDecisionState.accepted:
        current = CurrentRelationshipSelection(
            release_id=request.release_id,
            canonical_relationship_id=group.canonical_relationship_id,
            relationship_type_id=group.relationship_type_id,
            relationship_type_version=group.relationship_type_version,
            source_canonical_identity_id=group.source_canonical_identity_id,
            target_canonical_identity_id=group.target_canonical_identity_id,
            role_bindings=role_bindings,
            decision_id=decision.decision_id,
            supporting_assertion_ids=selected_ids,
            conflicting_assertion_ids=conflicting_ids,
        )
    else:
        conflict = UnresolvedConflict(
            release_id=request.release_id,
            decision_id=decision.decision_id,
            subject_id=group.canonical_relationship_id,
            path=group.relationship_type_id,
            assertion_ids=conflicting_ids,
        )
    return _RelationshipGroupResult(
        assertions=group.assertions,
        decision=decision,
        manifest=manifest,
        outcomes=outcomes,
        current=current,
        conflict=conflict,
    )


def _decision_result(
    *,
    request: DecisionBatchRequest,
    field_results: tuple[_FieldGroupResult, ...],
    relationship_results: tuple[_RelationshipGroupResult, ...],
) -> DecisionBatchResult:
    referenced_canonical_ids = {
        group.canonical_identity_id for group in request.field_groups
    } | {
        canonical_identity_id
        for group in request.relationship_groups
        for canonical_identity_id in (
            group.source_canonical_identity_id,
            group.target_canonical_identity_id,
        )
    }
    referenced_source_ids = {
        assertion.source_identity_id
        for group in request.field_groups
        for assertion in group.assertions
    } | {
        source_identity_id
        for group in request.relationship_groups
        for assertion in group.assertions
        for source_identity_id in (
            assertion.source_endpoint.identity_id,
            assertion.target_endpoint.identity_id,
        )
    }
    content = _DecisionBatchContent(
        release_id=request.release_id,
        decision_run_id=request.decision_run_id,
        as_of=request.as_of,
        canonical_identity_contexts=tuple(
            _canonical_constraint_context(identity)
            for identity in request.canonical_identities
            if identity.canonical_identity_id in referenced_canonical_ids
        ),
        source_identity_contexts=tuple(
            identity
            for identity in request.source_identities
            if identity.source_identity_id in referenced_source_ids
        ),
        field_assertions=tuple(
            sorted(
                (
                    assertion
                    for result in field_results
                    for assertion in result.assertions
                ),
                key=lambda assertion: assertion.assertion_id,
            )
        ),
        relationship_assertions=tuple(
            sorted(
                (
                    assertion
                    for result in relationship_results
                    for assertion in result.assertions
                ),
                key=lambda assertion: assertion.assertion_id,
            )
        ),
        canonical_decisions=tuple(
            sorted(
                (result.decision for result in field_results),
                key=lambda decision: (
                    decision.canonical_identity_id,
                    decision.field_path,
                    decision.decision_id,
                ),
            )
        ),
        relationship_decisions=tuple(
            sorted(
                (result.decision for result in relationship_results),
                key=lambda decision: (
                    decision.canonical_relationship_id,
                    decision.decision_id,
                ),
            )
        ),
        decision_group_manifests=tuple(
            sorted(
                (result.manifest for result in (*field_results, *relationship_results)),
                key=lambda manifest: manifest.decision_id,
            )
        ),
        constraint_outcomes=tuple(
            sorted(
                (
                    outcome
                    for result in (*field_results, *relationship_results)
                    for outcome in result.outcomes
                ),
                key=lambda outcome: (outcome.assertion_id, outcome.decision_id),
            )
        ),
        current_fields=tuple(
            sorted(
                (
                    result.current
                    for result in field_results
                    if result.current is not None
                ),
                key=lambda current: (
                    current.canonical_identity_id,
                    current.field_path,
                    current.decision_id,
                ),
            )
        ),
        current_relationships=tuple(
            sorted(
                (
                    result.current
                    for result in relationship_results
                    if result.current is not None
                ),
                key=lambda current: (
                    current.canonical_relationship_id,
                    current.decision_id,
                ),
            )
        ),
        unresolved_conflicts=tuple(
            sorted(
                (
                    result.conflict
                    for result in (*field_results, *relationship_results)
                    if result.conflict is not None
                ),
                key=lambda conflict: (
                    conflict.subject_id,
                    conflict.path,
                    conflict.decision_id,
                ),
            )
        ),
    )
    payload = cast(JsonValue, content.model_dump(mode="json"))
    try:
        return DecisionBatchResult(
            **content.model_dump(mode="python"),
            content_sha256=_content_sha256(payload),
        )
    except (UnicodeError, ValueError, ValidationError) as exc:
        raise DecisionBatchIntegrityError(
            "derived decision result violates its content hash or typed contract"
        ) from exc


class _EphemeralCanonicalDecisionEngine(CanonicalDecisionEngine):
    def __init__(self, *, adjudicator: StructuredAdjudicator | None) -> None:
        self._adjudicator = adjudicator

    def decide(self, request: DecisionBatchRequest) -> DecisionBatchResult:
        validated = _validated_request(request)
        source_identities = {
            identity.source_identity_id: identity
            for identity in validated.source_identities
        }
        canonical_identities = {
            identity.canonical_identity_id: identity
            for identity in validated.canonical_identities
        }
        field_results = tuple(
            _field_group_result(
                request=validated,
                group=group,
                canonical_identity=canonical_identities[group.canonical_identity_id],
                source_identities=source_identities,
                adjudicator=self._adjudicator,
            )
            for group in validated.field_groups
        )
        relationship_results = tuple(
            _relationship_group_result(
                request=validated,
                group=group,
                source_canonical_identity=canonical_identities[
                    group.source_canonical_identity_id
                ],
                target_canonical_identity=canonical_identities[
                    group.target_canonical_identity_id
                ],
                source_identities=source_identities,
                adjudicator=self._adjudicator,
            )
            for group in validated.relationship_groups
        )
        return _decision_result(
            request=validated,
            field_results=field_results,
            relationship_results=relationship_results,
        )


def create_ephemeral_canonical_decision_engine(
    *, adjudicator: StructuredAdjudicator | None = None
) -> CanonicalDecisionEngine:
    """Compose the decision core with an optional injected adjudicator adapter."""
    return _EphemeralCanonicalDecisionEngine(adjudicator=adjudicator)


__all__ = [
    "AdjudicationIntegrityError",
    "AdjudicationOutputError",
    "CanonicalDecision",
    "CanonicalDecisionEngine",
    "CanonicalDecisionEngineError",
    "CanonicalIdentity",
    "CanonicalIdentityConstraintContext",
    "ConstraintOutcome",
    "CurrentFieldSelection",
    "CurrentRelationshipSelection",
    "DecisionBatchIntegrityError",
    "DecisionBatchRequest",
    "DecisionBatchResult",
    "DecisionGroupManifest",
    "FieldAssertionGroup",
    "IdentityReference",
    "PolicyReference",
    "RecordedAdjudication",
    "RelationshipAssertion",
    "RelationshipAssertionGroup",
    "RelationshipDecision",
    "SourceAssertion",
    "SourceIdentity",
    "StructuredAdjudicator",
    "UnresolvedConflict",
    "canonical_adjudication_input_sha256",
    "create_ephemeral_canonical_decision_engine",
    "create_recorded_structured_adjudicator",
]
