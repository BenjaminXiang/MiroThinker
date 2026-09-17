"""Contract tests for the enriched audit surface: filters, export, statistics, identity capture."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import csv
import io
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from fastapi import Request
from fastapi.testclient import TestClient
import pytest

from backend.api.canonical_v2_chat import _record_access_turn
from backend.main import app
from tests.conftest import authorized_client
from backend.services.canonical_v2_access_log import (
    ANONYMOUS_IDENTITY,
    AccessLogStore,
    AccessLogTurnRecord,
    normalize_user_identity,
)

_STATE_NAME = "canonical_v2_access_log_store"
_SESSIONS = "/api/canonical-v2/admin/access-logs/sessions"
_STATS = "/api/canonical-v2/admin/access-logs/stats"
_EXPORT = "/api/canonical-v2/admin/access-logs/export"

CSV_COLUMNS = (
    "session_id",
    "user_identity",
    "turn_id",
    "turn_count",
    "query_type",
    "status",
    "started_at",
    "finished_at",
    "latency_ms",
    "answer_style",
    "query",
    "answer_text",
    "error_detail",
    "citations",
    "suggested_followups",
)


def _record(
    *,
    turn_id: str,
    session_id: str,
    query: str,
    user_identity: str = "anonymous",
    query_type: str = "canonical_v2:A:answer",
    answer_text: str = "示例回答。",
    status: str = "completed",
    error_detail: str | None = None,
    citations: tuple[dict, ...] = (
        {"index": 1, "label": "优必选", "url": "https://example.com/ubtech"},
    ),
    suggested_followups: tuple[str, ...] = ("它们的产品有哪些？",),
    started_at: datetime,
    latency_ms: int = 4000,
) -> AccessLogTurnRecord:
    return AccessLogTurnRecord(
        turn_id=turn_id,
        session_id=session_id,
        turn_count=0,
        query=query,
        query_type=query_type,
        answer_text=answer_text,
        answer_style="llm_synthesized",
        citations=citations,
        suggested_followups=suggested_followups,
        status=status,  # type: ignore[arg-type]
        error_detail=error_detail,
        started_at=started_at,
        finished_at=started_at + timedelta(milliseconds=latency_ms),
        latency_ms=latency_ms,
        user_identity=user_identity,
    )


def _seed(store: AccessLogStore) -> None:
    """Four sessions across identities, days, statuses, and query types."""

    store.record_turn(
        _record(
            turn_id="turn:alice-a:1",
            session_id="session:chat:alice-a",
            query="深圳有哪些具身智能企业？",
            user_identity="alice",
            started_at=datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC),
        )
    )
    store.record_turn(
        _record(
            turn_id="turn:alice-a:2",
            session_id="session:chat:alice-a",
            query="上述企业里总部在南山的有哪些？",
            user_identity="alice",
            answer_text="筛选后剩 3 家。",
            started_at=datetime(2026, 9, 1, 10, 5, 0, tzinfo=UTC),
        )
    )
    store.record_turn(
        _record(
            turn_id="turn:alice-b:1",
            session_id="session:chat:alice-b",
            query="触发内部错误的问题",
            user_identity="alice",
            query_type="",
            answer_text="",
            status="error",
            error_detail="canonical_v2_consumer_integrity_error",
            citations=(),
            suggested_followups=(),
            started_at=datetime(2026, 9, 2, 11, 0, 0, tzinfo=UTC),
        )
    )
    store.record_turn(
        _record(
            turn_id="turn:anon-c:1",
            session_id="session:chat:anon-c",
            query="他是谁？",
            query_type="canonical_v2:G:clarification_only",
            answer_text="请补充您想了解的对象。",
            started_at=datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC),
        )
    )
    store.record_turn(
        _record(
            turn_id="turn:anon-d:1",
            session_id="session:chat:anon-d",
            query="深圳有哪些具身智能企业？",
            status="interrupted",
            started_at=datetime(2026, 9, 4, 13, 0, 0, tzinfo=UTC),
        )
    )


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[AccessLogStore]:
    instance = AccessLogStore(tmp_path / "access-logs.sqlite3")
    _seed(instance)
    had_prior = hasattr(app.state, _STATE_NAME)
    prior = getattr(app.state, _STATE_NAME, None)
    setattr(app.state, _STATE_NAME, instance)
    try:
        yield instance
    finally:
        if had_prior:
            setattr(app.state, _STATE_NAME, prior)
        elif hasattr(app.state, _STATE_NAME):
            delattr(app.state, _STATE_NAME)
        instance.close()


@pytest.fixture()
def client(store: AccessLogStore) -> TestClient:
    del store
    return authorized_client(raise_server_exceptions=False)


def _session_ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["session_id"] for item in response.json()["sessions"]]


# --- identity capture -------------------------------------------------------


def test_normalize_user_identity_bounds_and_defaults() -> None:
    assert ANONYMOUS_IDENTITY == "anonymous"
    assert normalize_user_identity(None) == ANONYMOUS_IDENTITY
    assert normalize_user_identity("") == ANONYMOUS_IDENTITY
    assert normalize_user_identity("   ") == ANONYMOUS_IDENTITY
    assert normalize_user_identity("  alice  ") == "alice"
    assert normalize_user_identity("郭娴") == "郭娴"
    assert normalize_user_identity("x" * 400) == "x" * 120


def _request(*, headers: dict[str, str]) -> Request:
    raw = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in headers.items()
    ]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/chat",
            "headers": raw,
            "app": app,
            "query_string": b"",
        }
    )


def test_record_access_turn_stores_the_remote_user_header(store) -> None:
    started = datetime(2026, 9, 5, 9, 0, 0, tzinfo=UTC)
    _record_access_turn(
        _request(headers={"X-Remote-User": "alice"}),
        session_id="session:chat:http",
        query="头信息身份问题",
        chat_response=None,
        status="error",
        error_detail="canonical_v2_invalid_option",
        started_at=started,
    )
    detail = store.get_session("session:chat:http")
    assert detail is not None
    assert detail.turns[0].user_identity == "alice"


def test_record_access_turn_without_header_is_anonymous_and_fail_open(store) -> None:
    started = datetime(2026, 9, 5, 9, 0, 0, tzinfo=UTC)
    _record_access_turn(
        _request(headers={}),
        session_id="session:chat:anon",
        query="无头信息问题",
        chat_response=None,
        status="error",
        error_detail="canonical_v2_invalid_option",
        started_at=started,
    )
    detail = store.get_session("session:chat:anon")
    assert detail is not None
    assert detail.turns[0].user_identity == "anonymous"

    store.close()
    _record_access_turn(
        _request(headers={"X-Remote-User": "alice"}),
        session_id="session:chat:broken",
        query="存储失败记录",
        chat_response=None,
        status="error",
        error_detail=None,
        started_at=started,
    )


def test_recorded_payload_never_carries_network_identifiers(store) -> None:
    connection = sqlite3.connect(store.database_path)
    try:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(turns)")]
        values = connection.execute("SELECT * FROM turns LIMIT 1").fetchone()
    finally:
        connection.close()
    assert "user_identity" in columns
    forbidden = {"ip", "ip_address", "remote_addr", "client_ip", "user_agent", "cookie"}
    assert not forbidden.intersection({column.lower() for column in columns})
    assert values is not None
    assert "127.0.0.1" not in json.dumps(values, ensure_ascii=False)


# --- combined filters -------------------------------------------------------


def test_identity_is_exposed_on_sessions_and_turns(client) -> None:
    page = client.get(_SESSIONS, params={"limit": 100}).json()
    by_id = {item["session_id"]: item for item in page["sessions"]}
    assert set(by_id) == {
        "session:chat:alice-a",
        "session:chat:alice-b",
        "session:chat:anon-c",
        "session:chat:anon-d",
    }
    assert by_id["session:chat:alice-a"]["identities"] == ["alice"]
    assert by_id["session:chat:anon-c"]["identities"] == ["anonymous"]

    detail = client.get(f"{_SESSIONS}/session:chat:alice-a").json()
    assert [turn["user_identity"] for turn in detail["turns"]] == ["alice", "alice"]


def test_sessions_filter_by_time_range(client) -> None:
    assert _session_ids(client.get(_SESSIONS, params={"since": "2026-09-02"})) == [
        "session:chat:anon-d",
        "session:chat:anon-c",
        "session:chat:alice-b",
    ]
    assert _session_ids(
        client.get(_SESSIONS, params={"since": "2026-09-02", "until": "2026-09-03"})
    ) == ["session:chat:anon-c", "session:chat:alice-b"]
    assert _session_ids(
        client.get(
            _SESSIONS,
            params={
                "since": "2026-09-03T00:00:00+00:00",
                "until": "2026-09-03T23:59:59.999999+00:00",
            },
        )
    ) == ["session:chat:anon-c"]
    # An offset-bearing bound is converted to UTC, not reinterpreted.
    assert _session_ids(
        client.get(_SESSIONS, params={"since": "2026-09-03T08:00:00+08:00"})
    ) == ["session:chat:anon-d", "session:chat:anon-c"]
    assert _session_ids(client.get(_SESSIONS, params={"until": "2026-09-01"})) == [
        "session:chat:alice-a"
    ]


def test_sessions_filter_combines_status_query_type_and_identity(client) -> None:
    combined = client.get(
        _SESSIONS,
        params={
            "status": "interrupted",
            "query_type": "canonical_v2:A:answer",
            "identity": "anonymous",
            "since": "2026-09-01",
            "until": "2026-09-04",
        },
    )
    assert _session_ids(combined) == ["session:chat:anon-d"]
    assert combined.json()["total"] == 1

    # Every constraint must hold; a completed-only status drops that session.
    assert (
        client.get(
            _SESSIONS,
            params={
                "status": "completed",
                "query_type": "canonical_v2:A:answer",
                "identity": "anonymous",
            },
        ).json()["total"]
        == 0
    )

    alice_completed = client.get(
        _SESSIONS,
        params={
            "status": "completed",
            "query_type": "canonical_v2:A:answer",
            "identity": "alice",
        },
    )
    assert _session_ids(alice_completed) == ["session:chat:alice-a"]

    errors = client.get(_SESSIONS, params={"status": "error", "identity": "alice"})
    assert _session_ids(errors) == ["session:chat:alice-b"]

    clarification = client.get(
        _SESSIONS, params={"query_type": "canonical_v2:G:clarification_only"}
    )
    assert _session_ids(clarification) == ["session:chat:anon-c"]


def test_sessions_query_type_empty_bucket_is_filterable(client) -> None:
    assert _session_ids(client.get(_SESSIONS, params={"query_type": ""})) == [
        "session:chat:alice-b"
    ]


def test_sessions_unknown_identity_is_an_empty_page(client) -> None:
    response = client.get(_SESSIONS, params={"identity": "nobody"})
    assert response.status_code == 200
    assert response.json()["sessions"] == []
    assert response.json()["total"] == 0


def test_sessions_reject_invalid_filter_values(client) -> None:
    cases = (
        {"since": "2026-13-01"},
        {"since": "2026-09-01T10:00:00"},
        {"until": "01/09/2026"},
        {"since": "2026-09-05", "until": "2026-09-01"},
        {"identity": "x" * 121},
        {"identity": ""},
        {"query_type": "x" * 121},
        {"status": "bogus"},
    )
    for params in cases:
        response = client.get(_SESSIONS, params=params)
        assert response.status_code == 422, (params, response.status_code)


# --- export -----------------------------------------------------------------


def _csv_rows(body: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body)))


def _detail_turns(client: TestClient, session_id: str) -> dict[str, dict]:
    detail = client.get(f"{_SESSIONS}/{session_id}").json()
    return {turn["turn_id"]: turn for turn in detail["turns"]}


def test_export_csv_matches_what_the_page_shows(client) -> None:
    response = client.get(_EXPORT, params={"format": "csv"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    rows = _csv_rows(response.text)
    assert len(rows) == 5
    assert tuple(rows[0].keys()) == CSV_COLUMNS
    assert response.headers["x-access-log-turns"] == "5"
    assert response.headers["x-access-log-truncated"] == "false"

    for session_id in ("session:chat:alice-a", "session:chat:alice-b"):
        visible = _detail_turns(client, session_id)
        exported = {
            row["turn_id"]: row for row in rows if row["session_id"] == session_id
        }
        assert set(exported) == set(visible)
        for turn_id, turn in visible.items():
            row = exported[turn_id]
            assert row["user_identity"] == turn["user_identity"]
            assert row["turn_count"] == str(turn["turn_count"])
            assert row["query_type"] == turn["query_type"]
            assert row["status"] == turn["status"]
            assert row["started_at"] == turn["started_at"]
            assert row["finished_at"] == turn["finished_at"]
            assert row["latency_ms"] == str(turn["latency_ms"])
            assert row["answer_style"] == turn["answer_style"]
            assert row["query"] == turn["query"]
            assert row["answer_text"] == turn["answer_text"]
            assert row["error_detail"] == (turn["error_detail"] or "")
            assert json.loads(row["citations"]) == turn["citations"]
            assert (
                json.loads(row["suggested_followups"])
                == turn["suggested_followups"]
            )


def test_export_jsonl_matches_what_the_page_shows(client) -> None:
    response = client.get(_EXPORT, params={"format": "jsonl"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")

    rows = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert len(rows) == 5
    assert set(rows[0]) == set(CSV_COLUMNS)

    visible = _detail_turns(client, "session:chat:alice-a")
    exported = {row["turn_id"]: row for row in rows}
    for turn_id, turn in visible.items():
        row = exported[turn_id]
        assert row["query"] == turn["query"]
        assert row["answer_text"] == turn["answer_text"]
        assert row["citations"] == turn["citations"]
        assert row["suggested_followups"] == turn["suggested_followups"]
        assert row["user_identity"] == turn["user_identity"]


def test_export_honours_the_active_filters_and_reports_truncation(client) -> None:
    filtered = client.get(
        _EXPORT,
        params={"format": "csv", "status": "error", "identity": "alice"},
    )
    rows = _csv_rows(filtered.text)
    assert [row["turn_id"] for row in rows] == ["turn:alice-b:1"]

    windowed = client.get(
        _EXPORT, params={"format": "csv", "since": "2026-09-01", "until": "2026-09-01"}
    )
    assert [row["turn_id"] for row in _csv_rows(windowed.text)] == [
        "turn:alice-a:1",
        "turn:alice-a:2",
    ]

    capped = client.get(_EXPORT, params={"format": "csv", "max_turns": 2})
    assert capped.headers["x-access-log-truncated"] == "true"
    assert capped.headers["x-access-log-turns"] == "2"
    assert len(_csv_rows(capped.text)) == 2


def test_export_rejects_unknown_format_and_out_of_range_cap(client) -> None:
    assert client.get(_EXPORT, params={"format": "xlsx"}).status_code == 422
    assert client.get(_EXPORT, params={"format": "csv", "max_turns": 0}).status_code == 422
    assert (
        client.get(_EXPORT, params={"format": "csv", "max_turns": 20001}).status_code
        == 422
    )
    assert (
        client.get(_EXPORT, params={"format": "csv", "since": "2026-13-01"}).status_code
        == 422
    )


# --- statistics -------------------------------------------------------------


def _sql_counts(db_path: Path) -> dict:
    connection = sqlite3.connect(db_path)
    try:
        totals = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT session_id),"
            " COALESCE(SUM(status = 'error'), 0),"
            " COALESCE(SUM(status = 'interrupted'), 0) FROM turns"
        ).fetchone()
        daily = connection.execute(
            "SELECT substr(started_at, 1, 10) AS day, COUNT(*),"
            " COUNT(DISTINCT session_id) FROM turns GROUP BY day ORDER BY day"
        ).fetchall()
        query_types = connection.execute(
            "SELECT query_type, COUNT(*) AS n FROM turns"
            " GROUP BY query_type ORDER BY n DESC, query_type ASC"
        ).fetchall()
        identities = connection.execute(
            "SELECT COALESCE(NULLIF(user_identity, ''), 'anonymous') AS identity,"
            " COUNT(*) AS n FROM turns GROUP BY identity ORDER BY n DESC, identity ASC"
        ).fetchall()
        top_queries = connection.execute(
            "SELECT TRIM(query) AS q, COUNT(*) AS n FROM turns"
            " GROUP BY q ORDER BY n DESC, q ASC LIMIT 10"
        ).fetchall()
    finally:
        connection.close()
    return {
        "totals": totals,
        "daily": daily,
        "query_types": query_types,
        "identities": identities,
        "top_queries": top_queries,
    }


def test_statistics_reconcile_with_direct_sql(client, store) -> None:
    response = client.get(
        _STATS,
        params={"since": "2026-09-01", "until": "2026-09-30", "top_limit": 10},
    )
    assert response.status_code == 200
    stats = response.json()
    sql = _sql_counts(store.database_path)

    assert stats["totals"]["turns"] == sql["totals"][0] == 5
    assert stats["totals"]["sessions"] == sql["totals"][1] == 4
    assert stats["totals"]["errors"] == sql["totals"][2] == 1
    assert stats["totals"]["interrupted"] == sql["totals"][3] == 1
    assert stats["totals"]["error_rate"] == round(1 / 5, 4)

    assert [item["day"] for item in stats["daily"]] == [
        row[0] for row in sql["daily"]
    ]
    assert [(item["day"], item["turns"], item["sessions"]) for item in stats["daily"]] == [
        (row[0], row[1], row[2]) for row in sql["daily"]
    ]
    assert [(item["query_type"], item["turns"]) for item in stats["query_types"]] == [
        (row[0], row[1]) for row in sql["query_types"]
    ]
    assert [(item["identity"], item["turns"]) for item in stats["identities"]] == [
        (row[0], row[1]) for row in sql["identities"]
    ]
    assert [(item["query"], item["turns"]) for item in stats["top_queries"]] == [
        (row[0], row[1]) for row in sql["top_queries"]
    ]
    assert stats["top_queries"][0] == {
        "query": "深圳有哪些具身智能企业？",
        "turns": 2,
    }
    assert stats["window"]["since_defaulted"] is False


def test_statistics_default_window_and_empty_window(client) -> None:
    defaulted = client.get(_STATS)
    assert defaulted.status_code == 200
    window = defaulted.json()["window"]
    assert window["since_defaulted"] is True
    since = datetime.fromisoformat(window["since"])
    until = datetime.fromisoformat(window["until"])
    assert (until - since) == timedelta(days=30)

    empty = client.get(
        _STATS, params={"since": "2026-01-01", "until": "2026-01-31"}
    ).json()
    assert empty["totals"] == {
        "turns": 0,
        "sessions": 0,
        "errors": 0,
        "interrupted": 0,
        "error_rate": 0.0,
    }
    assert empty["daily"] == []
    assert empty["query_types"] == []
    assert empty["identities"] == []
    assert empty["top_queries"] == []


def test_statistics_honour_filters_and_reject_bad_limits(client) -> None:
    filtered = client.get(
        _STATS,
        params={
            "since": "2026-09-01",
            "until": "2026-09-30",
            "identity": "alice",
            "query_type": "canonical_v2:A:answer",
        },
    ).json()
    assert filtered["totals"]["turns"] == 2
    assert filtered["identities"] == [{"identity": "alice", "turns": 2}]

    capped = client.get(
        _STATS, params={"since": "2026-09-01", "until": "2026-09-30", "top_limit": 1}
    ).json()
    assert len(capped["top_queries"]) == 1

    assert client.get(_STATS, params={"top_limit": 0}).status_code == 422
    assert client.get(_STATS, params={"top_limit": 51}).status_code == 422
    assert client.get(_STATS, params={"since": "2026-09-30", "until": "2026-09-01"}).status_code == 422
