"""Strict run-local schema for Canonical V2 claim-level acceptance cases."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    model_validator,
)


__all__ = ["ClaimLevelCaseContract", "validate_case_contracts"]

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9:._-]*$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("case contract content is not canonical JSON") from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _require_unique(values: tuple[str, ...], *, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _claim_semantic_identity(claim: _ClaimConstraint) -> str:
    subject = {
        "entity_id": claim.subject.entity_id,
        "entity_type": claim.subject.entity_type,
    }
    object_constraint = {
        "accepted_values": _thaw_json(claim.object_constraint.accepted_values),
        "entity_id": claim.object_constraint.entity_id,
        "kind": claim.object_constraint.kind,
        "tolerance": claim.object_constraint.tolerance,
        "unit": claim.object_constraint.unit,
        "value": _thaw_json(claim.object_constraint.value),
    }
    return _canonical_sha256(
        {
            "object_constraint": object_constraint,
            "predicate": claim.predicate,
            "subject": subject,
            "temporal_scope": claim.temporal_scope,
        }
    )


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
    )


class _ClaimSubject(_StrictModel):
    entity_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    entity_type: str = Field(min_length=1, pattern=_ID_PATTERN)


class _ObjectConstraint(_StrictModel):
    kind: Literal["literal", "entity", "number", "boolean", "set"]
    value: Any | None = None
    entity_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    accepted_values: tuple[Any, ...] = ()
    unit: str | None = Field(default=None, min_length=1)
    tolerance: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_kind(self) -> Self:
        if self.kind == "literal":
            if self.value is None or self.entity_id is not None or self.accepted_values:
                raise ValueError("literal object requires only value")
            if self.unit is not None or self.tolerance is not None:
                raise ValueError("literal object cannot declare numeric fields")
        elif self.kind == "entity":
            if self.entity_id is None or self.value is not None or self.accepted_values:
                raise ValueError("entity object requires only entity_id")
            if self.unit is not None or self.tolerance is not None:
                raise ValueError("entity object cannot declare numeric fields")
        elif self.kind == "number":
            if (
                isinstance(self.value, bool)
                or not isinstance(self.value, (int, float))
                or not math.isfinite(float(self.value))
                or self.entity_id is not None
                or self.accepted_values
            ):
                raise ValueError("number object requires one finite numeric value")
        elif self.kind == "boolean":
            if (
                not isinstance(self.value, bool)
                or self.entity_id is not None
                or self.accepted_values
                or self.unit is not None
                or self.tolerance is not None
            ):
                raise ValueError("boolean object requires only a boolean value")
        elif (
            not self.accepted_values
            or self.value is not None
            or self.entity_id is not None
            or self.unit is not None
            or self.tolerance is not None
        ):
            raise ValueError("set object requires only accepted_values")
        canonical_values = tuple(
            _canonical_bytes(value).decode() for value in self.accepted_values
        )
        _require_unique(canonical_values, label="object accepted_values")
        object.__setattr__(self, "value", _freeze_json(self.value))
        object.__setattr__(
            self,
            "accepted_values",
            tuple(_freeze_json(value) for value in self.accepted_values),
        )
        return self

    @field_serializer("value")
    def _serialize_value(self, value: Any) -> Any:
        return _thaw_json(value)

    @field_serializer("accepted_values")
    def _serialize_accepted_values(self, values: tuple[Any, ...]) -> list[Any]:
        return [_thaw_json(value) for value in values]


class _ClaimConstraint(_StrictModel):
    claim_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    subject: _ClaimSubject
    predicate: str = Field(min_length=1, pattern=_ID_PATTERN)
    object_constraint: _ObjectConstraint
    materiality: Literal["material", "soft"]
    evidence_obligation: str = Field(min_length=1, pattern=_ID_PATTERN)
    source_snapshot_ids: tuple[str, ...] = ()
    temporal_scope: Literal["as_of", "timeless", "session_bound"]

    @model_validator(mode="after")
    def _validate_evidence(self) -> Self:
        if self.evidence_obligation.lower() == "none":
            raise ValueError("claims cannot disable their evidence obligation")
        _require_unique(self.source_snapshot_ids, label="claim source_snapshot_ids")
        return self


class _EntityConstraint(_StrictModel):
    constraint_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    entity_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    entity_type: str = Field(min_length=1, pattern=_ID_PATTERN)
    canonical_name: str = Field(min_length=1)
    allowed_aliases: tuple[str, ...] = ()
    match_policy: Literal[
        "reviewed_identity_or_alias",
        "exact_identifier",
        "case_scoped_identity",
    ]

    @model_validator(mode="after")
    def _validate_aliases(self) -> Self:
        _require_unique(self.allowed_aliases, label="allowed_aliases")
        if self.canonical_name in self.allowed_aliases:
            raise ValueError("canonical_name cannot repeat as an alias")
        return self


class _AllowedVariant(_StrictModel):
    variant_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    claim_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    variant_kind: Literal[
        "semantic_equivalence",
        "unit_equivalence",
        "qualified_outcome",
    ]
    accepted_values: tuple[Any, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_values(self) -> Self:
        canonical_values = tuple(
            _canonical_bytes(value).decode() for value in self.accepted_values
        )
        _require_unique(canonical_values, label="variant accepted_values")
        object.__setattr__(
            self,
            "accepted_values",
            tuple(_freeze_json(value) for value in self.accepted_values),
        )
        return self

    @field_serializer("accepted_values")
    def _serialize_accepted_values(self, values: tuple[Any, ...]) -> list[Any]:
        return [_thaw_json(value) for value in values]


class _SourceSnapshot(_StrictModel):
    snapshot_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    snapshot_role: Literal["claim_evidence", "requirement_context"] = "claim_evidence"
    source_nature: str = Field(min_length=1, pattern=_ID_PATTERN)
    source_locator: str = Field(min_length=1)
    content_sha256: str = Field(pattern=_SHA256_PATTERN)
    captured_at: AwareDatetime
    review_state: Literal["human_reviewed", "source_frozen", "pending_user_review"]


class _CoverageExpectation(_StrictModel):
    checked: int | None = Field(default=None, ge=0)
    eligible: int | None = Field(default=None, ge=0)
    retrieved: int | None = Field(default=None, ge=0)
    displayed: int | None = Field(default=None, ge=0)
    omitted: int | None = Field(default=None, ge=0)
    unknown: int | None = Field(default=None, ge=0)
    continuation_required: bool | None = None

    @model_validator(mode="after")
    def _validate_counts(self) -> Self:
        if self.checked is not None and self.eligible is not None:
            if self.eligible > self.checked:
                raise ValueError("eligible coverage cannot exceed checked coverage")
        if self.retrieved is not None and self.checked is not None:
            if self.retrieved > self.checked:
                raise ValueError("retrieved coverage cannot exceed checked coverage")
        display_ceiling = (
            self.retrieved if self.retrieved is not None else self.eligible
        )
        if self.displayed is not None and display_ceiling is not None:
            if self.displayed > display_ceiling:
                raise ValueError("displayed coverage exceeds its available population")
        if (
            self.eligible is not None
            and self.displayed is not None
            and self.omitted is not None
            and self.omitted != self.eligible - self.displayed
        ):
            raise ValueError("omitted coverage must equal eligible minus displayed")
        return self


class _EnumerationPolicy(_StrictModel):
    applicable: bool = True
    reason: (
        Literal[
            "non_enumeration_turn",
            "pending_bounded_universe_review",
            "safety_guidance_not_enumeration",
        ]
        | None
    ) = None
    obligation_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    mode: Literal["exhaustive_bounded", "required_members", "representative"] | None = (
        None
    )
    scope: str | None = Field(default=None, min_length=1)
    universe_entity_ids: tuple[str, ...] = ()
    required_entity_ids: tuple[str, ...] = ()
    expected_coverage: _CoverageExpectation | None = None

    @model_validator(mode="after")
    def _validate_policy(self) -> Self:
        _require_unique(
            self.universe_entity_ids, label="enumeration universe_entity_ids"
        )
        _require_unique(
            self.required_entity_ids, label="enumeration required_entity_ids"
        )
        if not self.applicable:
            if self.reason not in {
                "non_enumeration_turn",
                "pending_bounded_universe_review",
                "safety_guidance_not_enumeration",
            }:
                raise ValueError(
                    "non-applicable enumeration requires an explicit reason"
                )
            if (
                any(
                    value is not None
                    for value in (
                        self.obligation_id,
                        self.mode,
                        self.scope,
                        self.expected_coverage,
                    )
                )
                or self.universe_entity_ids
                or self.required_entity_ids
            ):
                raise ValueError(
                    "non-applicable enumeration cannot carry policy fields"
                )
            return self

        if self.reason is not None or any(
            value is None
            for value in (
                self.obligation_id,
                self.mode,
                self.scope,
                self.expected_coverage,
            )
        ):
            raise ValueError("applicable enumeration requires a complete policy")
        if self.mode == "exhaustive_bounded":
            if not self.universe_entity_ids:
                raise ValueError("exhaustive_bounded requires a finite universe")
            if (
                self.expected_coverage is not None
                and self.expected_coverage.checked is not None
                and self.expected_coverage.checked != len(self.universe_entity_ids)
            ):
                raise ValueError(
                    "exhaustive checked count must equal its finite universe"
                )
        elif self.mode == "required_members":
            if not self.required_entity_ids:
                raise ValueError("required_members requires named members")
        elif self.required_entity_ids:
            raise ValueError("representative enumeration cannot imply required members")
        if self.universe_entity_ids and not set(self.required_entity_ids).issubset(
            self.universe_entity_ids
        ):
            raise ValueError(
                "required enumeration members must belong to the named universe"
            )
        return self


class _StageExpectation(_StrictModel):
    expectation_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    observable_kind: Literal[
        "affected_claim_conflict_disclosure",
        "alias_resolution_trace",
        "ambiguity_resolution",
        "assessment_dimensions",
        "assessment_dimensions_and_uncertainty",
        "categorical_unsupported_verdict_count",
        "conflict_disclosure",
        "conflicting_assertions_retained",
        "constraint_preservation",
        "deterministic_degradation",
        "displayed_set_scope",
        "exact_identifier",
        "false_exhaustiveness_count",
        "identity_evidence",
        "identity_substitution_count",
        "local_web_fusion",
        "material_claim_evidence",
        "model_memory_fill_count",
        "prior_anchor_required",
        "prior_anchor_state",
        "protected_slot",
        "protected_slot_loss_count",
        "provider_failure",
        "query_interaction",
        "relationship_direction",
        "rendered_entity",
        "response_policy",
        "source_nature_disclosure",
        "supplemental_attempt_policy",
        "supported_subset",
        "supported_partial_or_limitation",
        "top_k_relevance",
        "undisplayed_member_use_count",
        "unsupported_capability_inference_count",
        "unsupported_scope_disclosure",
        "web_invocation",
    ]
    operator: Literal[
        "at_least", "at_most", "contains", "equals", "excludes", "exists", "one_of"
    ]
    value: Any
    hard: bool

    @model_validator(mode="after")
    def _validate_value(self) -> Self:
        _canonical_bytes(self.value)
        if self.operator == "one_of" and (
            not isinstance(self.value, (list, tuple)) or not self.value
        ):
            raise ValueError("one_of requires a non-empty value list")
        object.__setattr__(self, "value", _freeze_json(self.value))
        return self

    @field_serializer("value")
    def _serialize_value(self, value: Any) -> Any:
        return _thaw_json(value)


class _StageOracle(_StrictModel):
    oracle_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    stage: Literal[
        "candidate_recall",
        "claim_evidence_mapping",
        "fusion_sufficiency",
        "provider_execution",
        "query_understanding",
        "rendered_answer",
        "session_transition",
    ]
    expectations: tuple[_StageExpectation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_expectations(self) -> Self:
        _require_unique(
            tuple(item.expectation_id for item in self.expectations),
            label="stage expectation IDs",
        )
        return self


class _OutcomePolicy(_StrictModel):
    aggregation: Literal["all_hard_requirements_per_case"]
    hard_requirement_ids: tuple[str, ...]
    soft_metric_ids: tuple[str, ...] = ()
    reference_prose_normative: Literal[False]

    @model_validator(mode="after")
    def _validate_ids(self) -> Self:
        _require_unique(self.hard_requirement_ids, label="hard_requirement_ids")
        _require_unique(self.soft_metric_ids, label="soft_metric_ids")
        if set(self.hard_requirement_ids).intersection(self.soft_metric_ids):
            raise ValueError("hard and soft outcome IDs cannot overlap")
        if any(value.startswith("reference:") for value in self.hard_requirement_ids):
            raise ValueError("reference prose cannot be a hard requirement")
        return self


class _ReferenceContext(_StrictModel):
    answer_role: Literal["review_only"]
    reference_prose: str | None = None
    reference_key_points: str | None = None
    legacy_source_locator: str | None = None


class _ConversationContext(_StrictModel):
    group_id: str = Field(min_length=1)
    turn_index: int = Field(ge=1)
    predecessor_source_case_id: str | None = Field(default=None, pattern=_ID_PATTERN)

    @model_validator(mode="after")
    def _validate_predecessor(self) -> Self:
        if self.turn_index > 1 and self.predecessor_source_case_id is None:
            raise ValueError(
                "later conversation turns require a predecessor source case"
            )
        if self.turn_index == 1 and self.predecessor_source_case_id is not None:
            raise ValueError("first conversation turns cannot declare a predecessor")
        return self


class ClaimLevelCaseContract(_StrictModel):
    """One immutable, machine-readable acceptance-oracle draft or reviewed case."""

    schema_version: Literal["canonical-v2-claim-level-case-contract-v1"]
    contract_version: Literal["claim-level-contract-v1"]
    case_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    source_case_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    corpus_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    query: str = Field(min_length=1)
    review_state: Literal[
        "blocked_missing_evidence",
        "human_reviewed",
        "pending_user_review",
    ]
    source_review_state: (
        Literal[
            "pending_user_review",
            "user_confirmed_reference_gold",
        ]
        | None
    ) = None
    acceptance_eligible: bool = False
    conversation_context: _ConversationContext | None = None
    required_claims: tuple[_ClaimConstraint, ...]
    forbidden_claims: tuple[_ClaimConstraint, ...]
    required_entities: tuple[_EntityConstraint, ...]
    forbidden_entities: tuple[_EntityConstraint, ...]
    allowed_variants: tuple[_AllowedVariant, ...]
    source_snapshots: tuple[_SourceSnapshot, ...]
    as_of: AwareDatetime
    evidence_availability: Literal["snapshotted", "unavailable"]
    unavailable_evidence_reason: str | None = None
    enumeration_policy: _EnumerationPolicy
    stage_oracles: tuple[_StageOracle, ...]
    outcome_policy: _OutcomePolicy
    reference_context: _ReferenceContext
    content_sha256: str = Field(pattern=_SHA256_PATTERN)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Preserve the exact validated input shape so its content hash round-trips."""

        kwargs.setdefault("exclude_unset", True)
        return super().model_dump(*args, **kwargs)

    @model_validator(mode="before")
    @classmethod
    def _validate_content_hash(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        supplied = value.get("content_sha256")
        if not isinstance(supplied, str):
            raise ValueError("content_sha256 is required")
        content = dict(value)
        content.pop("content_sha256", None)
        actual = _canonical_sha256(content)
        if supplied != actual:
            raise ValueError(
                f"case contract content hash mismatch: expected {supplied}, actual {actual}"
            )
        return value

    @model_validator(mode="after")
    def _validate_contract(self) -> Self:
        if self.acceptance_eligible and self.review_state != "human_reviewed":
            raise ValueError("only human-reviewed contracts can be acceptance eligible")

        required_claim_ids = tuple(item.claim_id for item in self.required_claims)
        forbidden_claim_ids = tuple(item.claim_id for item in self.forbidden_claims)
        all_claim_ids = required_claim_ids + forbidden_claim_ids
        _require_unique(all_claim_ids, label="claim IDs")
        if set(required_claim_ids).intersection(forbidden_claim_ids):
            raise ValueError("a claim cannot be both required and forbidden")
        required_claim_semantics = {
            _claim_semantic_identity(claim) for claim in self.required_claims
        }
        forbidden_claim_semantics = {
            _claim_semantic_identity(claim) for claim in self.forbidden_claims
        }
        if required_claim_semantics.intersection(forbidden_claim_semantics):
            raise ValueError(
                "the same semantic claim cannot be both required and forbidden"
            )

        required_constraint_ids = tuple(
            item.constraint_id for item in self.required_entities
        )
        forbidden_constraint_ids = tuple(
            item.constraint_id for item in self.forbidden_entities
        )
        all_constraint_ids = required_constraint_ids + forbidden_constraint_ids
        _require_unique(all_constraint_ids, label="entity constraint IDs")
        required_entity_ids = {item.entity_id for item in self.required_entities}
        forbidden_entity_ids = {item.entity_id for item in self.forbidden_entities}
        all_declared_entity_ids = tuple(
            item.entity_id
            for item in (*self.required_entities, *self.forbidden_entities)
        )
        _require_unique(all_declared_entity_ids, label="declared entity IDs")
        if required_entity_ids.intersection(forbidden_entity_ids):
            raise ValueError("an entity cannot be both required and forbidden")
        declared_entity_types = {
            item.entity_id: item.entity_type
            for item in (*self.required_entities, *self.forbidden_entities)
        }
        for claim in (*self.required_claims, *self.forbidden_claims):
            declared_type = declared_entity_types.get(claim.subject.entity_id)
            if declared_type is not None and claim.subject.entity_type != declared_type:
                raise ValueError(
                    "claim subject type conflicts with its declared entity constraint"
                )

        variant_ids = tuple(item.variant_id for item in self.allowed_variants)
        _require_unique(variant_ids, label="variant IDs")
        if any(item.claim_id not in all_claim_ids for item in self.allowed_variants):
            raise ValueError("allowed variant references an unknown claim")

        snapshot_ids = tuple(item.snapshot_id for item in self.source_snapshots)
        _require_unique(snapshot_ids, label="source snapshot IDs")
        snapshot_by_id = {item.snapshot_id: item for item in self.source_snapshots}
        referenced_snapshot_ids = {
            snapshot_id
            for claim in (*self.required_claims, *self.forbidden_claims)
            for snapshot_id in claim.source_snapshot_ids
        }
        if not referenced_snapshot_ids.issubset(snapshot_by_id):
            raise ValueError("claim references an unknown source snapshot")
        if any(
            snapshot_by_id[item].snapshot_role != "claim_evidence"
            for item in referenced_snapshot_ids
        ):
            raise ValueError("claims may reference only claim-evidence snapshots")
        if self.acceptance_eligible and any(
            snapshot_by_id[snapshot_id].review_state != "human_reviewed"
            for snapshot_id in referenced_snapshot_ids
        ):
            raise ValueError(
                "acceptance-eligible claims require human-reviewed evidence snapshots"
            )
        if any(snapshot.captured_at > self.as_of for snapshot in self.source_snapshots):
            raise ValueError("source snapshot cannot be captured after the case as-of")

        if self.evidence_availability == "snapshotted":
            if not self.source_snapshots:
                raise ValueError(
                    "snapshotted evidence requires at least one source snapshot"
                )
            if self.unavailable_evidence_reason is not None:
                raise ValueError(
                    "snapshotted evidence cannot declare an unavailable reason"
                )
            material_claims = tuple(
                claim
                for claim in (*self.required_claims, *self.forbidden_claims)
                if claim.materiality == "material"
            )
            if any(not claim.source_snapshot_ids for claim in material_claims):
                raise ValueError("material claims require named evidence snapshots")
        else:
            if not self.unavailable_evidence_reason:
                raise ValueError("unavailable evidence requires an explicit reason")
            if referenced_snapshot_ids:
                raise ValueError("unavailable evidence cannot be referenced by claims")
            if any(
                snapshot.snapshot_role == "claim_evidence"
                for snapshot in self.source_snapshots
            ):
                raise ValueError(
                    "unavailable evidence cannot carry claim-evidence snapshots"
                )

        if self.enumeration_policy.applicable:
            enum_required = set(self.enumeration_policy.required_entity_ids)
            if not enum_required.issubset(required_entity_ids):
                raise ValueError(
                    "enumeration required members must be required entities"
                )

        oracle_ids = tuple(item.oracle_id for item in self.stage_oracles)
        _require_unique(oracle_ids, label="stage oracle IDs")
        expectations = tuple(
            expectation
            for oracle in self.stage_oracles
            for expectation in oracle.expectations
        )
        expectation_ids = tuple(item.expectation_id for item in expectations)
        _require_unique(expectation_ids, label="global stage expectation IDs")

        enumeration_ids: tuple[str, ...] = ()
        if self.enumeration_policy.applicable:
            assert self.enumeration_policy.obligation_id is not None
            enumeration_ids = (self.enumeration_policy.obligation_id,)
        local_contract_ids = (
            all_claim_ids
            + all_constraint_ids
            + variant_ids
            + snapshot_ids
            + oracle_ids
            + expectation_ids
            + enumeration_ids
            + self.outcome_policy.soft_metric_ids
        )
        _require_unique(
            local_contract_ids, label="local contract IDs across namespaces"
        )

        hard_ids = {
            claim.claim_id
            for claim in (*self.required_claims, *self.forbidden_claims)
            if claim.materiality == "material"
        }
        hard_ids.update(required_constraint_ids)
        hard_ids.update(forbidden_constraint_ids)
        hard_ids.update(item.expectation_id for item in expectations if item.hard)
        hard_ids.update(enumeration_ids)
        if self.acceptance_eligible and not hard_ids:
            raise ValueError(
                "acceptance-eligible cases require a non-empty hard atomic set"
            )
        if set(self.outcome_policy.hard_requirement_ids) != hard_ids:
            missing = sorted(
                hard_ids.difference(self.outcome_policy.hard_requirement_ids)
            )
            unexpected = sorted(
                set(self.outcome_policy.hard_requirement_ids).difference(hard_ids)
            )
            raise ValueError(
                f"hard_requirement_ids must be the closed atomic set; missing={missing}, "
                f"unexpected={unexpected}"
            )
        return self


ClaimLevelCaseContract.model_rebuild(_types_namespace=globals())


def validate_case_contracts(
    payloads: tuple[dict[str, Any] | ClaimLevelCaseContract, ...],
) -> tuple[ClaimLevelCaseContract, ...]:
    """Validate a deterministic case sequence while preserving its declared order."""

    contracts = tuple(
        ClaimLevelCaseContract.model_validate(
            payload.model_dump(mode="json")
            if isinstance(payload, ClaimLevelCaseContract)
            else payload
        )
        for payload in payloads
    )
    case_ids = tuple(contract.case_id for contract in contracts)
    _require_unique(case_ids, label="case IDs")
    return contracts
