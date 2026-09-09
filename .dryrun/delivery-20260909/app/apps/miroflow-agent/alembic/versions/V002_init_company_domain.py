"""init company domain: taxonomy, company canonical, company news, company signals

Revision ID: V002
Revises: V001
Create Date: 2026-04-18

Creates the Company Canonical layer tables per plan
docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
§6.2 and §6.7.

Explicitly excluded in this round:
- taxonomy/domain seed inserts: handled later by runtime seed-loader code
- professor FK on company_team_member.resolved_professor_id: deferred to V003/V005
- answer_pack and Phase 2+ tables: out of scope for V002
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V002"
down_revision: Union[str, None] = "V001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- enum value lists (kept in Python so test fixtures can import them) ---
TAXONOMY_STATUSES = ["active", "deprecated"]

SOURCE_DOMAIN_TIERS = ["official", "trusted", "unknown"]

COMPANY_IDENTITY_STATUSES = ["resolved", "needs_review", "merged_into", "inactive"]

COMPANY_SNAPSHOT_KINDS = ["xlsx_import", "website_crawl"]

TEAM_RESOLUTION_STATUSES = ["unresolved", "candidate", "matched", "rejected"]

COMPANY_FACT_TYPES = [
    "industry_tag",
    "product_tag",
    "technology_route",
    "data_route_type",
    "real_data_method",
    "synthetic_data_method",
    "movement_data_need",
    "operation_data_need",
    "customer_type",
    "founder_background",
    "business_model",
    "certification",
]
COMPANY_FACT_STATUSES = ["active", "pending_taxonomy", "deprecated", "superseded"]
COMPANY_FACT_SOURCE_KINDS = [
    "xlsx",
    "official_website",
    "news",
    "llm_from_official",
    "human_reviewed",
]

COMPANY_SIGNAL_EVENT_TYPES = [
    "funding",
    "product_launch",
    "partnership",
    "policy",
    "hiring",
    "order",
    "patent_grant",
    "award",
    "expansion",
    "executive_change",
]
COMPANY_SIGNAL_EVENT_STATUSES = ["active", "deprecated", "deduped_into"]


def _check_enum(column: str, values: list[str]) -> str:
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    # ------------------------- taxonomy_vocabulary -------------------------
    op.create_table(
        "taxonomy_vocabulary",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("display_name_en", sa.Text()),
        sa.Column("parent_code", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
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
        sa.CheckConstraint(
            _check_enum("status", TAXONOMY_STATUSES),
            name="ck_taxonomy_vocabulary_status",
        ),
    )
    op.create_foreign_key(
        "fk_taxonomy_vocabulary_parent_code",
        "taxonomy_vocabulary",
        "taxonomy_vocabulary",
        ["parent_code"],
        ["code"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_taxonomy_vocabulary_namespace_status",
        "taxonomy_vocabulary",
        ["namespace", "status"],
    )
    op.create_index(
        "ix_taxonomy_vocabulary_parent_code",
        "taxonomy_vocabulary",
        ["parent_code"],
    )

    # --------------------- source_domain_tier_registry ---------------------
    op.create_table(
        "source_domain_tier_registry",
        sa.Column("domain", sa.Text(), primary_key=True),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("tier_reason", sa.Text()),
        sa.Column("is_official_for_scope", sa.Text()),
        sa.Column("last_reviewed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _check_enum("tier", SOURCE_DOMAIN_TIERS),
            name="ck_source_domain_tier_registry_tier",
        ),
    )

    # ------------------------------- company -------------------------------
    op.create_table(
        "company",
        sa.Column("company_id", sa.Text(), primary_key=True),
        sa.Column("unified_credit_code", sa.Text()),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("registered_name", sa.Text()),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("website", sa.Text()),
        sa.Column(
            "website_host",
            sa.Text(),
            sa.Computed(
                "lower(split_part(substring(website from '://([^/]+)'), ':', 1))",
                persisted=True,
            ),
        ),
        sa.Column("hq_province", sa.Text()),
        sa.Column("hq_city", sa.Text()),
        sa.Column("hq_district", sa.Text()),
        sa.Column(
            "is_shenzhen",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "country", sa.Text(), nullable=False, server_default=sa.text("'国内'")
        ),
        sa.Column(
            "identity_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'resolved'"),
        ),
        sa.Column("merged_into_id", sa.Text()),
        sa.Column(
            "first_seen_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batch.batch_id", ondelete="SET NULL"),
        ),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_refreshed_at", sa.TIMESTAMP(timezone=True)),
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
        sa.UniqueConstraint(
            "unified_credit_code", name="uq_company_unified_credit_code"
        ),
        sa.CheckConstraint(
            _check_enum("identity_status", COMPANY_IDENTITY_STATUSES),
            name="ck_company_identity_status",
        ),
    )
    op.create_foreign_key(
        "fk_company_merged_into",
        "company",
        "company",
        ["merged_into_id"],
        ["company_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_company_website_host_nonempty",
        "company",
        ["website_host"],
        unique=False,
        postgresql_where=sa.text("website_host IS NOT NULL AND website_host != ''"),
    )
    op.create_index("ix_company_canonical_name", "company", ["canonical_name"])
    op.create_index(
        "ix_company_is_shenzhen_identity_status",
        "company",
        ["is_shenzhen", "identity_status"],
    )

    # --------------------------- company_snapshot --------------------------
    op.create_table(
        "company_snapshot",
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            sa.Text(),
            sa.ForeignKey("company.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batch.batch_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("snapshot_kind", sa.Text(), nullable=False),
        sa.Column("source_row_number", sa.Integer()),
        sa.Column("project_name", sa.Text()),
        sa.Column("industry", sa.Text()),
        sa.Column("sub_industry", sa.Text()),
        sa.Column("business", sa.Text()),
        sa.Column("region", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("logo_url", sa.Text()),
        sa.Column("star_rating", sa.Integer()),
        sa.Column("status_raw", sa.Text()),
        sa.Column("remarks", sa.Text()),
        sa.Column("is_high_tech", sa.Boolean()),
        sa.Column("company_name_xlsx", sa.Text(), nullable=False),
        sa.Column("country_xlsx", sa.Text()),
        sa.Column("established_date", sa.Date()),
        sa.Column("years_established", sa.Integer()),
        sa.Column("website_xlsx", sa.Text()),
        sa.Column("legal_representative", sa.Text()),
        sa.Column("registered_address", sa.Text()),
        sa.Column("registered_capital", sa.Text()),
        sa.Column("contact_phone", sa.Text()),
        sa.Column("contact_email", sa.Text()),
        sa.Column("reported_insured_count", sa.Integer()),
        sa.Column("reported_shareholder_count", sa.Integer()),
        sa.Column("reported_investment_count", sa.Integer()),
        sa.Column("reported_patent_count", sa.Integer()),
        sa.Column("reported_trademark_count", sa.Integer()),
        sa.Column("reported_copyright_count", sa.Integer()),
        sa.Column("reported_recruitment_count", sa.Integer()),
        sa.Column("reported_news_count", sa.Integer()),
        sa.Column("reported_institution_count", sa.Integer()),
        sa.Column("reported_funding_round_count", sa.Integer()),
        sa.Column("reported_total_funding_raw", sa.Text()),
        sa.Column("reported_valuation_raw", sa.Text()),
        sa.Column("latest_funding_round", sa.Text()),
        sa.Column("latest_funding_time_raw", sa.Text()),
        sa.Column("latest_funding_time", sa.Date()),
        sa.Column("latest_funding_amount_raw", sa.Text()),
        sa.Column("latest_funding_cny_wan", sa.Numeric(20, 2)),
        sa.Column("latest_funding_ratio", sa.Text()),
        sa.Column("latest_investors_raw", sa.Text()),
        sa.Column("latest_fa_info", sa.Text()),
        sa.Column("team_raw", sa.Text()),
        sa.Column(
            "snapshot_created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("raw_row_jsonb", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            _check_enum("snapshot_kind", COMPANY_SNAPSHOT_KINDS),
            name="ck_company_snapshot_kind",
        ),
        sa.CheckConstraint(
            "snapshot_kind != 'xlsx_import' OR source_row_number IS NOT NULL",
            name="ck_company_snapshot_xlsx_source_row_number",
        ),
    )
    op.create_index(
        "ix_company_snapshot_company_created",
        "company_snapshot",
        ["company_id", sa.text("snapshot_created_at DESC")],
    )
    op.create_index(
        "ix_company_snapshot_import_batch", "company_snapshot", ["import_batch_id"]
    )

    # -------------------------- company_team_member ------------------------
    op.create_table(
        "company_team_member",
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            sa.Text(),
            sa.ForeignKey("company.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_snapshot.snapshot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("member_order", sa.Integer(), nullable=False),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("raw_role", sa.Text()),
        sa.Column("raw_intro", sa.Text()),
        sa.Column("normalized_name", sa.Text()),
        sa.Column(
            "resolution_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unresolved'"),
        ),
        # Intentionally no FK in V002: professor table does not exist yet.
        # V003/V005 will add FK(company_team_member.resolved_professor_id -> professor.professor_id).
        sa.Column(
            "resolved_professor_id",
            sa.Text(),
            comment=(
                "FK to professor(professor_id) intentionally deferred until "
                "V003/V005 because professor table does not exist in V002."
            ),
        ),
        sa.Column("resolution_confidence", sa.Numeric(3, 2)),
        sa.Column("resolution_reason", sa.Text()),
        sa.Column("resolution_evidence", postgresql.JSONB()),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _check_enum("resolution_status", TEAM_RESOLUTION_STATUSES),
            name="ck_company_team_member_resolution_status",
        ),
    )
    op.create_index(
        "ix_company_team_member_company", "company_team_member", ["company_id"]
    )
    op.create_index(
        "ix_company_team_member_normalized_name",
        "company_team_member",
        ["normalized_name"],
        unique=False,
        postgresql_where=sa.text("normalized_name IS NOT NULL"),
    )
    op.create_index(
        "ix_company_team_member_resolution_open",
        "company_team_member",
        ["resolution_status"],
        unique=False,
        postgresql_where=sa.text("resolution_status IN ('unresolved','candidate')"),
    )

    # ----------------------------- company_fact ----------------------------
    op.create_table(
        "company_fact",
        sa.Column(
            "fact_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            sa.Text(),
            sa.ForeignKey("company.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fact_type", sa.Text(), nullable=False),
        sa.Column("value_raw", sa.Text()),
        sa.Column(
            "value_code",
            sa.Text(),
            sa.ForeignKey("taxonomy_vocabulary.code", ondelete="SET NULL"),
        ),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("evidence_span", sa.Text()),
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
        sa.CheckConstraint(
            _check_enum("fact_type", COMPANY_FACT_TYPES),
            name="ck_company_fact_type",
        ),
        sa.CheckConstraint(
            _check_enum("status", COMPANY_FACT_STATUSES),
            name="ck_company_fact_status",
        ),
        sa.CheckConstraint(
            _check_enum("source_kind", COMPANY_FACT_SOURCE_KINDS),
            name="ck_company_fact_source_kind",
        ),
    )
    op.create_index(
        "ix_company_fact_company_type", "company_fact", ["company_id", "fact_type"]
    )
    op.create_index(
        "ix_company_fact_value_code",
        "company_fact",
        ["value_code"],
        unique=False,
        postgresql_where=sa.text("value_code IS NOT NULL"),
    )

    # --------------------------- company_news_item -------------------------
    op.create_table(
        "company_news_item",
        sa.Column(
            "news_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            sa.Text(),
            sa.ForeignKey("company.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_page.page_id", ondelete="SET NULL"),
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_domain", sa.Text(), nullable=False),
        sa.Column("source_domain_tier", sa.Text(), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary_clean", sa.Text()),
        sa.Column("content_clean_path", sa.Text()),
        sa.Column(
            "is_company_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "refresh_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pipeline_run.run_id", ondelete="SET NULL"),
        ),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("source_url", name="uq_company_news_item_source_url"),
        sa.CheckConstraint(
            _check_enum("source_domain_tier", SOURCE_DOMAIN_TIERS),
            name="ck_company_news_item_source_domain_tier",
        ),
    )
    op.create_index(
        "ix_company_news_item_company_published",
        "company_news_item",
        ["company_id", sa.text("published_at DESC")],
    )
    op.create_index(
        "ix_company_news_item_source_domain", "company_news_item", ["source_domain"]
    )
    op.create_index(
        "ix_company_news_item_refresh_run",
        "company_news_item",
        ["refresh_run_id"],
        unique=False,
        postgresql_where=sa.text("refresh_run_id IS NOT NULL"),
    )

    # ------------------------- company_signal_event ------------------------
    op.create_table(
        "company_signal_event",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            sa.Text(),
            sa.ForeignKey("company.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("primary_news_id", postgresql.UUID(as_uuid=True)),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_subject_normalized", postgresql.JSONB(), nullable=False),
        sa.Column("event_summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column(
            "corroborating_news_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("dedup_key", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("deduped_into_id", postgresql.UUID(as_uuid=True)),
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
        sa.UniqueConstraint(
            "company_id",
            "event_type",
            "dedup_key",
            name="uq_company_signal_event_dedup",
        ),
        sa.CheckConstraint(
            _check_enum("event_type", COMPANY_SIGNAL_EVENT_TYPES),
            name="ck_company_signal_event_type",
        ),
        sa.CheckConstraint(
            _check_enum("status", COMPANY_SIGNAL_EVENT_STATUSES),
            name="ck_company_signal_event_status",
        ),
    )
    op.create_foreign_key(
        "fk_company_signal_event_primary_news",
        "company_signal_event",
        "company_news_item",
        ["primary_news_id"],
        ["news_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_company_signal_event_deduped_into",
        "company_signal_event",
        "company_signal_event",
        ["deduped_into_id"],
        ["event_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_company_signal_event_company_date",
        "company_signal_event",
        ["company_id", sa.text("event_date DESC")],
    )
    op.create_index(
        "ix_company_signal_event_type_date",
        "company_signal_event",
        ["event_type", sa.text("event_date DESC")],
    )


def downgrade() -> None:
    # Drop in reverse dependency order. Self-FKs are dropped with their tables.
    op.drop_table("company_signal_event")
    op.drop_table("company_news_item")
    op.drop_table("company_fact")
    op.drop_table("company_team_member")
    op.drop_table("company_snapshot")
    op.drop_table("company")
    op.drop_table("source_domain_tier_registry")
    op.drop_table("taxonomy_vocabulary")
