"""Add company_name to the patent applicant sub-object table.

Revision ID: C2_0012
Revises: C2_0011
Create Date: 2026-08-03

The s12f applicant-binding batch resolves each released patent applicant to a
canonical company; the bound sub-object now carries ``company_name`` (the
company's canonical display name) so the serving path can render the Chinese
name (e.g. 深圳市优必选科技股份有限公司) instead of the raw English
applicant string (e.g. "Shenzhen Ubtech Technology Co ltd").
"""

from __future__ import annotations

from typing import Final, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "C2_0012"
down_revision: Union[str, None] = "C2_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE patent.applicant ADD COLUMN company_name text"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE patent.applicant DROP COLUMN company_name")
