# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Cross-domain link models for professor → paper/company/patent associations."""
from __future__ import annotations

from pydantic import BaseModel


class PaperLink(BaseModel):
    """Professor record's embedded paper reference (compact, for professor profile)."""

    paper_id: str | None = None  # PAPER-xxx, backfilled after paper domain publishes
    title: str
    year: int | None = None
    venue: str | None = None
    citation_count: int | None = None
    doi: str | None = None
    source: str  # "semantic_scholar" | "dblp" | "arxiv" | "web_scrape"


class CompanyLink(BaseModel):
    """Professor → company association."""

    company_id: str | None = None  # COMP-xxx, backfilled after company domain publishes
    company_name: str
    role: str  # "联合创始人" | "首席科学家" | "董事" | ...
    evidence_url: str | None = None
    source: str  # "web_scrape" | "web_search" | "company_domain"


class PatentLink(BaseModel):
    """Professor → patent association."""

    patent_id: str | None = None  # PAT-xxx, backfilled after patent domain publishes
    patent_title: str
    patent_number: str | None = None
    role: str = "发明人"
    source: str  # "web_scrape" | "web_search" | "patent_domain"


class PaperStagingRecord(BaseModel):
    """Paper collected during professor enrichment, staged for paper domain consumption.

    Implements the 一鱼两吃 (one-fish-two-eats) principle: papers collected for
    professor profiling simultaneously feed the paper domain pipeline.
    """

    title: str
    authors: list[str]
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    doi: str | None = None
    citation_count: int | None = None
    keywords: list[str] = []
    source_url: str
    source: str  # "semantic_scholar" | "dblp" | "arxiv"
    anchoring_professor_id: str
    anchoring_professor_name: str
    anchoring_institution: str
