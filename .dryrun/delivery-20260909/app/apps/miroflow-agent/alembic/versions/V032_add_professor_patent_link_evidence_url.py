"""add professor patent link evidence URL fields

Revision ID: V032
Revises: V031
Create Date: 2026-05-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V032"
down_revision: Union[str, None] = "V031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professor_patent_link",
        sa.Column("evidence_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "professor_patent_link",
        sa.Column("evidence_anchor", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("professor_patent_link", "evidence_anchor")
    op.drop_column("professor_patent_link", "evidence_url")
