"""add professor lifecycle state

Revision ID: V030
Revises: V029
Create Date: 2026-05-23

Adds lifecycle state as an axis independent from professor quality. The
state defaults to active for existing rows, and a nullable self-reference
stores the merge target when a record is marked merged_to_other_school.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "V030"
down_revision: Union[str, None] = "V029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALID_PROFESSOR_LIFECYCLE_STATES = (
    "active",
    "archived",
    "merged_to_other_school",
)
PREVIOUS_PROFESSOR_ADMIN_ACTIONS = (
    "confirm_ready",
    "send_to_review",
    "flag_recrawl",
)
PROFESSOR_ADMIN_ACTIONS = (
    *PREVIOUS_PROFESSOR_ADMIN_ACTIONS,
    "set_lifecycle_state",
)


def upgrade() -> None:
    op.add_column(
        "professor",
        sa.Column(
            "lifecycle_state",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
    )
    op.add_column(
        "professor",
        sa.Column("lifecycle_merged_into_id", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_professor_lifecycle_state",
        "professor",
        f"lifecycle_state IN {VALID_PROFESSOR_LIFECYCLE_STATES!r}",
    )
    op.create_foreign_key(
        "fk_professor_lifecycle_merged_into",
        "professor",
        "professor",
        ["lifecycle_merged_into_id"],
        ["professor_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_professor_lifecycle_state",
        "professor",
        ["lifecycle_state"],
    )
    op.drop_constraint(
        "ck_professor_admin_action_action",
        "professor_admin_action",
        type_="check",
    )
    op.create_check_constraint(
        "ck_professor_admin_action_action",
        "professor_admin_action",
        f"action IN {PROFESSOR_ADMIN_ACTIONS!r}",
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE professor_admin_action
           SET action = 'flag_recrawl',
               note = COALESCE('set_lifecycle_state downgraded: ' || note,
                               'set_lifecycle_state downgraded')
         WHERE action = 'set_lifecycle_state'
        """
    )
    op.drop_constraint(
        "ck_professor_admin_action_action",
        "professor_admin_action",
        type_="check",
    )
    op.create_check_constraint(
        "ck_professor_admin_action_action",
        "professor_admin_action",
        f"action IN {PREVIOUS_PROFESSOR_ADMIN_ACTIONS!r}",
    )
    op.drop_index("ix_professor_lifecycle_state", table_name="professor")
    op.drop_constraint(
        "fk_professor_lifecycle_merged_into",
        "professor",
        type_="foreignkey",
    )
    op.drop_constraint("ck_professor_lifecycle_state", "professor", type_="check")
    op.drop_column("professor", "lifecycle_merged_into_id")
    op.drop_column("professor", "lifecycle_state")
