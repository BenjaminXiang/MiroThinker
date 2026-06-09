"""Allow review-gated company signal events.

Revision ID: V038
Revises: V037
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op


revision = "V038"
down_revision = "V037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_company_signal_event_status",
        "company_signal_event",
        type_="check",
    )
    op.create_check_constraint(
        "ck_company_signal_event_status",
        "company_signal_event",
        "status IN ('active', 'needs_review', 'deprecated', 'deduped_into')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE company_signal_event "
        "SET status = 'deprecated' "
        "WHERE status = 'needs_review'"
    )
    op.drop_constraint(
        "ck_company_signal_event_status",
        "company_signal_event",
        type_="check",
    )
    op.create_check_constraint(
        "ck_company_signal_event_status",
        "company_signal_event",
        "status IN ('active', 'deprecated', 'deduped_into')",
    )
