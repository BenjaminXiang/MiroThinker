from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from uuid import UUID

from psycopg import Connection

from src.data_agents.normalization import build_stable_id
from src.data_agents.quality.gating_contract import (
    normalize_quality_status as normalize_shared_quality_status,
)
from src.data_agents.storage.postgres.pipeline_run import require_real_run_id

from .quality_promotion import (
    NEEDS_REVIEW,
    READY,
    REJECTED,
    PaperEnrichmentSignals,
    evaluate_paper_promotion,
)
from .text_sanitizer import sanitize_optional_text_for_postgres
from .title_cleaner import clean_reference_like_paper_title


_WHITESPACE_RE = re.compile(r"\s+")
_CONFIRMED_TITLE_RESOLUTION_SOURCES = {"openalex", "arxiv", "doi_lookup"}


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
    run_id: UUID | str,
    title_resolution_source: str | None = None,
    quality_status: str | None = None,
    summary_zh: str | None = None,
) -> PaperUpsertReport:
    """Upsert a canonical paper row keyed by a stable paper id."""
    run_id = require_real_run_id(run_id, writer_name="upsert_paper")

    normalized_title = clean_reference_like_paper_title(title_clean)
    if not normalized_title:
        raise ValueError("title_clean must be non-empty")

    normalized_doi = _normalize_optional(doi)
    normalized_openalex = _normalize_optional(openalex_id)
    normalized_arxiv = _normalize_optional(arxiv_id)
    normalized_semantic_scholar = _normalize_optional(semantic_scholar_id)
    normalized_venue = _normalize_optional(venue)
    normalized_abstract = _normalize_optional(abstract_clean)
    normalized_authors = _normalize_optional(authors_display)
    normalized_summary_zh = _normalize_optional(summary_zh)
    identity_status = _identity_status_for_title_resolution_source(
        title_resolution_source or canonical_source
    )
    effective_quality_status = _normalize_quality_status(quality_status)
    paper_id = _build_paper_id(
        title_clean=normalized_title,
        doi=normalized_doi,
        openalex_id=normalized_openalex,
        arxiv_id=normalized_arxiv,
        year=year,
    )
    now = datetime.now(timezone.utc)
    existing_row = conn.execute(
        "SELECT quality_status FROM paper WHERE paper_id = %s",
        (paper_id,),
    ).fetchone()
    is_new = existing_row is None
    current_quality_status = _current_quality_status(
        existing_row,
        incoming_status=effective_quality_status,
    )
    promoted_quality_status = evaluate_paper_promotion(
        current_status=current_quality_status,
        signals=PaperEnrichmentSignals(
            has_title=bool(normalized_title),
            has_year=year is not None,
            has_venue=bool(normalized_venue),
            has_authors=bool(normalized_authors),
            has_abstract=bool(normalized_abstract),
            has_summary_zh=bool(normalized_summary_zh),
        ),
    ).next_status

    if current_quality_status == READY:
        promoted_quality_status = READY
    elif current_quality_status == REJECTED:
        promoted_quality_status = REJECTED

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
            summary_zh,
            authors_display,
            citation_count,
            canonical_source,
            identity_status,
            quality_status,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
               summary_zh           = COALESCE(EXCLUDED.summary_zh, paper.summary_zh),
               authors_display      = COALESCE(EXCLUDED.authors_display, paper.authors_display),
               citation_count       = COALESCE(EXCLUDED.citation_count, paper.citation_count),
               canonical_source     = EXCLUDED.canonical_source,
               identity_status      = EXCLUDED.identity_status,
               quality_status       = EXCLUDED.quality_status,
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
            normalized_venue,
            normalized_abstract,
            normalized_summary_zh,
            normalized_authors,
            citation_count,
            canonical_source,
            identity_status,
            promoted_quality_status,
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


def _identity_status_for_title_resolution_source(source: str | None) -> str:
    normalized_source = _normalize_optional(source)
    if normalized_source in _CONFIRMED_TITLE_RESOLUTION_SOURCES:
        return "confirmed"
    return "unverified"


def _normalize_optional(value: object) -> str | None:
    if value is None:
        return None
    return sanitize_optional_text_for_postgres(str(value))


def _normalize_quality_status(value: str | None) -> str:
    return normalize_shared_quality_status(_normalize_optional(value) or NEEDS_REVIEW)


def _current_quality_status(row: object | None, *, incoming_status: str) -> str:
    if row is None:
        return incoming_status
    if isinstance(row, dict):
        existing_status = row.get("quality_status")
    else:
        existing_status = row[0]  # type: ignore[index]
    normalized_existing = _normalize_quality_status(
        None if existing_status is None else str(existing_status)
    )
    if normalized_existing in {REJECTED, READY, NEEDS_REVIEW}:
        return normalized_existing
    if incoming_status == REJECTED:
        return REJECTED
    return normalized_existing
