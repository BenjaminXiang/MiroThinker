"""add professor admin action log

Revision ID: V025
Revises: V024
Create Date: 2026-05-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "V025"
down_revision: Union[str, None] = "V024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROFESSOR_ADMIN_ACTIONS = (
    "confirm_ready",
    "send_to_review",
    "flag_recrawl",
)


def _check_enum(column: str, values: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "professor_admin_action",
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("professor_id", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "observed_data_updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _check_enum("action", PROFESSOR_ADMIN_ACTIONS),
            name="ck_professor_admin_action_action",
        ),
    )
    op.create_foreign_key(
        "fk_professor_admin_action_professor",
        "professor_admin_action",
        "professor",
        ["professor_id"],
        ["professor_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_professor_admin_action_professor_created",
        "professor_admin_action",
        ["professor_id", "created_at"],
    )
    op.create_index(
        "idx_professor_admin_action_action_created",
        "professor_admin_action",
        ["action", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_professor_admin_action_action_created",
        table_name="professor_admin_action",
    )
    op.drop_index(
        "idx_professor_admin_action_professor_created",
        table_name="professor_admin_action",
    )
    op.drop_table("professor_admin_action")
