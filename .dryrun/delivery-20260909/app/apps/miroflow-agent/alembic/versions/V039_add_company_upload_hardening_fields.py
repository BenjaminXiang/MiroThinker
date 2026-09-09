"""Add company upload hardening metadata.

Revision ID: V039
Revises: V038
Create Date: 2026-06-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "V039"
down_revision = "V038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_enrichment_batch",
        sa.Column("runner_pid", sa.Integer(), nullable=True),
    )
    op.add_column(
        "company_enrichment_batch",
        sa.Column("runner_log_path", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_enrichment_batch",
        sa.Column("runner_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_enrichment_batch",
        sa.Column("runner_last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_enrichment_batch",
        sa.Column("last_completed_company_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_enrichment_batch",
        sa.Column(
            "miss_reason_buckets",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "company_enrichment_batch",
        sa.Column(
            "quality_report",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_company_enrichment_batch_runner_heartbeat",
        "company_enrichment_batch",
        ["status", "runner_heartbeat_at"],
    )
    op.alter_column(
        "company_enrichment_batch",
        "miss_reason_buckets",
        server_default=None,
    )
    op.alter_column(
        "company_enrichment_batch",
        "quality_report",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_enrichment_batch_runner_heartbeat",
        table_name="company_enrichment_batch",
    )
    op.drop_column("company_enrichment_batch", "quality_report")
    op.drop_column("company_enrichment_batch", "miss_reason_buckets")
    op.drop_column("company_enrichment_batch", "last_completed_company_id")
    op.drop_column("company_enrichment_batch", "runner_last_seen_at")
    op.drop_column("company_enrichment_batch", "runner_heartbeat_at")
    op.drop_column("company_enrichment_batch", "runner_log_path")
    op.drop_column("company_enrichment_batch", "runner_pid")
