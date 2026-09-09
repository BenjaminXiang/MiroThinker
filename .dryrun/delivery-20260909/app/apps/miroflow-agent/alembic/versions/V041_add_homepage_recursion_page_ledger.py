"""Add homepage recursion page ledger.

Revision ID: V041
Revises: V040
Create Date: 2026-06-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "V041"
down_revision: Union[str, None] = "V040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "homepage_recursion_page_ledger",
        sa.Column(
            "ledger_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("professor_id", sa.Text(), nullable=False),
        sa.Column("parent_source_page_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_page_id", postgresql.UUID(as_uuid=True)),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("page_role", sa.Text(), nullable=False),
        sa.Column("discovery_source", sa.Text(), nullable=False),
        sa.Column("recursion_depth", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("skip_reason", sa.Text()),
        sa.Column("fetch_error_type", sa.Text()),
        sa.Column("fetch_error_message", sa.Text()),
        sa.Column("http_status", sa.Integer()),
        sa.Column("publications_extracted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sections_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "heading_texts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('processed', 'zero_extraction', 'fetch_failed', 'skipped')",
            name="ck_homepage_recursion_page_ledger_status",
        ),
        sa.CheckConstraint(
            "recursion_depth >= 0",
            name="ck_homepage_recursion_page_ledger_depth",
        ),
        sa.CheckConstraint(
            "publications_extracted >= 0",
            name="ck_homepage_recursion_page_ledger_publications_extracted",
        ),
        sa.CheckConstraint(
            "sections_detected >= 0",
            name="ck_homepage_recursion_page_ledger_sections_detected",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["pipeline_run.run_id"],
            ondelete="CASCADE",
            name="fk_homepage_recursion_page_ledger_run",
        ),
        sa.ForeignKeyConstraint(
            ["parent_source_page_id"],
            ["source_page.page_id"],
            ondelete="SET NULL",
            name="fk_homepage_recursion_page_ledger_parent_source_page",
        ),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["source_page.page_id"],
            ondelete="SET NULL",
            name="fk_homepage_recursion_page_ledger_source_page",
        ),
        sa.UniqueConstraint(
            "run_id",
            "professor_id",
            "normalized_url",
            "discovery_source",
            name="uq_homepage_recursion_page_ledger_scope",
        ),
    )
    op.create_index(
        "ix_homepage_recursion_page_ledger_status",
        "homepage_recursion_page_ledger",
        ["status"],
    )
    op.create_index(
        "ix_homepage_recursion_page_ledger_professor",
        "homepage_recursion_page_ledger",
        ["professor_id", "status"],
    )
    op.create_index(
        "ix_homepage_recursion_page_ledger_run",
        "homepage_recursion_page_ledger",
        ["run_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_homepage_recursion_page_ledger_run",
        table_name="homepage_recursion_page_ledger",
    )
    op.drop_index(
        "ix_homepage_recursion_page_ledger_professor",
        table_name="homepage_recursion_page_ledger",
    )
    op.drop_index(
        "ix_homepage_recursion_page_ledger_status",
        table_name="homepage_recursion_page_ledger",
    )
    op.drop_table("homepage_recursion_page_ledger")
