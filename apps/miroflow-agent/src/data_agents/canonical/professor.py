"""Pydantic models for the Professor domain (V003).

Mirrors `alembic/versions/V003_init_professor_domain.py`. See plan 005 §6.3.
Kept separate from the legacy `professor.models` module — legacy keeps
driving the v2 pipeline during the double-write window.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .common import IdentityStatus


class Professor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    professor_id: str  # PROF-{12hex}
    canonical_name: str
    canonical_name_en: str | None = None
    canonical_name_zh: str | None = None  # Round 7.19a — explicit Chinese anchor
    aliases: list[str] = Field(default_factory=list)
    discipline_family: str
    primary_official_profile_page_id: UUID | None = None
    identity_status: IdentityStatus = IdentityStatus.resolved
    merged_into_id: str | None = None
    first_seen_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    run_id: UUID | None = None  # Round 7.16 — pipeline_run that produced this row
    # Round 9.1b / 7.19c — optional bio fields (columns land via future migration)
    profile_summary: str | None = None
    profile_raw_text: str | None = None


class ProfessorAffiliation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affiliation_id: UUID | None = None
    professor_id: str
    institution: str
    department: str | None = None
    title: str | None = None
    employment_type: str | None = None
    is_primary: bool = False
    is_current: bool = True
    start_year: int | None = None
    end_year: int | None = None
    source_page_id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None
    run_id: UUID | None = None  # Round 7.16 — pipeline_run that produced this row


class ProfessorFact(BaseModel):
    """One provenance-linked fact per row, for a professor.

    `fact_type` ∈ {research_topic, education, work_experience, award,
    academic_position, contact, homepage, external_profile,
    publication_count_reported}
    """

    model_config = ConfigDict(extra="forbid")

    fact_id: UUID | None = None
    professor_id: str
    fact_type: str
    value_raw: str
    value_normalized: str | None = None
    value_code: str | None = None  # FK taxonomy_vocabulary(code)
    source_page_id: UUID
    evidence_span: str
    confidence: Decimal
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    run_id: UUID | None = None  # Round 7.16 — pipeline_run that produced this row


__all__ = [
    "Professor",
    "ProfessorAffiliation",
    "ProfessorFact",
]
