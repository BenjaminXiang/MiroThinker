"""relax paper.title_clean NOT NULL (Round 7.12')

Revision ID: V008
Revises: V007
Create Date: 2026-04-19

Round 7.12' introduces a title-quality guard that detects author lists
and editorial bios glued into paper.title_clean and replaces them with
NULL (so downstream readers show "untitled" rather than misleading
fake titles). The V004 schema declared title_clean NOT NULL because at
import time every paper has a title string — but that string isn't
guaranteed to be a valid title. This migration drops the NOT NULL so
the cleanup script can set rejected rows to NULL.

Reversible: ALTER COLUMN SET NOT NULL in down() after ensuring no NULLs.
If there are NULLs when downgrading, the ALTER will fail by design —
operator must decide whether to repopulate or drop the NULL rows.
"""
from alembic import op

revision = "V008"
down_revision = "V007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE paper ALTER COLUMN title_clean DROP NOT NULL")


def downgrade() -> None:
    # Will raise if any NULLs remain; that's intentional — explicit remediation required.
    op.execute("ALTER TABLE paper ALTER COLUMN title_clean SET NOT NULL")
