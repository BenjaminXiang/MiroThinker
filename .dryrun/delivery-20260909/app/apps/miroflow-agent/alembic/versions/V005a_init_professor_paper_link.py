"""init professor-paper link: verified and candidate authorship links

Revision ID: V005a
Revises: V004
Create Date: 2026-04-18

Creates the professor-paper relation table per plan
docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
§6.5.

Explicitly excluded in this round:
- professor_company_role, professor_patent_link, and company_patent_link: deferred to V005b
- promotion logic / runtime writer behavior: handled later
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V005a"
down_revision: Union[str, None] = "V004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- enum value lists (kept in Python so test fixtures can import them) ---
PROFESSOR_PAPER_LINK_STATUSES = ["verified", "candidate", "rejected"]

PROFESSOR_PAPER_EVIDENCE_SOURCE_TYPES = [
    "official_publication_page",
    "personal_homepage",
    "cv_pdf",
    "official_external_profile",
    "academic_api_with_affiliation_match",
]

PROFESSOR_PAPER_VERIFIED_BY = [
    "rule_auto",
    "llm_auto",
    "rule_and_llm",
    "human_reviewed",
    "xlsx_anchored",
]


def _check_enum(column: str, values: list[str]) -> str:
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    # ------------------------ professor_paper_link ------------------------
    op.create_table(
        "professor_paper_link",
        sa.Column(
            "link_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("professor_id", sa.Text(), nullable=False),
        sa.Column("paper_id", sa.Text(), nullable=False),
        sa.Column(
            "link_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'candidate'"),
        ),
        sa.Column("evidence_source_type", sa.Text(), nullable=False),
        sa.Column("evidence_page_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_api_source", sa.Text()),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("author_name_match_score", sa.Numeric(3, 2), nullable=False),
        sa.Column("topic_consistency_score", sa.Numeric(3, 2)),
        sa.Column("institution_consistency_score", sa.Numeric(3, 2)),
        sa.Column(
            "is_officially_listed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("verified_by", sa.Text()),
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
            "paper_id",
            name="uq_professor_paper_link_professor_paper",
        ),
        sa.CheckConstraint(
            _check_enum("link_status", PROFESSOR_PAPER_LINK_STATUSES),
            name="ck_professor_paper_link_status",
        ),
        sa.CheckConstraint(
            _check_enum("evidence_source_type", PROFESSOR_PAPER_EVIDENCE_SOURCE_TYPES),
            name="ck_professor_paper_link_evidence_source_type",
        ),
        sa.CheckConstraint(
            "verified_by IS NULL OR "
            + _check_enum("verified_by", PROFESSOR_PAPER_VERIFIED_BY),
            name="ck_professor_paper_link_verified_by",
        ),
    )
    op.create_foreign_key(
        "fk_professor_paper_link_professor",
        "professor_paper_link",
        "professor",
        ["professor_id"],
        ["professor_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_professor_paper_link_paper",
        "professor_paper_link",
        "paper",
        ["paper_id"],
        ["paper_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_professor_paper_link_evidence_page",
        "professor_paper_link",
        "source_page",
        ["evidence_page_id"],
        ["page_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_professor_paper_link_professor_status",
        "professor_paper_link",
        ["professor_id", "link_status"],
    )
    op.create_index(
        "ix_professor_paper_link_paper_status",
        "professor_paper_link",
        ["paper_id", "link_status"],
    )
    op.create_index(
        "ix_professor_paper_link_candidate_score",
        "professor_paper_link",
        ["link_status", sa.text("author_name_match_score DESC")],
        unique=False,
        postgresql_where=sa.text("link_status = 'candidate'"),
    )


def downgrade() -> None:
    # Drop in reverse dependency order.
    op.drop_table("professor_paper_link")
