from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from uuid import UUID

from psycopg import Connection

from src.data_agents.normalization import build_stable_id

from .title_cleaner import clean_paper_title


_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PaperUpsertReport:
    paper_id: str
    is_new: bool


def upsert_paper(
    conn: Connection,
    *,
    title_clean: str,
    title_raw: str | None,
    doi: str | None,
    arxiv_id: str | None,
    openalex_id: str | None,
    semantic_scholar_id: str | None,
    year: int | None,
    venue: str | None,
    abstract_clean: str | None,
    authors_display: str | None,
    citation_count: int | None,
    canonical_source: str,
    run_id: UUID | str | None = None,
) -> PaperUpsertReport:
    """Upsert a canonical paper row keyed by a stable paper id."""

    normalized_title = clean_paper_title(title_clean)
    if not normalized_title:
        raise ValueError("title_clean must be non-empty")

    normalized_doi = _normalize_optional(doi)
    normalized_openalex = _normalize_optional(openalex_id)
    normalized_arxiv = _normalize_optional(arxiv_id)
    normalized_semantic_scholar = _normalize_optional(semantic_scholar_id)
    paper_id = _build_paper_id(
        title_clean=normalized_title,
        doi=normalized_doi,
        openalex_id=normalized_openalex,
        arxiv_id=normalized_arxiv,
        year=year,
    )
    now = datetime.now(timezone.utc)
    is_new = (
        conn.execute(
            "SELECT 1 FROM paper WHERE paper_id = %s",
            (paper_id,),
        ).fetchone()
        is None
    )

    conn.execute(
        """
        INSERT INTO paper (
            paper_id,
            title_clean,
            title_raw,
            doi,
            arxiv_id,
            openalex_id,
            semantic_scholar_id,
            year,
            venue,
            abstract_clean,
            authors_display,
            citation_count,
            canonical_source,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (paper_id) DO UPDATE
           SET title_clean          = EXCLUDED.title_clean,
               title_raw            = EXCLUDED.title_raw,
               doi                  = COALESCE(EXCLUDED.doi, paper.doi),
               arxiv_id             = COALESCE(EXCLUDED.arxiv_id, paper.arxiv_id),
               openalex_id          = COALESCE(EXCLUDED.openalex_id, paper.openalex_id),
               semantic_scholar_id  = COALESCE(EXCLUDED.semantic_scholar_id, paper.semantic_scholar_id),
               year                 = COALESCE(EXCLUDED.year, paper.year),
               venue                = COALESCE(EXCLUDED.venue, paper.venue),
               abstract_clean       = COALESCE(EXCLUDED.abstract_clean, paper.abstract_clean),
               authors_display      = COALESCE(EXCLUDED.authors_display, paper.authors_display),
               citation_count       = COALESCE(EXCLUDED.citation_count, paper.citation_count),
               canonical_source     = EXCLUDED.canonical_source,
               run_id               = COALESCE(EXCLUDED.run_id, paper.run_id),
               updated_at           = %s
        """,
        (
            paper_id,
            normalized_title,
            _normalize_optional(title_raw) or normalized_title,
            normalized_doi,
            normalized_arxiv,
            normalized_openalex,
            normalized_semantic_scholar,
            year,
            _normalize_optional(venue),
            _normalize_optional(abstract_clean),
            _normalize_optional(authors_display),
            citation_count,
            canonical_source,
            run_id,
            now,
        ),
    )
    return PaperUpsertReport(paper_id=paper_id, is_new=is_new)


def _build_paper_id(
    *,
    title_clean: str,
    doi: str | None,
    openalex_id: str | None,
    arxiv_id: str | None,
    year: int | None,
) -> str:
    if doi:
        return build_stable_id("paper", f"doi:{doi}")
    if openalex_id:
        return build_stable_id("paper", f"openalex:{openalex_id}")
    if arxiv_id:
        return build_stable_id("paper", f"arxiv:{arxiv_id}")
    normalized_title = _WHITESPACE_RE.sub("", title_clean).lower()
    return build_stable_id("paper", f"title:{normalized_title}|year:{year or 0}")


def _normalize_optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
