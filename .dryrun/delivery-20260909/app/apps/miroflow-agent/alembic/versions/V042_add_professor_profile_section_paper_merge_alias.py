"""Add Professor profile sections and Paper merge aliases.

Revision ID: V042
Revises: V041
Create Date: 2026-06-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "V042"
down_revision: Union[str, None] = "V041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROFESSOR_PROFILE_SECTION_TYPES = (
    "research_overview",
    "research_progress",
    "education_narrative",
    "work_narrative",
    "honors_narrative",
    "academic_service_narrative",
    "student_work_narrative",
)

PROFILE_SECTION_LANGUAGES = ("zh", "en", "mixed", "unknown")

PROFILE_SECTION_GENERATION_METHODS = (
    "official_extract",
    "llm_translation",
    "llm_summary",
    "manual",
)


def upgrade() -> None:
    op.create_table(
        "professor_profile_section",
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("professor_id", sa.Text(), nullable=False),
        sa.Column("section_type", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_page_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_language", sa.Text(), nullable=True),
        sa.Column("source_text_hash", sa.Text(), nullable=True),
        sa.Column("source_span", sa.Text(), nullable=True),
        sa.Column("generation_method", sa.Text(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            f"section_type IN {PROFESSOR_PROFILE_SECTION_TYPES!r}",
            name="ck_professor_profile_section_type",
        ),
        sa.CheckConstraint(
            f"language IN {PROFILE_SECTION_LANGUAGES!r}",
            name="ck_professor_profile_section_language",
        ),
        sa.CheckConstraint(
            f"generation_method IN {PROFILE_SECTION_GENERATION_METHODS!r}",
            name="ck_professor_profile_section_generation_method",
        ),
        sa.CheckConstraint(
            "NULLIF(BTRIM(content), '') IS NOT NULL",
            name="ck_professor_profile_section_content_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["professor_id"],
            ["professor.professor_id"],
            ondelete="CASCADE",
            name="fk_professor_profile_section_professor",
        ),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["source_page.page_id"],
            ondelete="SET NULL",
            name="fk_professor_profile_section_source_page",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["pipeline_run.run_id"],
            ondelete="SET NULL",
            name="fk_professor_profile_section_run",
        ),
        sa.UniqueConstraint(
            "professor_id",
            "section_type",
            "language",
            "source_text_hash",
            name="uq_professor_profile_section_source",
        ),
    )
    op.create_index(
        "ix_professor_profile_section_professor_type",
        "professor_profile_section",
        ["professor_id", "section_type", "language"],
    )
    op.create_index(
        "ix_professor_profile_section_source_page",
        "professor_profile_section",
        ["source_page_id"],
    )
    op.create_index(
        "ix_professor_profile_section_run",
        "professor_profile_section",
        ["run_id"],
    )

    op.create_table(
        "paper_merge_alias",
        sa.Column(
            "alias_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("old_paper_id", sa.Text(), nullable=False),
        sa.Column("canonical_paper_id", sa.Text(), nullable=False),
        sa.Column("merge_reason", sa.Text(), nullable=False),
        sa.Column("evidence_source", sa.Text(), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "old_paper_id <> canonical_paper_id",
            name="ck_paper_merge_alias_not_self",
        ),
        sa.CheckConstraint(
            "NULLIF(BTRIM(merge_reason), '') IS NOT NULL",
            name="ck_paper_merge_alias_reason_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["old_paper_id"],
            ["paper.paper_id"],
            ondelete="CASCADE",
            name="fk_paper_merge_alias_old_paper",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_paper_id"],
            ["paper.paper_id"],
            ondelete="CASCADE",
            name="fk_paper_merge_alias_canonical_paper",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["pipeline_run.run_id"],
            ondelete="SET NULL",
            name="fk_paper_merge_alias_run",
        ),
        sa.UniqueConstraint(
            "old_paper_id",
            name="uq_paper_merge_alias_old_paper",
        ),
    )
    op.create_index(
        "ix_paper_merge_alias_canonical_paper",
        "paper_merge_alias",
        ["canonical_paper_id"],
    )
    op.create_index(
        "ix_paper_merge_alias_run",
        "paper_merge_alias",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_paper_merge_alias_run", table_name="paper_merge_alias")
    op.drop_index(
        "ix_paper_merge_alias_canonical_paper",
        table_name="paper_merge_alias",
    )
    op.drop_table("paper_merge_alias")

    op.drop_index(
        "ix_professor_profile_section_run",
        table_name="professor_profile_section",
    )
    op.drop_index(
        "ix_professor_profile_section_source_page",
        table_name="professor_profile_section",
    )
    op.drop_index(
        "ix_professor_profile_section_professor_type",
        table_name="professor_profile_section",
    )
    op.drop_table("professor_profile_section")
