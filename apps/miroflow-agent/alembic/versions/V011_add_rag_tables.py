"""add RAG support tables for full text, title cache, and ORCID

Revision ID: V011
Revises: V010
Create Date: 2026-04-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V011"
down_revision: Union[str, None] = "V010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_full_text",
        sa.Column("paper_id", sa.String(length=64), nullable=False, primary_key=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("pdf_url", sa.Text(), nullable=True),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "fetched_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("fetch_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["paper.paper_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_paper_full_text_source",
        "paper_full_text",
        ["source"],
        unique=False,
    )

    op.create_table(
        "paper_title_resolution_cache",
        sa.Column("title_sha1", sa.String(length=40), nullable=False, primary_key=True),
        sa.Column("clean_title_preview", sa.String(length=500), nullable=True),
        sa.Column("resolved", postgresql.JSONB(), nullable=False),
        sa.Column("match_source", sa.String(length=32), nullable=True),
        sa.Column("match_confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "cached_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_paper_title_resolution_cache_cached_at_desc",
        "paper_title_resolution_cache",
        [sa.text("cached_at DESC")],
        unique=False,
    )

    op.create_table(
        "professor_orcid",
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("orcid", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column(
            "verified_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["professor_id"],
            ["professor.professor_id"],
        ),
        sa.PrimaryKeyConstraint("professor_id"),
        sa.UniqueConstraint("orcid"),
    )


def downgrade() -> None:
    op.drop_table("professor_orcid")
    op.drop_table("paper_title_resolution_cache")
    op.drop_table("paper_full_text")
