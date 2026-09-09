"""add paper full text raw PDF provenance columns

Revision ID: V031
Revises: V030
Create Date: 2026-05-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V031"
down_revision: Union[str, None] = "V030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "paper_full_text",
        sa.Column("pdf_byte_size", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "paper_full_text",
        sa.Column("raw_pdf_storage_ref", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_paper_full_text_pdf_sha256",
        "paper_full_text",
        ["pdf_sha256"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_paper_full_text_pdf_sha256", table_name="paper_full_text")
    op.drop_column("paper_full_text", "raw_pdf_storage_ref")
    op.drop_column("paper_full_text", "pdf_byte_size")
