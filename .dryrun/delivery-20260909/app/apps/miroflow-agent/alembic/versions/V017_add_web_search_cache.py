"""add web search cache

Revision ID: V017
Revises: V016
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V017"
down_revision: Union[str, None] = "V016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "web_search_cache",
        sa.Column("query_sha1", sa.String(length=40), primary_key=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            server_default="serper",
        ),
        sa.Column(
            "cached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_web_search_cache_cached_at",
        "web_search_cache",
        ["cached_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_web_search_cache_cached_at", table_name="web_search_cache")
    op.drop_table("web_search_cache")
