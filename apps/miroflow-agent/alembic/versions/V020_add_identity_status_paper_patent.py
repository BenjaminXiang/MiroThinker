"""add identity_status for paper and patent

Revision ID: V020
Revises: V019
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V020"
down_revision: Union[str, None] = "V019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALID_IDENTITY = ("confirmed", "unverified", "rejected", "merged")


def upgrade() -> None:
    op.add_column(
        "paper",
        sa.Column(
            "identity_status",
            sa.Text(),
            nullable=False,
            server_default="unverified",
        ),
    )
    op.create_check_constraint(
        "ck_paper_identity_status",
        "paper",
        f"identity_status IN {VALID_IDENTITY!r}",
    )
    op.create_index("ix_paper_identity_status", "paper", ["identity_status"])

    op.add_column(
        "patent",
        sa.Column(
            "identity_status",
            sa.Text(),
            nullable=False,
            server_default="confirmed",
        ),
    )
    op.create_check_constraint(
        "ck_patent_identity_status",
        "patent",
        f"identity_status IN {VALID_IDENTITY!r}",
    )
    op.create_index("ix_patent_identity_status", "patent", ["identity_status"])


def downgrade() -> None:
    for table in ("patent", "paper"):
        op.drop_index(f"ix_{table}_identity_status", table_name=table)
        op.drop_constraint(
            f"ck_{table}_identity_status",
            table,
            type_="check",
        )
        op.drop_column(table, "identity_status")
