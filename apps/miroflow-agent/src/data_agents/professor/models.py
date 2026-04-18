from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from .cross_domain import CompanyLink, PaperLink, PatentLink


@dataclass(frozen=True, slots=True)
class ProfessorRosterSeed:
    institution: str | None
    department: str | None
    roster_url: str
    label: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveredProfessorSeed:
    name: str
    institution: str
    department: str | None
    profile_url: str
    source_url: str


@dataclass(frozen=True, slots=True)
class ExtractedProfessorProfile:
    name: str | None
    institution: str | None
    department: str | None
    title: str | None
    email: str | None
    homepage_url: str | None
    profile_url: str
    office: str | None
    research_directions: tuple[str, ...]
    source_urls: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "research_directions", tuple(self.research_directions))
        object.__setattr__(self, "source_urls", tuple(self.source_urls))


@dataclass(frozen=True, slots=True)
class MergedProfessorProfileRecord:
    name: str | None
    institution: str | None
    department: str | None
    title: str | None
    email: str | None
    office: str | None
    homepage: str | None
    profile_url: str
    source_urls: tuple[str, ...]
    evidence: tuple[str, ...]
    research_directions: tuple[str, ...]
    extraction_status: str
    skip_reason: str | None
    error: str | None
    roster_source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_urls", tuple(self.source_urls))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "research_directions", tuple(self.research_directions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "institution": self.institution,
            "department": self.department,
            "title": self.title,
            "email": self.email,
            "office": self.office,
            "homepage": self.homepage,
            "profile_url": self.profile_url,
            "source_urls": list(self.source_urls),
            "evidence": list(self.evidence),
            "research_directions": list(self.research_directions),
            "extraction_status": self.extraction_status,
            "skip_reason": self.skip_reason,
            "error": self.error,
            "roster_source": self.roster_source,
        }


class EducationEntry(BaseModel):
    """Structured education history entry."""

    school: str
    degree: str | None = None
    field: str | None = None
    start_year: int | None = None
    end_year: int | None = None


class WorkEntry(BaseModel):
    """Structured work experience entry."""

    organization: str
    role: str | None = None
    start_year: int | None = None
    end_year: int | None = None


class OfficialAnchorProfile(BaseModel):
    """Official anchor facts extracted only from the main official teacher page."""

    source_url: str
    title: str | None = None
    email: str | None = None
    bio_text: str = ""
    research_topics: list[str] = []
    education_lines: list[str] = []
    award_lines: list[str] = []
    work_role_lines: list[str] = []
    english_name_candidates: list[str] = []
    topic_tokens: list[str] = []
    sparse_anchor: bool = True


class EnrichedProfessorProfile(BaseModel):
    """Stage 2 output — fully enriched professor profile.

    Superset of MergedProfessorProfileRecord with paper-driven research
    directions, academic metrics, cross-domain links, and LLM summaries.
    """

    name: str
    name_en: str | None = None
    institution: str
    department: str | None = None
    title: str | None = None
    email: str | None = None
    homepage: str | None = None
    office: str | None = None
    research_directions: list[str] = []
    research_directions_source: str = ""  # "paper_driven" | "official_only" | "merged"
    education_structured: list[EducationEntry] = []
    work_experience: list[WorkEntry] = []
    h_index: int | None = None
    citation_count: int | None = None
    paper_count: int | None = None
    top_papers: list[PaperLink] = []
    official_paper_count: int | None = None
    official_top_papers: list[PaperLink] = []
    publication_evidence_urls: list[str] = []
    scholarly_profile_urls: list[str] = []
    cv_urls: list[str] = []
    official_anchor_profile: OfficialAnchorProfile | None = None
    awards: list[str] = []
    academic_positions: list[str] = []
    projects: list[str] = []
    company_roles: list[CompanyLink] = []
    patent_ids: list[PatentLink] = []
    profile_summary: str = ""
    evaluation_summary: str = ""  # V3: no longer generated, kept for backward compat
    enrichment_source: str = "regex_only"  # "regex_only" | "paper_enriched" | "agent_local" | "agent_online"
    evidence_urls: list[str] = []
    field_provenance: dict[str, str] = {}
    profile_url: str
    roster_source: str
    extraction_status: str
