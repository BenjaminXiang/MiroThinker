"""Allow pack_backfill as a paper canonical source.

The serving-pack backfill (P2 of unify-collection-as-source-of-truth) imports
papers that were built from external source bundles. Mapping them onto an
existing value (e.g. ``openalex``) would misstate provenance, so the enum gains
an explicit value.

Revision ID: V043
Revises: V042
Create Date: 2026-10-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "V043"
down_revision: Union[str, None] = "V042"
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
    "pack_backfill",
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
    "dblp",
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
         WHERE canonical_source = 'pack_backfill'
        """
    )
    op.drop_constraint(_CONSTRAINT, "paper", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "paper",
        _source_check(_DOWNGRADE_SOURCES),
    )
