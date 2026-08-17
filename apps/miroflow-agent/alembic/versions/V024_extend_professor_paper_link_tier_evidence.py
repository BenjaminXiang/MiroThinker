"""extend professor_paper_link evidence source for homepage tiers

Revision ID: V024
Revises: V023
Create Date: 2026-05-15
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "V024"
down_revision: Union[str, None] = "V023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BASE_EVIDENCE_SOURCES = (
    "official_publication_page",
    "personal_homepage",
    "cv_pdf",
    "official_external_profile",
    "academic_api_with_affiliation_match",
)
_EXTENDED_EVIDENCE_SOURCES = (
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


def upgrade() -> None:
    op.drop_constraint(
        "ck_professor_paper_link_evidence_source_type",
        "professor_paper_link",
        type_="check",
    )
    op.create_check_constraint(
        "ck_professor_paper_link_evidence_source_type",
        "professor_paper_link",
        _check(_EXTENDED_EVIDENCE_SOURCES),
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE professor_paper_link
           SET evidence_source_type = CASE
               WHEN evidence_source_type = 'prof_homepage_tier2'
                   THEN 'official_publication_page'
               WHEN evidence_source_type = 'prof_homepage_tier3'
                   THEN 'personal_homepage'
               ELSE evidence_source_type
           END
         WHERE evidence_source_type IN ('prof_homepage_tier2', 'prof_homepage_tier3')
        """
    )
    op.drop_constraint(
        "ck_professor_paper_link_evidence_source_type",
        "professor_paper_link",
        type_="check",
    )
    op.create_check_constraint(
        "ck_professor_paper_link_evidence_source_type",
        "professor_paper_link",
        _check(_BASE_EVIDENCE_SOURCES),
    )
