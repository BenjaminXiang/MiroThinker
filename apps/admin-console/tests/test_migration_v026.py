"""V026 patent page-only canonical migration checks."""

from __future__ import annotations

import uuid

from .conftest import (
    _alembic_config,
    _load_alembic,
    _load_postgres_dependencies,
    _psycopg_dsn,
    _raw_database_url,
)


def test_v026_patent_number_is_nullable_for_page_only_rows() -> None:
    alembic_command, _ = _load_alembic()
    config = _alembic_config()
    pg_dsn = _psycopg_dsn(_raw_database_url())
    psycopg, _, _, _ = _load_postgres_dependencies()
    patent_id = f"PAT-V026-{uuid.uuid4().hex[:8]}"
    run_id = "11111111-1111-1111-1111-111111111111"

    alembic_command.upgrade(config, "head")
    try:
        with psycopg.connect(pg_dsn) as conn:
            nullable = conn.execute(
                """
                SELECT is_nullable
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = 'patent'
                   AND column_name = 'patent_number'
                """
            ).fetchone()[0]
            assert nullable == "YES"

            conn.execute(
                """
                INSERT INTO pipeline_run (
                    run_id,
                    run_kind,
                    run_scope,
                    status,
                    started_at,
                    triggered_by
                )
                VALUES (%s, 'backfill_real', '{}'::jsonb, 'running', now(), 'test')
                ON CONFLICT (run_id) DO NOTHING
                """,
                (run_id,),
            )
            conn.execute(
                """
                INSERT INTO patent (
                    patent_id,
                    patent_number,
                    title_clean,
                    title_raw,
                    identity_status,
                    quality_status,
                    run_id
                )
                VALUES (%s, NULL, %s, %s, 'unverified', 'needs_enrichment', %s)
                """,
                (
                    patent_id,
                    "A title-only professor-page patent",
                    "A title-only professor-page patent",
                    run_id,
                ),
            )
            row = conn.execute(
                "SELECT patent_number, quality_status FROM patent WHERE patent_id = %s",
                (patent_id,),
            ).fetchone()
            assert row == (None, "needs_enrichment")
    finally:
        with psycopg.connect(pg_dsn) as conn:
            conn.execute("DELETE FROM patent WHERE patent_id = %s", (patent_id,))
            conn.commit()
        alembic_command.downgrade(config, "base")
