"""add company enrichment source and product tables

Revision ID: V033
Revises: V032
Create Date: 2026-05-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V033"
down_revision: Union[str, None] = "V032"
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
        "company_news_item",
        sa.Column("source_adapter", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_news_item",
        sa.Column(
            "extraction_diagnostics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "company_product",
        sa.Column("product_id", sa.Text(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Text(),
            sa.ForeignKey("company.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("official_product_url", sa.Text(), nullable=True),
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
            "canonical_name",
            name="uq_company_product_company_name",
        ),
        sa.CheckConstraint(
            _check_enum("quality_status", QUALITY_STATUSES),
            name="ck_company_product_quality_status",
        ),
    )
    op.create_index(
        "ix_company_product_company_status",
        "company_product",
        ["company_id", "quality_status"],
    )

    op.create_table(
        "company_product_evidence",
        sa.Column(
            "evidence_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "product_id",
            sa.Text(),
            sa.ForeignKey("company_product.product_id", ondelete="CASCADE"),
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
        "ix_company_product_evidence_product_field",
        "company_product_evidence",
        ["product_id", "field_name"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_product_evidence_product_field",
        table_name="company_product_evidence",
    )
    op.drop_table("company_product_evidence")
    op.drop_index("ix_company_product_company_status", table_name="company_product")
    op.drop_table("company_product")
    op.drop_column("company_news_item", "extraction_diagnostics")
    op.drop_column("company_news_item", "source_adapter")
