"""Explicit typed domain and business sub-object models for Canonical V2."""

from __future__ import annotations

from datetime import date as Date
from decimal import Decimal
import hashlib
import json
from typing import Literal, cast

from pydantic import Field, JsonValue, ValidationInfo, field_validator, model_validator

from .contracts import (
    CanonicalDatetime,
    ContractModel,
    NonEmptyStr,
    NonNegativeInt,
    Sha256,
    TemporalRelation,
    TemporalValue,
    compare_temporal_values,
)
from .domain_catalog import (
    CATALOG_CONTENT_SHA256,
    CATALOG_SCHEMA_VERSION,
    CATALOG_VERSION,
)


QualitySignal = NonEmptyStr
Year = int


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


class NamedReference(ContractModel):
    reference_id: NonEmptyStr
    name: NonEmptyStr


class Money(ContractModel):
    amount: Decimal
    currency: NonEmptyStr | None = None


class ProjectionEvidenceReference(ContractModel):
    assertion_id: NonEmptyStr
    decision_id: NonEmptyStr
    field_path: NonEmptyStr
    artifact_ids: tuple[NonEmptyStr, ...] = ()


class RelationshipProjectionReference(ContractModel):
    relationship_id: NonEmptyStr
    relationship_type_id: NonEmptyStr
    target_canonical_identity_id: NonEmptyStr


class FieldProjectionLineage(ContractModel):
    field_path: NonEmptyStr
    decision_id: NonEmptyStr
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("supporting_assertion_ids")
    @classmethod
    def validate_assertion_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("field lineage assertion IDs must be unique")
        return tuple(sorted(values))


class TypedSubobject(ContractModel):
    subobject_id: NonEmptyStr
    parent_canonical_identity_id: NonEmptyStr
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    decision_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    observed_at: CanonicalDatetime
    valid_from: TemporalValue | None = None
    valid_to: TemporalValue | None = None
    projection_content_sha256: Sha256

    @field_validator("supporting_assertion_ids", "decision_ids")
    @classmethod
    def validate_lineage_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("sub-object lineage IDs must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_interval_and_hash(self, info: ValidationInfo) -> TypedSubobject:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and type(self.valid_from) is not type(self.valid_to)
        ):
            raise ValueError("valid_from and valid_to must use the same time shape")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and compare_temporal_values(self.valid_from, self.valid_to)
            is TemporalRelation.after
        ):
            raise ValueError("valid_from must not be after valid_to")
        if not (info.context or {}).get("allow_unbound_projection_hash"):
            payload = cast(
                JsonValue,
                self.model_dump(mode="json", exclude={"projection_content_sha256"}),
            )
            if self.projection_content_sha256 != _canonical_sha256(payload):
                raise ValueError(
                    "projection_content_sha256 must bind the typed sub-object"
                )
        return self


# Company sub-objects
class CompanyBusinessScenario(TypedSubobject):
    name: NonEmptyStr
    description: NonEmptyStr


class CompanyCapability(TypedSubobject):
    name: NonEmptyStr
    description: NonEmptyStr


class CompanyFinancingEvent(TypedSubobject):
    round: NonEmptyStr
    amount: Money | None = None
    investors: tuple[NamedReference, ...] = ()
    event_date: Date | None = None


class CompanyKeyPersonnel(TypedSubobject):
    name: NonEmptyStr
    role: NonEmptyStr
    description: NonEmptyStr | None = None


class CompanyPersonnelEducation(TypedSubobject):
    person: NamedReference
    institution: NamedReference
    degree: NonEmptyStr | None = None
    field: NonEmptyStr | None = None
    year: Year | None = Field(default=None, ge=1000, le=9999)


class CompanyPersonnelWorkExperience(TypedSubobject):
    person: NamedReference
    organization: NamedReference
    role: NonEmptyStr
    start: Date | None = None
    end: Date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> CompanyPersonnelWorkExperience:
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must not be after end")
        return self


class CompanyProduct(TypedSubobject):
    name: NonEmptyStr
    description: NonEmptyStr | None = None
    technology_tags: tuple[NamedReference, ...] = ()


class CompanyPublicUpdate(TypedSubobject):
    headline: NonEmptyStr
    source_url: NonEmptyStr
    event_date: Date | None = None
    summary: NonEmptyStr | None = None


# Paper sub-objects
class PaperAuthor(TypedSubobject):
    name: NonEmptyStr
    author_order: NonNegativeInt
    orcid: NonEmptyStr | None = None
    affiliations: tuple[NamedReference, ...] = ()


class PaperEnrichmentProvenance(TypedSubobject):
    provider: NonEmptyStr
    fetched_at: CanonicalDatetime
    source_record_id: NonEmptyStr


class PaperFullText(TypedSubobject):
    content_sha256: Sha256
    storage_reference: NonEmptyStr
    source_url: NonEmptyStr | None = None
    parser_version: NonEmptyStr


class PaperFunding(TypedSubobject):
    funder: NamedReference
    grant_number: NonEmptyStr | None = None


class PaperIdentifier(TypedSubobject):
    scheme: NonEmptyStr
    value: NonEmptyStr


class PaperPublication(TypedSubobject):
    venue: NamedReference | None = None
    publication_date: Date | None = None
    year: Year = Field(ge=1000, le=9999)


class PaperReference(TypedSubobject):
    target_paper_id: NonEmptyStr | None = None
    raw_citation: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> PaperReference:
        if self.target_paper_id is None and self.raw_citation is None:
            raise ValueError("paper reference requires a target or raw citation")
        return self


class PaperSummary(TypedSubobject):
    language: NonEmptyStr
    summary_kind: NonEmptyStr
    content: NonEmptyStr
    content_hash: Sha256


# Patent sub-objects
class PatentApplicant(TypedSubobject):
    name: NonEmptyStr
    applicant_order: NonNegativeInt
    canonical_company_id: NonEmptyStr | None = None
    company_name: NonEmptyStr | None = None


class PatentInventor(TypedSubobject):
    name: NonEmptyStr
    inventor_order: NonNegativeInt
    affiliation: NamedReference | None = None
    canonical_professor_id: NonEmptyStr | None = None


class PatentIpcClassification(TypedSubobject):
    code: NonEmptyStr
    version: NonEmptyStr
    label: NonEmptyStr | None = None


class PatentMilestone(TypedSubobject):
    kind: NonEmptyStr
    date: Date


class PatentTechnicalSummary(TypedSubobject):
    summary_text: NonEmptyStr
    technology_effect: NonEmptyStr | None = None
    content_hash: Sha256
    model_version: NonEmptyStr


# Professor sub-objects
class ProfessorAffiliationHistory(TypedSubobject):
    institution: NamedReference
    department: NamedReference | None = None
    title: NonEmptyStr | None = None


class ProfessorAward(TypedSubobject):
    name: NonEmptyStr
    issuer: NamedReference | None = None
    date: Date | None = None


class ProfessorContact(TypedSubobject):
    kind: NonEmptyStr
    value: NonEmptyStr
    public_source: ProjectionEvidenceReference


class ProfessorEducationHistory(TypedSubobject):
    institution: NamedReference
    degree: NonEmptyStr | None = None
    field: NonEmptyStr | None = None
    start: Date | None = None
    end: Date | None = None


class ProfessorMetricSnapshot(TypedSubobject):
    provider: NonEmptyStr
    observed_at: CanonicalDatetime
    h_index: NonNegativeInt | None = None
    citation_count: NonNegativeInt | None = None
    paper_count: NonNegativeInt | None = None


class ProfessorResearchProject(TypedSubobject):
    name: NonEmptyStr
    funder: NamedReference | None = None
    role: NonEmptyStr | None = None


class ProfessorWorkHistory(TypedSubobject):
    organization: NamedReference
    role: NonEmptyStr


class DomainProjectionEnvelope(ContractModel):
    release_id: NonEmptyStr
    canonical_identity_id: NonEmptyStr
    identity_decision_id: NonEmptyStr
    inclusion_decision_id: NonEmptyStr
    projection_version: NonEmptyStr
    catalog_schema_version: NonEmptyStr
    catalog_version: NonEmptyStr
    catalog_content_sha256: Sha256
    as_of: CanonicalDatetime
    field_lineage: tuple[FieldProjectionLineage, ...] = Field(min_length=1)
    content_sha256: Sha256

    @field_validator("field_lineage")
    @classmethod
    def validate_field_lineage(
        cls, values: tuple[FieldProjectionLineage, ...]
    ) -> tuple[FieldProjectionLineage, ...]:
        paths = tuple(value.field_path for value in values)
        if len(paths) != len(set(paths)):
            raise ValueError("field lineage paths must be unique")
        return tuple(sorted(values, key=lambda value: value.field_path))

    @model_validator(mode="after")
    def validate_envelope(self, info: ValidationInfo) -> DomainProjectionEnvelope:
        if (
            self.catalog_schema_version,
            self.catalog_version,
            self.catalog_content_sha256,
        ) != (
            CATALOG_SCHEMA_VERSION,
            CATALOG_VERSION,
            CATALOG_CONTENT_SHA256,
        ):
            raise ValueError("projection must bind the installed catalog identity")
        if getattr(self, "id", None) != self.canonical_identity_id:
            raise ValueError("projection id must equal canonical_identity_id")
        last_updated = getattr(self, "last_updated", None)
        if last_updated is not None and last_updated > self.as_of:
            raise ValueError("last_updated cannot be after projection as_of")
        evidence = getattr(self, "evidence", ())
        evidence_edges = {
            (item.field_path, item.decision_id, item.assertion_id) for item in evidence
        }
        lineage_edges = {
            (lineage.field_path, lineage.decision_id, assertion_id)
            for lineage in self.field_lineage
            for assertion_id in lineage.supporting_assertion_ids
        }
        if evidence_edges != lineage_edges:
            raise ValueError("projection evidence must exactly match field lineage")
        if not (info.context or {}).get("allow_unbound_projection_hash"):
            payload = cast(
                JsonValue,
                self.model_dump(mode="json", exclude={"content_sha256"}),
            )
            if self.content_sha256 != _canonical_sha256(payload):
                raise ValueError("content_sha256 must bind the typed projection")
        return self


class CompanyProjection(DomainProjectionEnvelope):
    entity_type: Literal["company"] = "company"
    aliases: tuple[NonEmptyStr, ...] = ()
    credit_code: NonEmptyStr | None = None
    evidence: tuple[ProjectionEvidenceReference, ...] = Field(min_length=1)
    founded_at: Date | None = None
    geography: NamedReference | None = None
    id: NonEmptyStr
    industry: NamedReference | None = None
    industry_tags: tuple[NamedReference, ...] = ()
    key_personnel: tuple[CompanyKeyPersonnel, ...] = ()
    last_updated: CanonicalDatetime
    latest_public_updates: tuple[CompanyPublicUpdate, ...] = ()
    legal_representative: NamedReference | None = None
    name: NonEmptyStr
    normalized_name: NonEmptyStr
    patent_count: NonNegativeInt | None = None
    product_description: NonEmptyStr | None = None
    profile_summary: NonEmptyStr
    quality_status: QualitySignal
    registered_address: NonEmptyStr | None = None
    registered_capital: Money | None = None
    run_id: NonEmptyStr
    team_description: NonEmptyStr | None = None
    tech_tags: tuple[NamedReference, ...] = ()
    technology_route_summary: NonEmptyStr
    website: NonEmptyStr | None = None
    business_scenarios: tuple[CompanyBusinessScenario, ...] = ()
    capabilities: tuple[CompanyCapability, ...] = ()
    financing_events: tuple[CompanyFinancingEvent, ...] = ()
    personnel_education: tuple[CompanyPersonnelEducation, ...] = ()
    personnel_work_experience: tuple[CompanyPersonnelWorkExperience, ...] = ()
    products: tuple[CompanyProduct, ...] = ()


class PaperProjection(DomainProjectionEnvelope):
    entity_type: Literal["paper"] = "paper"
    abstract: NonEmptyStr | None = None
    arxiv_id: NonEmptyStr | None = None
    authors: tuple[PaperAuthor, ...]
    citation_count: NonNegativeInt | None = None
    doi: NonEmptyStr | None = None
    enrichment_sources: tuple[PaperEnrichmentProvenance, ...] = ()
    evidence: tuple[ProjectionEvidenceReference, ...] = Field(min_length=1)
    fields_of_study: tuple[NamedReference, ...] = ()
    funders: tuple[PaperFunding, ...] = ()
    id: NonEmptyStr
    keywords: tuple[NonEmptyStr, ...] = ()
    last_updated: CanonicalDatetime
    license: NonEmptyStr | None = None
    oa_status: NonEmptyStr | None = None
    pdf_path: NonEmptyStr | None = None
    professor_ids: tuple[NonEmptyStr, ...] = ()
    publication_date: Date | None = None
    quality_status: QualitySignal
    reference_count: NonNegativeInt | None = None
    run_id: NonEmptyStr
    summary_text: NonEmptyStr | None = None
    summary_zh: NonEmptyStr | None = None
    title: NonEmptyStr
    title_zh: NonEmptyStr | None = None
    tldr: NonEmptyStr | None = None
    venue: NamedReference
    year: Year = Field(ge=1000, le=9999)
    full_texts: tuple[PaperFullText, ...] = ()
    identifiers: tuple[PaperIdentifier, ...] = ()
    publications: tuple[PaperPublication, ...] = ()
    references: tuple[PaperReference, ...] = ()
    summaries: tuple[PaperSummary, ...] = ()


class PatentProjection(DomainProjectionEnvelope):
    entity_type: Literal["patent"] = "patent"
    abstract: NonEmptyStr | None = None
    applicants: tuple[PatentApplicant, ...]
    company_ids: tuple[NonEmptyStr, ...] = ()
    evidence: tuple[ProjectionEvidenceReference, ...] = Field(min_length=1)
    filing_date: Date | None = None
    grant_date: Date | None = None
    id: NonEmptyStr
    inventors: tuple[PatentInventor, ...] = ()
    ipc_codes: tuple[PatentIpcClassification, ...] = ()
    last_updated: CanonicalDatetime
    patent_number: NonEmptyStr | None = None
    patent_type: NonEmptyStr | None = None
    professor_ids: tuple[NonEmptyStr, ...] = ()
    publication_date: Date | None = None
    quality_status: QualitySignal
    run_id: NonEmptyStr
    summary_text: NonEmptyStr
    technology_effect: NonEmptyStr | None = None
    title: NonEmptyStr
    title_en: NonEmptyStr | None = None
    milestones: tuple[PatentMilestone, ...] = ()
    technical_summaries: tuple[PatentTechnicalSummary, ...] = ()


class ProfessorProjection(DomainProjectionEnvelope):
    entity_type: Literal["professor"] = "professor"
    aliases: tuple[NonEmptyStr, ...] = ()
    awards: tuple[ProfessorAward, ...] = ()
    canonical_name_en: NonEmptyStr | None = None
    canonical_name_zh: NonEmptyStr
    citation_count: NonNegativeInt | None = None
    company_roles: tuple[RelationshipProjectionReference, ...] = ()
    department: NamedReference
    email: NonEmptyStr
    evidence: tuple[ProjectionEvidenceReference, ...] = Field(min_length=1)
    h_index: NonNegativeInt | None = None
    homepage: NonEmptyStr
    id: NonEmptyStr
    institution: NonEmptyStr
    last_updated: CanonicalDatetime
    lifecycle_state: NonEmptyStr | None = None
    manual_override: dict[NonEmptyStr, NonEmptyStr] | None = None
    name: NonEmptyStr
    office: NonEmptyStr | None = None
    paper_count: NonNegativeInt | None = None
    paper_summary: NonEmptyStr
    patent_ids: tuple[NonEmptyStr, ...]
    patent_summary: NonEmptyStr
    phone: NonEmptyStr | None = None
    profile_summary: NonEmptyStr
    projects: tuple[ProfessorResearchProject, ...] = ()
    quality_status: QualitySignal
    research_directions: tuple[NamedReference, ...]
    run_id: NonEmptyStr
    title: NonEmptyStr
    affiliation_history: tuple[ProfessorAffiliationHistory, ...] = ()
    contacts: tuple[ProfessorContact, ...] = ()
    education_history: tuple[ProfessorEducationHistory, ...] = ()
    metric_snapshots: tuple[ProfessorMetricSnapshot, ...] = ()
    work_history: tuple[ProfessorWorkHistory, ...] = ()


DOMAIN_SUBOBJECT_MODELS = {
    "company": {
        "business_scenario": CompanyBusinessScenario,
        "capability": CompanyCapability,
        "financing_event": CompanyFinancingEvent,
        "key_personnel": CompanyKeyPersonnel,
        "personnel_education": CompanyPersonnelEducation,
        "personnel_work_experience": CompanyPersonnelWorkExperience,
        "product": CompanyProduct,
        "public_update": CompanyPublicUpdate,
    },
    "paper": {
        "author": PaperAuthor,
        "enrichment_provenance": PaperEnrichmentProvenance,
        "full_text": PaperFullText,
        "funding": PaperFunding,
        "identifier": PaperIdentifier,
        "publication": PaperPublication,
        "reference": PaperReference,
        "summary": PaperSummary,
    },
    "patent": {
        "applicant": PatentApplicant,
        "inventor": PatentInventor,
        "ipc_classification": PatentIpcClassification,
        "patent_milestone": PatentMilestone,
        "technical_summary": PatentTechnicalSummary,
    },
    "professor": {
        "affiliation_history": ProfessorAffiliationHistory,
        "award": ProfessorAward,
        "contact": ProfessorContact,
        "education_history": ProfessorEducationHistory,
        "metric_snapshot": ProfessorMetricSnapshot,
        "research_project": ProfessorResearchProject,
        "work_history": ProfessorWorkHistory,
    },
}

DOMAIN_SUBOBJECT_ATTRIBUTES = {
    "company": {
        "business_scenario": "business_scenarios",
        "capability": "capabilities",
        "financing_event": "financing_events",
        "key_personnel": "key_personnel",
        "personnel_education": "personnel_education",
        "personnel_work_experience": "personnel_work_experience",
        "product": "products",
        "public_update": "latest_public_updates",
    },
    "paper": {
        "author": "authors",
        "enrichment_provenance": "enrichment_sources",
        "full_text": "full_texts",
        "funding": "funders",
        "identifier": "identifiers",
        "publication": "publications",
        "reference": "references",
        "summary": "summaries",
    },
    "patent": {
        "applicant": "applicants",
        "inventor": "inventors",
        "ipc_classification": "ipc_codes",
        "patent_milestone": "milestones",
        "technical_summary": "technical_summaries",
    },
    "professor": {
        "affiliation_history": "affiliation_history",
        "award": "awards",
        "contact": "contacts",
        "education_history": "education_history",
        "metric_snapshot": "metric_snapshots",
        "research_project": "projects",
        "work_history": "work_history",
    },
}


__all__ = [
    "CompanyProjection",
    "DOMAIN_SUBOBJECT_ATTRIBUTES",
    "DOMAIN_SUBOBJECT_MODELS",
    "DomainProjectionEnvelope",
    "FieldProjectionLineage",
    "Money",
    "NamedReference",
    "PaperProjection",
    "PatentProjection",
    "ProfessorProjection",
    "ProjectionEvidenceReference",
    "RelationshipProjectionReference",
    "TypedSubobject",
]
