"""Relax the two shape CHECKs that reject a NULL venue/department.

Revision ID: C2_0016
Revises: C2_0015
Create Date: 2026-09-16

C2_0015 dropped NOT NULL from the optional projection columns, but two shape
constraints still demanded a present value and only surfaced when a build
reached persistence (run16 attempt 7):

    psycopg.errors.CheckViolation: new row for relation "current_projection"
    violates check constraint "ck_paper_current_projection_venue_shape"

Both use `COALESCE(is_valid_..., false)`, which is false for NULL.  Every other
`*_nonempty` check on the relaxed columns is NULL-tolerant (`btrim(NULL) <> ''`
evaluates to NULL, which a CHECK accepts), and the sub-object tables
(`paper.publication`, `professor.affiliation_history`) already carry the
`(X IS NULL) OR ...` form — verified by sweeping all four schemas' constraints.

Downgrade restores the strict predicate; it fails if any row carries NULL in the
affected column (restore the data first).
"""

from __future__ import annotations

from typing import Final, Sequence, Union

from alembic import op


revision: str = "C2_0016"
down_revision: Union[str, None] = "C2_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reviewed scope: (schema, table, constraint, column, shape function).
TARGETS: Final[tuple[tuple[str, str, str, str, str], ...]] = (
    (
        "paper",
        "current_projection",
        "ck_paper_current_projection_venue_shape",
        "venue",
        "knowledge.is_valid_projection_named_reference",
    ),
    (
        "professor",
        "current_projection",
        "ck_professor_current_projection_department_shape",
        "department",
        "knowledge.is_valid_projection_named_reference",
    ),
)


def _predicate(column: str, function: str, *, allow_null: bool) -> str:
    shape = f"COALESCE({function}({column}), false)"
    return f"({column} IS NULL) OR {shape}" if allow_null else shape


def upgrade() -> None:
    for schema, table, constraint, column, function in TARGETS:
        op.execute(f'ALTER TABLE {schema}.{table} DROP CONSTRAINT "{constraint}"')
        op.execute(
            f'ALTER TABLE {schema}.{table} ADD CONSTRAINT "{constraint}" '
            f"CHECK ({_predicate(column, function, allow_null=True)})"
        )


def downgrade() -> None:
    for schema, table, constraint, column, function in TARGETS:
        op.execute(f'ALTER TABLE {schema}.{table} DROP CONSTRAINT "{constraint}"')
        op.execute(
            f'ALTER TABLE {schema}.{table} ADD CONSTRAINT "{constraint}" '
            f"CHECK ({_predicate(column, function, allow_null=False)})"
        )
