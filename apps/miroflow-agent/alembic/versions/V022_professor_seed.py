"""init professor_seed: admin-managed roster URL registry

Revision ID: V022
Revises: V021
Create Date: 2026-05-10

Per OpenSpec change `prof-seed-admin-console` (Phase A):

- Schema codified by Professor Requirement Review §3.1 Theme 2 (locked
  2026-05-10) — 5 user-visible columns + auto timestamps + surrogate id.
- `last_run_status` uses 5 enum values, including `adapter_missing`.
  Phase A only writes `never_run`; status transitions are wired in Phase B
  (pipeline integration).

Explicitly excluded in this round (deferred to Phase B):
- `pipeline_issue.stage` extension to include `adapter_missing`
- backfill from `scripts/e2e_seeds/*.md` markdown files (admin enters
  initial seeds manually)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V022"
down_revision: Union[str, None] = "V021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Kept in Python so application code (Pydantic) and tests can import a
# single source of truth for the enum values.
PROFESSOR_SEED_LAST_RUN_STATUSES = [
    "success",
    "failure",
    "in_progress",
    "never_run",
    "adapter_missing",
]


def upgrade() -> None:
    op.create_table(
        "professor_seed",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("school", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("seed_url", sa.Text(), nullable=False),
        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "last_run_status",
            sa.Text(),
            nullable=False,
            server_default="never_run",
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
    )

    op.create_check_constraint(
        "ck_professor_seed_last_run_status",
        "professor_seed",
        f"last_run_status IN {tuple(PROFESSOR_SEED_LAST_RUN_STATUSES)!r}",
    )

    op.create_index(
        "ix_professor_seed_last_run_status",
        "professor_seed",
        ["last_run_status"],
    )

    # seed_url is the seed's natural identifier; prevent accidental duplicates.
    op.create_index(
        "uq_professor_seed_url",
        "professor_seed",
        ["seed_url"],
        unique=True,
    )

    # Common admin filter: list seeds for one school.
    op.create_index(
        "ix_professor_seed_school",
        "professor_seed",
        ["school"],
    )


def downgrade() -> None:
    op.drop_index("ix_professor_seed_school", table_name="professor_seed")
    op.drop_index("uq_professor_seed_url", table_name="professor_seed")
    op.drop_index(
        "ix_professor_seed_last_run_status", table_name="professor_seed"
    )
    op.drop_constraint(
        "ck_professor_seed_last_run_status",
        "professor_seed",
        type_="check",
    )
    op.drop_table("professor_seed")
