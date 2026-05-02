"""add paper summary_zh field

Revision ID: V018
Revises: V017
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V018"
down_revision: Union[str, None] = "V017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paper", sa.Column("summary_zh", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("paper", "summary_zh")
