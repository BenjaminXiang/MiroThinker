import os

import pytest
import psycopg
from psycopg.rows import dict_row

from src.data_agents.storage.postgres.connection import resolve_dsn
from src.data_agents.storage.postgres.pipeline_run import (
    close_pipeline_run,
    open_pipeline_run,
)


_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"


def _dsn() -> str | None:
    raw = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not raw:
        return None
    return resolve_dsn(raw)


@pytest.fixture
def pg_conn():
    dsn = _dsn()
    if dsn is None:
        pytest.skip(_SKIP_REASON)
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        yield conn
        conn.rollback()


def test_open_returns_uuid_and_row_has_status_running(pg_conn):
    run_id = open_pipeline_run(
        pg_conn,
        run_kind="backfill_real",
        run_scope={"test": "unit"},
        triggered_by="test_pipeline_run.py",
    )
    row = pg_conn.execute(
        "SELECT status, finished_at, run_kind FROM pipeline_run WHERE run_id = %s",
        (run_id,),
    ).fetchone()
    assert row["status"] == "running"
    assert row["finished_at"] is None
    assert row["run_kind"] == "backfill_real"


def test_close_sets_finished_status_and_counts(pg_conn):
    run_id = open_pipeline_run(
        pg_conn, run_kind="backfill_real", run_scope={"test": "close"}
    )
    close_pipeline_run(
        pg_conn,
        run_id,
        status="succeeded",
        items_processed=42,
        items_failed=0,
    )
    row = pg_conn.execute(
        """
        SELECT status, items_processed, items_failed, finished_at IS NOT NULL AS is_closed
        FROM pipeline_run WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()
    assert row["status"] == "succeeded"
    assert row["items_processed"] == 42
    assert row["items_failed"] == 0
    assert row["is_closed"] is True


def test_close_accepts_error_summary(pg_conn):
    run_id = open_pipeline_run(pg_conn, run_kind="backfill_real", run_scope={})
    close_pipeline_run(
        pg_conn, run_id, status="failed", error_summary={"msg": "boom"}
    )
    row = pg_conn.execute(
        "SELECT status, error_summary FROM pipeline_run WHERE run_id = %s",
        (run_id,),
    ).fetchone()
    assert row["status"] == "failed"
    assert row["error_summary"]["msg"] == "boom"
