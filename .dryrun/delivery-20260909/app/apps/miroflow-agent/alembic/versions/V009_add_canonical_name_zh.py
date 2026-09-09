"""add professor.canonical_name_zh for bilingual name backfill (Round 7.19a)

Revision ID: V009
Revises: V008
Create Date: 2026-04-19

Round 7.19a backfills bilingual professor names. Existing schema only had
`canonical_name` and `canonical_name_en`, which leaves English-anchor rows
without a place to persist the Chinese name. This migration adds an explicit
nullable `canonical_name_zh` column to `professor`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "V009"
down_revision = "V008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("professor", sa.Column("canonical_name_zh", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("professor", "canonical_name_zh")
