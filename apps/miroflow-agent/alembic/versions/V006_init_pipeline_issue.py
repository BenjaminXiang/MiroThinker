"""init pipeline_issue: human-in-loop bug report table for pipeline verification console

Revision ID: V006
Revises: V005b
Create Date: 2026-04-18
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401

revision = "V006"
down_revision = "V005b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE pipeline_issue (
            issue_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            professor_id text REFERENCES professor(professor_id) ON DELETE SET NULL,
            link_id uuid REFERENCES professor_paper_link(link_id) ON DELETE SET NULL,
            institution text,
            stage text NOT NULL CHECK (stage IN (
                'discovery','name_extraction','affiliation','paper_attribution',
                'paper_quality','research_directions','identity_gate','coverage',
                'data_quality_flag'
            )),
            severity text NOT NULL CHECK (severity IN ('high','medium','low')),
            description text NOT NULL,
            description_hash text GENERATED ALWAYS AS (md5(description)) STORED,
            evidence_snapshot jsonb,
            reported_by text NOT NULL,
            reported_at timestamptz NOT NULL DEFAULT now(),
            resolved boolean NOT NULL DEFAULT false,
            resolved_at timestamptz,
            resolution_notes text,
            resolution_round text,
            CONSTRAINT ck_pipeline_issue_has_target CHECK (
                professor_id IS NOT NULL OR link_id IS NOT NULL OR institution IS NOT NULL
            )
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_pipeline_issue_open
            ON pipeline_issue (
                COALESCE(professor_id,''),
                COALESCE(link_id::text,''),
                COALESCE(institution,''),
                stage,
                reported_by,
                description_hash
            ) WHERE resolved = false;
        """
    )
    op.execute(
        "CREATE INDEX idx_pipeline_issue_unresolved ON pipeline_issue(resolved, reported_at DESC);"
    )
    op.execute(
        "CREATE INDEX idx_pipeline_issue_stage ON pipeline_issue(stage, resolved);"
    )
    op.execute(
        "CREATE INDEX idx_pipeline_issue_professor ON pipeline_issue(professor_id) WHERE professor_id IS NOT NULL;"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pipeline_issue CASCADE;")
