"""add company enrichment batch operations tables

Revision ID: V035
Revises: V034
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V035"
down_revision: Union[str, None] = "V034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BATCH_STATUSES = ("queued", "running", "succeeded", "partial", "failed")
COMPANY_STATUSES = ("queued", "running", "succeeded", "partial", "failed", "skipped")
REVIEW_ACTIONS = ("accept", "reject", "needs_review")
REVIEW_TARGET_TYPES = ("product", "scenario")


def _check_enum(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "company_enrichment_batch",
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "upload_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pipeline_run.run_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("current_stage", sa.Text(), nullable=True),
        sa.Column("companies_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("companies_selected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("companies_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("companies_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("companies_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "run_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("triggered_by", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _check_enum("status", BATCH_STATUSES),
            name="ck_company_enrichment_batch_status",
        ),
    )
    op.create_index(
        "ix_company_enrichment_batch_status_created",
        "company_enrichment_batch",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_company_enrichment_batch_import_batch",
        "company_enrichment_batch",
        ["import_batch_id"],
    )

    op.create_table(
        "company_enrichment_company_state",
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_enrichment_batch.batch_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Text(),
            sa.ForeignKey("company.company_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("current_stage", sa.Text(), nullable=True),
        sa.Column(
            "stage_status",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("query_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("product_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scenario_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("official_product_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("milvus_refreshed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("miss_reason", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _check_enum("status", COMPANY_STATUSES),
            name="ck_company_enrichment_company_state_status",
        ),
    )
    op.create_index(
        "ix_company_enrichment_company_state_status",
        "company_enrichment_company_state",
        ["batch_id", "status", "company_id"],
    )

    op.create_table(
        "company_enrichment_search_audit",
        sa.Column(
            "audit_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_enrichment_batch.batch_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Text(),
            sa.ForeignKey("company.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_adapter", sa.Text(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_kind", sa.Text(), nullable=False, server_default="site_search"),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_offsite", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "rejected_irrelevant_path",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "rejected_name_mismatch",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("miss_reason", sa.Text(), nullable=True),
        sa.Column(
            "llm_hints",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "diagnostics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "searched_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_company_enrichment_search_audit_company_source",
        "company_enrichment_search_audit",
        ["batch_id", "company_id", "source_adapter"],
    )

    op.create_table(
        "company_enrichment_review_action",
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("previous_status", sa.Text(), nullable=True),
        sa.Column("new_status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _check_enum("target_type", REVIEW_TARGET_TYPES),
            name="ck_company_enrichment_review_action_target_type",
        ),
        sa.CheckConstraint(
            _check_enum("action", REVIEW_ACTIONS),
            name="ck_company_enrichment_review_action_action",
        ),
    )
    op.create_index(
        "ix_company_enrichment_review_action_company_target",
        "company_enrichment_review_action",
        ["company_id", "target_type", "target_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_enrichment_review_action_company_target",
        table_name="company_enrichment_review_action",
    )
    op.drop_table("company_enrichment_review_action")
    op.drop_index(
        "ix_company_enrichment_search_audit_company_source",
        table_name="company_enrichment_search_audit",
    )
    op.drop_table("company_enrichment_search_audit")
    op.drop_index(
        "ix_company_enrichment_company_state_status",
        table_name="company_enrichment_company_state",
    )
    op.drop_table("company_enrichment_company_state")
    op.drop_index(
        "ix_company_enrichment_batch_import_batch",
        table_name="company_enrichment_batch",
    )
    op.drop_index(
        "ix_company_enrichment_batch_status_created",
        table_name="company_enrichment_batch",
    )
    op.drop_table("company_enrichment_batch")
