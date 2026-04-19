"""Pydantic models for the Paper and Patent domains (V004) plus the
professor_paper_link relation (V005a).

Mirrors `alembic/versions/V004_init_paper_patent_domain.py` and
`V005a_init_professor_paper_link.py`. See plan 005 §6.4 and §6.5.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .common import LinkStatus, PaperAuthorMatch


class Paper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str  # PAPER-{12hex}
    title_clean: str | None = None
    title_raw: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    semantic_scholar_id: str | None = None
    year: int | None = None
    venue: str | None = None
    abstract_clean: str | None = None
    authors_display: str | None = None
    authors_raw: list[dict[str, Any]] | dict[str, Any] | None = None
    citation_count: int | None = None
    canonical_source: (
        str  # 'openalex' | 'semantic_scholar' | 'crossref' | 'official_page' | 'manual'
    )
    first_seen_at: datetime | None = None
    updated_at: datetime | None = None
    run_id: UUID | None = None  # Round 7.16 — pipeline_run that produced this row


class Patent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patent_id: str  # PAT-{12hex}
    patent_number: str
    title_clean: str
    title_raw: str | None = None
    title_en: str | None = None
    applicants_raw: str | None = None
    applicants_parsed: list[dict[str, Any]] | None = None
    inventors_raw: str | None = None
    inventors_parsed: list[dict[str, Any]] | None = None
    filing_date: date | None = None
    publication_date: date | None = None
    grant_date: date | None = None
    patent_type: str | None = None  # '发明' | '实用新型' | '外观' | 'PCT' | '其他'
    status: str | None = None
    abstract_clean: str | None = None
    technology_effect: str | None = None
    ipc_codes: list[str] = Field(default_factory=list)
    first_seen_at: datetime | None = None
    updated_at: datetime | None = None
    run_id: UUID | None = None  # Round 7.16 — pipeline_run that produced this row


class ProfessorPaperLink(BaseModel):
    """Verified/candidate/rejected link between a professor and a paper.

    Plan §6.5 — this REPLACES `PaperRecord.professor_ids` as the authoritative
    source for "which papers belong to which professor". Promotion rules live
    in `data_agents.quality.threshold_config.PROFESSOR_PAPER_LINK_PROMOTION`.
    """

    model_config = ConfigDict(extra="forbid")

    link_id: UUID | None = None
    professor_id: str
    paper_id: str
    link_status: LinkStatus = LinkStatus.candidate
    evidence_source_type: PaperAuthorMatch
    evidence_page_id: UUID | None = None
    evidence_api_source: str | None = None
    match_reason: str
    author_name_match_score: Decimal
    topic_consistency_score: Decimal | None = None
    institution_consistency_score: Decimal | None = None
    is_officially_listed: bool = False
    verified_by: str | None = None
    verified_at: datetime | None = None
    rejected_at: datetime | None = None
    rejected_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    run_id: UUID | None = None  # Round 7.16 — pipeline_run that produced this row


__all__ = [
    "Paper",
    "Patent",
    "ProfessorPaperLink",
]
