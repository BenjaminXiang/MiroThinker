"""add quality_status and patent summary fields

Revision ID: V019
Revises: V018
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V019"
down_revision: Union[str, None] = "V018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CANONICAL_TABLES = ("professor", "company", "paper", "patent")
VALID_QUALITY_STATUSES = (
    "needs_review",
    "ready",
    "low_confidence",
    "needs_enrichment",
    "partial",
    "rejected",
)
VALID_SUMMARY_METHODS = ("llm", "fallback_template")


def upgrade() -> None:
    for table in CANONICAL_TABLES:
        op.add_column(
            table,
            sa.Column(
                "quality_status",
                sa.Text(),
                nullable=False,
                server_default="needs_review",
            ),
        )
        op.create_check_constraint(
            f"ck_{table}_quality_status",
            table,
            f"quality_status IN {VALID_QUALITY_STATUSES!r}",
        )
        op.create_index(
            f"ix_{table}_quality_status",
            table,
            ["quality_status"],
        )

    op.add_column("patent", sa.Column("summary_text", sa.Text(), nullable=True))
    op.add_column(
        "patent",
        sa.Column("summary_text_method", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_patent_summary_text_method",
        "patent",
        f"summary_text_method IS NULL OR summary_text_method IN {VALID_SUMMARY_METHODS!r}",
    )


def downgrade() -> None:
    op.drop_constraint("ck_patent_summary_text_method", "patent", type_="check")
    op.drop_column("patent", "summary_text_method")
    op.drop_column("patent", "summary_text")

    for table in CANONICAL_TABLES:
        op.drop_index(f"ix_{table}_quality_status", table_name=table)
        op.drop_constraint(f"ck_{table}_quality_status", table, type_="check")
        op.drop_column(table, "quality_status")
