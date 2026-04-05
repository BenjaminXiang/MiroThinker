from __future__ import annotations

from dataclasses import dataclass


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
