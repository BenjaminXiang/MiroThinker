"""add source tier to company product and scenario evidence

Revision ID: V037
Revises: V036
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V037"
down_revision: Union[str, None] = "V036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_product_evidence",
        sa.Column("source_tier", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_application_scenario_evidence",
        sa.Column("source_tier", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_application_scenario_evidence", "source_tier")
    op.drop_column("company_product_evidence", "source_tier")
