"""init source layer: seed_registry, import_batch, source_row_lineage, source_page, pipeline_run

Revision ID: V001
Revises:
Create Date: 2026-04-17

Creates the Source Layer tables per plan
docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md §6.1.

Explicitly excluded (r2 裁剪):
- page_link_candidate: 不独立建表；递归决策记录放 pipeline_run.run_scope jsonb
- offline_enrichment_queue: Phase 5+ 再建
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- enum value lists (kept in Python so test fixtures can import them) ---
SEED_KINDS = [
    "company_xlsx",
    "patent_xlsx",
    "teacher_roster",
    "department_hub",
    "company_official_site",
    "company_news_feed",
]
REFRESH_POLICIES = ["manual", "daily", "weekly", "monthly", "quarterly", "on_batch"]
SEED_STATUSES = ["active", "paused", "deprecated"]

BATCH_RUN_STATUSES = ["running", "succeeded", "partial", "failed", "reverted"]

LINEAGE_RESOLUTION_STATUSES = ["matched", "created", "merged", "failed", "skipped"]

PAGE_ROLES = [
    "roster_seed",
    "department_hub",
    "official_profile",
    "personal_homepage",
    "lab_homepage",
    "official_publication_page",
    "cv_pdf",
    "official_external_profile",
    "company_official_site",
    "company_news_article",
    "unknown",
]
OWNER_SCOPE_KINDS = ["institution", "department", "professor", "company", "global"]

PIPELINE_RUN_KINDS = [
    "import_xlsx",
    "roster_crawl",
    "profile_enrichment",
    "news_refresh",
    "team_resolver",
    "paper_link_resolver",
    "projection_build",
    "answer_readiness_eval",
    "quality_scan",
]
PIPELINE_RUN_STATUSES = ["running", "succeeded", "partial", "failed"]


def _check_enum(column: str, values: list[str]) -> str:
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    # Enable required extensions (idempotent).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # for gen_random_uuid()

    # ---------------------------- seed_registry ----------------------------
    op.create_table(
        "seed_registry",
        sa.Column("seed_id", sa.Text(), primary_key=True),
        sa.Column("seed_kind", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("refresh_policy", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("last_processed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("config", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("seed_kind", "scope_key", name="uq_seed_registry_scope"),
        sa.CheckConstraint(
            _check_enum("seed_kind", SEED_KINDS), name="ck_seed_registry_kind"
        ),
        sa.CheckConstraint(
            _check_enum("refresh_policy", REFRESH_POLICIES),
            name="ck_seed_registry_refresh_policy",
        ),
        sa.CheckConstraint(
            _check_enum("status", SEED_STATUSES), name="ck_seed_registry_status"
        ),
    )
    op.create_index(
        "ix_seed_registry_status_priority",
        "seed_registry",
        ["status", sa.text("priority DESC")],
    )

    # ---------------------------- import_batch -----------------------------
    op.create_table(
        "import_batch",
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "seed_id",
            sa.Text(),
            sa.ForeignKey("seed_registry.seed_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("file_content_hash", sa.Text(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("rows_read", sa.Integer()),
        sa.Column("records_parsed", sa.Integer()),
        sa.Column("records_new", sa.Integer()),
        sa.Column("records_updated", sa.Integer()),
        sa.Column("records_merged", sa.Integer()),
        sa.Column("records_failed", sa.Integer()),
        sa.Column("run_status", sa.Text(), nullable=False),
        sa.Column("error_summary", postgresql.JSONB()),
        sa.Column("triggered_by", sa.Text()),
        sa.UniqueConstraint(
            "seed_id", "file_content_hash", name="uq_import_batch_dedup"
        ),
        sa.CheckConstraint(
            _check_enum("run_status", BATCH_RUN_STATUSES),
            name="ck_import_batch_status",
        ),
    )
    op.create_index("ix_import_batch_seed", "import_batch", ["seed_id", "started_at"])

    # -------------------------- source_row_lineage -------------------------
    op.create_table(
        "source_row_lineage",
        sa.Column(
            "lineage_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batch.batch_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("target_entity_type", sa.Text(), nullable=False),
        sa.Column("target_entity_id", sa.Text()),
        sa.Column("resolution_status", sa.Text(), nullable=False),
        sa.Column("resolution_reason", sa.Text()),
        sa.Column("raw_row_jsonb", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _check_enum("resolution_status", LINEAGE_RESOLUTION_STATUSES),
            name="ck_source_row_lineage_status",
        ),
    )
    op.create_index(
        "ix_source_row_lineage_target",
        "source_row_lineage",
        ["target_entity_type", "target_entity_id"],
    )
    op.create_index("ix_source_row_lineage_batch", "source_row_lineage", ["batch_id"])

    # ----------------------------- source_page -----------------------------
    op.create_table(
        "source_page",
        sa.Column(
            "page_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "url_host",
            sa.Text(),
            sa.Computed(
                "lower(split_part(substring(url from '://([^/]+)'), ':', 1))",
                persisted=True,
            ),
        ),
        sa.Column("page_role", sa.Text(), nullable=False),
        sa.Column("owner_scope_kind", sa.Text()),
        sa.Column("owner_scope_ref", sa.Text()),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("content_hash", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("clean_text_path", sa.Text()),
        sa.Column(
            "is_official_source",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("fetch_run_id", postgresql.UUID(as_uuid=True)),  # FK set below
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("url", name="uq_source_page_url"),
        sa.CheckConstraint(
            _check_enum("page_role", PAGE_ROLES), name="ck_source_page_role"
        ),
        sa.CheckConstraint(
            "owner_scope_kind IS NULL OR "
            + _check_enum("owner_scope_kind", OWNER_SCOPE_KINDS),
            name="ck_source_page_owner_scope_kind",
        ),
    )
    op.create_index(
        "ix_source_page_owner",
        "source_page",
        ["owner_scope_kind", "owner_scope_ref"],
    )
    op.create_index(
        "ix_source_page_role_host", "source_page", ["page_role", "url_host"]
    )

    # ---------------------------- pipeline_run -----------------------------
    op.create_table(
        "pipeline_run",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_kind", sa.Text(), nullable=False),
        sa.Column("run_scope", postgresql.JSONB(), nullable=False),
        sa.Column(
            "seed_id",
            sa.Text(),
            sa.ForeignKey("seed_registry.seed_id", ondelete="SET NULL"),
        ),
        sa.Column("parent_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("items_processed", sa.Integer()),
        sa.Column("items_failed", sa.Integer()),
        sa.Column("error_summary", postgresql.JSONB()),
        sa.Column("triggered_by", sa.Text()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _check_enum("run_kind", PIPELINE_RUN_KINDS), name="ck_pipeline_run_kind"
        ),
        sa.CheckConstraint(
            _check_enum("status", PIPELINE_RUN_STATUSES),
            name="ck_pipeline_run_status",
        ),
    )
    op.create_foreign_key(
        "fk_pipeline_run_parent",
        "pipeline_run",
        "pipeline_run",
        ["parent_run_id"],
        ["run_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_source_page_fetch_run",
        "source_page",
        "pipeline_run",
        ["fetch_run_id"],
        ["run_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_pipeline_run_kind_started",
        "pipeline_run",
        ["run_kind", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_pipeline_run_status",
        "pipeline_run",
        ["status", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    # Drop in reverse dependency order. FK constraints auto-drop with tables.
    op.drop_constraint("fk_source_page_fetch_run", "source_page", type_="foreignkey")
    op.drop_table("pipeline_run")
    op.drop_table("source_page")
    op.drop_table("source_row_lineage")
    op.drop_table("import_batch")
    op.drop_table("seed_registry")
    # pgcrypto extension intentionally left installed (harmless, may be used by other migrations).
