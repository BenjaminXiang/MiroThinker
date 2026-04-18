"""init cross-domain relations: professor-company, professor-patent, company-patent

Revision ID: V005b
Revises: V005a
Create Date: 2026-04-18

Creates the remaining cross-domain relation tables per plan
docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
§6.5.

Explicitly included in this round:
- professor_company_role
- professor_patent_link
- company_patent_link
- deferred FK on company_team_member.resolved_professor_id -> professor.professor_id
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V005b"
down_revision: Union[str, None] = "V005a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- enum value lists (kept in Python so test fixtures can import them) ---
RELATION_LINK_STATUSES = ["verified", "candidate", "rejected"]

RELATION_VERIFIED_BY = [
    "rule_auto",
    "llm_auto",
    "rule_and_llm",
    "human_reviewed",
    "xlsx_anchored",
]

PROFESSOR_COMPANY_ROLE_TYPES = [
    "founder",
    "cofounder",
    "chief_scientist",
    "advisor",
    "board_member",
]

PROFESSOR_COMPANY_EVIDENCE_SOURCE_TYPES = [
    "company_official_site",
    "professor_official_profile",
    "trusted_media",
    "xlsx_team_with_explicit_role",
    "gov_registry",
]

PROFESSOR_PATENT_LINK_ROLES = ["inventor", "applicant_represented_person"]

PROFESSOR_PATENT_EVIDENCE_SOURCE_TYPES = [
    "patent_xlsx_inventor_match",
    "company_official_site",
    "personal_homepage",
]

COMPANY_PATENT_LINK_ROLES = ["applicant", "assignee"]

COMPANY_PATENT_EVIDENCE_SOURCE_TYPES = [
    "patent_xlsx_applicant_exact_match",
    "patent_xlsx_applicant_normalized_match",
    "gov_registry",
    "company_official_site",
]


def _check_enum(column: str, values: list[str]) -> str:
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    # ------------------------- professor_company_role -------------------------
    op.create_table(
        "professor_company_role",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("professor_id", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("role_type", sa.Text(), nullable=False),
        sa.Column(
            "link_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'candidate'"),
        ),
        sa.Column("evidence_source_type", sa.Text(), nullable=False),
        sa.Column("evidence_url", sa.Text(), nullable=False),
        sa.Column("evidence_page_id", postgresql.UUID(as_uuid=True)),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text()),
        sa.Column("verified_by", sa.Text()),
        sa.Column("start_year", sa.Integer()),
        sa.Column("end_year", sa.Integer()),
        sa.Column("is_current", sa.Boolean()),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("rejected_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("rejected_reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "professor_id",
            "company_id",
            "role_type",
            name="uq_professor_company_role_professor_company_role",
        ),
        sa.CheckConstraint(
            _check_enum("role_type", PROFESSOR_COMPANY_ROLE_TYPES),
            name="ck_professor_company_role_role_type",
        ),
        sa.CheckConstraint(
            _check_enum("link_status", RELATION_LINK_STATUSES),
            name="ck_professor_company_role_link_status",
        ),
        sa.CheckConstraint(
            _check_enum(
                "evidence_source_type", PROFESSOR_COMPANY_EVIDENCE_SOURCE_TYPES
            ),
            name="ck_professor_company_role_evidence_source_type",
        ),
        sa.CheckConstraint(
            "verified_by IS NULL OR "
            + _check_enum("verified_by", RELATION_VERIFIED_BY),
            name="ck_professor_company_role_verified_by",
        ),
    )
    op.create_foreign_key(
        "fk_professor_company_role_professor",
        "professor_company_role",
        "professor",
        ["professor_id"],
        ["professor_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_professor_company_role_company",
        "professor_company_role",
        "company",
        ["company_id"],
        ["company_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_professor_company_role_evidence_page",
        "professor_company_role",
        "source_page",
        ["evidence_page_id"],
        ["page_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_professor_company_role_professor_status",
        "professor_company_role",
        ["professor_id", "link_status"],
    )
    op.create_index(
        "ix_professor_company_role_company_status",
        "professor_company_role",
        ["company_id", "link_status"],
    )
    op.create_index(
        "ix_professor_company_role_candidate_only",
        "professor_company_role",
        ["link_status"],
        unique=False,
        postgresql_where=sa.text("link_status = 'candidate'"),
    )

    # -------------------------- professor_patent_link -------------------------
    op.create_table(
        "professor_patent_link",
        sa.Column(
            "link_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("professor_id", sa.Text(), nullable=False),
        sa.Column("patent_id", sa.Text(), nullable=False),
        sa.Column("link_role", sa.Text(), nullable=False),
        sa.Column(
            "link_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'candidate'"),
        ),
        sa.Column("evidence_source_type", sa.Text(), nullable=False),
        sa.Column("match_reason", sa.Text()),
        sa.Column("verified_by", sa.Text()),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "professor_id",
            "patent_id",
            "link_role",
            name="uq_professor_patent_link_professor_patent_role",
        ),
        sa.CheckConstraint(
            _check_enum("link_role", PROFESSOR_PATENT_LINK_ROLES),
            name="ck_professor_patent_link_link_role",
        ),
        sa.CheckConstraint(
            _check_enum("link_status", RELATION_LINK_STATUSES),
            name="ck_professor_patent_link_link_status",
        ),
        sa.CheckConstraint(
            _check_enum("evidence_source_type", PROFESSOR_PATENT_EVIDENCE_SOURCE_TYPES),
            name="ck_professor_patent_link_evidence_source_type",
        ),
        sa.CheckConstraint(
            "verified_by IS NULL OR "
            + _check_enum("verified_by", RELATION_VERIFIED_BY),
            name="ck_professor_patent_link_verified_by",
        ),
    )
    op.create_foreign_key(
        "fk_professor_patent_link_professor",
        "professor_patent_link",
        "professor",
        ["professor_id"],
        ["professor_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_professor_patent_link_patent",
        "professor_patent_link",
        "patent",
        ["patent_id"],
        ["patent_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_professor_patent_link_professor_status",
        "professor_patent_link",
        ["professor_id", "link_status"],
    )
    op.create_index(
        "ix_professor_patent_link_patent_status",
        "professor_patent_link",
        ["patent_id", "link_status"],
    )

    # --------------------------- company_patent_link --------------------------
    op.create_table(
        "company_patent_link",
        sa.Column(
            "link_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("patent_id", sa.Text(), nullable=False),
        sa.Column("link_role", sa.Text(), nullable=False),
        sa.Column(
            "link_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'candidate'"),
        ),
        sa.Column("evidence_source_type", sa.Text(), nullable=False),
        sa.Column("match_reason", sa.Text()),
        sa.Column("verified_by", sa.Text()),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "company_id",
            "patent_id",
            "link_role",
            name="uq_company_patent_link_company_patent_role",
        ),
        sa.CheckConstraint(
            _check_enum("link_role", COMPANY_PATENT_LINK_ROLES),
            name="ck_company_patent_link_link_role",
        ),
        sa.CheckConstraint(
            _check_enum("link_status", RELATION_LINK_STATUSES),
            name="ck_company_patent_link_link_status",
        ),
        sa.CheckConstraint(
            _check_enum("evidence_source_type", COMPANY_PATENT_EVIDENCE_SOURCE_TYPES),
            name="ck_company_patent_link_evidence_source_type",
        ),
        sa.CheckConstraint(
            "verified_by IS NULL OR "
            + _check_enum("verified_by", RELATION_VERIFIED_BY),
            name="ck_company_patent_link_verified_by",
        ),
    )
    op.create_foreign_key(
        "fk_company_patent_link_company",
        "company_patent_link",
        "company",
        ["company_id"],
        ["company_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_company_patent_link_patent",
        "company_patent_link",
        "patent",
        ["patent_id"],
        ["patent_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_company_patent_link_company_status",
        "company_patent_link",
        ["company_id", "link_status"],
    )
    op.create_index(
        "ix_company_patent_link_patent_status",
        "company_patent_link",
        ["patent_id", "link_status"],
    )

    # ---------------------- deferred company_team_member FK -------------------
    op.create_foreign_key(
        "fk_company_team_member_resolved_professor",
        "company_team_member",
        "professor",
        ["resolved_professor_id"],
        ["professor_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop the deferred FK first, then relation tables in reverse order.
    op.drop_constraint(
        "fk_company_team_member_resolved_professor",
        "company_team_member",
        type_="foreignkey",
    )
    op.drop_table("company_patent_link")
    op.drop_table("professor_patent_link")
    op.drop_table("professor_company_role")
