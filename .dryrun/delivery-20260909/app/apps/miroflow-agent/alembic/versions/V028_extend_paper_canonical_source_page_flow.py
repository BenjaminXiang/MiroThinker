"""extend paper canonical_source for prof-page paper flow

Revision ID: V028
Revises: V027
Create Date: 2026-05-13

The prof-paper-patent-from-page-flow change writes professor-page-only
publications with canonical_source='prof_page_only'. Title resolution can
also resolve directly from arXiv. V004's original paper canonical_source
CHECK predated those runtime sources.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "V028"
down_revision: Union[str, None] = "V027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONSTRAINT = "ck_paper_canonical_source"
_UPGRADE_SOURCES = (
    "openalex",
    "semantic_scholar",
    "crossref",
    "official_page",
    "manual",
    "prof_page_only",
    "arxiv",
    "web_search",
)
_DOWNGRADE_SOURCES = (
    "openalex",
    "semantic_scholar",
    "crossref",
    "official_page",
    "manual",
)


def _source_check(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"canonical_source IN ({quoted})"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "paper", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "paper",
        _source_check(_UPGRADE_SOURCES),
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE paper
           SET canonical_source = 'official_page'
         WHERE canonical_source = 'prof_page_only'
        """
    )
    op.execute(
        """
        UPDATE paper
           SET canonical_source = 'manual'
         WHERE canonical_source IN ('arxiv', 'web_search')
        """
    )
    op.drop_constraint(_CONSTRAINT, "paper", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "paper",
        _source_check(_DOWNGRADE_SOURCES),
    )
