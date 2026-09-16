"""Relax the projection columns the D0-a cleaning rules may publish as absent.

Revision ID: C2_0015
Revises: C2_0014
Create Date: 2026-09-16

D0-a (`data-cleaning-batch1`) made nine projection fields optional in the typed
models (placeholder-only values publish as absent), and the venue follow-up
(`fee2fc85`/`41a8d96e`) added `paper.venue`.  The PostgreSQL projection tables
still carried NOT NULL for those columns, which only surfaced when a build
reached the persistence stage for the first time (run16 attempt 6):

    psycopg.errors.NotNullViolation: null value in column
    "technology_route_summary" of relation "current_projection"

`paper.title` and `patent.title` stay NOT NULL: those model fields are still
required and no cleaning rule can null them.

Downgrade restores NOT NULL; it fails if any row already carries NULL in the
affected column (restore the data first).
"""

from __future__ import annotations

from typing import Final, Sequence, Union

from alembic import op


revision: str = "C2_0015"
down_revision: Union[str, None] = "C2_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reviewed scope: (schema, table, column) — the optional projection fields.
TARGETS: Final[tuple[tuple[str, str, str], ...]] = (
    ("company", "current_projection", "profile_summary"),
    ("company", "current_projection", "technology_route_summary"),
    ("paper", "current_projection", "venue"),
    ("professor", "current_projection", "department"),
    ("professor", "current_projection", "email"),
    ("professor", "current_projection", "homepage"),
    ("professor", "current_projection", "paper_summary"),
    ("professor", "current_projection", "patent_summary"),
    ("professor", "current_projection", "profile_summary"),
    ("professor", "current_projection", "title"),
)


def upgrade() -> None:
    for schema, table, column in TARGETS:
        op.execute(
            f'ALTER TABLE {schema}.{table} ALTER COLUMN "{column}" DROP NOT NULL'
        )


def downgrade() -> None:
    for schema, table, column in TARGETS:
        op.execute(
            f'ALTER TABLE {schema}.{table} ALTER COLUMN "{column}" SET NOT NULL'
        )
