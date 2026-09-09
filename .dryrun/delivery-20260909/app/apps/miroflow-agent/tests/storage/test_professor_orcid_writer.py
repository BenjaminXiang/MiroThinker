"""RED-phase tests for M2.4 Unit 4 — professor_orcid writer.

The table + writer ship in M2.4; M1.3 will be the first caller.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from src.data_agents.storage.postgres.professor_orcid import (
    get_professor_orcid,
    upsert_professor_orcid,
)

_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"


def _dsn() -> str | None:
    raw = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    return raw or None


# =============================================================================
# Unit tests (mocked Connection)
# =============================================================================


def test_upsert_professor_orcid_executes_upsert():
    conn = MagicMock()
    upsert_professor_orcid(
        conn,
        professor_id="00000000-0000-0000-0000-000000000001",
        orcid="0000-0001-2345-6789",
        source="openalex",
        confidence=0.9,
    )
    assert conn.execute.called
    sql = conn.execute.call_args[0][0]
    assert "ON CONFLICT" in sql.upper()
    assert "professor_orcid" in sql.lower()


def test_upsert_professor_orcid_rejects_malformed_orcid():
    conn = MagicMock()
    with pytest.raises(ValueError):
        upsert_professor_orcid(
            conn,
            professor_id="00000000-0000-0000-0000-000000000001",
            orcid="not-an-orcid",
            source="manual",
            confidence=0.5,
        )
    conn.execute.assert_not_called()


def test_upsert_professor_orcid_accepts_x_checksum():
    """ORCID last digit can be 'X' (uppercase) per spec."""
    conn = MagicMock()
    upsert_professor_orcid(
        conn,
        professor_id="00000000-0000-0000-0000-000000000002",
        orcid="0000-0002-1825-009X",
        source="manual",
        confidence=1.0,
    )
    assert conn.execute.called


def test_upsert_professor_orcid_rejects_lowercase_x():
    """Lowercase 'x' is not valid ORCID."""
    conn = MagicMock()
    with pytest.raises(ValueError):
        upsert_professor_orcid(
            conn,
            professor_id="00000000-0000-0000-0000-000000000003",
            orcid="0000-0002-1825-009x",  # lowercase
            source="manual",
            confidence=1.0,
        )


def test_upsert_professor_orcid_does_not_commit():
    conn = MagicMock()
    upsert_professor_orcid(
        conn,
        professor_id="00000000-0000-0000-0000-000000000004",
        orcid="0000-0001-2345-6789",
        source="openalex",
        confidence=0.9,
    )
    conn.commit.assert_not_called()


def test_get_professor_orcid_returns_string_when_present():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = {"orcid": "0000-0001-2345-6789"}
    conn.execute.return_value = cursor
    assert (
        get_professor_orcid(conn, "00000000-0000-0000-0000-000000000001")
        == "0000-0001-2345-6789"
    )


def test_get_professor_orcid_returns_none_when_absent():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    conn.execute.return_value = cursor
    assert get_professor_orcid(conn, "ghost_id") is None


# =============================================================================
# Integration tests
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


def test_integration_upsert_and_get_roundtrip(pg_conn):
    try:
        pg_conn.execute("SELECT 1 FROM professor_orcid LIMIT 1")
    except Exception:
        pytest.skip("professor_orcid table not present; run alembic V011")

    prof = pg_conn.execute("SELECT professor_id FROM professor LIMIT 1").fetchone()
    if prof is None:
        pytest.skip("no professor rows")

    upsert_professor_orcid(
        pg_conn,
        professor_id=prof["professor_id"],
        orcid="0000-0001-2345-6789",
        source="test",
        confidence=0.85,
    )
    got = get_professor_orcid(pg_conn, prof["professor_id"])
    assert got == "0000-0001-2345-6789"


def test_integration_upsert_overwrites(pg_conn):
    try:
        pg_conn.execute("SELECT 1 FROM professor_orcid LIMIT 1")
    except Exception:
        pytest.skip("professor_orcid table not present")

    prof = pg_conn.execute("SELECT professor_id FROM professor LIMIT 1").fetchone()
    if prof is None:
        pytest.skip("no professor rows")

    upsert_professor_orcid(
        pg_conn, professor_id=prof["professor_id"],
        orcid="0000-0001-1111-1111", source="x", confidence=0.5,
    )
    upsert_professor_orcid(
        pg_conn, professor_id=prof["professor_id"],
        orcid="0000-0002-2222-2222", source="y", confidence=0.8,
    )
    got = get_professor_orcid(pg_conn, prof["professor_id"])
    assert got == "0000-0002-2222-2222"
