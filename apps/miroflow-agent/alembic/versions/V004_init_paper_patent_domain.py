"""init paper and patent domain: canonical papers and patents

Revision ID: V004
Revises: V003
Create Date: 2026-04-18

Creates the Paper and Patent canonical layer tables per plan
docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
§6.4.

Explicitly excluded in this round:
- relation tables linking papers/patents to other entities: handled in V005a/V005b
- pipeline writer logic and runtime backfills: handled later
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V004"
down_revision: Union[str, None] = "V003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- enum value lists (kept in Python so test fixtures can import them) ---
PAPER_CANONICAL_SOURCES = [
    "openalex",
    "semantic_scholar",
    "crossref",
    "official_page",
    "manual",
]

PATENT_TYPES = ["发明", "实用新型", "外观", "PCT", "其他"]


def _check_enum(column: str, values: list[str]) -> str:
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    # -------------------------------- paper -------------------------------
    op.create_table(
        "paper",
        sa.Column("paper_id", sa.Text(), primary_key=True),
        sa.Column("title_clean", sa.Text(), nullable=False),
        sa.Column("title_raw", sa.Text()),
        sa.Column("doi", sa.Text()),
        sa.Column("arxiv_id", sa.Text()),
        sa.Column("openalex_id", sa.Text()),
        sa.Column("semantic_scholar_id", sa.Text()),
        sa.Column("year", sa.Integer()),
        sa.Column("venue", sa.Text()),
        sa.Column("abstract_clean", sa.Text()),
        sa.Column("authors_display", sa.Text()),
        sa.Column("authors_raw", postgresql.JSONB()),
        sa.Column("citation_count", sa.Integer()),
        sa.Column("canonical_source", sa.Text(), nullable=False),
        sa.Column(
            "first_seen_at",
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
        sa.UniqueConstraint("doi", name="uq_paper_doi"),
        sa.CheckConstraint(
            _check_enum("canonical_source", PAPER_CANONICAL_SOURCES),
            name="ck_paper_canonical_source",
        ),
    )
    op.create_index("ix_paper_year_desc", "paper", [sa.text("year DESC")])
    op.create_index("ix_paper_canonical_source", "paper", ["canonical_source"])
    op.create_index(
        "ix_paper_openalex_id",
        "paper",
        ["openalex_id"],
        unique=False,
        postgresql_where=sa.text("openalex_id IS NOT NULL"),
    )
    op.create_index(
        "ix_paper_arxiv_id",
        "paper",
        ["arxiv_id"],
        unique=False,
        postgresql_where=sa.text("arxiv_id IS NOT NULL"),
    )

    # -------------------------------- patent -----------------------------
    op.create_table(
        "patent",
        sa.Column("patent_id", sa.Text(), primary_key=True),
        sa.Column("patent_number", sa.Text(), nullable=False),
        sa.Column("title_clean", sa.Text(), nullable=False),
        sa.Column("title_raw", sa.Text()),
        sa.Column("title_en", sa.Text()),
        sa.Column("applicants_raw", sa.Text()),
        sa.Column("applicants_parsed", postgresql.JSONB()),
        sa.Column("inventors_raw", sa.Text()),
        sa.Column("inventors_parsed", postgresql.JSONB()),
        sa.Column("filing_date", sa.Date()),
        sa.Column("publication_date", sa.Date()),
        sa.Column("grant_date", sa.Date()),
        sa.Column("patent_type", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("abstract_clean", sa.Text()),
        sa.Column("technology_effect", sa.Text()),
        sa.Column(
            "ipc_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "first_seen_at",
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
        sa.UniqueConstraint("patent_number", name="uq_patent_patent_number"),
        sa.CheckConstraint(
            "patent_type IS NULL OR " + _check_enum("patent_type", PATENT_TYPES),
            name="ck_patent_type",
        ),
    )
    op.create_index("ix_patent_patent_number", "patent", ["patent_number"])
    op.create_index(
        "ix_patent_filing_date_desc", "patent", [sa.text("filing_date DESC")]
    )


def downgrade() -> None:
    # Drop in reverse dependency order.
    op.drop_table("patent")
    op.drop_table("paper")
