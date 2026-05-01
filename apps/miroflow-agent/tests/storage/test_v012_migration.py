"""V012 professor academic metrics migration checks."""

from __future__ import annotations

import os

import pytest

_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"
_REAL_DB_NAMES = ("miroflow_real",)


def _dsn() -> str | None:
    raw = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not raw:
        return None
    if any(name in raw for name in _REAL_DB_NAMES):
        pytest.fail(
            f"Refusing to run V012 tests against a real-data database: {raw!r}"
        )
    return raw.replace("postgresql+psycopg://", "postgresql://", 1)


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


def test_v012_adds_professor_metrics_columns(pg_conn) -> None:
    columns = {
        row["column_name"]: row
        for row in pg_conn.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'professor'
              AND column_name IN (
                  'h_index',
                  'citation_count',
                  'paper_count',
                  'metrics_computed_at',
                  'metrics_source'
              )
            """
        ).fetchall()
    }

    assert set(columns) == {
        "h_index",
        "citation_count",
        "paper_count",
        "metrics_computed_at",
        "metrics_source",
    }
    assert columns["h_index"]["data_type"] == "integer"
    assert columns["citation_count"]["data_type"] == "bigint"
    assert columns["paper_count"]["data_type"] == "integer"
    assert columns["metrics_computed_at"]["data_type"] == "timestamp with time zone"
    assert columns["metrics_source"]["data_type"] == "text"
    assert {row["is_nullable"] for row in columns.values()} == {"YES"}


def test_v012_metrics_source_check_constraint(pg_conn) -> None:
    row = pg_conn.execute(
        """
        SELECT cc.check_clause
        FROM information_schema.check_constraints cc
        JOIN information_schema.constraint_column_usage ccu
          ON cc.constraint_name = ccu.constraint_name
        WHERE ccu.table_name = 'professor'
          AND ccu.column_name = 'metrics_source'
          AND cc.constraint_name = 'ck_professor_metrics_source'
        """
    ).fetchone()

    assert row is not None
    assert "openalex" in row["check_clause"]
    assert "verified_link_only" in row["check_clause"]
    assert "mixed" in row["check_clause"]


def test_v012_keeps_professor_orcid_table_from_v011(pg_conn) -> None:
    row = pg_conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_name = 'professor_orcid'
        """
    ).fetchone()

    assert row is not None
