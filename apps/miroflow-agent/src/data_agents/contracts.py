from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


QualityStatus = Literal["ready", "needs_review", "low_confidence", "needs_enrichment"]
LegacyQualityStatus = Literal["ready", "needs_review", "low_confidence", "needs_enrichment", "incomplete", "shallow_summary"]

QUALITY_STATUS_CANONICAL_MAP: dict[str, QualityStatus] = {
    "ready": "ready",
    "needs_review": "needs_review",
    "low_confidence": "low_confidence",
    "needs_enrichment": "needs_enrichment",
    "incomplete": "needs_review",
    "shallow_summary": "needs_review",
}


def normalize_quality_status(raw_status: str) -> QualityStatus:
    """Normalize legacy and current statuses into shared quality states."""
    if raw_status not in QUALITY_STATUS_CANONICAL_MAP:
        return "needs_review"
    return QUALITY_STATUS_CANONICAL_MAP[raw_status]


def quality_status_compatibility_rows() -> dict[str, list[str]]:
    """Return compact compatibility mapping for docs and troubleshooting."""
    mapping: dict[str, list[str]] = {
        "ready": ["ready"],
        "needs_review": ["needs_review", "incomplete", "shallow_summary"],
        "needs_enrichment": ["needs_enrichment"],
        "low_confidence": ["low_confidence"],
    }
    return mapping
EvidenceSourceType = Literal[
    "official_site",
    "xlsx_import",
    "public_web",
    "academic_platform",
    "manual_review",
]
ObjectType = Literal["professor", "company", "paper", "patent", "professor_paper_link"]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OptionalNonEmptyStr = NonEmptyStr | None
SHENZHEN_INSTITUTION_KEYWORDS = (
    "清华大学深圳国际研究生院",
    "南方科技大学",
    "SUSTech",
    "深圳大学",
    "北京大学深圳研究生院",
    "PKUSZ",
    "深圳理工大学",
    "深圳技术大学",
    "SZTU",
    "哈尔滨工业大学（深圳）",
    "HIT Shenzhen",
    "香港中文大学（深圳）",
    "CUHK-Shenzhen",
    "中山大学（深圳）",
)


class SharedBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(SharedBaseModel):
    source_type: EvidenceSourceType
    source_url: OptionalNonEmptyStr = None
    source_file: OptionalNonEmptyStr = None
    fetched_at: datetime
    snippet: OptionalNonEmptyStr = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_source_reference(self) -> Evidence:
        if not self.source_url and not self.source_file:
            raise ValueError("source_url or source_file is required")
        return self


class ReleasedObject(SharedBaseModel):
    id: NonEmptyStr
    object_type: ObjectType
    display_name: NonEmptyStr
    core_facts: dict[str, Any]
    summary_fields: dict[str, Any]
    evidence: list[Evidence] = Field(min_length=1)
    last_updated: datetime
    quality_status: QualityStatus = "needs_review"


ProfessorPaperLinkStatus = Literal["verified", "candidate", "rejected"]


class ProfessorCompanyRole(SharedBaseModel):
    company_name: NonEmptyStr
    role: NonEmptyStr


class ProfessorPaperLinkRecord(SharedBaseModel):
    id: NonEmptyStr
    professor_id: NonEmptyStr
    paper_id: NonEmptyStr
    professor_name: NonEmptyStr
    paper_title: NonEmptyStr
    link_status: ProfessorPaperLinkStatus
    evidence_source: OptionalNonEmptyStr = None
    evidence_url: OptionalNonEmptyStr = None
    match_reason: NonEmptyStr
    verified_by: OptionalNonEmptyStr = None
    evidence: list[Evidence] = Field(min_length=1)
    last_updated: datetime
    quality_status: QualityStatus = "needs_review"

    @property
    def display_name(self) -> str:
        return f"{self.professor_name} -> {self.paper_title}"

    def to_released_object(self) -> ReleasedObject:
        return ReleasedObject(
            id=self.id,
            object_type="professor_paper_link",
            display_name=self.display_name,
            core_facts={
                "professor_id": self.professor_id,
                "paper_id": self.paper_id,
                "professor_name": self.professor_name,
                "paper_title": self.paper_title,
                "link_status": self.link_status,
                "evidence_source": self.evidence_source,
                "evidence_url": self.evidence_url,
                "verified_by": self.verified_by,
            },
            summary_fields={"match_reason": self.match_reason},
            evidence=self.evidence,
            last_updated=self.last_updated,
            quality_status=self.quality_status,
        )


class EducationExperience(SharedBaseModel):
    school: NonEmptyStr
    degree: OptionalNonEmptyStr = None
    field: OptionalNonEmptyStr = None
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    end_year: int | None = Field(default=None, ge=1900, le=2100)


class CompanyKeyPerson(SharedBaseModel):
    name: NonEmptyStr
    role: NonEmptyStr


class ProfessorRecord(SharedBaseModel):
    id: NonEmptyStr
    name: NonEmptyStr
    institution: NonEmptyStr
    department: OptionalNonEmptyStr = None
    title: OptionalNonEmptyStr = None
    email: OptionalNonEmptyStr = None
    homepage: OptionalNonEmptyStr = None
    office: OptionalNonEmptyStr = None
    research_directions: list[NonEmptyStr] = Field(default_factory=list)
    education_structured: list[EducationExperience] = Field(default_factory=list)
    work_experience: list[NonEmptyStr] = Field(default_factory=list)
    h_index: int | None = Field(default=None, ge=0)
    citation_count: int | None = Field(default=None, ge=0)
    paper_count: int | None = Field(default=None, ge=0)
    awards: list[NonEmptyStr] = Field(default_factory=list)
    academic_positions: list[NonEmptyStr] = Field(default_factory=list)
    projects: list[NonEmptyStr] = Field(default_factory=list)
    profile_summary: NonEmptyStr
    evaluation_summary: str = ""
    company_roles: list[ProfessorCompanyRole] = Field(default_factory=list)
    patent_ids: list[NonEmptyStr] = Field(default_factory=list)
    evidence: list[Evidence] = Field(min_length=1)
    last_updated: datetime
    quality_status: QualityStatus = "needs_review"

    @model_validator(mode="after")
    def validate_professor_baseline(self) -> ProfessorRecord:
        if not any(keyword in self.institution for keyword in SHENZHEN_INSTITUTION_KEYWORDS):
            raise ValueError("institution must be in the Shenzhen institution roster")
        if not any(item.source_type == "official_site" for item in self.evidence):
            raise ValueError("at least one evidence item must use source_type=official_site")
        return self

    @property
    def display_name(self) -> str:
        return self.name

    def to_released_object(self) -> ReleasedObject:
        return ReleasedObject(
            id=self.id,
            object_type="professor",
            display_name=self.display_name,
            core_facts={
                "name": self.name,
                "institution": self.institution,
                "department": self.department,
                "title": self.title,
                "email": self.email,
                "homepage": self.homepage,
                "office": self.office,
                "research_directions": self.research_directions,
                "education_structured": [
                    item.model_dump(mode="json") for item in self.education_structured
                ],
                "work_experience": self.work_experience,
                "h_index": self.h_index,
                "citation_count": self.citation_count,
                "paper_count": self.paper_count,
                "awards": self.awards,
                "academic_positions": self.academic_positions,
                "projects": self.projects,
                "company_roles": [
                    role.model_dump(mode="json") for role in self.company_roles
                ],
                "patent_ids": self.patent_ids,
            },
            summary_fields={
                "profile_summary": self.profile_summary,
                **({"evaluation_summary": self.evaluation_summary} if self.evaluation_summary else {}),
            },
            evidence=self.evidence,
            last_updated=self.last_updated,
            quality_status=self.quality_status,
        )


class CompanyRecord(SharedBaseModel):
    id: NonEmptyStr
    name: NonEmptyStr
    normalized_name: NonEmptyStr
    industry: NonEmptyStr
    website: OptionalNonEmptyStr = None
    key_personnel: list[CompanyKeyPerson] = Field(default_factory=list)
    profile_summary: NonEmptyStr
    evaluation_summary: NonEmptyStr
    technology_route_summary: NonEmptyStr
    evidence: list[Evidence] = Field(min_length=1)
    last_updated: datetime
    quality_status: QualityStatus = "needs_review"

    @property
    def display_name(self) -> str:
        return self.name

    def to_released_object(self) -> ReleasedObject:
        return ReleasedObject(
            id=self.id,
            object_type="company",
            display_name=self.display_name,
            core_facts={
                "name": self.name,
                "normalized_name": self.normalized_name,
                "industry": self.industry,
                "website": self.website,
                "key_personnel": [
                    person.model_dump(mode="json") for person in self.key_personnel
                ],
            },
            summary_fields={
                "profile_summary": self.profile_summary,
                "evaluation_summary": self.evaluation_summary,
                "technology_route_summary": self.technology_route_summary,
            },
            evidence=self.evidence,
            last_updated=self.last_updated,
            quality_status=self.quality_status,
        )


class PaperRecord(SharedBaseModel):
    id: NonEmptyStr
    title: NonEmptyStr
    title_zh: OptionalNonEmptyStr = None
    authors: list[NonEmptyStr] = Field(min_length=1)
    year: int
    venue: OptionalNonEmptyStr = None
    doi: OptionalNonEmptyStr = None
    arxiv_id: OptionalNonEmptyStr = None
    abstract: OptionalNonEmptyStr = None
    publication_date: OptionalNonEmptyStr = None
    keywords: list[NonEmptyStr] = Field(default_factory=list)
    citation_count: int | None = Field(default=None, ge=0)
    fields_of_study: list[NonEmptyStr] = Field(default_factory=list)
    tldr: OptionalNonEmptyStr = None
    license: OptionalNonEmptyStr = None
    funders: list[NonEmptyStr] = Field(default_factory=list)
    oa_status: OptionalNonEmptyStr = None
    reference_count: int | None = Field(default=None, ge=0)
    enrichment_sources: list[NonEmptyStr] = Field(default_factory=list)
    pdf_path: OptionalNonEmptyStr = None
    professor_ids: list[NonEmptyStr] = Field(default_factory=list)
    summary_zh: NonEmptyStr
    summary_text: NonEmptyStr
    evidence: list[Evidence] = Field(min_length=1)
    last_updated: datetime
    quality_status: QualityStatus = "needs_review"

    @property
    def display_name(self) -> str:
        return self.title

    def to_released_object(self) -> ReleasedObject:
        return ReleasedObject(
            id=self.id,
            object_type="paper",
            display_name=self.display_name,
            core_facts={
                "title": self.title,
                "title_zh": self.title_zh,
                "authors": self.authors,
                "year": self.year,
                "venue": self.venue,
                "doi": self.doi,
                "arxiv_id": self.arxiv_id,
                "abstract": self.abstract,
                "publication_date": self.publication_date,
                "keywords": self.keywords,
                "citation_count": self.citation_count,
                "fields_of_study": self.fields_of_study,
                "tldr": self.tldr,
                "license": self.license,
                "funders": self.funders,
                "oa_status": self.oa_status,
                "reference_count": self.reference_count,
                "enrichment_sources": self.enrichment_sources,
                "pdf_path": self.pdf_path,
                "professor_ids": self.professor_ids,
            },
            summary_fields={
                "summary_zh": self.summary_zh,
                "summary_text": self.summary_text,
            },
            evidence=self.evidence,
            last_updated=self.last_updated,
            quality_status=self.quality_status,
        )


class PatentRecord(SharedBaseModel):
    id: NonEmptyStr
    title: NonEmptyStr
    title_en: OptionalNonEmptyStr = None
    patent_number: OptionalNonEmptyStr = None
    applicants: list[NonEmptyStr] = Field(min_length=1)
    inventors: list[NonEmptyStr] = Field(default_factory=list)
    patent_type: NonEmptyStr
    filing_date: OptionalNonEmptyStr = None
    publication_date: OptionalNonEmptyStr = None
    grant_date: OptionalNonEmptyStr = None
    abstract: OptionalNonEmptyStr = None
    technology_effect: OptionalNonEmptyStr = None
    ipc_codes: list[NonEmptyStr] = Field(default_factory=list)
    company_ids: list[NonEmptyStr] = Field(default_factory=list)
    professor_ids: list[NonEmptyStr] = Field(default_factory=list)
    summary_text: NonEmptyStr
    evidence: list[Evidence] = Field(min_length=1)
    last_updated: datetime
    quality_status: QualityStatus = "needs_review"

    @model_validator(mode="after")
    def validate_patent_dates(self) -> PatentRecord:
        if not self.filing_date and not self.publication_date:
            raise ValueError("filing_date or publication_date is required")
        return self

    @property
    def display_name(self) -> str:
        return self.title

    def to_released_object(self) -> ReleasedObject:
        return ReleasedObject(
            id=self.id,
            object_type="patent",
            display_name=self.display_name,
            core_facts={
                "title": self.title,
                "title_en": self.title_en,
                "patent_number": self.patent_number,
                "applicants": self.applicants,
                "inventors": self.inventors,
                "patent_type": self.patent_type,
                "filing_date": self.filing_date,
                "publication_date": self.publication_date,
                "grant_date": self.grant_date,
                "abstract": self.abstract,
                "technology_effect": self.technology_effect,
                "ipc_codes": self.ipc_codes,
                "company_ids": self.company_ids,
                "professor_ids": self.professor_ids,
            },
            summary_fields={"summary_text": self.summary_text},
            evidence=self.evidence,
            last_updated=self.last_updated,
            quality_status=self.quality_status,
        )
