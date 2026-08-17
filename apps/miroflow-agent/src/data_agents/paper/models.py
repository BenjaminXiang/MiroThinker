from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PaperAuthor:
    name: str
    orcid: str | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class IdentifierConflict:
    identifier_type: str
    canonical_value: str
    incoming_value: str
    incoming_source: str


@dataclass(frozen=True, slots=True)
class PaperMetadataEnrichment:
    abstract: str | None = None
    venue: str | None = None
    publication_date: str | None = None
    citation_count: int | None = None
    authors: tuple[PaperAuthor, ...] = ()
    doi: str | None = None
    arxiv_id: str | None = None
    fields_of_study: tuple[str, ...] = ()
    tldr: str | None = None
    license: str | None = None
    funders: tuple[str, ...] = ()
    oa_status: str | None = None
    reference_count: int | None = None
    source_url: str | None = None
    enrichment_sources: tuple[str, ...] = ()
    identifier_conflicts: tuple[IdentifierConflict, ...] = ()


@dataclass(frozen=True, slots=True)
class DiscoveredPaper:
    paper_id: str
    title: str
    year: int
    publication_date: str | None
    venue: str | None
    doi: str | None
    arxiv_id: str | None
    abstract: str | None
    authors: tuple[str, ...]
    professor_ids: tuple[str, ...]
    citation_count: int | None
    source_url: str
    fields_of_study: tuple[str, ...] = ()
    tldr: str | None = None
    license: str | None = None
    funders: tuple[str, ...] = ()
    oa_status: str | None = None
    reference_count: int | None = None
    enrichment_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthorPaperMetrics:
    professor_id: str
    author_id: str
    h_index: int | None
    citation_count: int | None


@dataclass(frozen=True, slots=True)
class ProfessorPaperDiscoveryResult:
    professor_id: str
    professor_name: str
    institution: str
    author_id: str | None
    h_index: int | None
    citation_count: int | None
    papers: list[DiscoveredPaper]
    paper_count: int | None = None
    source: str | None = None
    school_matched: bool = False
    fallback_used: bool = False
    name_disambiguation_conflict: bool = False
    candidate_count: int = 0
    query_name: str | None = None
