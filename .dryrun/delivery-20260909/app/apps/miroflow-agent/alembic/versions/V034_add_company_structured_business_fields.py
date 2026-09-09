"""add structured company business fields

Revision ID: V034
Revises: V033
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V034"
down_revision: Union[str, None] = "V033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUALITY_STATUSES = (
    "ready",
    "needs_review",
    "low_confidence",
    "needs_enrichment",
    "partial",
    "rejected",
)


def _check_enum(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.add_column(
        "company_product",
        sa.Column("product_category", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_product",
        sa.Column(
            "target_customers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "company_product",
        sa.Column(
            "application_scenarios",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "company_product",
        sa.Column(
            "technical_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.create_table(
        "company_application_scenario",
        sa.Column("scenario_id", sa.Text(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Text(),
            sa.ForeignKey("company.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "related_product_id",
            sa.Text(),
            sa.ForeignKey("company_product.product_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("scenario_name", sa.Text(), nullable=False),
        sa.Column("scenario_category", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_customer", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "quality_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'needs_review'"),
        ),
        sa.Column(
            "confidence",
            sa.Numeric(3, 2),
            nullable=False,
            server_default=sa.text("0.50"),
        ),
        sa.Column(
            "first_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_refreshed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
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
        sa.UniqueConstraint(
            "company_id",
            "scenario_name",
            name="uq_company_application_scenario_company_name",
        ),
        sa.CheckConstraint(
            _check_enum("quality_status", QUALITY_STATUSES),
            name="ck_company_application_scenario_quality_status",
        ),
    )
    op.create_index(
        "ix_company_application_scenario_company_status",
        "company_application_scenario",
        ["company_id", "quality_status"],
    )

    op.create_table(
        "company_application_scenario_evidence",
        sa.Column(
            "evidence_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "scenario_id",
            sa.Text(),
            sa.ForeignKey("company_application_scenario.scenario_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column(
            "source_page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_page.page_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("evidence_span", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("extractor_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_company_application_scenario_evidence_scenario_field",
        "company_application_scenario_evidence",
        ["scenario_id", "field_name"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_application_scenario_evidence_scenario_field",
        table_name="company_application_scenario_evidence",
    )
    op.drop_table("company_application_scenario_evidence")
    op.drop_index(
        "ix_company_application_scenario_company_status",
        table_name="company_application_scenario",
    )
    op.drop_table("company_application_scenario")
    op.drop_column("company_product", "technical_tags")
    op.drop_column("company_product", "application_scenarios")
    op.drop_column("company_product", "target_customers")
    op.drop_column("company_product", "product_category")
