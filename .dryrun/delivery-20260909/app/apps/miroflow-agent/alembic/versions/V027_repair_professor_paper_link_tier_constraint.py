"""repair professor_paper_link evidence source tier constraint

Revision ID: V027
Revises: V026
Create Date: 2026-05-15
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "V027"
down_revision: Union[str, None] = "V026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONSTRAINT_NAME = "ck_professor_paper_link_evidence_source_type"
_EVIDENCE_SOURCES = (
    "official_publication_page",
    "personal_homepage",
    "prof_homepage_tier2",
    "prof_homepage_tier3",
    "cv_pdf",
    "official_external_profile",
    "academic_api_with_affiliation_match",
)


def _check(values: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{value}'" for value in values)
    return f"evidence_source_type IN ({quoted})"


def _recreate_constraint() -> None:
    op.execute(
        f"""
        ALTER TABLE professor_paper_link
        DROP CONSTRAINT IF EXISTS {_CONSTRAINT_NAME}
        """
    )
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "professor_paper_link",
        _check(_EVIDENCE_SOURCES),
    )


def upgrade() -> None:
    _recreate_constraint()


def downgrade() -> None:
    # V026's intended schema already includes the tier evidence values.
    # Keep downgrade idempotent and do not recreate the historical drift.
    _recreate_constraint()
