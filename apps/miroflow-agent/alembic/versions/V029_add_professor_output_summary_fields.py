"""add professor output summary fields

Revision ID: V029
Revises: V028
Create Date: 2026-05-23

Adds nullable professor-level aggregate summaries for accepted linked
papers and patents. The fields are additive so existing rows remain
valid and downstream vector publishers can query them directly from the
professor table.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V029"
down_revision: Union[str, None] = "V028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("professor", sa.Column("paper_summary", sa.Text(), nullable=True))
    op.add_column("professor", sa.Column("patent_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("professor", "patent_summary")
    op.drop_column("professor", "paper_summary")
