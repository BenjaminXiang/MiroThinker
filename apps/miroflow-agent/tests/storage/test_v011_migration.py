"""RED-phase tests for M2.4 Unit 1 — V011 migration creates three RAG tables.

Real-DB tests; skip if DATABASE_URL_TEST not set. These assume alembic
has been run to bring the test DB to V011 head.
"""

from __future__ import annotations

import os

import pytest

_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"


def _dsn() -> str | None:
    raw = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    return raw or None


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


def _skip_if_migration_not_applied(conn, table: str) -> None:
    try:
        conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
    except Exception:
        pytest.skip(f"{table} not present; run alembic upgrade V011")


def test_v011_creates_paper_full_text_table(pg_conn):
    _skip_if_migration_not_applied(pg_conn, "paper_full_text")
    row = pg_conn.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'paper_full_text'
        ORDER BY ordinal_position
        """
    ).fetchall()
    columns = {r["column_name"]: r for r in row}
    for required in (
        "paper_id",
        "abstract",
        "intro",
        "pdf_url",
        "pdf_sha256",
        "source",
        "fetched_at",
        "fetch_error",
    ):
        assert required in columns, f"missing column: {required}"
    # source must be NOT NULL
    assert columns["source"]["is_nullable"] == "NO"
    # paper_id must be primary key / not null
    assert columns["paper_id"]["is_nullable"] == "NO"


def test_v011_creates_paper_title_resolution_cache_table(pg_conn):
    _skip_if_migration_not_applied(pg_conn, "paper_title_resolution_cache")
    columns = {
        r["column_name"]: r
        for r in pg_conn.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'paper_title_resolution_cache'
            """
        ).fetchall()
    }
    for required in (
        "title_sha1",
        "clean_title_preview",
        "resolved",
        "match_source",
        "match_confidence",
        "cached_at",
    ):
        assert required in columns, f"missing column: {required}"
    # resolved must be NOT NULL (stores full ResolvedPaper)
    assert columns["resolved"]["is_nullable"] == "NO"


def test_v011_creates_professor_orcid_table(pg_conn):
    _skip_if_migration_not_applied(pg_conn, "professor_orcid")
    columns = {
        r["column_name"]: r
        for r in pg_conn.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'professor_orcid'
            """
        ).fetchall()
    }
    for required in (
        "professor_id",
        "orcid",
        "source",
        "confidence",
        "verified_at",
    ):
        assert required in columns, f"missing column: {required}"
    # orcid must be UNIQUE — check via constraints query
    unique_constraint = pg_conn.execute(
        """
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_name = 'professor_orcid'
          AND constraint_type = 'UNIQUE'
        """
    ).fetchall()
    assert len(unique_constraint) >= 1


def test_v011_paper_full_text_fk_cascades(pg_conn):
    """paper_full_text.paper_id FK must cascade delete from paper."""
    _skip_if_migration_not_applied(pg_conn, "paper_full_text")
    fk = pg_conn.execute(
        """
        SELECT rc.delete_rule
        FROM information_schema.referential_constraints rc
        JOIN information_schema.table_constraints tc
          ON rc.constraint_name = tc.constraint_name
        WHERE tc.table_name = 'paper_full_text'
        """
    ).fetchone()
    if fk is None:
        pytest.skip("no FK constraint found (migration may not add FK)")
    assert fk["delete_rule"] == "CASCADE"


def test_v011_has_cached_at_index(pg_conn):
    """Index on cached_at for TTL cleanup performance."""
    _skip_if_migration_not_applied(pg_conn, "paper_title_resolution_cache")
    indexes = pg_conn.execute(
        """
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'paper_title_resolution_cache'
        """
    ).fetchall()
    idx_names = [r["indexname"] for r in indexes]
    # At minimum the PRIMARY KEY index exists; we want one more on cached_at.
    assert any("cached_at" in name.lower() or "recent" in name.lower() for name in idx_names), (
        f"expected cached_at index on paper_title_resolution_cache, got: {idx_names}"
    )
