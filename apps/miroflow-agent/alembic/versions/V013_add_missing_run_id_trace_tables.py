"""add missing run_id trace columns for company and paper_full_text

Revision ID: V013
Revises: V012
Create Date: 2026-05-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "V013"
down_revision: Union[str, None] = "V012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_RUN_ID = "00000000-0000-0000-0000-000000000001"
_TRACED_TABLES = ("company", "paper_full_text")


def upgrade() -> None:
    for table in _TRACED_TABLES:
        op.execute(
            f"""
            ALTER TABLE {table}
              ADD COLUMN IF NOT EXISTS run_id uuid
              REFERENCES pipeline_run(run_id) ON DELETE SET NULL;
            """
        )
        op.execute(
            f"""
            UPDATE {table}
               SET run_id = '{_LEGACY_RUN_ID}'::uuid
             WHERE run_id IS NULL;
            """
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_run_id ON {table}(run_id);"
        )


def downgrade() -> None:
    for table in reversed(_TRACED_TABLES):
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_run_id;")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS run_id;")
