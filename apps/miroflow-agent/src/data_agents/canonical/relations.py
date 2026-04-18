"""Pydantic models for cross-domain relation tables (V005b).

Mirrors `alembic/versions/V005b_init_cross_domain_relations.py`.
See plan 005 §6.5.

`ProfessorPaperLink` lives in `paper.py` (co-located with paper/patent
because it directly references `paper`). The three relations here
(`ProfessorCompanyRole`, `ProfessorPatentLink`, `CompanyPatentLink`) cross
more domains and share the same three-state `LinkStatus` pattern.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .common import LinkStatus


ProfessorCompanyRoleType = Literal[
    "founder",
    "cofounder",
    "chief_scientist",
    "advisor",
    "board_member",
]

ProfessorCompanyEvidenceKind = Literal[
    "company_official_site",
    "professor_official_profile",
    "trusted_media",
    "xlsx_team_with_explicit_role",
    "gov_registry",
]

ProfessorPatentLinkRole = Literal["inventor", "applicant_represented_person"]

ProfessorPatentEvidenceKind = Literal[
    "patent_xlsx_inventor_match",
    "company_official_site",
    "personal_homepage",
]

CompanyPatentLinkRole = Literal["applicant", "assignee"]

CompanyPatentEvidenceKind = Literal[
    "patent_xlsx_applicant_exact_match",
    "patent_xlsx_applicant_normalized_match",
    "gov_registry",
    "company_official_site",
]

VerifiedBy = Literal[
    "rule_auto",
    "llm_auto",
    "rule_and_llm",
    "human_reviewed",
    "xlsx_anchored",
]


class ProfessorCompanyRole(BaseModel):
    """Strong professor↔company role (founder / cofounder / advisor / etc.).

    Plan §6.5: a general "employee" does NOT belong here — it stays in
    `company_team_member.resolved_professor_id`. Only founder-level roles
    earn a row in this table.
    """

    model_config = ConfigDict(extra="forbid")

    role_id: UUID | None = None
    professor_id: str
    company_id: str
    role_type: ProfessorCompanyRoleType
    link_status: LinkStatus = LinkStatus.candidate
    evidence_source_type: ProfessorCompanyEvidenceKind
    evidence_url: str
    evidence_page_id: UUID | None = None
    match_reason: str
    source_ref: str | None = None
    verified_by: VerifiedBy | None = None
    start_year: int | None = None
    end_year: int | None = None
    is_current: bool | None = None
    verified_at: datetime | None = None
    rejected_at: datetime | None = None
    rejected_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProfessorPatentLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: UUID | None = None
    professor_id: str
    patent_id: str
    link_role: ProfessorPatentLinkRole
    link_status: LinkStatus = LinkStatus.candidate
    evidence_source_type: ProfessorPatentEvidenceKind
    match_reason: str | None = None
    verified_by: VerifiedBy | None = None
    verified_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CompanyPatentLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: UUID | None = None
    company_id: str
    patent_id: str
    link_role: CompanyPatentLinkRole
    link_status: LinkStatus = LinkStatus.candidate
    evidence_source_type: CompanyPatentEvidenceKind
    match_reason: str | None = None
    verified_by: VerifiedBy | None = None
    verified_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = [
    "CompanyPatentLink",
    "CompanyPatentEvidenceKind",
    "CompanyPatentLinkRole",
    "ProfessorCompanyRole",
    "ProfessorCompanyEvidenceKind",
    "ProfessorCompanyRoleType",
    "ProfessorPatentEvidenceKind",
    "ProfessorPatentLink",
    "ProfessorPatentLinkRole",
    "VerifiedBy",
]
