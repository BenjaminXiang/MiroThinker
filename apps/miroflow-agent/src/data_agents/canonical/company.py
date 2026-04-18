"""Pydantic models for the Company domain (V002).

Mirrors the schema that `V002_init_company_domain.py` will create.
See plan 005 §6.2. Field names and nullability match the DDL contract so
that `Company(**row)` works directly against a `SELECT * FROM company` row.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .common import IdentityStatus


# ============================================================================
# company (core identity)
# ============================================================================


class Company(BaseModel):
    """Canonical company identity. Most columns are populated by the
    canonical_import pipeline; `aliases` grows as we see more names."""

    model_config = ConfigDict(extra="forbid")

    company_id: str  # COMP-{12hex}
    unified_credit_code: str | None = None
    canonical_name: str
    registered_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    website: str | None = None
    website_host: str | None = Field(
        default=None, description="DB GENERATED from website; do not set manually"
    )
    hq_province: str | None = None
    hq_city: str | None = None
    hq_district: str | None = None
    is_shenzhen: bool = False
    country: str = "国内"
    identity_status: IdentityStatus = IdentityStatus.resolved
    merged_into_id: str | None = None
    first_seen_batch_id: UUID | None = None
    first_seen_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ============================================================================
# company_snapshot — 42 xlsx columns + metadata
# ============================================================================


class CompanySnapshot(BaseModel):
    """Append-only snapshot of a company from a single xlsx import or crawl.

    Field grouping matches xlsx column order. `raw_row_jsonb` preserves the
    original row dict verbatim for future re-cleaning.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID | None = None
    company_id: str
    import_batch_id: UUID
    snapshot_kind: str  # 'xlsx_import' | 'website_crawl'
    source_row_number: int | None = None

    # project / industry (xlsx cols 1-4, 15)
    project_name: str | None = None
    industry: str | None = None
    sub_industry: str | None = None
    business: str | None = None
    region: str | None = None
    description: str | None = None

    # visual / status (xlsx cols 16-19, 14)
    logo_url: str | None = None
    star_rating: int | None = None
    status_raw: str | None = None
    remarks: str | None = None
    is_high_tech: bool | None = None

    # company core (xlsx cols 20-29)
    company_name_xlsx: str
    country_xlsx: str | None = None
    established_date: date | None = None
    years_established: int | None = None
    website_xlsx: str | None = None
    legal_representative: str | None = None  # PII
    registered_address: str | None = None
    registered_capital: str | None = None
    contact_phone: str | None = None  # PII
    contact_email: str | None = None  # PII

    # reported statistics (xlsx cols 30-41)
    reported_insured_count: int | None = None
    reported_shareholder_count: int | None = None
    reported_investment_count: int | None = None
    reported_patent_count: int | None = None
    reported_trademark_count: int | None = None
    reported_copyright_count: int | None = None
    reported_recruitment_count: int | None = None
    reported_news_count: int | None = None
    reported_institution_count: int | None = None
    reported_funding_round_count: int | None = None
    reported_total_funding_raw: str | None = None
    reported_valuation_raw: str | None = None

    # latest funding (xlsx cols 6-12)
    latest_funding_round: str | None = None
    latest_funding_time_raw: str | None = None
    latest_funding_time: date | None = None
    latest_funding_amount_raw: str | None = None
    latest_funding_cny_wan: Decimal | None = None
    latest_funding_ratio: str | None = None
    latest_investors_raw: str | None = None
    latest_fa_info: str | None = None

    # raw team text (xlsx col 25) — team_parser consumes this
    team_raw: str | None = None

    snapshot_created_at: datetime | None = None
    raw_row_jsonb: dict[str, Any]


# ============================================================================
# company_team_member
# ============================================================================


class CompanyTeamMember(BaseModel):
    """Parsed team entry from `company_snapshot.team_raw`.

    `resolved_professor_id` is populated later by `team_resolver` (Phase 4),
    not at import time.
    """

    model_config = ConfigDict(extra="forbid")

    member_id: UUID | None = None
    company_id: str
    snapshot_id: UUID
    member_order: int
    raw_name: str
    raw_role: str | None = None
    raw_intro: str | None = None
    normalized_name: str | None = None
    resolution_status: str = "unresolved"
    resolved_professor_id: str | None = None
    resolution_confidence: Decimal | None = None
    resolution_reason: str | None = None
    resolution_evidence: dict[str, Any] | None = None
    resolved_at: datetime | None = None
    created_at: datetime | None = None


# ============================================================================
# company_fact
# ============================================================================


class CompanyFact(BaseModel):
    """Structured, taxonomy-coded fact about a company."""

    model_config = ConfigDict(extra="forbid")

    fact_id: UUID | None = None
    company_id: str
    fact_type: str
    value_raw: str | None = None
    value_code: str | None = None  # FK taxonomy_vocabulary(code)
    status: str = "active"
    source_kind: str
    source_ref: str
    confidence: Decimal
    evidence_span: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ============================================================================
# company_news_item
# ============================================================================


class CompanyNewsItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_id: UUID | None = None
    company_id: str
    source_page_id: UUID | None = None
    source_url: str
    source_domain: str
    source_domain_tier: str  # 'official' | 'trusted' | 'unknown'
    published_at: datetime | None = None
    fetched_at: datetime
    title: str
    summary_clean: str | None = None
    content_clean_path: str | None = None
    is_company_confirmed: bool = False
    refresh_run_id: UUID | None = None
    confidence: Decimal
    created_at: datetime | None = None


# ============================================================================
# company_signal_event
# ============================================================================


class CompanySignalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID | None = None
    company_id: str
    primary_news_id: UUID | None = None
    event_type: str
    event_date: date
    event_subject_normalized: dict[str, Any]
    event_summary: str
    confidence: Decimal
    corroborating_news_ids: list[UUID] = Field(default_factory=list)
    dedup_key: str
    status: str = "active"
    deduped_into_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = [
    "Company",
    "CompanyFact",
    "CompanyNewsItem",
    "CompanySignalEvent",
    "CompanySnapshot",
    "CompanyTeamMember",
]
