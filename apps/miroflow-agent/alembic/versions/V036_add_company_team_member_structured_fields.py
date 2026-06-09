"""add structured company team member fields

Revision ID: V036
Revises: V035
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V036"
down_revision: Union[str, None] = "V035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_team_member",
        sa.Column("structured_background", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_team_member",
        sa.Column(
            "structured_experience_highlights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "company_team_member",
        sa.Column("structured_relevance", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_team_member",
        sa.Column("structured_confidence", sa.Numeric(3, 2), nullable=True),
    )
    op.add_column(
        "company_team_member",
        sa.Column("structured_evidence_span", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_team_member",
        sa.Column("structured_raw_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_team_member", "structured_raw_text")
    op.drop_column("company_team_member", "structured_evidence_span")
    op.drop_column("company_team_member", "structured_confidence")
    op.drop_column("company_team_member", "structured_relevance")
    op.drop_column("company_team_member", "structured_experience_highlights")
    op.drop_column("company_team_member", "structured_background")
