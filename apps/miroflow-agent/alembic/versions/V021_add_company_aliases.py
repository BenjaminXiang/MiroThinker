"""convert company aliases to JSONB

Revision ID: V021
Revises: V020
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V021"
down_revision: Union[str, None] = "V020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "company",
        "aliases",
        server_default=None,
        existing_type=postgresql.ARRAY(sa.Text()),
        existing_nullable=False,
    )
    op.execute(
        """
        ALTER TABLE company
        ALTER COLUMN aliases TYPE jsonb
        USING COALESCE(to_jsonb(aliases), '[]'::jsonb)
        """
    )
    op.alter_column(
        "company",
        "aliases",
        server_default=sa.text("'[]'::jsonb"),
        existing_type=postgresql.JSONB(),
        existing_nullable=False,
    )
    op.create_index(
        "ix_company_aliases_gin",
        "company",
        ["aliases"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_company_aliases_gin", table_name="company")
    op.alter_column(
        "company",
        "aliases",
        server_default=None,
        existing_type=postgresql.JSONB(),
        existing_nullable=False,
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pg_temp._jsonb_text_array(value jsonb)
        RETURNS text[]
        LANGUAGE sql
        IMMUTABLE
        AS $$
            SELECT COALESCE(array_agg(element), '{}'::text[])
            FROM jsonb_array_elements_text(
                CASE
                    WHEN jsonb_typeof(value) = 'array' THEN value
                    ELSE '[]'::jsonb
                END
            ) AS element
        $$;
        """
    )
    op.execute(
        """
        ALTER TABLE company
        ALTER COLUMN aliases TYPE text[]
        USING pg_temp._jsonb_text_array(aliases)
        """
    )
    op.alter_column(
        "company",
        "aliases",
        server_default=sa.text("'{}'::text[]"),
        existing_type=postgresql.ARRAY(sa.Text()),
        existing_nullable=False,
    )
