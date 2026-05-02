"""add company narrative fields for semantic retrieval

Revision ID: V014
Revises: V013
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V014"
down_revision: Union[str, None] = "V013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("company", sa.Column("profile_summary", sa.Text(), nullable=True))
    op.add_column(
        "company",
        sa.Column("technology_route_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company", "technology_route_summary")
    op.drop_column("company", "profile_summary")
