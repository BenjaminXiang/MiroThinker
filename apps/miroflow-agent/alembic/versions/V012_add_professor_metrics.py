"""add professor academic metrics columns

Revision ID: V012
Revises: V011
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V012"
down_revision: Union[str, None] = "V011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("professor", sa.Column("h_index", sa.Integer(), nullable=True))
    op.add_column("professor", sa.Column("citation_count", sa.BigInteger(), nullable=True))
    op.add_column("professor", sa.Column("paper_count", sa.Integer(), nullable=True))
    op.add_column(
        "professor",
        sa.Column("metrics_computed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column("professor", sa.Column("metrics_source", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_professor_metrics_source",
        "professor",
        "metrics_source IS NULL OR metrics_source IN "
        "('openalex', 'verified_link_only', 'mixed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_professor_metrics_source", "professor", type_="check")
    for column_name in (
        "metrics_source",
        "metrics_computed_at",
        "paper_count",
        "citation_count",
        "h_index",
    ):
        op.drop_column("professor", column_name)
