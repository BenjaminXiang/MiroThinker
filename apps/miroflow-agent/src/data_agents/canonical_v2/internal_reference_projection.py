"""Pure internal Person and Technology projection for Canonical V2 candidates.

The module consumes complete accepted four-domain projections plus the exact
request/result pair produced by the offline identity-resolution deep module.  It
derives evidence anchors and internal resolution state; callers cannot declare a
Person or Technology canonical identity, alias, hierarchy, or resolved reference
at this seam.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
import hashlib
import json
from typing import Any, Literal, cast

from pydantic import Field, JsonValue, ValidationError, ValidationInfo
from pydantic import field_validator, model_validator

from .canonical_identity_resolution import (
    CanonicalIdentityResolutionError,
    IdentityCandidateOutcome,
    IdentityDecisionContext,
    IdentityResolutionRequest,
    IdentityResolutionResult,
    PERSON_IDENTITY_METHOD_VERSION,
    TECHNOLOGY_IDENTITY_METHOD_VERSION,
    normalize_identity_key_value,
    validate_identity_resolution_result,
)
from .contracts import (
    CanonicalDatetime,
    CanonicalIdentityState,
    ContractModel,
    NonEmptyStr,
    Sha256,
    SourceAssertion,
    SourceIdentity,
    TemporalRelation,
    TemporalValue,
    compare_temporal_values,
)
from .domain_projection import (
    DomainProjectionRequest,
    DomainProjectionResult,
    Projection,
    create_ephemeral_domain_projection_builder,
)
from .domain_projection_models import (
    CompanyKeyPersonnel,
    CompanyPersonnelEducation,
    CompanyPersonnelWorkExperience,
    CompanyProjection,
    PaperAuthor,
    PatentInventor,
    ProfessorEducationHistory,
    ProfessorProjection,
    ProfessorWorkHistory,
    TypedSubobject,
)
from .internal_reference_catalog import (
    INTERNAL_REFERENCE_TYPES,
    PACKAGED_REFERENCE_CATALOG,
    PUBLIC_DOMAIN_TYPES,
    REFERENCE_CATALOG_CONTENT_SHA256,
    REFERENCE_CATALOG_SCHEMA_VERSION,
    REFERENCE_CATALOG_VERSION,
    InstalledInternalReferenceCatalog,
)


PublicDomainType = Literal["company", "paper", "patent", "professor"]
PersonResolutionState = Literal["resolved", "unresolved"]
TechnologyReferenceType = Literal["technology_concept", "technology_route"]
TechnologyResolutionState = Literal["resolved", "unresolved"]
PersonSourceKind = Literal[
    "company_personnel",
    "company_personnel_education",
    "company_personnel_work_experience",
    "paper_author",
    "patent_inventor",
    "professor",
    "professor_education",
    "professor_work_history",
]

INTERNAL_REFERENCE_PROJECTION_VERSION = "internal-reference-v1"
_PERSON_DEFINITION = next(
    item
    for item in PACKAGED_REFERENCE_CATALOG.internal_reference_types
    if item.reference_type == "person"
)
PERSON_REFERENCE_PROJECTION_VERSION = _PERSON_DEFINITION.projection_schema_version
if PERSON_REFERENCE_PROJECTION_VERSION != "person-reference-projection-v1":
    raise RuntimeError("installed Person projection schema version is unsupported")
_TECHNOLOGY_CONCEPT_DEFINITION = next(
    item
    for item in PACKAGED_REFERENCE_CATALOG.internal_reference_types
    if item.reference_type == "technology_concept"
)
_TECHNOLOGY_ROUTE_DEFINITION = next(
    item
    for item in PACKAGED_REFERENCE_CATALOG.internal_reference_types
    if item.reference_type == "technology_route"
)
TECHNOLOGY_CONCEPT_PROJECTION_VERSION = (
    _TECHNOLOGY_CONCEPT_DEFINITION.projection_schema_version
)
TECHNOLOGY_ROUTE_PROJECTION_VERSION = (
    _TECHNOLOGY_ROUTE_DEFINITION.projection_schema_version
)
if (
    TECHNOLOGY_CONCEPT_PROJECTION_VERSION != "technology-concept-projection-v1"
    or TECHNOLOGY_ROUTE_PROJECTION_VERSION != "technology-route-projection-v1"
):
    raise RuntimeError("installed Technology projection schema version is unsupported")

_SOURCE_KIND_SPECS: dict[
    PersonSourceKind,
    tuple[PublicDomainType, str | None, str | None],
] = {
    "company_personnel": ("company", "key_personnel", "key_personnel"),
    "company_personnel_education": (
        "company",
        "personnel_education",
        "personnel_education",
    ),
    "company_personnel_work_experience": (
        "company",
        "personnel_work_experience",
        "personnel_work_experience",
    ),
    "paper_author": ("paper", "author", "authors"),
    "patent_inventor": ("patent", "inventor", "inventors"),
    "professor": ("professor", None, None),
    "professor_education": (
        "professor",
        "education_history",
        "education_history",
    ),
    "professor_work_history": (
        "professor",
        "work_history",
        "work_history",
    ),
}
_SUBOBJECT_MODELS: dict[PersonSourceKind, type[TypedSubobject]] = {
    "company_personnel": CompanyKeyPersonnel,
    "company_personnel_education": CompanyPersonnelEducation,
    "company_personnel_work_experience": CompanyPersonnelWorkExperience,
    "paper_author": PaperAuthor,
    "patent_inventor": PatentInventor,
    "professor_education": ProfessorEducationHistory,
    "professor_work_history": ProfessorWorkHistory,
}
_PROFESSOR_NAME_PATHS = {"name", "canonical_name_zh", "canonical_name_en"}


class InternalReferenceProjectionIntegrityError(ValueError):
    """The supplied accepted-reference projection inputs are inconsistent."""


def _unique_sorted(values: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(values)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return tuple(sorted(result))


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


def _installed_catalog_identity() -> tuple[str, str, str]:
    return (
        REFERENCE_CATALOG_SCHEMA_VERSION,
        REFERENCE_CATALOG_VERSION,
        REFERENCE_CATALOG_CONTENT_SHA256,
    )


class ReferenceCatalogIdentity(ContractModel):
    schema_version: Literal["canonical-v2-reference-catalog-v1"]
    catalog_version: Literal["canonical-v2-person-technology-reference-2026-07-13"]
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_installed_identity(self) -> ReferenceCatalogIdentity:
        if (
            self.schema_version,
            self.catalog_version,
            self.content_sha256,
        ) != _installed_catalog_identity():
            raise ValueError("reference catalog identity differs from the installation")
        return self


class PersonEvidenceLocator(ContractModel):
    reference_id: NonEmptyStr
    source_kind: PersonSourceKind
    root_canonical_identity_id: NonEmptyStr
    source_subobject_id: NonEmptyStr | None = None
    source_identity_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_locator_shape(self) -> PersonEvidenceLocator:
        _, expected_subobject_type, _ = _SOURCE_KIND_SPECS[self.source_kind]
        if (expected_subobject_type is None) != (self.source_subobject_id is None):
            raise ValueError(
                "Person locator subobject shape differs from its source kind"
            )
        return self


class PersonEvidenceCrosswalk(ContractModel):
    source_kind: PersonSourceKind
    root_canonical_identity_id: NonEmptyStr
    source_subobject_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_crosswalk_shape(self) -> PersonEvidenceCrosswalk:
        _, expected_subobject_type, _ = _SOURCE_KIND_SPECS[self.source_kind]
        if (expected_subobject_type is None) != (self.source_subobject_id is None):
            raise ValueError(
                "Person evidence crosswalk shape differs from its source kind"
            )
        return self


class PublicDomainEvidenceAnchor(ContractModel):
    anchor_id: NonEmptyStr
    source_kind: PersonSourceKind
    public_domain: PublicDomainType
    root_canonical_identity_id: NonEmptyStr
    root_projection_version: NonEmptyStr
    root_projection_content_sha256: Sha256
    root_projection_as_of: CanonicalDatetime
    domain_catalog_schema_version: NonEmptyStr
    domain_catalog_version: NonEmptyStr
    domain_catalog_content_sha256: Sha256
    source_field_paths: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_subobject_type: NonEmptyStr | None = None
    source_subobject_id: NonEmptyStr | None = None
    source_subobject_content_sha256: Sha256 | None = None
    person_name: NonEmptyStr
    person_orcid: NonEmptyStr | None = None
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    decision_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    observed_at: CanonicalDatetime
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    release_id: NonEmptyStr
    content_sha256: Sha256

    @field_validator(
        "source_field_paths",
        "supporting_assertion_ids",
        "decision_ids",
        "source_record_ids",
    )
    @classmethod
    def validate_sorted_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = _unique_sorted(values, "public evidence anchor lineage values")
        if values != normalized:
            raise ValueError("public evidence anchor lineage values must be sorted")
        return values

    @model_validator(mode="after")
    def validate_anchor(self, info: ValidationInfo) -> PublicDomainEvidenceAnchor:
        expected_domain, expected_subobject_type, _ = _SOURCE_KIND_SPECS[
            self.source_kind
        ]
        if self.public_domain != expected_domain:
            raise ValueError("public evidence anchor domain differs from source kind")
        base_catalog = PACKAGED_REFERENCE_CATALOG.base_domain_catalog
        if (
            self.domain_catalog_schema_version,
            self.domain_catalog_version,
            self.domain_catalog_content_sha256,
        ) != (
            base_catalog.schema_version,
            base_catalog.catalog_version,
            base_catalog.content_sha256,
        ):
            raise ValueError("public evidence anchor domain catalog identity differs")
        subobject_values = (
            self.source_subobject_type,
            self.source_subobject_id,
            self.source_subobject_content_sha256,
        )
        if expected_subobject_type is None:
            if any(value is not None for value in subobject_values):
                raise ValueError("Professor root anchor cannot carry a subobject")
        elif (
            any(value is None for value in subobject_values)
            or self.source_subobject_type != expected_subobject_type
        ):
            raise ValueError("public evidence anchor typed subobject differs")
        if expected_subobject_type is None:
            if not set(self.source_field_paths) <= _PROFESSOR_NAME_PATHS:
                raise ValueError("Professor root anchor paths are not Person names")
        elif self.source_field_paths != (_SOURCE_KIND_SPECS[self.source_kind][2],):
            raise ValueError("typed Person anchor field path differs from source kind")
        if self.source_kind != "paper_author" and self.person_orcid is not None:
            raise ValueError("only a Paper author anchor may carry a typed ORCID")
        if self.observed_at > self.root_projection_as_of:
            raise ValueError("source observation cannot be after projection as_of")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and type(self.valid_from) is not type(self.valid_to)
        ):
            raise ValueError("anchor validity endpoints must use one time shape")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and compare_temporal_values(self.valid_from, self.valid_to)
            is TemporalRelation.after
        ):
            raise ValueError("anchor valid_from must not be after valid_to")
        semantic_payload = cast(
            JsonValue,
            self.model_dump(mode="json", exclude={"anchor_id", "content_sha256"}),
        )
        expected_hash = _canonical_sha256(semantic_payload)
        if not (info.context or {}).get("allow_unbound_anchor_hash") and (
            self.content_sha256 != expected_hash
            or self.anchor_id != f"public-domain-evidence:sha256:{expected_hash}"
        ):
            raise ValueError("public evidence anchor must be content-addressed")
        return self


class PersonReference(ContractModel):
    reference_id: NonEmptyStr
    name: NonEmptyStr
    source_kind: PersonSourceKind
    source_anchor_id: NonEmptyStr
    source_identity_id: NonEmptyStr
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    identity_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    shared_source_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    identity_resolution_content_sha256: Sha256
    resolution_state: PersonResolutionState
    canonical_person_identity_id: NonEmptyStr | None
    assignment_decision_id: NonEmptyStr | None
    candidate_verdict_id: NonEmptyStr | None = None
    review_case_id: NonEmptyStr | None = None

    @field_validator(
        "supporting_assertion_ids",
        "identity_assertion_ids",
        "shared_source_record_ids",
    )
    @classmethod
    def validate_assertion_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = _unique_sorted(values, "Person reference assertion IDs")
        if values != normalized:
            raise ValueError("Person reference assertion IDs must be sorted")
        return values

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> PersonReference:
        if self.resolution_state == "resolved":
            if (
                self.canonical_person_identity_id is None
                or self.assignment_decision_id is None
                or self.review_case_id is not None
            ):
                raise ValueError("resolved Person reference lineage is incomplete")
        elif (
            self.canonical_person_identity_id is not None
            or self.assignment_decision_id is not None
        ):
            raise ValueError("unresolved Person reference cannot expose an identity")
        if self.review_case_id is not None and self.candidate_verdict_id is None:
            raise ValueError("Person review lineage requires its candidate verdict")
        return self


class PersonProjection(ContractModel):
    canonical_person_identity_id: NonEmptyStr
    display_name: NonEmptyStr
    aliases: tuple[NonEmptyStr, ...]
    references: tuple[PersonReference, ...] = Field(min_length=1)
    source_anchor_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_public_domains: tuple[PublicDomainType, ...] = Field(min_length=1)
    source_identity_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    identity_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    assignment_decision_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    identity_verdict_ids: tuple[NonEmptyStr, ...] = ()
    identity_decision_id: NonEmptyStr
    identity_resolution_content_sha256: Sha256
    release_id: NonEmptyStr
    projection_version: Literal["person-reference-projection-v1"]
    projection_scope: Literal["internal_auxiliary"]
    reference_type: Literal["person"]
    domain: None = None
    reference_catalog_schema_version: Literal["canonical-v2-reference-catalog-v1"]
    reference_catalog_version: Literal[
        "canonical-v2-person-technology-reference-2026-07-13"
    ]
    reference_catalog_content_sha256: Sha256
    as_of: CanonicalDatetime
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_projection(self, info: ValidationInfo) -> PersonProjection:
        ordered_references = tuple(
            sorted(
                self.references,
                key=lambda item: (item.source_kind, item.reference_id),
            )
        )
        if self.references != ordered_references:
            raise ValueError("Person projection references must be deterministic")
        if any(
            reference.resolution_state != "resolved"
            or reference.canonical_person_identity_id
            != self.canonical_person_identity_id
            or reference.identity_resolution_content_sha256
            != self.identity_resolution_content_sha256
            for reference in self.references
        ):
            raise ValueError(
                "Person projection references have different identity lineage"
            )
        reference_names = {reference.name for reference in self.references}
        if self.display_name not in reference_names or self.aliases != tuple(
            sorted(reference_names - {self.display_name})
        ):
            raise ValueError("Person projection names must derive from its references")
        expected_sets = {
            "source_anchor_ids": {
                reference.source_anchor_id for reference in self.references
            },
            "source_identity_ids": {
                reference.source_identity_id for reference in self.references
            },
            "supporting_assertion_ids": {
                assertion_id
                for reference in self.references
                for assertion_id in reference.supporting_assertion_ids
            },
            "identity_assertion_ids": {
                assertion_id
                for reference in self.references
                for assertion_id in reference.identity_assertion_ids
            },
            "source_record_ids": {
                source_record_id
                for reference in self.references
                for source_record_id in reference.shared_source_record_ids
            },
            "assignment_decision_ids": {
                cast(str, reference.assignment_decision_id)
                for reference in self.references
            },
            "identity_verdict_ids": {
                reference.candidate_verdict_id
                for reference in self.references
                if reference.candidate_verdict_id is not None
            },
        }
        for field_name, expected in expected_sets.items():
            if getattr(self, field_name) != tuple(sorted(expected)):
                raise ValueError(f"Person projection {field_name} differs")
        if self.source_public_domains != tuple(
            sorted(
                {_SOURCE_KIND_SPECS[item.source_kind][0] for item in self.references}
            )
        ):
            raise ValueError("Person projection public domains differ")
        if (
            self.reference_catalog_schema_version,
            self.reference_catalog_version,
            self.reference_catalog_content_sha256,
        ) != _installed_catalog_identity():
            raise ValueError("Person projection reference catalog identity differs")
        if not (info.context or {}).get("allow_unbound_projection_hash"):
            payload = cast(
                JsonValue,
                self.model_dump(mode="json", exclude={"content_sha256"}),
            )
            if self.content_sha256 != _canonical_sha256(payload):
                raise ValueError("content_sha256 must bind the Person projection")
        return self


class TechnologyEvidenceLocator(ContractModel):
    """Locate one retained public object without declaring Technology facts."""

    reference_id: NonEmptyStr
    reference_type: TechnologyReferenceType
    technology_source_identity_id: NonEmptyStr
    public_domain: PublicDomainType
    root_canonical_identity_id: NonEmptyStr
    source_field_path: NonEmptyStr
    source_subobject_type: Literal["product"] | None = None
    source_subobject_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_locator_shape(self) -> TechnologyEvidenceLocator:
        has_type = self.source_subobject_type is not None
        has_id = self.source_subobject_id is not None
        if has_type != has_id:
            raise ValueError("Technology locator subobject shape is incomplete")
        if has_type and (
            self.public_domain != "company"
            or self.source_field_path != "product"
            or self.source_subobject_type != "product"
        ):
            raise ValueError("only a Company Product may be a typed Technology anchor")
        if not has_type and self.public_domain not in {"company", "paper", "patent"}:
            raise ValueError("Technology root anchors exclude the Professor domain")
        return self

    def crosswalk_value(self) -> dict[str, JsonValue]:
        return {
            "public_domain": self.public_domain,
            "root_canonical_identity_id": self.root_canonical_identity_id,
            "source_field_path": self.source_field_path,
            "source_subobject_type": self.source_subobject_type,
            "source_subobject_id": self.source_subobject_id,
        }


class TechnologyEvidenceAnchor(ContractModel):
    anchor_id: NonEmptyStr
    reference_id: NonEmptyStr
    reference_type: TechnologyReferenceType
    technology_source_identity_id: NonEmptyStr
    public_domain: PublicDomainType
    root_canonical_identity_id: NonEmptyStr
    root_projection_version: NonEmptyStr
    root_projection_content_sha256: Sha256
    root_projection_as_of: CanonicalDatetime
    domain_catalog_schema_version: NonEmptyStr
    domain_catalog_version: NonEmptyStr
    domain_catalog_content_sha256: Sha256
    source_field_path: NonEmptyStr
    source_subobject_type: Literal["product"] | None = None
    source_subobject_id: NonEmptyStr | None = None
    source_subobject_content_sha256: Sha256 | None = None
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    decision_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    observed_at: CanonicalDatetime
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    release_id: NonEmptyStr
    content_sha256: Sha256

    @field_validator(
        "supporting_assertion_ids",
        "decision_ids",
        "source_record_ids",
    )
    @classmethod
    def validate_sorted_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = _unique_sorted(values, "Technology anchor lineage values")
        if values != normalized:
            raise ValueError("Technology anchor lineage values must be sorted")
        return values

    @model_validator(mode="after")
    def validate_anchor(self, info: ValidationInfo) -> TechnologyEvidenceAnchor:
        base_catalog = PACKAGED_REFERENCE_CATALOG.base_domain_catalog
        if (
            self.domain_catalog_schema_version,
            self.domain_catalog_version,
            self.domain_catalog_content_sha256,
        ) != (
            base_catalog.schema_version,
            base_catalog.catalog_version,
            base_catalog.content_sha256,
        ):
            raise ValueError("Technology anchor domain catalog identity differs")
        has_subobject = self.source_subobject_type is not None
        subobject_values = (
            self.source_subobject_id,
            self.source_subobject_content_sha256,
        )
        if has_subobject != all(value is not None for value in subobject_values):
            raise ValueError("Technology anchor subobject lineage is incomplete")
        if has_subobject and (
            self.public_domain != "company"
            or self.source_field_path != "product"
            or self.source_subobject_type != "product"
        ):
            raise ValueError("Technology typed anchor must be a Company Product")
        if self.observed_at > self.root_projection_as_of:
            raise ValueError("Technology source observation is after projection as_of")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and type(self.valid_from) is not type(self.valid_to)
        ):
            raise ValueError("Technology anchor validity precision differs")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and compare_temporal_values(self.valid_from, self.valid_to)
            is TemporalRelation.after
        ):
            raise ValueError("Technology anchor valid_from is after valid_to")
        payload = cast(
            JsonValue,
            self.model_dump(mode="json", exclude={"anchor_id", "content_sha256"}),
        )
        expected_hash = _canonical_sha256(payload)
        if not (info.context or {}).get("allow_unbound_anchor_hash") and (
            self.content_sha256 != expected_hash
            or self.anchor_id != f"technology-evidence:sha256:{expected_hash}"
        ):
            raise ValueError("Technology evidence anchor must be content-addressed")
        return self


class TechnologyFieldLineage(ContractModel):
    field_path: NonEmptyStr
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("supporting_assertion_ids")
    @classmethod
    def validate_assertion_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = _unique_sorted(values, "Technology field assertion IDs")
        if values != normalized:
            raise ValueError("Technology field assertion IDs must be sorted")
        return values


class UnresolvedTechnologyReference(ContractModel):
    reference_id: NonEmptyStr
    reference_type: TechnologyReferenceType
    preferred_name: NonEmptyStr
    source_anchor_id: NonEmptyStr
    technology_source_identity_id: NonEmptyStr
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    identity_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    technology_identity_resolution_content_sha256: Sha256
    resolution_state: Literal["unresolved"] = "unresolved"
    candidate_verdict_id: NonEmptyStr | None = None
    review_case_id: NonEmptyStr | None = None


class _TechnologyProjectionBase(ContractModel):
    canonical_technology_identity_id: NonEmptyStr
    preferred_name: NonEmptyStr
    aliases: tuple[NonEmptyStr, ...]
    definition: NonEmptyStr
    source_anchor_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_identity_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    assignment_decision_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    identity_verdict_ids: tuple[NonEmptyStr, ...] = ()
    identity_decision_id: NonEmptyStr
    technology_identity_resolution_content_sha256: Sha256
    field_lineage: tuple[TechnologyFieldLineage, ...] = Field(min_length=1)
    observed_at: CanonicalDatetime
    release_id: NonEmptyStr
    projection_version: NonEmptyStr
    projection_scope: Literal["internal_auxiliary"] = "internal_auxiliary"
    reference_type: TechnologyReferenceType
    domain: None = None
    reference_catalog_schema_version: Literal["canonical-v2-reference-catalog-v1"]
    reference_catalog_version: Literal[
        "canonical-v2-person-technology-reference-2026-07-13"
    ]
    reference_catalog_content_sha256: Sha256
    as_of: CanonicalDatetime
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_projection(self, info: ValidationInfo) -> _TechnologyProjectionBase:
        for field_name in (
            "aliases",
            "source_anchor_ids",
            "source_identity_ids",
            "supporting_assertion_ids",
            "source_record_ids",
            "assignment_decision_ids",
            "identity_verdict_ids",
        ):
            values = cast(tuple[str, ...], getattr(self, field_name))
            if values != tuple(sorted(set(values))):
                raise ValueError(f"Technology projection {field_name} must be sorted")
        if self.preferred_name in self.aliases:
            raise ValueError("Technology aliases cannot repeat the preferred name")
        paths = tuple(item.field_path for item in self.field_lineage)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("Technology field lineage must be unique and sorted")
        if self.observed_at > self.as_of:
            raise ValueError("Technology observation is after projection as_of")
        if (
            self.reference_catalog_schema_version,
            self.reference_catalog_version,
            self.reference_catalog_content_sha256,
        ) != _installed_catalog_identity():
            raise ValueError("Technology projection reference catalog differs")
        if not (info.context or {}).get("allow_unbound_projection_hash"):
            payload = cast(
                JsonValue,
                self.model_dump(mode="json", exclude={"content_sha256"}),
            )
            if self.content_sha256 != _canonical_sha256(payload):
                raise ValueError("content_sha256 must bind Technology projection")
        return self


class TechnologyConceptProjection(_TechnologyProjectionBase):
    parent_concept_ids: tuple[NonEmptyStr, ...]

    @field_validator("parent_concept_ids")
    @classmethod
    def validate_parent_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("Technology concept parents must be unique and sorted")
        return values

    @model_validator(mode="after")
    def validate_concept_envelope(self) -> TechnologyConceptProjection:
        if (
            self.reference_type != "technology_concept"
            or self.projection_version != TECHNOLOGY_CONCEPT_PROJECTION_VERSION
        ):
            raise ValueError("Technology concept projection envelope differs")
        return self


class TechnologyRouteProjection(_TechnologyProjectionBase):
    concept_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("concept_ids")
    @classmethod
    def validate_concept_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("Technology route concepts must be unique and sorted")
        return values

    @model_validator(mode="after")
    def validate_route_envelope(self) -> TechnologyRouteProjection:
        if (
            self.reference_type != "technology_route"
            or self.projection_version != TECHNOLOGY_ROUTE_PROJECTION_VERSION
        ):
            raise ValueError("Technology route projection envelope differs")
        return self


class InternalReferenceProjectionRequest(ContractModel):
    release_id: NonEmptyStr
    build_run_id: NonEmptyStr
    as_of: CanonicalDatetime
    projection_version: Literal["internal-reference-v1"]
    reference_catalog_identity: ReferenceCatalogIdentity
    public_domain_projection_request: DomainProjectionRequest
    public_domain_projection_result: DomainProjectionResult
    person_identity_resolution_request: IdentityResolutionRequest
    person_identity_resolution_result: IdentityResolutionResult
    person_evidence_locators: tuple[PersonEvidenceLocator, ...]
    technology_identity_resolution_request: IdentityResolutionRequest | None = None
    technology_identity_resolution_result: IdentityResolutionResult | None = None
    technology_evidence_locators: tuple[TechnologyEvidenceLocator, ...] = ()

    @model_validator(mode="after")
    def validate_unique_inputs(self) -> InternalReferenceProjectionRequest:
        _unique_sorted(
            (item.reference_id for item in self.person_evidence_locators),
            "Person evidence locator reference IDs",
        )
        locator_keys = tuple(
            (
                item.source_kind,
                item.root_canonical_identity_id,
                item.source_subobject_id,
            )
            for item in self.person_evidence_locators
        )
        if len(locator_keys) != len(set(locator_keys)):
            raise ValueError("Person evidence locators must name unique source objects")
        _unique_sorted(
            (item.reference_id for item in self.technology_evidence_locators),
            "Technology evidence locator reference IDs",
        )
        technology_locator_keys = tuple(
            (
                item.technology_source_identity_id,
                item.public_domain,
                item.root_canonical_identity_id,
                item.source_field_path,
                item.source_subobject_id,
            )
            for item in self.technology_evidence_locators
        )
        if len(technology_locator_keys) != len(set(technology_locator_keys)):
            raise ValueError("Technology evidence locators must be unique")
        technology_pair = (
            self.technology_identity_resolution_request,
            self.technology_identity_resolution_result,
        )
        if (technology_pair[0] is None) != (technology_pair[1] is None):
            raise ValueError(
                "Technology identity request/result must be supplied together"
            )
        if (technology_pair[0] is None) != (not self.technology_evidence_locators):
            raise ValueError(
                "Technology locators require one exact identity request/result pair"
            )
        domain_request = self.public_domain_projection_request
        domain_result = self.public_domain_projection_result
        if (
            domain_request.release_id != self.release_id
            or domain_result.release_id != self.release_id
            or domain_request.as_of != self.as_of
            or domain_result.as_of != self.as_of
            or domain_request.build_run_id != domain_result.build_run_id
            or domain_request.projection_version != domain_result.projection_version
            or domain_request.catalog_schema_version
            != domain_result.catalog_schema_version
            or domain_request.catalog_version != domain_result.catalog_version
            or domain_request.catalog_content_sha256
            != domain_result.catalog_content_sha256
        ):
            raise ValueError("public domain projection request/result envelope differs")
        identity_request = self.person_identity_resolution_request
        identity_result = self.person_identity_resolution_result
        if (
            identity_request.release_id != self.release_id
            or identity_result.release_id != self.release_id
            or identity_request.as_of > self.as_of
            or identity_result.as_of > self.as_of
            or identity_request.identity_method_version
            != identity_result.identity_method_version
        ):
            raise ValueError("Person identity request/result envelope differs")
        technology_request = self.technology_identity_resolution_request
        technology_result = self.technology_identity_resolution_result
        if (
            technology_request is not None
            and technology_result is not None
            and (
                technology_request.release_id != self.release_id
                or technology_result.release_id != self.release_id
                or technology_request.as_of > self.as_of
                or technology_result.as_of > self.as_of
                or technology_request.identity_method_version
                != technology_result.identity_method_version
            )
        ):
            raise ValueError("Technology identity request/result envelope differs")
        return self


class InternalReferenceProjectionResult(ContractModel):
    release_id: NonEmptyStr
    build_run_id: NonEmptyStr
    as_of: CanonicalDatetime
    projection_version: Literal["internal-reference-v1"]
    reference_catalog_schema_version: Literal["canonical-v2-reference-catalog-v1"]
    reference_catalog_version: Literal[
        "canonical-v2-person-technology-reference-2026-07-13"
    ]
    reference_catalog_content_sha256: Sha256
    public_domain_projection_result_content_sha256: Sha256
    identity_resolution_content_sha256: Sha256
    technology_identity_resolution_content_sha256: Sha256 | None = None
    public_evidence_anchors: tuple[PublicDomainEvidenceAnchor, ...]
    person_projections: tuple[PersonProjection, ...]
    unresolved_person_references: tuple[PersonReference, ...]
    technology_evidence_anchors: tuple[TechnologyEvidenceAnchor, ...] = ()
    technology_concept_projections: tuple[TechnologyConceptProjection, ...] = ()
    technology_route_projections: tuple[TechnologyRouteProjection, ...] = ()
    unresolved_technology_references: tuple[UnresolvedTechnologyReference, ...] = ()
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_result(
        self, info: ValidationInfo
    ) -> InternalReferenceProjectionResult:
        if (
            self.reference_catalog_schema_version,
            self.reference_catalog_version,
            self.reference_catalog_content_sha256,
        ) != _installed_catalog_identity():
            raise ValueError("internal reference result catalog identity differs")
        ordered_anchors = tuple(
            sorted(self.public_evidence_anchors, key=lambda item: item.anchor_id)
        )
        if self.public_evidence_anchors != ordered_anchors or len(
            ordered_anchors
        ) != len({item.anchor_id for item in ordered_anchors}):
            raise ValueError("public evidence anchors must be unique and deterministic")
        ordered_projections = tuple(
            sorted(
                self.person_projections,
                key=lambda item: item.canonical_person_identity_id,
            )
        )
        projection_identity_ids = tuple(
            item.canonical_person_identity_id for item in ordered_projections
        )
        if self.person_projections != ordered_projections or len(
            projection_identity_ids
        ) != len(set(projection_identity_ids)):
            raise ValueError("Person projections must be unique and deterministic")
        if self.unresolved_person_references != tuple(
            sorted(
                self.unresolved_person_references,
                key=lambda item: item.reference_id,
            )
        ):
            raise ValueError("unresolved Person references must be deterministic")
        if any(
            item.resolution_state != "unresolved"
            for item in self.unresolved_person_references
        ):
            raise ValueError("unresolved result contains a resolved Person reference")
        anchors = {item.anchor_id: item for item in self.public_evidence_anchors}
        if any(
            item.release_id != self.release_id for item in self.public_evidence_anchors
        ):
            raise ValueError("result evidence anchor release differs")
        if any(
            projection.release_id != self.release_id
            or projection.projection_version != PERSON_REFERENCE_PROJECTION_VERSION
            or projection.as_of != self.as_of
            or projection.identity_resolution_content_sha256
            != self.identity_resolution_content_sha256
            for projection in self.person_projections
        ):
            raise ValueError("Person projection envelope differs from result")
        all_references = (
            tuple(
                reference
                for projection in self.person_projections
                for reference in projection.references
            )
            + self.unresolved_person_references
        )
        if len(all_references) != len(
            {reference.reference_id for reference in all_references}
        ):
            raise ValueError("result Person reference ownership is duplicated")
        reference_anchor_ids = tuple(
            reference.source_anchor_id for reference in all_references
        )
        if len(reference_anchor_ids) != len(set(reference_anchor_ids)):
            raise ValueError("one public evidence anchor cannot own two references")
        if len(all_references) != len(anchors):
            raise ValueError(
                "Person references and public evidence anchors must be 1:1"
            )
        source_owners: dict[str, tuple[str, str | None]] = {}
        for reference in all_references:
            anchor = anchors.get(reference.source_anchor_id)
            if anchor is None:
                raise ValueError(
                    "result Person reference has a missing evidence anchor"
                )
            if (
                reference.source_kind != anchor.source_kind
                or reference.name != anchor.person_name
                or reference.supporting_assertion_ids != anchor.supporting_assertion_ids
                or not set(reference.shared_source_record_ids)
                <= set(anchor.source_record_ids)
                or reference.identity_resolution_content_sha256
                != self.identity_resolution_content_sha256
            ):
                raise ValueError("result Person reference evidence is cross-wired")
            owner = (
                reference.resolution_state,
                reference.canonical_person_identity_id,
            )
            prior_owner = source_owners.setdefault(reference.source_identity_id, owner)
            if prior_owner != owner:
                raise ValueError(
                    "one Person source identity cannot have different result owners"
                )
        if set(anchors) != {reference.source_anchor_id for reference in all_references}:
            raise ValueError("result contains an unused public evidence anchor")
        technology_anchors = tuple(
            sorted(self.technology_evidence_anchors, key=lambda item: item.anchor_id)
        )
        if self.technology_evidence_anchors != technology_anchors or len(
            technology_anchors
        ) != len({item.anchor_id for item in technology_anchors}):
            raise ValueError("Technology evidence anchors must be deterministic")
        concepts = tuple(
            sorted(
                self.technology_concept_projections,
                key=lambda item: item.canonical_technology_identity_id,
            )
        )
        routes = tuple(
            sorted(
                self.technology_route_projections,
                key=lambda item: item.canonical_technology_identity_id,
            )
        )
        unresolved_technology = tuple(
            sorted(
                self.unresolved_technology_references,
                key=lambda item: item.reference_id,
            )
        )
        if (
            self.technology_concept_projections != concepts
            or self.technology_route_projections != routes
            or self.unresolved_technology_references != unresolved_technology
        ):
            raise ValueError("Technology projections/references must be deterministic")
        technology_identity_ids = tuple(
            item.canonical_technology_identity_id for item in (*concepts, *routes)
        )
        if len(technology_identity_ids) != len(set(technology_identity_ids)):
            raise ValueError("Technology projection identities must be unique")
        technology_present = bool(
            technology_anchors or concepts or routes or unresolved_technology
        )
        if technology_present != (
            self.technology_identity_resolution_content_sha256 is not None
        ):
            raise ValueError("Technology result identity lineage is incomplete")
        if any(
            item.release_id != self.release_id
            for item in self.technology_evidence_anchors
        ):
            raise ValueError("Technology anchor release differs from result")
        if any(
            projection.release_id != self.release_id
            or projection.as_of != self.as_of
            or projection.technology_identity_resolution_content_sha256
            != self.technology_identity_resolution_content_sha256
            for projection in (*concepts, *routes)
        ):
            raise ValueError("Technology projection envelope differs from result")
        referenced_anchor_ids = tuple(
            anchor_id
            for projection in (*concepts, *routes)
            for anchor_id in projection.source_anchor_ids
        ) + tuple(item.source_anchor_id for item in unresolved_technology)
        if len(referenced_anchor_ids) != len(set(referenced_anchor_ids)) or set(
            referenced_anchor_ids
        ) != {item.anchor_id for item in technology_anchors}:
            raise ValueError("Technology anchors must have exactly one result owner")
        concept_ids = {item.canonical_technology_identity_id for item in concepts}
        if any(
            parent_id not in concept_ids
            or parent_id == concept.canonical_technology_identity_id
            for concept in concepts
            for parent_id in concept.parent_concept_ids
        ):
            raise ValueError("Technology concept hierarchy has an invalid parent")
        if any(
            concept_id not in concept_ids
            for route in routes
            for concept_id in route.concept_ids
        ):
            raise ValueError("Technology route references a missing concept")

        parents_by_id = {
            item.canonical_technology_identity_id: item.parent_concept_ids
            for item in concepts
        }

        def visit(node: str, active: set[str], complete: set[str]) -> None:
            if node in active:
                raise ValueError("Technology concept hierarchy contains a cycle")
            if node in complete:
                return
            active.add(node)
            for parent in parents_by_id[node]:
                visit(parent, active, complete)
            active.remove(node)
            complete.add(node)

        completed: set[str] = set()
        for concept_id in sorted(concept_ids):
            visit(concept_id, set(), completed)
        if not (info.context or {}).get("allow_unbound_projection_hash"):
            payload = cast(
                JsonValue,
                self.model_dump(mode="json", exclude={"content_sha256"}),
            )
            if self.content_sha256 != _canonical_sha256(payload):
                raise ValueError(
                    "content_sha256 must bind the internal reference result"
                )
        return self


class InternalReferenceProjectionBuilder(ABC):
    """Project accepted reference knowledge without resolving or persisting it."""

    @abstractmethod
    def project(
        self,
        request: InternalReferenceProjectionRequest,
    ) -> InternalReferenceProjectionResult:
        """Build one deterministic internal-reference candidate result."""


def _content_bound_anchor(payload: dict[str, object]) -> PublicDomainEvidenceAnchor:
    provisional = PublicDomainEvidenceAnchor.model_validate(
        {
            **payload,
            "anchor_id": "public-domain-evidence:provisional",
            "content_sha256": "0" * 64,
        },
        context={"allow_unbound_anchor_hash": True},
    )
    semantic_payload = cast(
        JsonValue,
        provisional.model_dump(mode="json", exclude={"anchor_id", "content_sha256"}),
    )
    content_sha256 = _canonical_sha256(semantic_payload)
    return PublicDomainEvidenceAnchor.model_validate(
        {
            **provisional.model_dump(mode="python"),
            "anchor_id": f"public-domain-evidence:sha256:{content_sha256}",
            "content_sha256": content_sha256,
        }
    )


def _content_bound_person_projection(
    payload: dict[str, object],
) -> PersonProjection:
    provisional = PersonProjection.model_validate(
        {**payload, "content_sha256": "0" * 64},
        context={"allow_unbound_projection_hash": True},
    )
    content_payload = cast(
        JsonValue,
        provisional.model_dump(mode="json", exclude={"content_sha256"}),
    )
    return PersonProjection.model_validate(
        {
            **provisional.model_dump(mode="python"),
            "content_sha256": _canonical_sha256(content_payload),
        }
    )


def _content_bound_technology_anchor(
    payload: dict[str, object],
) -> TechnologyEvidenceAnchor:
    provisional = TechnologyEvidenceAnchor.model_validate(
        {
            **payload,
            "anchor_id": "technology-evidence:provisional",
            "content_sha256": "0" * 64,
        },
        context={"allow_unbound_anchor_hash": True},
    )
    semantic_payload = cast(
        JsonValue,
        provisional.model_dump(mode="json", exclude={"anchor_id", "content_sha256"}),
    )
    content_sha256 = _canonical_sha256(semantic_payload)
    return TechnologyEvidenceAnchor.model_validate(
        {
            **provisional.model_dump(mode="python"),
            "anchor_id": f"technology-evidence:sha256:{content_sha256}",
            "content_sha256": content_sha256,
        }
    )


def _content_bound_technology_concept(
    payload: dict[str, object],
) -> TechnologyConceptProjection:
    provisional = TechnologyConceptProjection.model_validate(
        {**payload, "content_sha256": "0" * 64},
        context={"allow_unbound_projection_hash": True},
    )
    content_payload = cast(
        JsonValue,
        provisional.model_dump(mode="json", exclude={"content_sha256"}),
    )
    return TechnologyConceptProjection.model_validate(
        {
            **provisional.model_dump(mode="python"),
            "content_sha256": _canonical_sha256(content_payload),
        }
    )


def _content_bound_technology_route(
    payload: dict[str, object],
) -> TechnologyRouteProjection:
    provisional = TechnologyRouteProjection.model_validate(
        {**payload, "content_sha256": "0" * 64},
        context={"allow_unbound_projection_hash": True},
    )
    content_payload = cast(
        JsonValue,
        provisional.model_dump(mode="json", exclude={"content_sha256"}),
    )
    return TechnologyRouteProjection.model_validate(
        {
            **provisional.model_dump(mode="python"),
            "content_sha256": _canonical_sha256(content_payload),
        }
    )


def _content_bound_result(
    payload: dict[str, object],
) -> InternalReferenceProjectionResult:
    provisional = InternalReferenceProjectionResult.model_validate(
        {**payload, "content_sha256": "0" * 64},
        context={"allow_unbound_projection_hash": True},
    )
    content_payload = cast(
        JsonValue,
        provisional.model_dump(mode="json", exclude={"content_sha256"}),
    )
    return InternalReferenceProjectionResult.model_validate(
        {
            **provisional.model_dump(mode="python"),
            "content_sha256": _canonical_sha256(content_payload),
        }
    )


def _subobject_name(
    source_kind: PersonSourceKind,
    projection: Projection,
    subobject: TypedSubobject | None,
) -> str:
    if source_kind in {
        "professor",
        "professor_education",
        "professor_work_history",
    }:
        if not isinstance(projection, ProfessorProjection):
            raise InternalReferenceProjectionIntegrityError(
                "Professor Person reference requires a Professor projection"
            )
        return projection.name
    if isinstance(subobject, CompanyKeyPersonnel | PaperAuthor | PatentInventor):
        return subobject.name
    if isinstance(
        subobject,
        CompanyPersonnelEducation | CompanyPersonnelWorkExperience,
    ):
        return subobject.person.name
    raise InternalReferenceProjectionIntegrityError(
        "Person reference typed subobject cannot provide a Person name"
    )


def _derive_anchor_and_name(
    *,
    locator: PersonEvidenceLocator,
    projections: dict[tuple[str, str], Projection],
    domain_assertions: dict[str, SourceAssertion],
) -> tuple[PublicDomainEvidenceAnchor, str]:
    domain, subobject_type, attribute = _SOURCE_KIND_SPECS[locator.source_kind]
    projection = projections.get((domain, locator.root_canonical_identity_id))
    if projection is None:
        raise InternalReferenceProjectionIntegrityError(
            "Person locator root projection is missing or has the wrong public domain"
        )

    subobject: TypedSubobject | None = None
    if subobject_type is None:
        if not isinstance(projection, ProfessorProjection):
            raise InternalReferenceProjectionIntegrityError(
                "Professor root locator must bind a Professor projection"
            )
        name_lineage = tuple(
            item
            for item in projection.field_lineage
            if item.field_path in _PROFESSOR_NAME_PATHS
        )
        if not name_lineage:
            raise InternalReferenceProjectionIntegrityError(
                "Professor root Person reference requires retained name lineage"
            )
        source_field_paths = tuple(sorted(item.field_path for item in name_lineage))
        supporting_assertion_ids = tuple(
            sorted(
                {
                    assertion_id
                    for item in name_lineage
                    for assertion_id in item.supporting_assertion_ids
                }
            )
        )
        decision_ids = tuple(sorted({item.decision_id for item in name_lineage}))
        observed_at = projection.last_updated
        valid_from = None
        valid_to = None
        subobject_content_sha256 = None
    else:
        assert attribute is not None
        candidates = tuple(
            item
            for item in cast(tuple[TypedSubobject, ...], getattr(projection, attribute))
            if item.subobject_id == locator.source_subobject_id
        )
        if len(candidates) != 1:
            raise InternalReferenceProjectionIntegrityError(
                "Person locator typed subobject is missing or duplicated"
            )
        subobject = candidates[0]
        expected_model = _SUBOBJECT_MODELS[locator.source_kind]
        if not isinstance(subobject, expected_model):
            raise InternalReferenceProjectionIntegrityError(
                "Person locator typed subobject model differs from source kind"
            )
        if subobject.parent_canonical_identity_id != projection.canonical_identity_id:
            raise InternalReferenceProjectionIntegrityError(
                "Person locator typed subobject parent is cross-wired"
            )
        source_field_paths = (attribute,)
        supporting_assertion_ids = subobject.supporting_assertion_ids
        decision_ids = subobject.decision_ids
        observed_at = subobject.observed_at
        valid_from = subobject.valid_from
        valid_to = subobject.valid_to
        subobject_content_sha256 = subobject.projection_content_sha256

    name = _subobject_name(locator.source_kind, projection, subobject)
    person_orcid = subobject.orcid if isinstance(subobject, PaperAuthor) else None
    retained_assertions: list[SourceAssertion] = []
    for assertion_id in supporting_assertion_ids:
        assertion = domain_assertions.get(assertion_id)
        if (
            assertion is None
            or assertion.subject_entity_type != domain
            or assertion.field_path not in source_field_paths
        ):
            raise InternalReferenceProjectionIntegrityError(
                "Person public anchor lineage is absent from the exact domain request"
            )
        retained_assertions.append(assertion)
    source_record_ids = tuple(
        sorted({assertion.source_record_id for assertion in retained_assertions})
    )
    anchor = _content_bound_anchor(
        {
            "source_kind": locator.source_kind,
            "public_domain": domain,
            "root_canonical_identity_id": projection.canonical_identity_id,
            "root_projection_version": projection.projection_version,
            "root_projection_content_sha256": projection.content_sha256,
            "root_projection_as_of": projection.as_of,
            "domain_catalog_schema_version": projection.catalog_schema_version,
            "domain_catalog_version": projection.catalog_version,
            "domain_catalog_content_sha256": projection.catalog_content_sha256,
            "source_field_paths": source_field_paths,
            "source_subobject_type": subobject_type,
            "source_subobject_id": locator.source_subobject_id,
            "source_subobject_content_sha256": subobject_content_sha256,
            "person_name": name,
            "person_orcid": person_orcid,
            "supporting_assertion_ids": supporting_assertion_ids,
            "decision_ids": decision_ids,
            "source_record_ids": source_record_ids,
            "observed_at": observed_at,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "release_id": projection.release_id,
        }
    )
    return anchor, name


def _context_index(
    request: IdentityResolutionRequest,
    result: IdentityResolutionResult,
) -> dict[str, IdentityDecisionContext]:
    contexts: dict[str, IdentityDecisionContext] = {}
    for context in (*request.prior_decision_contexts, *result.decision_contexts):
        previous = contexts.setdefault(context.decision_id, context)
        if previous != context:
            raise InternalReferenceProjectionIntegrityError(
                "identity decision context is duplicated with different content"
            )
    return contexts


def _context_has_evidence_bound_identifier(
    *,
    context: IdentityDecisionContext,
    source_identity_id: str,
    key: str,
    field_path: str,
) -> bool:
    """Confirm that accepted topology was created from exact stable-ID evidence."""

    sources = tuple(
        source
        for source in context.source_identities
        if source.source_identity_id == source_identity_id
    )
    if len(sources) != 1:
        return False
    normalized_identifier = normalize_identity_key_value(
        key, sources[0].normalized_keys.get(key)
    )
    if normalized_identifier is None:
        return False
    identifier_assertions = tuple(
        assertion
        for assertion in context.identity_assertions
        if assertion.source_identity_id == source_identity_id
        and assertion.field_path == field_path
    )
    return bool(identifier_assertions) and all(
        isinstance(assertion.value, str)
        and normalize_identity_key_value(key, assertion.value) == normalized_identifier
        for assertion in identifier_assertions
    )


def _identity_assertions_for_source(
    source: SourceIdentity,
    assertions: Iterable[SourceAssertion],
) -> tuple[SourceAssertion, ...]:
    return tuple(
        assertion
        for assertion in assertions
        if assertion.source_identity_id == source.source_identity_id
    )


def _person_evidence_connection(
    *,
    locator: PersonEvidenceLocator,
    source: SourceIdentity,
    assertions: Iterable[SourceAssertion],
    anchor: PublicDomainEvidenceAnchor,
    person_name: str,
) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    source_assertions = tuple(assertions)
    shared_source_record_ids = tuple(
        sorted(set(source.source_record_ids) & set(anchor.source_record_ids))
    )
    if not shared_source_record_ids:
        raise InternalReferenceProjectionIntegrityError(
            "Person identity evidence does not share a source record with public evidence"
        )
    shared_records = set(shared_source_record_ids)
    connected = tuple(
        assertion
        for assertion in source_assertions
        if assertion.source_record_id in shared_records
    )
    name_assertions = tuple(
        assertion
        for assertion in connected
        if assertion.field_path == "identity.name" and assertion.value == person_name
    )
    if not name_assertions:
        raise InternalReferenceProjectionIntegrityError(
            "Person identity name assertion does not connect to public evidence"
        )

    expected_crosswalk = PersonEvidenceCrosswalk(
        source_kind=locator.source_kind,
        root_canonical_identity_id=locator.root_canonical_identity_id,
        source_subobject_id=locator.source_subobject_id,
    ).model_dump(mode="json")
    crosswalk_assertions = tuple(
        assertion
        for assertion in connected
        if assertion.field_path == "identity.public_reference_locator"
        and assertion.value == expected_crosswalk
    )
    if not crosswalk_assertions:
        raise InternalReferenceProjectionIntegrityError(
            "Person identity lacks an exact object-level crosswalk to public evidence"
        )

    raw_normalized_orcid = source.normalized_keys.get("orcid")
    normalized_orcid = normalize_identity_key_value("orcid", raw_normalized_orcid)
    orcid_assertions = tuple(
        assertion
        for assertion in source_assertions
        if assertion.field_path == "identity.orcid"
        and isinstance(assertion.value, str)
        and normalize_identity_key_value("orcid", assertion.value) == normalized_orcid
    )
    if raw_normalized_orcid is not None and (
        normalized_orcid is None or not orcid_assertions
    ):
        raise InternalReferenceProjectionIntegrityError(
            "Person normalized ORCID lacks an exact source-bound assertion"
        )
    if anchor.person_orcid is not None and (
        normalized_orcid is None
        or normalize_identity_key_value("orcid", anchor.person_orcid)
        != normalized_orcid
    ):
        raise InternalReferenceProjectionIntegrityError(
            "typed public-reference ORCID differs from Person identity ORCID"
        )
    identity_assertion_ids = tuple(
        sorted(
            {
                assertion.assertion_id
                for assertion in (
                    *name_assertions,
                    *crosswalk_assertions,
                    *orcid_assertions,
                )
            }
        )
    )
    return (
        identity_assertion_ids,
        shared_source_record_ids,
        normalized_orcid is not None,
    )


class _TechnologySourceFacts(ContractModel):
    source: SourceIdentity
    assertions: tuple[SourceAssertion, ...]
    preferred_name: NonEmptyStr
    aliases: tuple[NonEmptyStr, ...]
    definition: NonEmptyStr | None
    linked_source_identity_ids: tuple[NonEmptyStr, ...]
    has_evidence_bound_identifier: bool
    has_complete_projection_metadata: bool


def _technology_assertion_comparison_value(
    field_path: str,
    value: JsonValue,
) -> object:
    if field_path in {
        "technology.aliases",
        "technology.parent_source_identity_ids",
        "technology.concept_source_identity_ids",
    } and isinstance(value, list):
        return tuple(
            sorted(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                for item in value
            )
        )
    return value


def _one_technology_assertion(
    assertions: tuple[SourceAssertion, ...],
    field_path: str,
    *,
    required: bool = True,
) -> SourceAssertion | None:
    matches = tuple(item for item in assertions if item.field_path == field_path)
    if required and not matches:
        raise InternalReferenceProjectionIntegrityError(
            f"Technology source requires a {field_path} assertion"
        )
    expected_value = (
        _technology_assertion_comparison_value(field_path, matches[0].value)
        if matches
        else None
    )
    if matches and any(
        _technology_assertion_comparison_value(field_path, item.value) != expected_value
        for item in matches[1:]
    ):
        raise InternalReferenceProjectionIntegrityError(
            f"Technology source has conflicting {field_path} assertions"
        )
    return matches[0] if matches else None


def _technology_source_facts(
    source: SourceIdentity,
    identity_assertions: tuple[SourceAssertion, ...],
) -> _TechnologySourceFacts:
    assertions = tuple(
        sorted(
            (
                item
                for item in identity_assertions
                if item.source_identity_id == source.source_identity_id
            ),
            key=lambda item: item.assertion_id,
        )
    )
    allowed_paths = {
        "technology.preferred_name",
        "identity.technology_id",
        "technology.aliases",
        "technology.definition",
        "technology.public_reference_locator",
        {
            "technology_concept": "technology.parent_source_identity_ids",
            "technology_route": "technology.concept_source_identity_ids",
        }.get(source.entity_type),
    }
    unknown_paths = {
        item.field_path for item in assertions if item.field_path not in allowed_paths
    }
    if unknown_paths:
        raise InternalReferenceProjectionIntegrityError(
            f"Technology source contains unsupported assertions: {sorted(unknown_paths)}"
        )
    link_path = {
        "technology_concept": "technology.parent_source_identity_ids",
        "technology_route": "technology.concept_source_identity_ids",
    }.get(source.entity_type)
    if link_path is None:
        raise InternalReferenceProjectionIntegrityError(
            f"unsupported internal reference identity type: {source.entity_type}"
        )
    preferred_assertion = _one_technology_assertion(
        assertions, "technology.preferred_name"
    )
    identifier_assertion = _one_technology_assertion(
        assertions, "identity.technology_id", required=False
    )
    raw_identifier = source.normalized_keys.get("technology_id")
    normalized_identifier = normalize_identity_key_value(
        "technology_id", raw_identifier
    )
    has_identifier = (
        identifier_assertion is not None
        and isinstance(identifier_assertion.value, str)
        and normalized_identifier is not None
        and normalize_identity_key_value("technology_id", identifier_assertion.value)
        == normalized_identifier
    )
    if raw_identifier is not None and not has_identifier:
        raise InternalReferenceProjectionIntegrityError(
            "Technology normalized identifier lacks an exact source assertion"
        )
    if identifier_assertion is not None and normalized_identifier is None:
        raise InternalReferenceProjectionIntegrityError(
            "Technology identifier assertion lacks its normalized identity key"
        )
    aliases_assertion = _one_technology_assertion(
        assertions, "technology.aliases", required=has_identifier
    )
    definition_assertion = _one_technology_assertion(
        assertions, "technology.definition", required=has_identifier
    )
    link_assertion = _one_technology_assertion(
        assertions, link_path, required=has_identifier
    )
    invalid_aliases = aliases_assertion is not None and (
        not isinstance(aliases_assertion.value, list)
        or not all(
            isinstance(item, str) and item.strip() for item in aliases_assertion.value
        )
    )
    invalid_links = link_assertion is not None and (
        not isinstance(link_assertion.value, list)
        or not all(
            isinstance(item, str) and item.strip() for item in link_assertion.value
        )
    )
    if (
        preferred_assertion is None
        or not isinstance(preferred_assertion.value, str)
        or (
            definition_assertion is not None
            and not isinstance(definition_assertion.value, str)
        )
        or invalid_aliases
        or invalid_links
    ):
        raise InternalReferenceProjectionIntegrityError(
            "Technology metadata assertions have an invalid typed value"
        )
    aliases = (
        tuple(sorted(cast(list[str], aliases_assertion.value)))
        if aliases_assertion is not None
        else ()
    )
    linked_source_ids = (
        tuple(sorted(cast(list[str], link_assertion.value)))
        if link_assertion is not None
        else ()
    )
    if len(aliases) != len(set(aliases)) or len(linked_source_ids) != len(
        set(linked_source_ids)
    ):
        raise InternalReferenceProjectionIntegrityError(
            "Technology aliases and hierarchy links must be unique"
        )
    return _TechnologySourceFacts(
        source=source,
        assertions=assertions,
        preferred_name=preferred_assertion.value,
        aliases=aliases,
        definition=(
            definition_assertion.value
            if definition_assertion is not None
            and isinstance(definition_assertion.value, str)
            else None
        ),
        linked_source_identity_ids=linked_source_ids,
        has_evidence_bound_identifier=has_identifier,
        has_complete_projection_metadata=(
            aliases_assertion is not None
            and definition_assertion is not None
            and link_assertion is not None
        ),
    )


def _derive_technology_anchor(
    *,
    locator: TechnologyEvidenceLocator,
    domain_request: DomainProjectionRequest,
    projections: dict[tuple[str, str], Projection],
) -> TechnologyEvidenceAnchor:
    projection = projections.get(
        (locator.public_domain, locator.root_canonical_identity_id)
    )
    if projection is None:
        raise InternalReferenceProjectionIntegrityError(
            "Technology locator root is not an accepted public projection"
        )
    selection = next(
        (
            item
            for item in domain_request.current_fields
            if item.canonical_identity_id == locator.root_canonical_identity_id
            and item.field_path == locator.source_field_path
        ),
        None,
    )
    if selection is None:
        raise InternalReferenceProjectionIntegrityError(
            "Technology locator field is not selected in the public projection"
        )
    lineage = next(
        (
            item
            for item in projection.field_lineage
            if item.field_path == locator.source_field_path
        ),
        None,
    )
    if (
        lineage is None
        or lineage.decision_id != selection.decision_id
        or lineage.supporting_assertion_ids != selection.supporting_assertion_ids
    ):
        raise InternalReferenceProjectionIntegrityError(
            "Technology locator field lineage differs from the exact domain graph"
        )
    assertion_by_id = {
        item.assertion_id: item for item in domain_request.source_assertions
    }
    supporting_assertions = tuple(
        assertion_by_id.get(assertion_id)
        for assertion_id in selection.supporting_assertion_ids
    )
    if any(item is None for item in supporting_assertions):
        raise InternalReferenceProjectionIntegrityError(
            "Technology locator field has a missing source assertion"
        )
    typed_assertions = cast(tuple[SourceAssertion, ...], supporting_assertions)
    source_record_ids = tuple(
        sorted({item.source_record_id for item in typed_assertions})
    )
    subobject_content_sha256: str | None = None
    observed_at = max(item.observed_at for item in typed_assertions)
    if locator.source_subobject_type is not None:
        if not isinstance(projection, CompanyProjection):
            raise InternalReferenceProjectionIntegrityError(
                "Technology Product locator requires a Company projection"
            )
        subobject = next(
            (
                item
                for item in projection.products
                if item.subobject_id == locator.source_subobject_id
            ),
            None,
        )
        if (
            subobject is None
            or subobject.parent_canonical_identity_id
            != locator.root_canonical_identity_id
            or subobject.supporting_assertion_ids != selection.supporting_assertion_ids
            or subobject.decision_ids != (selection.decision_id,)
        ):
            raise InternalReferenceProjectionIntegrityError(
                "Technology locator does not name the exact selected Product"
            )
        subobject_content_sha256 = subobject.projection_content_sha256
        observed_at = max(observed_at, subobject.observed_at)
    return _content_bound_technology_anchor(
        {
            "reference_id": locator.reference_id,
            "reference_type": locator.reference_type,
            "technology_source_identity_id": (locator.technology_source_identity_id),
            "public_domain": locator.public_domain,
            "root_canonical_identity_id": locator.root_canonical_identity_id,
            "root_projection_version": projection.projection_version,
            "root_projection_content_sha256": projection.content_sha256,
            "root_projection_as_of": projection.as_of,
            "domain_catalog_schema_version": projection.catalog_schema_version,
            "domain_catalog_version": projection.catalog_version,
            "domain_catalog_content_sha256": projection.catalog_content_sha256,
            "source_field_path": locator.source_field_path,
            "source_subobject_type": locator.source_subobject_type,
            "source_subobject_id": locator.source_subobject_id,
            "source_subobject_content_sha256": subobject_content_sha256,
            "supporting_assertion_ids": selection.supporting_assertion_ids,
            "decision_ids": (selection.decision_id,),
            "source_record_ids": source_record_ids,
            "observed_at": observed_at,
            "valid_from": selection.valid_from,
            "valid_to": selection.valid_to,
            "release_id": projection.release_id,
        }
    )


def _technology_crosswalk_assertion_ids(
    *,
    locator: TechnologyEvidenceLocator,
    source: SourceIdentity,
    facts: _TechnologySourceFacts,
    anchor: TechnologyEvidenceAnchor,
) -> tuple[str, ...]:
    crosswalks = tuple(
        item
        for item in facts.assertions
        if item.field_path == "technology.public_reference_locator"
        and item.value == locator.crosswalk_value()
        and item.source_record_id in anchor.source_record_ids
    )
    if not crosswalks or not (
        set(source.source_record_ids) & set(anchor.source_record_ids)
    ):
        raise InternalReferenceProjectionIntegrityError(
            "Technology public-reference crosswalk is not evidence-bound"
        )
    return tuple(sorted(item.assertion_id for item in crosswalks))


def _technology_field_lineage(
    assertions: Iterable[SourceAssertion],
) -> tuple[TechnologyFieldLineage, ...]:
    grouped: dict[str, set[str]] = {}
    for assertion in assertions:
        grouped.setdefault(assertion.field_path, set()).add(assertion.assertion_id)
    return tuple(
        TechnologyFieldLineage(
            field_path=field_path,
            supporting_assertion_ids=tuple(sorted(assertion_ids)),
        )
        for field_path, assertion_ids in sorted(grouped.items())
    )


class _EphemeralInternalReferenceProjectionBuilder(InternalReferenceProjectionBuilder):
    def __init__(self, catalog: InstalledInternalReferenceCatalog) -> None:
        self._catalog = catalog

    def _project_technology(
        self,
        *,
        request: InternalReferenceProjectionRequest,
        domain_request: DomainProjectionRequest,
        projections: dict[tuple[str, str], Projection],
        identity_request: IdentityResolutionRequest | None,
        identity_result: IdentityResolutionResult | None,
    ) -> tuple[
        tuple[TechnologyEvidenceAnchor, ...],
        tuple[TechnologyConceptProjection, ...],
        tuple[TechnologyRouteProjection, ...],
        tuple[UnresolvedTechnologyReference, ...],
    ]:
        if identity_request is None or identity_result is None:
            return (), (), (), ()
        sources = {
            item.source_identity_id: item for item in identity_result.source_identities
        }
        locator_source_ids = {
            item.technology_source_identity_id
            for item in request.technology_evidence_locators
        }
        if locator_source_ids != set(sources):
            raise InternalReferenceProjectionIntegrityError(
                "Technology locators must exactly cover identity-resolution sources"
            )
        facts_by_source = {
            source_id: _technology_source_facts(
                source, identity_result.identity_assertions
            )
            for source_id, source in sources.items()
        }
        anchors_by_source: dict[str, list[TechnologyEvidenceAnchor]] = {}
        covered_crosswalk_assertion_ids: set[str] = set()
        for locator in sorted(
            request.technology_evidence_locators,
            key=lambda item: item.reference_id,
        ):
            source = sources[locator.technology_source_identity_id]
            if locator.reference_type != source.entity_type:
                raise InternalReferenceProjectionIntegrityError(
                    "Technology locator type differs from its source identity"
                )
            anchor = _derive_technology_anchor(
                locator=locator,
                domain_request=domain_request,
                projections=projections,
            )
            covered_crosswalk_assertion_ids.update(
                _technology_crosswalk_assertion_ids(
                    locator=locator,
                    source=source,
                    facts=facts_by_source[source.source_identity_id],
                    anchor=anchor,
                )
            )
            anchors_by_source.setdefault(source.source_identity_id, []).append(anchor)
        all_crosswalk_assertion_ids = {
            assertion.assertion_id
            for facts in facts_by_source.values()
            for assertion in facts.assertions
            if assertion.field_path == "technology.public_reference_locator"
        }
        if covered_crosswalk_assertion_ids != all_crosswalk_assertion_ids:
            raise InternalReferenceProjectionIntegrityError(
                "Technology public-reference assertions must be exhaustively "
                "covered by validated locators"
            )

        assignments = {
            item.source_identity_id: item
            for item in identity_result.source_identity_assignments
        }
        identities = {
            item.canonical_identity_id: item
            for item in identity_result.current_canonical_identities
        }
        contexts = _context_index(identity_request, identity_result)
        verdict_by_source = {
            source_id: verdict
            for verdict in identity_result.candidate_verdicts
            for source_id in verdict.source_identity_ids
        }
        review_by_verdict = {
            item.originating_record_id: item for item in identity_result.review_cases
        }
        accepted_outcomes = {
            IdentityCandidateOutcome.same_entity,
            IdentityCandidateOutcome.different_entities,
        }
        resolved_source_to_canonical: dict[str, str] = {}
        effective_verdict_by_source: dict[str, object] = {}
        unresolved: list[UnresolvedTechnologyReference] = []
        for source_id, source in sorted(sources.items()):
            assignment = assignments.get(source_id)
            identity = (
                identities.get(assignment.canonical_identity_id)
                if assignment is not None
                else None
            )
            context = (
                contexts.get(assignment.identity_decision_id)
                if assignment is not None
                else None
            )
            topology_context = (
                contexts.get(identity.identity_decision_id)
                if identity is not None
                else None
            )
            lineage_values = (assignment, identity, context, topology_context)
            has_lineage = any(item is not None for item in lineage_values)
            complete_lineage = all(item is not None for item in lineage_values)
            if has_lineage and not complete_lineage:
                raise InternalReferenceProjectionIntegrityError(
                    "Technology assignment lacks exact identity decision lineage"
                )
            if complete_lineage:
                assert assignment is not None
                assert identity is not None
                assert context is not None
                assert topology_context is not None
                if source_id not in identity.source_identity_ids:
                    raise InternalReferenceProjectionIntegrityError(
                        "Technology assignment lacks exact identity decision lineage"
                    )
            current_verdict = verdict_by_source.get(source_id)
            topology_verdict = (
                topology_context.candidate_verdict
                if topology_context is not None
                else None
            )
            accepted_current = (
                current_verdict is not None
                and current_verdict.verdict in accepted_outcomes
            )
            accepted_topology = (
                topology_verdict is not None
                and topology_verdict.verdict in accepted_outcomes
            )
            accepted_singleton_topology = (
                complete_lineage
                and topology_verdict is None
                and topology_context is not None
                and _context_has_evidence_bound_identifier(
                    context=topology_context,
                    source_identity_id=source_id,
                    key="technology_id",
                    field_path="identity.technology_id",
                )
            )
            effective_verdict = (
                current_verdict
                if accepted_current
                else topology_verdict
                if accepted_topology
                else None
                if accepted_singleton_topology
                else current_verdict or topology_verdict
            )
            if effective_verdict is not None:
                effective_verdict_by_source[source_id] = effective_verdict
            if accepted_current or accepted_topology or accepted_singleton_topology:
                if not complete_lineage or identity is None:
                    raise InternalReferenceProjectionIntegrityError(
                        "resolved Technology verdict requires exact canonical "
                        "identity lineage"
                    )
                resolved_source_to_canonical[source_id] = identity.canonical_identity_id
                continue
            if complete_lineage:
                raise InternalReferenceProjectionIntegrityError(
                    "unresolved Technology reference cannot retain a canonical identity"
                )
            review_case = (
                review_by_verdict.get(effective_verdict.verdict_id)
                if effective_verdict is not None
                else None
            )
            facts = facts_by_source[source_id]
            identity_assertion_ids = tuple(
                sorted(item.assertion_id for item in facts.assertions)
            )
            for anchor in anchors_by_source[source_id]:
                unresolved.append(
                    UnresolvedTechnologyReference(
                        reference_id=anchor.reference_id,
                        reference_type=cast(
                            TechnologyReferenceType, source.entity_type
                        ),
                        preferred_name=facts.preferred_name,
                        source_anchor_id=anchor.anchor_id,
                        technology_source_identity_id=source_id,
                        supporting_assertion_ids=anchor.supporting_assertion_ids,
                        identity_assertion_ids=identity_assertion_ids,
                        source_record_ids=tuple(sorted(source.source_record_ids)),
                        technology_identity_resolution_content_sha256=(
                            identity_result.content_sha256
                        ),
                        candidate_verdict_id=(
                            effective_verdict.verdict_id
                            if effective_verdict is not None
                            else None
                        ),
                        review_case_id=(
                            review_case.review_case_id
                            if review_case is not None
                            else None
                        ),
                    )
                )

        grouped_sources: dict[str, list[str]] = {}
        for source_id, canonical_id in resolved_source_to_canonical.items():
            grouped_sources.setdefault(canonical_id, []).append(source_id)
        concepts: list[TechnologyConceptProjection] = []
        routes: list[TechnologyRouteProjection] = []
        for canonical_id, source_ids_list in sorted(grouped_sources.items()):
            source_ids = tuple(sorted(source_ids_list))
            identity = identities[canonical_id]
            if set(source_ids) != set(identity.source_identity_ids):
                raise InternalReferenceProjectionIntegrityError(
                    "Technology identity mixes resolved and unresolved sources"
                )
            grouped_facts = tuple(facts_by_source[item] for item in source_ids)
            if any(
                not item.has_complete_projection_metadata or item.definition is None
                for item in grouped_facts
            ):
                raise InternalReferenceProjectionIntegrityError(
                    "resolved Technology source lacks complete projection metadata"
                )
            reference_types = {item.source.entity_type for item in grouped_facts}
            if len(reference_types) != 1:
                raise InternalReferenceProjectionIntegrityError(
                    "Technology identity cannot mix concept and route sources"
                )
            reference_type = cast(TechnologyReferenceType, next(iter(reference_types)))
            names = {item.preferred_name for item in grouped_facts}
            definitions = {cast(str, item.definition) for item in grouped_facts}
            if len(definitions) != 1:
                raise InternalReferenceProjectionIntegrityError(
                    "Technology definition assertions conflict"
                )
            preferred_name = (
                identity.display_name
                if identity.display_name is not None and identity.display_name in names
                else sorted(names)[0]
            )
            aliases = tuple(
                sorted(
                    (
                        {alias for item in grouped_facts for alias in item.aliases}
                        | (names - {preferred_name})
                    )
                    - {preferred_name}
                )
            )
            source_assertions = tuple(
                item for facts in grouped_facts for item in facts.assertions
            )
            linked_source_ids = tuple(
                sorted(
                    {
                        linked_id
                        for facts in grouped_facts
                        for linked_id in facts.linked_source_identity_ids
                    }
                )
            )
            linked_canonical_ids: list[str] = []
            for linked_source_id in linked_source_ids:
                linked_source = sources.get(linked_source_id)
                linked_canonical_id = resolved_source_to_canonical.get(linked_source_id)
                if linked_source is None or linked_canonical_id is None:
                    raise InternalReferenceProjectionIntegrityError(
                        "Technology hierarchy references an unresolved source"
                    )
                if linked_source.entity_type != "technology_concept":
                    raise InternalReferenceProjectionIntegrityError(
                        "Technology hierarchy target must be a concept"
                    )
                linked_canonical_ids.append(linked_canonical_id)
            source_anchors = tuple(
                sorted(
                    (
                        anchor
                        for source_id in source_ids
                        for anchor in anchors_by_source[source_id]
                    ),
                    key=lambda item: item.anchor_id,
                )
            )
            source_records = tuple(
                sorted(
                    {
                        record_id
                        for facts in grouped_facts
                        for record_id in facts.source.source_record_ids
                    }
                )
            )
            verdict_ids = tuple(
                sorted(
                    {
                        cast(Any, effective_verdict_by_source[source_id]).verdict_id
                        for source_id in source_ids
                        if source_id in effective_verdict_by_source
                    }
                )
            )
            assignment_decision_ids = tuple(
                sorted({assignments[item].identity_decision_id for item in source_ids})
            )
            common_payload: dict[str, object] = {
                "canonical_technology_identity_id": canonical_id,
                "preferred_name": preferred_name,
                "aliases": aliases,
                "definition": next(iter(definitions)),
                "source_anchor_ids": tuple(item.anchor_id for item in source_anchors),
                "source_identity_ids": source_ids,
                "supporting_assertion_ids": tuple(
                    sorted(item.assertion_id for item in source_assertions)
                ),
                "source_record_ids": source_records,
                "assignment_decision_ids": assignment_decision_ids,
                "identity_verdict_ids": verdict_ids,
                "identity_decision_id": identity.identity_decision_id,
                "technology_identity_resolution_content_sha256": (
                    identity_result.content_sha256
                ),
                "field_lineage": _technology_field_lineage(source_assertions),
                "observed_at": max(
                    *(item.observed_at for item in source_assertions),
                    *(item.observed_at for item in source_anchors),
                ),
                "release_id": request.release_id,
                "projection_scope": "internal_auxiliary",
                "reference_type": reference_type,
                "domain": None,
                "reference_catalog_schema_version": self._catalog.schema_version,
                "reference_catalog_version": self._catalog.catalog_version,
                "reference_catalog_content_sha256": self._catalog.content_sha256,
                "as_of": request.as_of,
            }
            if reference_type == "technology_concept":
                concepts.append(
                    _content_bound_technology_concept(
                        {
                            **common_payload,
                            "projection_version": (
                                TECHNOLOGY_CONCEPT_PROJECTION_VERSION
                            ),
                            "parent_concept_ids": tuple(
                                sorted(set(linked_canonical_ids))
                            ),
                        }
                    )
                )
            else:
                routes.append(
                    _content_bound_technology_route(
                        {
                            **common_payload,
                            "projection_version": TECHNOLOGY_ROUTE_PROJECTION_VERSION,
                            "concept_ids": tuple(sorted(set(linked_canonical_ids))),
                        }
                    )
                )
        return (
            tuple(
                sorted(
                    (
                        anchor
                        for values in anchors_by_source.values()
                        for anchor in values
                    ),
                    key=lambda item: item.anchor_id,
                )
            ),
            tuple(
                sorted(
                    concepts,
                    key=lambda item: item.canonical_technology_identity_id,
                )
            ),
            tuple(
                sorted(
                    routes,
                    key=lambda item: item.canonical_technology_identity_id,
                )
            ),
            tuple(sorted(unresolved, key=lambda item: item.reference_id)),
        )

    def project(
        self,
        request: InternalReferenceProjectionRequest,
    ) -> InternalReferenceProjectionResult:
        installed_identity = (
            self._catalog.schema_version,
            self._catalog.catalog_version,
            self._catalog.content_sha256,
        )
        supplied_identity = (
            request.reference_catalog_identity.schema_version,
            request.reference_catalog_identity.catalog_version,
            request.reference_catalog_identity.content_sha256,
        )
        if supplied_identity != installed_identity:
            raise InternalReferenceProjectionIntegrityError(
                "request reference catalog identity differs from the builder"
            )
        try:
            domain_request = DomainProjectionRequest.model_validate(
                request.public_domain_projection_request.model_dump(mode="python")
            )
            domain_result = DomainProjectionResult.model_validate(
                request.public_domain_projection_result.model_dump(mode="python")
            )
            rebuilt_domain_result = (
                create_ephemeral_domain_projection_builder().project(domain_request)
            )
            identity_request = IdentityResolutionRequest.model_validate(
                request.person_identity_resolution_request.model_dump(mode="python")
            )
            identity_result = validate_identity_resolution_result(
                identity_request,
                request.person_identity_resolution_result,
            )
            technology_request = (
                IdentityResolutionRequest.model_validate(
                    request.technology_identity_resolution_request.model_dump(
                        mode="python"
                    )
                )
                if request.technology_identity_resolution_request is not None
                else None
            )
            technology_result = (
                validate_identity_resolution_result(
                    technology_request,
                    request.technology_identity_resolution_result,
                )
                if technology_request is not None
                and request.technology_identity_resolution_result is not None
                else None
            )
        except (
            AttributeError,
            CanonicalIdentityResolutionError,
            ValidationError,
            ValueError,
        ) as exc:
            raise InternalReferenceProjectionIntegrityError(
                "closed domain or identity lineage is invalid"
            ) from exc
        if rebuilt_domain_result != domain_result:
            raise InternalReferenceProjectionIntegrityError(
                "public domain result cannot be rebuilt from its exact request"
            )

        base_catalog = self._catalog.base_domain_catalog
        if (
            domain_result.catalog_schema_version,
            domain_result.catalog_version,
            domain_result.catalog_content_sha256,
        ) != (
            base_catalog.schema_version,
            base_catalog.catalog_version,
            base_catalog.content_sha256,
        ):
            raise InternalReferenceProjectionIntegrityError(
                "public domain result differs from the reference catalog base"
            )
        if (
            domain_result.release_id != request.release_id
            or domain_result.as_of != request.as_of
        ):
            raise InternalReferenceProjectionIntegrityError(
                "public domain result release or as_of differs from request"
            )
        if (
            identity_request.release_id != request.release_id
            or identity_result.release_id != request.release_id
            or identity_result.as_of > request.as_of
            or identity_request.identity_method_version
            != PERSON_IDENTITY_METHOD_VERSION
        ):
            raise InternalReferenceProjectionIntegrityError(
                "Person identity resolution release or as_of differs from request"
            )
        if any(
            source.entity_type != "person"
            for source in identity_result.source_identities
        ):
            raise InternalReferenceProjectionIntegrityError(
                "Person identity resolution may contain only person source identities"
            )
        if any(
            source.last_observed_at > request.as_of
            for source in identity_result.source_identities
        ) or any(
            assertion.observed_at > request.as_of
            for assertion in identity_result.identity_assertions
        ):
            raise InternalReferenceProjectionIntegrityError(
                "Person identity evidence observation is after request as_of"
            )
        if any(
            identity.entity_type != "person"
            or identity.state is not CanonicalIdentityState.active
            or identity.release_id != request.release_id
            for identity in identity_result.current_canonical_identities
        ):
            raise InternalReferenceProjectionIntegrityError(
                "Person identity resolution contains a non-active Person identity"
            )
        if technology_request is not None and technology_result is not None:
            if (
                technology_request.release_id != request.release_id
                or technology_result.release_id != request.release_id
                or technology_result.as_of > request.as_of
                or technology_request.identity_method_version
                != TECHNOLOGY_IDENTITY_METHOD_VERSION
            ):
                raise InternalReferenceProjectionIntegrityError(
                    "Technology identity resolution release, as_of, or method differs"
                )
            for source in technology_result.source_identities:
                if source.entity_type not in {
                    "technology_concept",
                    "technology_route",
                }:
                    raise InternalReferenceProjectionIntegrityError(
                        "unsupported internal reference identity type: "
                        f"{source.entity_type}"
                    )
            if any(
                source.last_observed_at > request.as_of
                for source in technology_result.source_identities
            ) or any(
                assertion.observed_at > request.as_of
                for assertion in technology_result.identity_assertions
            ):
                raise InternalReferenceProjectionIntegrityError(
                    "Technology identity evidence observation is after request as_of"
                )
            if any(
                identity.entity_type not in {"technology_concept", "technology_route"}
                or identity.state is not CanonicalIdentityState.active
                or identity.release_id != request.release_id
                for identity in technology_result.current_canonical_identities
            ):
                raise InternalReferenceProjectionIntegrityError(
                    "Technology identity result contains an invalid active identity"
                )

        projections = {
            (item.entity_type, item.canonical_identity_id): item
            for item in domain_result.projections
        }
        domain_assertions = {
            item.assertion_id: item for item in domain_request.source_assertions
        }
        sources = {
            item.source_identity_id: item for item in identity_result.source_identities
        }
        locator_source_ids = {
            item.source_identity_id for item in request.person_evidence_locators
        }
        if locator_source_ids != set(sources):
            raise InternalReferenceProjectionIntegrityError(
                "Person locators must exactly cover identity-resolution sources"
            )
        assignments = {
            item.source_identity_id: item
            for item in identity_result.source_identity_assignments
        }
        identities = {
            item.canonical_identity_id: item
            for item in identity_result.current_canonical_identities
        }
        contexts = _context_index(identity_request, identity_result)
        verdict_by_source = {
            source_id: verdict
            for verdict in identity_result.candidate_verdicts
            for source_id in verdict.source_identity_ids
        }
        review_by_verdict = {
            item.originating_record_id: item for item in identity_result.review_cases
        }

        anchors: list[PublicDomainEvidenceAnchor] = []
        references: list[PersonReference] = []
        for locator in sorted(
            request.person_evidence_locators, key=lambda item: item.reference_id
        ):
            source = sources[locator.source_identity_id]
            anchor, name = _derive_anchor_and_name(
                locator=locator,
                projections=projections,
                domain_assertions=domain_assertions,
            )
            if anchor.observed_at > request.as_of:
                raise InternalReferenceProjectionIntegrityError(
                    "Person public evidence observation is after request as_of"
                )
            source_assertions = _identity_assertions_for_source(
                source, identity_result.identity_assertions
            )
            (
                identity_assertion_ids,
                shared_source_record_ids,
                has_evidence_bound_orcid,
            ) = _person_evidence_connection(
                locator=locator,
                source=source,
                assertions=source_assertions,
                anchor=anchor,
                person_name=name,
            )

            current_verdict = verdict_by_source.get(source.source_identity_id)
            assignment = assignments.get(source.source_identity_id)
            identity = (
                identities.get(assignment.canonical_identity_id)
                if assignment is not None
                else None
            )
            context = (
                contexts.get(assignment.identity_decision_id)
                if assignment is not None
                else None
            )
            topology_context = (
                contexts.get(identity.identity_decision_id)
                if identity is not None
                else None
            )
            lineage_values = (assignment, identity, context, topology_context)
            has_lineage = any(item is not None for item in lineage_values)
            complete_lineage = all(item is not None for item in lineage_values)
            if has_lineage and not complete_lineage:
                raise InternalReferenceProjectionIntegrityError(
                    "Person assignment requires exact assignment and topology contexts"
                )
            if complete_lineage:
                assert assignment is not None
                assert identity is not None
                assert context is not None
                assert topology_context is not None
                if (
                    source.source_identity_id not in identity.source_identity_ids
                    or assignment.release_id != request.release_id
                    or context.release_id != request.release_id
                    or topology_context.release_id != request.release_id
                ):
                    raise InternalReferenceProjectionIntegrityError(
                        "Person assignment and identity decision lineage are cross-wired"
                    )
                topology_verdict = topology_context.candidate_verdict
            else:
                topology_verdict = None
            accepted_outcomes = {
                IdentityCandidateOutcome.same_entity,
                IdentityCandidateOutcome.different_entities,
            }
            accepted_current = (
                current_verdict is not None
                and current_verdict.verdict in accepted_outcomes
            )
            accepted_topology = (
                topology_verdict is not None
                and topology_verdict.verdict in accepted_outcomes
            )
            accepted_singleton_topology = (
                complete_lineage
                and topology_verdict is None
                and topology_context is not None
                and _context_has_evidence_bound_identifier(
                    context=topology_context,
                    source_identity_id=source.source_identity_id,
                    key="orcid",
                    field_path="identity.orcid",
                )
            )
            unresolved = not (
                accepted_current or accepted_topology or accepted_singleton_topology
            )
            if not complete_lineage and (accepted_current or accepted_topology):
                raise InternalReferenceProjectionIntegrityError(
                    "resolved Person verdict requires exact canonical identity lineage"
                )
            if complete_lineage and unresolved:
                raise InternalReferenceProjectionIntegrityError(
                    "unresolved Person reference cannot retain a canonical identity"
                )
            if accepted_current:
                effective_verdict = current_verdict
            elif accepted_topology:
                effective_verdict = topology_verdict
            elif accepted_singleton_topology:
                effective_verdict = None
            else:
                effective_verdict = current_verdict or topology_verdict
            review_case = (
                review_by_verdict.get(effective_verdict.verdict_id)
                if effective_verdict is not None
                else None
            )

            if unresolved:
                reference = PersonReference(
                    reference_id=locator.reference_id,
                    name=name,
                    source_kind=locator.source_kind,
                    source_anchor_id=anchor.anchor_id,
                    source_identity_id=source.source_identity_id,
                    supporting_assertion_ids=anchor.supporting_assertion_ids,
                    identity_assertion_ids=identity_assertion_ids,
                    shared_source_record_ids=shared_source_record_ids,
                    identity_resolution_content_sha256=identity_result.content_sha256,
                    resolution_state="unresolved",
                    canonical_person_identity_id=None,
                    assignment_decision_id=None,
                    candidate_verdict_id=(
                        effective_verdict.verdict_id
                        if effective_verdict is not None
                        else None
                    ),
                    review_case_id=(
                        review_case.review_case_id if review_case is not None else None
                    ),
                )
            else:
                assert assignment is not None
                assert identity is not None
                reference = PersonReference(
                    reference_id=locator.reference_id,
                    name=name,
                    source_kind=locator.source_kind,
                    source_anchor_id=anchor.anchor_id,
                    source_identity_id=source.source_identity_id,
                    supporting_assertion_ids=anchor.supporting_assertion_ids,
                    identity_assertion_ids=identity_assertion_ids,
                    shared_source_record_ids=shared_source_record_ids,
                    identity_resolution_content_sha256=identity_result.content_sha256,
                    resolution_state="resolved",
                    canonical_person_identity_id=identity.canonical_identity_id,
                    assignment_decision_id=assignment.identity_decision_id,
                    candidate_verdict_id=(
                        effective_verdict.verdict_id
                        if effective_verdict is not None
                        else None
                    ),
                )
            anchors.append(anchor)
            references.append(reference)

        grouped: dict[str, list[PersonReference]] = {}
        for reference in references:
            if reference.resolution_state == "resolved":
                grouped.setdefault(
                    cast(str, reference.canonical_person_identity_id), []
                ).append(reference)
        person_projections: list[PersonProjection] = []
        for canonical_id, grouped_references in sorted(grouped.items()):
            identity = identities[canonical_id]
            ordered_references = tuple(
                sorted(
                    grouped_references,
                    key=lambda item: (item.source_kind, item.reference_id),
                )
            )
            names = {item.name for item in ordered_references}
            display_name = (
                identity.display_name
                if identity.display_name is not None and identity.display_name in names
                else ordered_references[0].name
            )
            person_projections.append(
                _content_bound_person_projection(
                    {
                        "canonical_person_identity_id": canonical_id,
                        "display_name": display_name,
                        "aliases": tuple(sorted(names - {display_name})),
                        "references": ordered_references,
                        "source_anchor_ids": tuple(
                            sorted(
                                {item.source_anchor_id for item in ordered_references}
                            )
                        ),
                        "source_public_domains": tuple(
                            sorted(
                                {
                                    _SOURCE_KIND_SPECS[item.source_kind][0]
                                    for item in ordered_references
                                }
                            )
                        ),
                        "source_identity_ids": tuple(
                            sorted(
                                {item.source_identity_id for item in ordered_references}
                            )
                        ),
                        "supporting_assertion_ids": tuple(
                            sorted(
                                {
                                    assertion_id
                                    for item in ordered_references
                                    for assertion_id in item.supporting_assertion_ids
                                }
                            )
                        ),
                        "identity_assertion_ids": tuple(
                            sorted(
                                {
                                    assertion_id
                                    for item in ordered_references
                                    for assertion_id in item.identity_assertion_ids
                                }
                            )
                        ),
                        "source_record_ids": tuple(
                            sorted(
                                {
                                    source_record_id
                                    for item in ordered_references
                                    for source_record_id in (
                                        item.shared_source_record_ids
                                    )
                                }
                            )
                        ),
                        "assignment_decision_ids": tuple(
                            sorted(
                                {
                                    cast(str, item.assignment_decision_id)
                                    for item in ordered_references
                                }
                            )
                        ),
                        "identity_verdict_ids": tuple(
                            sorted(
                                {
                                    item.candidate_verdict_id
                                    for item in ordered_references
                                    if item.candidate_verdict_id is not None
                                }
                            )
                        ),
                        "identity_decision_id": identity.identity_decision_id,
                        "identity_resolution_content_sha256": (
                            identity_result.content_sha256
                        ),
                        "release_id": request.release_id,
                        "projection_version": PERSON_REFERENCE_PROJECTION_VERSION,
                        "projection_scope": "internal_auxiliary",
                        "reference_type": "person",
                        "domain": None,
                        "reference_catalog_schema_version": (
                            self._catalog.schema_version
                        ),
                        "reference_catalog_version": self._catalog.catalog_version,
                        "reference_catalog_content_sha256": self._catalog.content_sha256,
                        "as_of": request.as_of,
                    }
                )
            )

        unresolved_references = tuple(
            sorted(
                (item for item in references if item.resolution_state == "unresolved"),
                key=lambda item: item.reference_id,
            )
        )
        (
            technology_anchors,
            technology_concepts,
            technology_routes,
            unresolved_technology,
        ) = self._project_technology(
            request=request,
            domain_request=domain_request,
            projections=projections,
            identity_request=technology_request,
            identity_result=technology_result,
        )
        return _content_bound_result(
            {
                "release_id": request.release_id,
                "build_run_id": request.build_run_id,
                "as_of": request.as_of,
                "projection_version": request.projection_version,
                "reference_catalog_schema_version": self._catalog.schema_version,
                "reference_catalog_version": self._catalog.catalog_version,
                "reference_catalog_content_sha256": self._catalog.content_sha256,
                "public_domain_projection_result_content_sha256": (
                    domain_result.content_sha256
                ),
                "identity_resolution_content_sha256": identity_result.content_sha256,
                "technology_identity_resolution_content_sha256": (
                    technology_result.content_sha256
                    if technology_result is not None
                    else None
                ),
                "public_evidence_anchors": tuple(
                    sorted(anchors, key=lambda item: item.anchor_id)
                ),
                "person_projections": tuple(person_projections),
                "unresolved_person_references": unresolved_references,
                "technology_evidence_anchors": technology_anchors,
                "technology_concept_projections": technology_concepts,
                "technology_route_projections": technology_routes,
                "unresolved_technology_references": unresolved_technology,
            }
        )


def create_ephemeral_internal_reference_projection_builder(
    *, catalog: InstalledInternalReferenceCatalog = PACKAGED_REFERENCE_CATALOG
) -> InternalReferenceProjectionBuilder:
    return _EphemeralInternalReferenceProjectionBuilder(catalog)


def validate_internal_reference_projection_result(
    request: InternalReferenceProjectionRequest,
    result: InternalReferenceProjectionResult,
) -> InternalReferenceProjectionResult:
    """Validate a result by replaying the complete closed projection graph."""

    try:
        validated_request = InternalReferenceProjectionRequest.model_validate(
            request.model_dump(mode="python")
        )
        validated_result = InternalReferenceProjectionResult.model_validate(
            result.model_dump(mode="python")
        )
        rebuilt_result = (
            create_ephemeral_internal_reference_projection_builder().project(
                validated_request
            )
        )
    except (AttributeError, ValidationError, ValueError) as exc:
        raise InternalReferenceProjectionIntegrityError(
            "internal reference result or its closed request is invalid"
        ) from exc
    if rebuilt_result != validated_result:
        raise InternalReferenceProjectionIntegrityError(
            "internal reference result cannot be replayed from its exact request"
        )
    return validated_result


__all__ = [
    "INTERNAL_REFERENCE_TYPES",
    "INTERNAL_REFERENCE_PROJECTION_VERSION",
    "PERSON_REFERENCE_PROJECTION_VERSION",
    "PUBLIC_DOMAIN_TYPES",
    "TECHNOLOGY_CONCEPT_PROJECTION_VERSION",
    "TECHNOLOGY_ROUTE_PROJECTION_VERSION",
    "InternalReferenceProjectionBuilder",
    "InternalReferenceProjectionIntegrityError",
    "InternalReferenceProjectionRequest",
    "InternalReferenceProjectionResult",
    "PersonEvidenceCrosswalk",
    "PersonEvidenceLocator",
    "PersonProjection",
    "PersonReference",
    "PublicDomainEvidenceAnchor",
    "ReferenceCatalogIdentity",
    "TechnologyConceptProjection",
    "TechnologyEvidenceAnchor",
    "TechnologyEvidenceLocator",
    "TechnologyFieldLineage",
    "TechnologyRouteProjection",
    "UnresolvedTechnologyReference",
    "create_ephemeral_internal_reference_projection_builder",
    "validate_internal_reference_projection_result",
]
