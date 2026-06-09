"""allow page-only patent rows without patent_number

Revision ID: V026
Revises: V025
Create Date: 2026-05-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V026"
down_revision: Union[str, None] = "V025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "patent",
        "patent_number",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    # Preserve reversibility for databases that already contain page-only
    # rows. The synthetic value remains unique because patent_id is primary.
    op.execute(
        """
        UPDATE patent
           SET patent_number = patent_id
         WHERE patent_number IS NULL
        """
    )
    op.alter_column(
        "patent",
        "patent_number",
        existing_type=sa.Text(),
        nullable=False,
    )
