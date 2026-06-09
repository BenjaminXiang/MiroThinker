"""Allow DBLP as a paper canonical source.

Revision ID: V040
Revises: V039
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "V040"
down_revision: Union[str, None] = "V039"
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
    "dblp",
)
_DOWNGRADE_SOURCES = (
    "openalex",
    "semantic_scholar",
    "crossref",
    "official_page",
    "manual",
    "prof_page_only",
    "arxiv",
    "web_search",
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
           SET canonical_source = 'manual'
         WHERE canonical_source = 'dblp'
        """
    )
    op.drop_constraint(_CONSTRAINT, "paper", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "paper",
        _source_check(_DOWNGRADE_SOURCES),
    )
