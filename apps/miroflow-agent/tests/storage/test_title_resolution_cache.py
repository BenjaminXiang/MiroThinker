"""RED-phase tests for M2.4 Unit 3 — PostgresTitleResolutionCache.

Implements M2.2's TitleResolutionCache Protocol against Postgres with 30-day TTL.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

import pytest

from src.data_agents.paper.title_resolver import ResolvedPaper
from src.data_agents.storage.postgres.title_resolution_cache import (
    PostgresTitleResolutionCache,
)

_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"


def _dsn() -> str | None:
    raw = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    return raw or None


def _resolved_fixture(source: str = "openalex") -> ResolvedPaper:
    return ResolvedPaper(
        title="Some Paper",
        doi="10.1/x" if source == "openalex" else None,
        openalex_id="W1" if source == "openalex" else None,
        arxiv_id="2301.00001" if source == "arxiv" else None,
        abstract="We study a problem.",
        pdf_url=None,
        authors=("Alice", "Bob"),
        year=2023,
        venue="NeurIPS",
        match_confidence=0.92,
        match_source=source,
    )


# =============================================================================
# Unit tests (mocked Connection)
# =============================================================================


def test_cache_get_returns_none_when_row_missing():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn.execute.return_value = cursor
    cache = PostgresTitleResolutionCache(conn)
    assert cache.get("some_key") is None


def test_cache_get_queries_with_ttl_filter():
    """get() must filter by `cached_at > now() - interval '30 days'`."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn.execute.return_value = cursor
    cache = PostgresTitleResolutionCache(conn)
    cache.get("k")
    sql = conn.execute.call_args[0][0]
    assert "cached_at" in sql.lower()
    assert "30 days" in sql.lower() or "interval" in sql.lower()


def test_cache_get_deserializes_jsonb_to_resolved_paper():
    conn = MagicMock()
    resolved = _resolved_fixture()
    serialized = {
        "title": resolved.title,
        "doi": resolved.doi,
        "openalex_id": resolved.openalex_id,
        "arxiv_id": resolved.arxiv_id,
        "abstract": resolved.abstract,
        "pdf_url": resolved.pdf_url,
        "authors": list(resolved.authors),  # JSONB stores as list
        "year": resolved.year,
        "venue": resolved.venue,
        "match_confidence": resolved.match_confidence,
        "match_source": resolved.match_source,
    }
    cursor = MagicMock()
    cursor.fetchone.return_value = {"resolved": serialized}
    conn.execute.return_value = cursor
    cache = PostgresTitleResolutionCache(conn)
    got = cache.get("k")
    assert got is not None
    assert got.title == resolved.title
    assert got.authors == resolved.authors  # tuple on read
    assert isinstance(got.authors, tuple)
    assert got.match_confidence == resolved.match_confidence


def test_cache_set_executes_insert_on_conflict():
    conn = MagicMock()
    cache = PostgresTitleResolutionCache(conn)
    resolved = _resolved_fixture()
    cache.set("k", resolved)
    assert conn.execute.called
    sql = conn.execute.call_args[0][0]
    assert "ON CONFLICT" in sql.upper()
    assert "paper_title_resolution_cache" in sql.lower()


def test_cache_set_serializes_resolved_paper_as_json():
    conn = MagicMock()
    cache = PostgresTitleResolutionCache(conn)
    resolved = _resolved_fixture()
    cache.set("k", resolved)
    params = conn.execute.call_args[0][1]
    # Find the JSON/JSONB param (should be a string that parses back to dict)
    found_json = False
    for p in params:
        if isinstance(p, (str, bytes)):
            try:
                payload = json.loads(p)
                if isinstance(payload, dict) and payload.get("title") == resolved.title:
                    found_json = True
                    # authors is a list in JSON (tuple not JSON-serializable)
                    assert payload["authors"] == list(resolved.authors)
                    break
            except (json.JSONDecodeError, TypeError):
                continue
    assert found_json, "serialized ResolvedPaper JSON not found in params"


def test_cache_set_includes_match_confidence_and_source_columns():
    """Set should populate match_confidence + match_source columns for ops queries."""
    conn = MagicMock()
    cache = PostgresTitleResolutionCache(conn)
    resolved = _resolved_fixture()
    cache.set("k", resolved)
    params = conn.execute.call_args[0][1]
    assert 0.92 in params or str(0.92) in [str(p) for p in params]
    assert "openalex" in params


def test_cache_does_not_commit():
    conn = MagicMock()
    cache = PostgresTitleResolutionCache(conn)
    cache.set("k", _resolved_fixture())
    conn.commit.assert_not_called()


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


def test_integration_set_get_roundtrip(pg_conn):
    try:
        pg_conn.execute("SELECT 1 FROM paper_title_resolution_cache LIMIT 1")
    except Exception:
        pytest.skip("paper_title_resolution_cache table not present; run alembic V011")

    cache = PostgresTitleResolutionCache(pg_conn)
    resolved = _resolved_fixture()
    cache.set("test_key_xyz", resolved)
    got = cache.get("test_key_xyz")
    assert got is not None
    assert got.title == resolved.title
    assert got.authors == resolved.authors


def test_integration_get_missing_returns_none(pg_conn):
    try:
        pg_conn.execute("SELECT 1 FROM paper_title_resolution_cache LIMIT 1")
    except Exception:
        pytest.skip("paper_title_resolution_cache table not present")
    cache = PostgresTitleResolutionCache(pg_conn)
    assert cache.get("definitely_absent_key_abc") is None


def test_integration_upsert_is_idempotent(pg_conn):
    try:
        pg_conn.execute("SELECT 1 FROM paper_title_resolution_cache LIMIT 1")
    except Exception:
        pytest.skip("paper_title_resolution_cache table not present")
    cache = PostgresTitleResolutionCache(pg_conn)
    cache.set("k_dup", _resolved_fixture(source="openalex"))
    cache.set("k_dup", _resolved_fixture(source="arxiv"))
    got = cache.get("k_dup")
    assert got is not None
    assert got.match_source == "arxiv"  # second set wins
