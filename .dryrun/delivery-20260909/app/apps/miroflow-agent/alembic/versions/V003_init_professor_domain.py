"""init professor domain: professor canonical, affiliations, and facts

Revision ID: V003
Revises: V002
Create Date: 2026-04-18

Creates the Professor Canonical layer tables per plan
docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
§6.3.

Explicitly excluded in this round:
- runtime writes / seed inserts: handled later by canonical writers
- professor-paper and other cross-domain relation tables: deferred to V005a/V005b
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V003"
down_revision: Union[str, None] = "V002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- enum value lists (kept in Python so test fixtures can import them) ---
PROFESSOR_DISCIPLINE_FAMILIES = [
    "computer_science",
    "electrical_engineering",
    "mechanical_engineering",
    "materials",
    "biomedical",
    "mathematics",
    "physics",
    "chemistry",
    "interdisciplinary",
    "other",
]

PROFESSOR_IDENTITY_STATUSES = [
    "resolved",
    "needs_review",
    "merged_into",
    "inactive",
]

PROFESSOR_FACT_TYPES = [
    "research_topic",
    "education",
    "work_experience",
    "award",
    "academic_position",
    "contact",
    "homepage",
    "external_profile",
    "publication_count_reported",
]

PROFESSOR_FACT_STATUSES = ["active", "deprecated", "superseded"]


def _check_enum(column: str, values: list[str]) -> str:
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    # ------------------------------ professor -----------------------------
    op.create_table(
        "professor",
        sa.Column("professor_id", sa.Text(), primary_key=True),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("canonical_name_en", sa.Text()),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("discipline_family", sa.Text(), nullable=False),
        sa.Column("primary_official_profile_page_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "identity_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'resolved'"),
        ),
        sa.Column("merged_into_id", sa.Text()),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_refreshed_at", sa.TIMESTAMP(timezone=True)),
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
        sa.CheckConstraint(
            _check_enum("discipline_family", PROFESSOR_DISCIPLINE_FAMILIES),
            name="ck_professor_discipline_family",
        ),
        sa.CheckConstraint(
            _check_enum("identity_status", PROFESSOR_IDENTITY_STATUSES),
            name="ck_professor_identity_status",
        ),
    )
    op.create_foreign_key(
        "fk_professor_primary_official_profile_page",
        "professor",
        "source_page",
        ["primary_official_profile_page_id"],
        ["page_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_professor_merged_into",
        "professor",
        "professor",
        ["merged_into_id"],
        ["professor_id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_professor_canonical_name", "professor", ["canonical_name"])
    op.create_index(
        "ix_professor_identity_status_canonical_name",
        "professor",
        ["identity_status", "canonical_name"],
    )

    # ------------------------- professor_affiliation ----------------------
    op.create_table(
        "professor_affiliation",
        sa.Column(
            "affiliation_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("professor_id", sa.Text(), nullable=False),
        sa.Column("institution", sa.Text(), nullable=False),
        sa.Column("department", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("employment_type", sa.Text()),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("start_year", sa.Integer()),
        sa.Column("end_year", sa.Integer()),
        sa.Column("source_page_id", postgresql.UUID(as_uuid=True), nullable=False),
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
    )
    op.create_foreign_key(
        "fk_professor_affiliation_professor",
        "professor_affiliation",
        "professor",
        ["professor_id"],
        ["professor_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_professor_affiliation_source_page",
        "professor_affiliation",
        "source_page",
        ["source_page_id"],
        ["page_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_professor_affiliation_professor_current",
        "professor_affiliation",
        ["professor_id", "is_current"],
    )
    op.create_index(
        "ix_professor_affiliation_institution_current",
        "professor_affiliation",
        ["institution", "is_current"],
    )

    # ---------------------------- professor_fact --------------------------
    op.create_table(
        "professor_fact",
        sa.Column(
            "fact_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("professor_id", sa.Text(), nullable=False),
        sa.Column("fact_type", sa.Text(), nullable=False),
        sa.Column("value_raw", sa.Text(), nullable=False),
        sa.Column("value_normalized", sa.Text()),
        sa.Column("value_code", sa.Text()),
        sa.Column("source_page_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_span", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
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
        sa.CheckConstraint(
            _check_enum("fact_type", PROFESSOR_FACT_TYPES),
            name="ck_professor_fact_type",
        ),
        sa.CheckConstraint(
            _check_enum("status", PROFESSOR_FACT_STATUSES),
            name="ck_professor_fact_status",
        ),
    )
    op.create_foreign_key(
        "fk_professor_fact_professor",
        "professor_fact",
        "professor",
        ["professor_id"],
        ["professor_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_professor_fact_value_code",
        "professor_fact",
        "taxonomy_vocabulary",
        ["value_code"],
        ["code"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_professor_fact_source_page",
        "professor_fact",
        "source_page",
        ["source_page_id"],
        ["page_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_professor_fact_professor_type",
        "professor_fact",
        ["professor_id", "fact_type"],
    )
    op.create_index(
        "ix_professor_fact_value_code",
        "professor_fact",
        ["value_code"],
        unique=False,
        postgresql_where=sa.text("value_code IS NOT NULL"),
    )


def downgrade() -> None:
    # Drop in reverse dependency order. Self-FKs are dropped with their tables.
    op.drop_table("professor_fact")
    op.drop_table("professor_affiliation")
    op.drop_table("professor")
