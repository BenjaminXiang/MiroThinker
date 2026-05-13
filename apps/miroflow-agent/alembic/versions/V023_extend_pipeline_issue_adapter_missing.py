"""extend pipeline_issue.stage for professor seed adapter_missing

Revision ID: V023
Revises: V022
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "V023"
down_revision: Union[str, None] = "V022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BASE_STAGES = (
    "discovery",
    "name_extraction",
    "affiliation",
    "paper_attribution",
    "paper_quality",
    "research_directions",
    "identity_gate",
    "coverage",
    "data_quality_flag",
)
_EXTENDED_STAGES = (*_BASE_STAGES, "adapter_missing")


def _stage_check(values: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{value}'" for value in values)
    return f"stage IN ({quoted})"


def upgrade() -> None:
    op.drop_constraint(
        "pipeline_issue_stage_check",
        "pipeline_issue",
        type_="check",
    )
    op.create_check_constraint(
        "pipeline_issue_stage_check",
        "pipeline_issue",
        _stage_check(_EXTENDED_STAGES),
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE pipeline_issue
           SET stage = 'discovery',
               description = 'adapter_missing downgraded: '
                   || issue_id::text || ': ' || description
         WHERE stage = 'adapter_missing'
        """
    )
    op.drop_constraint(
        "pipeline_issue_stage_check",
        "pipeline_issue",
        type_="check",
    )
    op.create_check_constraint(
        "pipeline_issue_stage_check",
        "pipeline_issue",
        _stage_check(_BASE_STAGES),
    )
