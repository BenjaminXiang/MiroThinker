"""add profile_summary + profile_raw_text columns (Round 7.19c / 9.1b)

Revision ID: V010
Revises: V009
Create Date: 2026-04-19

Round 9.1b surfaces two optional bio fields on the professor detail UI:
  - profile_summary  — LLM-generated AI professor brief
  - profile_raw_text — verbatim bio paragraph scraped from the official page

EnrichedProfessorProfile already has `profile_summary: str = ""` in Python
since V3, but the DB canonical `professor` table never got a column to
persist it. This migration adds both as nullable text so 9.1b can render
them conditionally (null → card hidden) without a coordinated refactor.

Backfill is a SEPARATE concern:
  - profile_summary can be regenerated via `scripts/run_profile_summary_generate.py`
    (existing) for professors where the column is currently NULL.
  - profile_raw_text requires re-scraping the primary source page because
    `source_page.clean_text_path` is currently unpopulated (0 rows today).
    Treat that as Round 7.19c-ext follow-up.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "V010"
down_revision = "V009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "professor",
        sa.Column("profile_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "professor",
        sa.Column("profile_raw_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("professor", "profile_raw_text")
    op.drop_column("professor", "profile_summary")
