"""RED-phase tests for M2.4 Unit 2 — paper_full_text writer.

Source of truth: docs/plans/2026-04-21-004-m2.4-homepage-paper-ingest-orchestrator.md Unit 2.

Mix of unit tests (mocked psycopg) and integration tests (real DB, skip if
DATABASE_URL_TEST unset). Mirror the skip pattern from
tests/storage/test_pipeline_run.py.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from src.data_agents.paper.full_text_fetcher import FullTextExtract
from src.data_agents.storage.postgres.paper_full_text import (
    paper_full_text_exists,
    upsert_paper_full_text,
)

_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"


def _dsn() -> str | None:
    raw = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    return raw or None


# =============================================================================
# Unit tests (mocked Connection)
# =============================================================================


def test_upsert_paper_full_text_executes_insert_on_conflict():
    conn = MagicMock()
    extract = FullTextExtract(
        paper_id="paper:arxiv:2310.12345",
        abstract="Abstract text.",
        intro="Intro text.",
        pdf_url="https://arxiv.org/pdf/2310.12345.pdf",
        pdf_sha256="a" * 64,
        source="arxiv",
        fetch_error=None,
    )
    upsert_paper_full_text(conn, paper_id="paper:arxiv:2310.12345", extract=extract)
    # The writer must call conn.execute at least once.
    assert conn.execute.called
    # The SQL should contain ON CONFLICT for idempotent upsert.
    call_args = conn.execute.call_args
    sql = call_args[0][0]
    assert "ON CONFLICT" in sql.upper()
    assert "paper_full_text" in sql.lower()


def test_upsert_paper_full_text_passes_all_fields():
    conn = MagicMock()
    extract = FullTextExtract(
        paper_id="p1",
        abstract="abs",
        intro="intro",
        pdf_url="u",
        pdf_sha256="s" * 64,
        source="arxiv",
        fetch_error=None,
    )
    upsert_paper_full_text(conn, paper_id="p1", extract=extract)
    # Params passed should include all extract fields in some order.
    call_args = conn.execute.call_args
    params = call_args[0][1]
    assert "p1" in params
    assert "abs" in params
    assert "intro" in params
    assert "u" in params
    assert "s" * 64 in params
    assert "arxiv" in params


def test_upsert_paper_full_text_handles_none_values():
    conn = MagicMock()
    extract = FullTextExtract(
        paper_id="p_failed",
        abstract=None,
        intro=None,
        pdf_url=None,
        pdf_sha256=None,
        source="failed",
        fetch_error="http_404",
    )
    # Should not raise on None content fields.
    upsert_paper_full_text(conn, paper_id="p_failed", extract=extract)
    assert conn.execute.called


def test_upsert_paper_full_text_does_not_commit():
    """Writer must NOT call conn.commit(). Caller owns transaction."""
    conn = MagicMock()
    extract = FullTextExtract(
        paper_id="p",
        abstract=None,
        intro=None,
        pdf_url=None,
        pdf_sha256=None,
        source="failed",
        fetch_error="no_arxiv_id",
    )
    upsert_paper_full_text(conn, paper_id="p", extract=extract)
    conn.commit.assert_not_called()


def test_paper_full_text_exists_returns_bool():
    """paper_full_text_exists queries and returns bool."""
    conn = MagicMock()
    result_cursor = MagicMock()
    result_cursor.fetchone.return_value = (1,)  # row exists
    conn.execute.return_value = result_cursor
    assert paper_full_text_exists(conn, "some_paper_id") is True


def test_paper_full_text_exists_false_when_no_row():
    conn = MagicMock()
    result_cursor = MagicMock()
    result_cursor.fetchone.return_value = None
    conn.execute.return_value = result_cursor
    assert paper_full_text_exists(conn, "missing") is False


# =============================================================================
# Integration tests (real DB)
# =============================================================================


@pytest.fixture
def pg_conn():
    import psycopg
    from psycopg.rows import dict_row

    dsn = _dsn()
    if dsn is None:
        pytest.skip(_SKIP_REASON)
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        yield conn
        conn.rollback()


def test_integration_upsert_and_read_back(pg_conn):
    """Full roundtrip: upsert → SELECT confirms fields."""
    # Requires V011 migration applied + at least one paper row to satisfy FK.
    # Skip if the required schema isn't present.
    try:
        pg_conn.execute("SELECT 1 FROM paper_full_text LIMIT 1")
    except Exception:
        pytest.skip("paper_full_text table not present; run alembic upgrade V011")

    # Need a paper row for FK; use the first existing one or skip.
    paper = pg_conn.execute(
        "SELECT paper_id FROM paper LIMIT 1"
    ).fetchone()
    if paper is None:
        pytest.skip("no paper rows; cannot test FK")
    paper_id = paper["paper_id"]

    extract = FullTextExtract(
        paper_id=paper_id,
        abstract="Integration test abstract.",
        intro="Integration test intro.",
        pdf_url="https://example.com/test.pdf",
        pdf_sha256="b" * 64,
        source="arxiv",
        fetch_error=None,
    )
    upsert_paper_full_text(pg_conn, paper_id=paper_id, extract=extract)
    row = pg_conn.execute(
        "SELECT abstract, intro, source FROM paper_full_text WHERE paper_id = %s",
        (paper_id,),
    ).fetchone()
    assert row["abstract"] == "Integration test abstract."
    assert row["source"] == "arxiv"


def test_integration_upsert_is_idempotent(pg_conn):
    """Two upserts with same paper_id → one row, second call updates fields."""
    try:
        pg_conn.execute("SELECT 1 FROM paper_full_text LIMIT 1")
    except Exception:
        pytest.skip("paper_full_text table not present")

    paper = pg_conn.execute("SELECT paper_id FROM paper LIMIT 1").fetchone()
    if paper is None:
        pytest.skip("no paper rows")
    paper_id = paper["paper_id"]

    extract1 = FullTextExtract(
        paper_id=paper_id, abstract="v1", intro=None, pdf_url=None,
        pdf_sha256=None, source="arxiv", fetch_error=None,
    )
    extract2 = FullTextExtract(
        paper_id=paper_id, abstract="v2", intro=None, pdf_url=None,
        pdf_sha256=None, source="openalex", fetch_error=None,
    )
    upsert_paper_full_text(pg_conn, paper_id=paper_id, extract=extract1)
    upsert_paper_full_text(pg_conn, paper_id=paper_id, extract=extract2)
    row = pg_conn.execute(
        "SELECT abstract, source FROM paper_full_text WHERE paper_id = %s",
        (paper_id,),
    ).fetchone()
    assert row["abstract"] == "v2"
    assert row["source"] == "openalex"


def test_integration_paper_full_text_exists_real_db(pg_conn):
    try:
        pg_conn.execute("SELECT 1 FROM paper_full_text LIMIT 1")
    except Exception:
        pytest.skip("paper_full_text table not present")
    assert paper_full_text_exists(pg_conn, "definitely_missing_id_xyz") is False
