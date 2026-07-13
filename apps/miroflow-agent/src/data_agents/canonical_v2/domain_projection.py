"""Typed, evidence-bound current projections for Canonical V2 domains.

The public surface in this module is package-internal.  Storage and provider
concerns live behind separate adapters; projection construction remains a pure,
deterministic operation over explicit retained inputs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import date as Date, datetime
import hashlib
import json
from typing import Any, cast

from pydantic import JsonValue, field_validator, model_validator

from .canonical_decision_engine import CurrentFieldSelection
from .canonical_identity_resolution import SourceIdentityAssignment
from .contracts import (
    CanonicalDatetime,
    CanonicalDecision,
    CanonicalIdentity,
    CanonicalIdentityState,
    ContractModel,
    DecisionState,
    NonEmptyStr,
    PolicyDecision,
    PolicyKind,
    PolicyOutcome,
    Sha256,
    SourceAssertion,
    TemporalDateValue,
    TemporalInstantValue,
)
from .domain_catalog import (
    CATALOG_CONTENT_SHA256,
    CATALOG_SCHEMA_VERSION,
    CATALOG_VERSION,
    PACKAGED_CATALOG,
    CatalogDomainDefinition,
)
from .domain_inclusion import DomainInclusionResult
from .domain_projection_models import (
    DOMAIN_SUBOBJECT_ATTRIBUTES,
    DOMAIN_SUBOBJECT_MODELS,
    CompanyProjection,
    FieldProjectionLineage,
    PaperProjection,
    PatentProjection,
    ProfessorProjection,
    ProjectionEvidenceReference,
    TypedSubobject,
)


Projection = (
    ProfessorProjection | CompanyProjection | PaperProjection | PatentProjection
)
_DOMAINS = ("company", "paper", "patent", "professor")


class DomainProjectionIntegrityError(ValueError):
    """Projection inputs do not form one closed retained-evidence graph."""


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
            raise DomainProjectionIntegrityError(f"duplicate {label}: {identity}")
        result[identity] = value
    return result


class DomainProjectionRequest(ContractModel):
    """Evidence-bound input for one deterministic projection build."""

    release_id: NonEmptyStr
    build_run_id: NonEmptyStr
    as_of: CanonicalDatetime
    projection_version: NonEmptyStr
    catalog_schema_version: NonEmptyStr
    catalog_version: NonEmptyStr
    catalog_content_sha256: Sha256
    canonical_identities: tuple[CanonicalIdentity, ...]
    source_identity_assignments: tuple[SourceIdentityAssignment, ...]
    source_assertions: tuple[SourceAssertion, ...]
    canonical_decisions: tuple[CanonicalDecision, ...]
    current_fields: tuple[CurrentFieldSelection, ...]
    inclusion_result: DomainInclusionResult


class RejectedProjection(ContractModel):
    canonical_identity_id: NonEmptyStr
    entity_type: NonEmptyStr
    reason_codes: tuple[NonEmptyStr, ...]


class DomainProjectionManifestEntry(ContractModel):
    canonical_identity_id: NonEmptyStr
    entity_type: NonEmptyStr
    projection_content_sha256: Sha256


class DomainProjectionResult(ContractModel):
    """Four-domain projection output plus deterministic build metadata."""

    release_id: NonEmptyStr
    build_run_id: NonEmptyStr
    as_of: CanonicalDatetime
    projection_version: NonEmptyStr
    catalog_schema_version: NonEmptyStr
    catalog_version: NonEmptyStr
    catalog_content_sha256: Sha256
    inclusion_result: DomainInclusionResult
    inclusion_result_content_sha256: Sha256
    approved_source_scope_manifest_sha256: Sha256
    projections: tuple[Projection, ...]
    rejected_projections: tuple[RejectedProjection, ...]
    inclusion_decisions: tuple[PolicyDecision, ...]
    manifest: tuple[DomainProjectionManifestEntry, ...]
    counts_by_domain: dict[NonEmptyStr, int]
    content_sha256: Sha256

    @field_validator("projections")
    @classmethod
    def validate_projection_order(
        cls, values: tuple[Projection, ...]
    ) -> tuple[Projection, ...]:
        keys = tuple(
            (value.entity_type, value.canonical_identity_id) for value in values
        )
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("projections must be sorted unique by domain and identity")
        return values

    @model_validator(mode="after")
    def validate_result_hash(self) -> DomainProjectionResult:
        rejected_keys = tuple(
            (item.entity_type, item.canonical_identity_id)
            for item in self.rejected_projections
        )
        if rejected_keys != tuple(sorted(rejected_keys)) or len(rejected_keys) != len(
            set(rejected_keys)
        ):
            raise ValueError("rejected projections must be sorted unique")
        projection_entries = tuple(
            (item.entity_type, item.canonical_identity_id, item.content_sha256)
            for item in self.projections
        )
        manifest_entries = tuple(
            (
                item.entity_type,
                item.canonical_identity_id,
                item.projection_content_sha256,
            )
            for item in self.manifest
        )
        if projection_entries != manifest_entries:
            raise ValueError("manifest must bind every projection in exact order")
        projection_keys = {
            (item.entity_type, item.canonical_identity_id) for item in self.projections
        }
        if projection_keys & set(rejected_keys):
            raise ValueError("one identity cannot be both projected and rejected")
        expected_counts = {
            domain: sum(item.entity_type == domain for item in self.projections)
            for domain in ("company", "paper", "patent", "professor")
        }
        if self.counts_by_domain != expected_counts:
            raise ValueError("counts_by_domain must match the typed projections")
        if any(
            item.release_id != self.release_id
            or item.as_of != self.as_of
            or item.projection_version != self.projection_version
            or item.catalog_schema_version != self.catalog_schema_version
            or item.catalog_version != self.catalog_version
            or item.catalog_content_sha256 != self.catalog_content_sha256
            for item in self.projections
        ):
            raise ValueError("every projection must bind the result envelope")
        inclusion_subjects = tuple(
            decision.subject_identity_id for decision in self.inclusion_decisions
        )
        if inclusion_subjects != tuple(sorted(inclusion_subjects)) or len(
            inclusion_subjects
        ) != len(set(inclusion_subjects)):
            raise ValueError("inclusion decisions must be sorted unique by identity")
        accounted_identities = {
            item.canonical_identity_id for item in self.projections
        } | {item.canonical_identity_id for item in self.rejected_projections}
        if set(inclusion_subjects) != accounted_identities:
            raise ValueError(
                "inclusion decisions must account for every projected/rejected identity"
            )
        if any(
            decision.release_id != self.release_id
            or decision.policy.policy_kind is not PolicyKind.inclusion
            for decision in self.inclusion_decisions
        ):
            raise ValueError("result inclusion decisions must bind this release")
        if (
            self.inclusion_result.release_id != self.release_id
            or self.inclusion_result.policy_decisions != self.inclusion_decisions
            or self.inclusion_result.content_sha256
            != self.inclusion_result_content_sha256
            or self.inclusion_result.approved_source_scope_manifest_sha256
            != self.approved_source_scope_manifest_sha256
            or self.inclusion_result.evaluated_at > self.as_of
        ):
            raise ValueError(
                "result inclusion lineage must equal the complete validated result"
            )
        decision_by_identity = {
            decision.subject_identity_id: decision
            for decision in self.inclusion_decisions
        }
        outcome_maps = {
            PolicyOutcome.admitted: (
                self.inclusion_result.admitted_identity_ids_by_domain
            ),
            PolicyOutcome.review: self.inclusion_result.review_identity_ids_by_domain,
            PolicyOutcome.excluded: (
                self.inclusion_result.excluded_identity_ids_by_domain
            ),
        }
        domain_by_identity = {
            identity_id: domain
            for mapping in outcome_maps.values()
            for domain, identity_ids in mapping.items()
            for identity_id in identity_ids
        }
        for projection in self.projections:
            decision = decision_by_identity[projection.canonical_identity_id]
            if projection.inclusion_decision_id != decision.decision_id:
                raise ValueError(
                    "projection inclusion decision must exactly match its subject"
                )
            if (
                projection.entity_type not in _DOMAINS
                or decision.outcome is not PolicyOutcome.admitted
                or domain_by_identity.get(projection.canonical_identity_id)
                != projection.entity_type
            ):
                raise ValueError(
                    "projection inclusion semantics must match admitted outcome/domain"
                )
        for rejected in self.rejected_projections:
            decision = decision_by_identity[rejected.canonical_identity_id]
            expected_reasons = (
                f"inclusion_{decision.outcome.value}",
                *decision.hard_exclusion_codes,
            )
            if (
                rejected.entity_type not in _DOMAINS
                or decision.outcome is PolicyOutcome.admitted
                or domain_by_identity.get(rejected.canonical_identity_id)
                != rejected.entity_type
                or rejected.reason_codes != expected_reasons
            ):
                raise ValueError(
                    "rejected projection semantics must exactly match "
                    "inclusion outcome/domain/reasons"
                )
        payload = cast(
            JsonValue,
            self.model_dump(mode="json", exclude={"content_sha256"}),
        )
        if self.content_sha256 != _canonical_sha256(payload):
            raise ValueError("content_sha256 must bind the complete projection result")
        return self


class DomainProjectionBuilder(ABC):
    """Build typed current projections without performing persistence."""

    @abstractmethod
    def project(self, request: DomainProjectionRequest) -> DomainProjectionResult:
        """Project one release from retained identity and decision inputs."""


class _EphemeralDomainProjectionBuilder(DomainProjectionBuilder):
    def project(self, request: DomainProjectionRequest) -> DomainProjectionResult:
        context = _ProjectionContext(request)
        projections: list[Projection] = []
        rejected: list[RejectedProjection] = []
        for identity in sorted(
            request.canonical_identities,
            key=lambda item: (item.entity_type, item.canonical_identity_id),
        ):
            inclusion = context.inclusion_by_identity.get(
                identity.canonical_identity_id
            )
            if inclusion is None:
                raise DomainProjectionIntegrityError(
                    "every projection identity requires an inclusion decision"
                )
            if inclusion.outcome is not PolicyOutcome.admitted:
                rejected.append(
                    RejectedProjection(
                        canonical_identity_id=identity.canonical_identity_id,
                        entity_type=identity.entity_type,
                        reason_codes=(
                            f"inclusion_{inclusion.outcome.value}",
                            *inclusion.hard_exclusion_codes,
                        ),
                    )
                )
                continue
            projections.append(context.project_identity(identity, inclusion))

        projection_values = tuple(
            sorted(
                projections,
                key=lambda item: (item.entity_type, item.canonical_identity_id),
            )
        )
        rejected_values = tuple(
            sorted(
                rejected,
                key=lambda item: (item.entity_type, item.canonical_identity_id),
            )
        )
        manifest = tuple(
            DomainProjectionManifestEntry(
                canonical_identity_id=item.canonical_identity_id,
                entity_type=item.entity_type,
                projection_content_sha256=item.content_sha256,
            )
            for item in projection_values
        )
        counts = {
            domain: sum(item.entity_type == domain for item in projection_values)
            for domain in ("company", "paper", "patent", "professor")
        }
        content: dict[str, Any] = {
            "release_id": request.release_id,
            "build_run_id": request.build_run_id,
            "as_of": request.as_of,
            "projection_version": request.projection_version,
            "catalog_schema_version": request.catalog_schema_version,
            "catalog_version": request.catalog_version,
            "catalog_content_sha256": request.catalog_content_sha256,
            "inclusion_result": request.inclusion_result,
            "inclusion_result_content_sha256": (
                request.inclusion_result.content_sha256
            ),
            "approved_source_scope_manifest_sha256": (
                request.inclusion_result.approved_source_scope_manifest_sha256
            ),
            "projections": projection_values,
            "rejected_projections": rejected_values,
            "inclusion_decisions": tuple(
                sorted(
                    request.inclusion_result.policy_decisions,
                    key=lambda item: item.subject_identity_id,
                )
            ),
            "manifest": manifest,
            "counts_by_domain": counts,
        }
        provisional = DomainProjectionResult.model_construct(
            **content,
            content_sha256="0" * 64,
        )
        payload = cast(
            JsonValue,
            provisional.model_dump(mode="json", exclude={"content_sha256"}),
        )
        return DomainProjectionResult(
            **content,
            content_sha256=_canonical_sha256(payload),
        )


class _ProjectionContext:
    def __init__(self, request: DomainProjectionRequest) -> None:
        self.request = request
        self.catalog_by_domain = {
            item.domain: item for item in PACKAGED_CATALOG.domains
        }
        self.identities = _index_unique(
            request.canonical_identities,
            "canonical_identity_id",
            "canonical identities",
        )
        self.assertions = _index_unique(
            request.source_assertions, "assertion_id", "source assertions"
        )
        self.decisions = _index_unique(
            request.canonical_decisions, "decision_id", "canonical decisions"
        )
        self.inclusion_by_identity = _index_unique(
            request.inclusion_result.policy_decisions,
            "subject_identity_id",
            "inclusion decisions",
        )
        self.assignments = _index_unique(
            request.source_identity_assignments,
            "source_identity_id",
            "source identity assignments",
        )
        self.current_by_subject_path: dict[tuple[str, str], CurrentFieldSelection] = {}
        self._validate_catalog_identity()
        self._validate_graph()

    def _validate_catalog_identity(self) -> None:
        identity = (
            self.request.catalog_schema_version,
            self.request.catalog_version,
            self.request.catalog_content_sha256,
        )
        expected = (
            CATALOG_SCHEMA_VERSION,
            CATALOG_VERSION,
            CATALOG_CONTENT_SHA256,
        )
        if identity != expected:
            raise DomainProjectionIntegrityError(
                "projection request does not bind the installed catalog"
            )

    def _validate_graph(self) -> None:
        if (
            self.request.inclusion_result.release_id != self.request.release_id
            or self.request.inclusion_result.evaluated_at > self.request.as_of
        ):
            raise DomainProjectionIntegrityError(
                "inclusion result does not bind the projection release/as-of"
            )
        source_to_identity: dict[str, str] = {}
        for identity in self.identities.values():
            if identity.release_id != self.request.release_id:
                raise DomainProjectionIntegrityError(
                    "canonical identity release does not match projection release"
                )
            if identity.state is not CanonicalIdentityState.active:
                raise DomainProjectionIntegrityError(
                    "only active canonical identities may receive current projections"
                )
            if identity.entity_type not in self.catalog_by_domain:
                raise DomainProjectionIntegrityError(
                    f"unsupported canonical identity domain: {identity.entity_type}"
                )
            for source_identity_id in identity.source_identity_ids:
                assignment = self.assignments.get(source_identity_id)
                if assignment is None:
                    raise DomainProjectionIntegrityError(
                        "canonical identity has a missing source assignment"
                    )
                if (
                    assignment.release_id != self.request.release_id
                    or assignment.canonical_identity_id
                    != identity.canonical_identity_id
                    or assignment.identity_decision_id != identity.identity_decision_id
                ):
                    raise DomainProjectionIntegrityError(
                        "source assignment does not bind the active identity decision"
                    )
                source_to_identity[source_identity_id] = identity.canonical_identity_id
        if set(self.assignments) != set(source_to_identity):
            raise DomainProjectionIntegrityError(
                "source assignments must belong to supplied active identities"
            )
        for assertion in self.assertions.values():
            identity_id = source_to_identity.get(assertion.source_identity_id)
            if identity_id is None:
                raise DomainProjectionIntegrityError(
                    "source assertion has no active canonical assignment"
                )
            identity = self.identities[identity_id]
            if assertion.subject_entity_type != identity.entity_type:
                raise DomainProjectionIntegrityError(
                    "source assertion domain does not match its canonical identity"
                )
            if assertion.observed_at > self.request.as_of:
                raise DomainProjectionIntegrityError(
                    "projection cannot select a future source assertion"
                )
        for decision in self.decisions.values():
            identity = self.identities.get(decision.canonical_identity_id)
            if identity is None:
                raise DomainProjectionIntegrityError(
                    "canonical decision references a missing identity"
                )
            if decision.release_id != self.request.release_id:
                raise DomainProjectionIntegrityError(
                    "canonical decision release does not match projection release"
                )
            if decision.decided_at > self.request.as_of:
                raise DomainProjectionIntegrityError(
                    "projection cannot select a future canonical decision"
                )
            if not set(decision.candidate_assertion_ids) <= set(self.assertions):
                raise DomainProjectionIntegrityError(
                    "canonical decision references a missing assertion"
                )
            for assertion_id in decision.candidate_assertion_ids:
                assertion = self.assertions[assertion_id]
                if (
                    source_to_identity.get(assertion.source_identity_id)
                    != decision.canonical_identity_id
                    or assertion.field_path != decision.field_path
                ):
                    raise DomainProjectionIntegrityError(
                        "canonical decision candidate assertion belongs to another "
                        "identity or field path"
                    )
        for current in self.request.current_fields:
            key = (current.canonical_identity_id, current.field_path)
            if key in self.current_by_subject_path:
                raise DomainProjectionIntegrityError(
                    "duplicate current field selection for one identity/path"
                )
            identity = self.identities.get(current.canonical_identity_id)
            decision = self.decisions.get(current.decision_id)
            if identity is None or decision is None:
                raise DomainProjectionIntegrityError(
                    "current field references a missing identity or decision"
                )
            if current.release_id != self.request.release_id:
                raise DomainProjectionIntegrityError(
                    "current field release does not match projection release"
                )
            if (
                decision.state is not DecisionState.selected
                or decision.canonical_identity_id != current.canonical_identity_id
                or decision.field_path != current.field_path
                or decision.selected_assertion_ids != current.supporting_assertion_ids
            ):
                raise DomainProjectionIntegrityError(
                    "current field does not match its selected canonical decision"
                )
            for assertion_id in current.supporting_assertion_ids:
                assertion = self.assertions.get(assertion_id)
                if (
                    assertion is None
                    or source_to_identity.get(assertion.source_identity_id)
                    != current.canonical_identity_id
                    or assertion.field_path != current.field_path
                    or assertion.value != current.value
                ):
                    raise DomainProjectionIntegrityError(
                        "current field value is not bound to its selected assertion"
                    )
                if (current.valid_from, current.valid_to) != (
                    assertion.valid_from,
                    assertion.valid_to,
                ):
                    raise DomainProjectionIntegrityError(
                        "current field validity must exactly match every selected "
                        "assertion"
                    )
            self.current_by_subject_path[key] = current
        for inclusion in self.inclusion_by_identity.values():
            identity = self.identities.get(inclusion.subject_identity_id)
            if identity is None:
                raise DomainProjectionIntegrityError(
                    "inclusion decision references a missing identity"
                )
            if (
                inclusion.release_id != self.request.release_id
                or inclusion.policy.policy_kind is not PolicyKind.inclusion
                or inclusion.evaluated_at > self.request.as_of
            ):
                raise DomainProjectionIntegrityError(
                    "inclusion decision is not valid for this release/as-of"
                )
            if not set(inclusion.supporting_assertion_ids) <= set(self.assertions):
                raise DomainProjectionIntegrityError(
                    "inclusion decision references a missing assertion"
                )
            for assertion_id in inclusion.supporting_assertion_ids:
                assertion = self.assertions[assertion_id]
                if (
                    source_to_identity.get(assertion.source_identity_id)
                    != inclusion.subject_identity_id
                    or assertion.subject_entity_type != identity.entity_type
                ):
                    raise DomainProjectionIntegrityError(
                        "inclusion supporting assertion must belong to the exact "
                        "subject identity and domain"
                    )

    def project_identity(
        self,
        identity: CanonicalIdentity,
        inclusion: PolicyDecision,
    ) -> Projection:
        catalog = self.catalog_by_domain[identity.entity_type]
        selections = tuple(
            sorted(
                (
                    selection
                    for (
                        identity_id,
                        _,
                    ), selection in self.current_by_subject_path.items()
                    if identity_id == identity.canonical_identity_id
                ),
                key=lambda item: item.field_path,
            )
        )
        allowed_fields = {field.field_path for field in catalog.fields}
        subobject_inputs = _SUBOBJECT_INPUTS[identity.entity_type]
        unknown_fields = {
            selection.field_path
            for selection in selections
            if selection.field_path not in allowed_fields
            and selection.field_path not in subobject_inputs
        }
        if unknown_fields:
            raise DomainProjectionIntegrityError(
                f"current selection uses unknown {identity.entity_type} fields: "
                f"{sorted(unknown_fields)}"
            )
        field_values = {item.field_path: item.value for item in selections}
        projected_values: dict[str, Any] = {}
        for selection in selections:
            subobject_input = subobject_inputs.get(selection.field_path)
            if subobject_input is None:
                projected_values[selection.field_path] = selection.value
                continue
            attribute, subobject_model = subobject_input
            if attribute in projected_values:
                raise DomainProjectionIntegrityError(
                    f"multiple selections populate sub-object container: {attribute}"
                )
            if not isinstance(selection.value, list):
                raise DomainProjectionIntegrityError(
                    f"sub-object selection must be a list: {selection.field_path}"
                )
            typed_values: list[TypedSubobject] = []
            for raw_value in selection.value:
                if not isinstance(raw_value, dict):
                    raise DomainProjectionIntegrityError(
                        f"{selection.field_path} members must be typed objects"
                    )
                if "projection_content_sha256" in raw_value:
                    raise DomainProjectionIntegrityError(
                        "callers cannot provide a precomputed sub-object projection hash"
                    )
                provisional_values = {
                    **raw_value,
                    "projection_content_sha256": "0" * 64,
                }
                for bound in ("valid_from", "valid_to"):
                    raw_bound = raw_value.get(bound)
                    expected_bound = getattr(selection, bound)
                    if (raw_bound is None) != (expected_bound is None):
                        raise DomainProjectionIntegrityError(
                            f"{selection.field_path} sub-object validity must exactly "
                            "match its current selection and assertions"
                        )
                    if not isinstance(raw_bound, str):
                        continue
                    try:
                        if (
                            isinstance(expected_bound, TemporalDateValue)
                            or type(expected_bound) is Date
                        ):
                            provisional_values[bound] = Date.fromisoformat(raw_bound)
                        elif isinstance(
                            expected_bound, (TemporalInstantValue, datetime)
                        ):
                            provisional_values[bound] = datetime.fromisoformat(
                                raw_bound.replace("Z", "+00:00")
                            )
                    except ValueError as exc:
                        raise DomainProjectionIntegrityError(
                            f"{selection.field_path} sub-object validity is invalid"
                        ) from exc
                try:
                    provisional_subobject = subobject_model.model_validate(
                        provisional_values,
                        context={"allow_unbound_projection_hash": True},
                    )
                except ValueError as exc:
                    raise DomainProjectionIntegrityError(
                        f"invalid {selection.field_path} sub-object: {exc}"
                    ) from exc
                subobject_payload = cast(
                    JsonValue,
                    provisional_subobject.model_dump(
                        mode="json", exclude={"projection_content_sha256"}
                    ),
                )
                typed_value = subobject_model.model_validate(
                    {
                        **provisional_subobject.model_dump(mode="python"),
                        "projection_content_sha256": _canonical_sha256(
                            subobject_payload
                        ),
                    }
                )
                if (
                    typed_value.parent_canonical_identity_id
                    != identity.canonical_identity_id
                    or typed_value.supporting_assertion_ids
                    != selection.supporting_assertion_ids
                    or typed_value.decision_ids != (selection.decision_id,)
                    or typed_value.observed_at > self.request.as_of
                ):
                    raise DomainProjectionIntegrityError(
                        f"{selection.field_path} sub-object lineage does not match "
                        "its current selection"
                    )
                if (typed_value.valid_from, typed_value.valid_to) != (
                    selection.valid_from,
                    selection.valid_to,
                ):
                    raise DomainProjectionIntegrityError(
                        f"{selection.field_path} sub-object validity must exactly "
                        "match its current selection and assertions"
                    )
                typed_values.append(typed_value)
            projected_values[attribute] = tuple(
                sorted(typed_values, key=lambda item: item.subobject_id)
            )
        lineage = tuple(
            FieldProjectionLineage(
                field_path=item.field_path,
                decision_id=item.decision_id,
                supporting_assertion_ids=item.supporting_assertion_ids,
            )
            for item in selections
        )
        supporting_assertions = tuple(
            self.assertions[assertion_id]
            for item in selections
            for assertion_id in item.supporting_assertion_ids
        )
        if not supporting_assertions:
            raise DomainProjectionIntegrityError(
                "admitted current projection requires selected field evidence"
            )
        evidence = tuple(
            ProjectionEvidenceReference(
                assertion_id=assertion.assertion_id,
                decision_id=self.current_by_subject_path[
                    (identity.canonical_identity_id, assertion.field_path)
                ].decision_id,
                field_path=assertion.field_path,
            )
            for assertion in sorted(
                supporting_assertions, key=lambda item: item.assertion_id
            )
        )
        values: dict[str, Any] = {
            "release_id": self.request.release_id,
            "canonical_identity_id": identity.canonical_identity_id,
            "identity_decision_id": identity.identity_decision_id,
            "inclusion_decision_id": inclusion.decision_id,
            "projection_version": self.request.projection_version,
            "catalog_schema_version": self.request.catalog_schema_version,
            "catalog_version": self.request.catalog_version,
            "catalog_content_sha256": self.request.catalog_content_sha256,
            "as_of": self.request.as_of,
            "field_lineage": lineage,
            "id": identity.canonical_identity_id,
            "evidence": evidence,
            "last_updated": max(item.observed_at for item in supporting_assertions),
            "quality_status": self._quality_status(catalog, field_values),
            "run_id": self.request.build_run_id,
            **projected_values,
            "content_sha256": "0" * 64,
        }
        model = _MODEL_BY_DOMAIN[identity.entity_type]
        try:
            provisional = model.model_validate(
                values,
                context={"allow_unbound_projection_hash": True},
            )
        except ValueError as exc:
            raise DomainProjectionIntegrityError(
                f"invalid typed {identity.entity_type} projection: {exc}"
            ) from exc
        payload = cast(
            JsonValue,
            provisional.model_dump(mode="json", exclude={"content_sha256"}),
        )
        values["content_sha256"] = _canonical_sha256(payload)
        return model.model_validate(values)

    @staticmethod
    def _quality_status(
        catalog: CatalogDomainDefinition, field_values: dict[str, JsonValue]
    ) -> str:
        optional_paths = {
            field.field_path
            for field in catalog.fields
            if field.requiredness != "required"
        }
        return "partial" if optional_paths - set(field_values) else "complete"


_MODEL_BY_DOMAIN: dict[str, type[Projection]] = {
    "company": CompanyProjection,
    "paper": PaperProjection,
    "patent": PatentProjection,
    "professor": ProfessorProjection,
}

_SUBOBJECT_INPUTS: dict[
    str,
    dict[str, tuple[str, type[TypedSubobject]]],
] = {
    "company": {
        "business_scenario": (
            "business_scenarios",
            DOMAIN_SUBOBJECT_MODELS["company"]["business_scenario"],
        ),
        "capability": (
            "capabilities",
            DOMAIN_SUBOBJECT_MODELS["company"]["capability"],
        ),
        "financing_event": (
            "financing_events",
            DOMAIN_SUBOBJECT_MODELS["company"]["financing_event"],
        ),
        "key_personnel": (
            "key_personnel",
            DOMAIN_SUBOBJECT_MODELS["company"]["key_personnel"],
        ),
        "personnel_education": (
            "personnel_education",
            DOMAIN_SUBOBJECT_MODELS["company"]["personnel_education"],
        ),
        "personnel_work_experience": (
            "personnel_work_experience",
            DOMAIN_SUBOBJECT_MODELS["company"]["personnel_work_experience"],
        ),
        "product": (
            "products",
            DOMAIN_SUBOBJECT_MODELS["company"]["product"],
        ),
        "latest_public_updates": (
            "latest_public_updates",
            DOMAIN_SUBOBJECT_MODELS["company"]["public_update"],
        ),
        "public_update": (
            "latest_public_updates",
            DOMAIN_SUBOBJECT_MODELS["company"]["public_update"],
        ),
    },
    "paper": {
        "author": ("authors", DOMAIN_SUBOBJECT_MODELS["paper"]["author"]),
        "authors": ("authors", DOMAIN_SUBOBJECT_MODELS["paper"]["author"]),
        "enrichment_provenance": (
            "enrichment_sources",
            DOMAIN_SUBOBJECT_MODELS["paper"]["enrichment_provenance"],
        ),
        "enrichment_sources": (
            "enrichment_sources",
            DOMAIN_SUBOBJECT_MODELS["paper"]["enrichment_provenance"],
        ),
        "full_text": (
            "full_texts",
            DOMAIN_SUBOBJECT_MODELS["paper"]["full_text"],
        ),
        "funding": ("funders", DOMAIN_SUBOBJECT_MODELS["paper"]["funding"]),
        "funders": ("funders", DOMAIN_SUBOBJECT_MODELS["paper"]["funding"]),
        "identifier": (
            "identifiers",
            DOMAIN_SUBOBJECT_MODELS["paper"]["identifier"],
        ),
        "publication": (
            "publications",
            DOMAIN_SUBOBJECT_MODELS["paper"]["publication"],
        ),
        "reference": (
            "references",
            DOMAIN_SUBOBJECT_MODELS["paper"]["reference"],
        ),
        "summary": ("summaries", DOMAIN_SUBOBJECT_MODELS["paper"]["summary"]),
    },
    "patent": {
        "applicant": (
            "applicants",
            DOMAIN_SUBOBJECT_MODELS["patent"]["applicant"],
        ),
        "applicants": (
            "applicants",
            DOMAIN_SUBOBJECT_MODELS["patent"]["applicant"],
        ),
        "inventor": (
            "inventors",
            DOMAIN_SUBOBJECT_MODELS["patent"]["inventor"],
        ),
        "inventors": (
            "inventors",
            DOMAIN_SUBOBJECT_MODELS["patent"]["inventor"],
        ),
        "ipc_classification": (
            "ipc_codes",
            DOMAIN_SUBOBJECT_MODELS["patent"]["ipc_classification"],
        ),
        "ipc_codes": (
            "ipc_codes",
            DOMAIN_SUBOBJECT_MODELS["patent"]["ipc_classification"],
        ),
        "patent_milestone": (
            "milestones",
            DOMAIN_SUBOBJECT_MODELS["patent"]["patent_milestone"],
        ),
        "technical_summary": (
            "technical_summaries",
            DOMAIN_SUBOBJECT_MODELS["patent"]["technical_summary"],
        ),
    },
    "professor": {
        "affiliation_history": (
            "affiliation_history",
            DOMAIN_SUBOBJECT_MODELS["professor"]["affiliation_history"],
        ),
        "award": ("awards", DOMAIN_SUBOBJECT_MODELS["professor"]["award"]),
        "awards": ("awards", DOMAIN_SUBOBJECT_MODELS["professor"]["award"]),
        "contact": (
            "contacts",
            DOMAIN_SUBOBJECT_MODELS["professor"]["contact"],
        ),
        "education_history": (
            "education_history",
            DOMAIN_SUBOBJECT_MODELS["professor"]["education_history"],
        ),
        "metric_snapshot": (
            "metric_snapshots",
            DOMAIN_SUBOBJECT_MODELS["professor"]["metric_snapshot"],
        ),
        "projects": (
            "projects",
            DOMAIN_SUBOBJECT_MODELS["professor"]["research_project"],
        ),
        "research_project": (
            "projects",
            DOMAIN_SUBOBJECT_MODELS["professor"]["research_project"],
        ),
        "work_history": (
            "work_history",
            DOMAIN_SUBOBJECT_MODELS["professor"]["work_history"],
        ),
    },
}


def create_ephemeral_domain_projection_builder() -> DomainProjectionBuilder:
    """Return the pure in-process projection implementation."""

    return _EphemeralDomainProjectionBuilder()


__all__ = [
    "CompanyProjection",
    "DOMAIN_SUBOBJECT_ATTRIBUTES",
    "DOMAIN_SUBOBJECT_MODELS",
    "DomainProjectionBuilder",
    "DomainProjectionIntegrityError",
    "DomainProjectionManifestEntry",
    "DomainProjectionRequest",
    "DomainProjectionResult",
    "PaperProjection",
    "PatentProjection",
    "PACKAGED_CATALOG",
    "ProfessorProjection",
    "RejectedProjection",
    "create_ephemeral_domain_projection_builder",
]
