"""add run_id trace columns to write-target tables (Round 7.16)

Revision ID: V007
Revises: V006
Create Date: 2026-04-18

Adds a nullable `run_id` column (FK to pipeline_run.run_id, ON DELETE SET NULL)
to every table that pipelines write to. Also creates one synthetic
pipeline_run row ("legacy_backfill") and backfills all existing rows
with its run_id so the column has non-empty meaning from day one.

NOT NULL is deliberately deferred to a future migration once all
writers in production pass run_id. See docs/plans/2026-04-18-008-pipeline-run-id-trace.md
§3.4 for the migration-safety rationale.
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401

revision = "V007"
down_revision = "V006"
branch_labels = None
depends_on = None


_TRACED_TABLES = (
    "professor",
    "professor_affiliation",
    "professor_fact",
    "professor_paper_link",
    "paper",
    "patent",
    "source_page",
)

_LEGACY_RUN_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # 1. Loosen the run_kind CHECK so 'legacy_backfill' is permitted.
    # Round 7.16 introduces new run_kind categories ('legacy_backfill' for
    # the one-time pre-trace seed, and 'professor_v3'/'backfill_real' for
    # future pipeline entrypoints). Drop + recreate the check with the
    # expanded whitelist.
    op.execute("ALTER TABLE pipeline_run DROP CONSTRAINT IF EXISTS ck_pipeline_run_kind;")
    op.execute(
        """
        ALTER TABLE pipeline_run ADD CONSTRAINT ck_pipeline_run_kind CHECK (
            run_kind = ANY (ARRAY[
                'import_xlsx','roster_crawl','profile_enrichment','news_refresh',
                'team_resolver','paper_link_resolver','projection_build',
                'answer_readiness_eval','quality_scan',
                'legacy_backfill','professor_v3','backfill_real'
            ])
        );
        """
    )

    # 2. Seed the legacy pipeline_run row (idempotent — safe to re-run).
    op.execute(
        f"""
        INSERT INTO pipeline_run (
            run_id, run_kind, run_scope, status,
            started_at, finished_at, triggered_by
        )
        VALUES (
            '{_LEGACY_RUN_ID}'::uuid,
            'legacy_backfill',
            '{{"note":"synthetic run created by V007 migration for pre-trace rows"}}'::jsonb,
            'succeeded',
            '2026-04-18 00:00:00+00',
            '2026-04-18 00:00:00+00',
            'round_7_16_migration'
        )
        ON CONFLICT (run_id) DO NOTHING;
        """
    )

    # 2. For each traced table: add column, backfill, index.
    for table in _TRACED_TABLES:
        op.execute(
            f"""
            ALTER TABLE {table}
              ADD COLUMN IF NOT EXISTS run_id uuid
              REFERENCES pipeline_run(run_id) ON DELETE SET NULL;
            """
        )
        # Backfill in a single UPDATE — miroflow_real is small enough.
        # For a bigger dataset we'd batch this in 10k chunks. See plan §3.4.
        op.execute(
            f"""
            UPDATE {table}
               SET run_id = '{_LEGACY_RUN_ID}'::uuid
             WHERE run_id IS NULL;
            """
        )
        # Index is NOT CONCURRENTLY because alembic runs inside a transaction.
        # For production deployment where CONCURRENTLY is required, split this
        # into a separate non-transactional migration.
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_run_id ON {table}(run_id);"
        )


def downgrade() -> None:
    for table in _TRACED_TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_run_id;")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS run_id;")
    # Deliberately do NOT delete the legacy pipeline_run row. It's audit history.
