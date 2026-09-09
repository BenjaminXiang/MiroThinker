from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator

from fastapi.testclient import TestClient
import pytest

from backend.main import app
from backend.services.canonical_v2_access_log import (
    AccessLogStore,
    AccessLogTurnRecord,
)


_STATE_NAME = "canonical_v2_access_log_store"


def _record(
    *,
    turn_id: str,
    session_id: str,
    query: str,
    answer_text: str = "示例回答。",
    status: str = "completed",
    error_detail: str | None = None,
    started_at: datetime | None = None,
) -> AccessLogTurnRecord:
    started = started_at or datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
    return AccessLogTurnRecord(
        turn_id=turn_id,
        session_id=session_id,
        turn_count=0,
        query=query,
        query_type="enumeration",
        answer_text=answer_text,
        answer_style="llm_synthesized",
        citations=(
            {"index": 1, "label": "优必选", "url": "https://example.com/ubtech"},
        ),
        suggested_followups=("后续问题",),
        status=status,  # type: ignore[arg-type]
        error_detail=error_detail,
        started_at=started,
        finished_at=started + timedelta(seconds=5),
        latency_ms=5000,
    )


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[AccessLogStore]:
    instance = AccessLogStore(tmp_path / "access-logs.sqlite3")
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
    return TestClient(app, raise_server_exceptions=False)


def test_sessions_endpoint_lists_and_filters(client, store) -> None:
    store.record_turn(
        _record(
            turn_id="turn:1",
            session_id="session:chat:a",
            query="深圳有哪些具身智能企业？",
        )
    )
    store.record_turn(
        _record(
            turn_id="turn:2",
            session_id="session:chat:b",
            query="触发内部错误的问题",
            answer_text="",
            status="error",
            error_detail="internal_error",
            started_at=datetime(2026, 8, 7, 12, 30, 0, tzinfo=UTC),
        )
    )

    response = client.get("/api/canonical-v2/admin/access-logs/sessions")
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 2
    assert [item["session_id"] for item in page["sessions"]] == [
        "session:chat:b",
        "session:chat:a",
    ]
    assert page["sessions"][0]["statuses"] == ["error"]

    filtered = client.get(
        "/api/canonical-v2/admin/access-logs/sessions",
        params={"status": "completed"},
    )
    assert filtered.status_code == 200
    assert [item["session_id"] for item in filtered.json()["sessions"]] == [
        "session:chat:a"
    ]

    searched = client.get(
        "/api/canonical-v2/admin/access-logs/sessions",
        params={"q": "具身智能"},
    )
    assert searched.status_code == 200
    assert searched.json()["total"] == 1


def test_session_detail_returns_turns(client, store) -> None:
    store.record_turn(
        _record(
            turn_id="turn:1",
            session_id="session:chat:a",
            query="深圳有哪些具身智能企业？",
        )
    )
    store.record_turn(
        _record(
            turn_id="turn:2",
            session_id="session:chat:a",
            query="上述企业里总部在南山的有哪些？",
            answer_text="筛选后 3 家。",
            started_at=datetime(2026, 8, 7, 12, 5, 0, tzinfo=UTC),
        )
    )
    response = client.get(
        "/api/canonical-v2/admin/access-logs/sessions/session:chat:a"
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["session"]["turn_count"] == 2
    assert [turn["turn_count"] for turn in detail["turns"]] == [1, 2]
    first = detail["turns"][0]
    assert first["query"] == "深圳有哪些具身智能企业？"
    assert first["citations"][0]["label"] == "优必选"
    assert first["suggested_followups"] == ["后续问题"]
    assert first["latency_ms"] == 5000


def test_session_detail_unknown_returns_404(client) -> None:
    response = client.get(
        "/api/canonical-v2/admin/access-logs/sessions/session:chat:missing"
    )
    assert response.status_code == 404


def test_sessions_rejects_invalid_filters(client) -> None:
    bad_status = client.get(
        "/api/canonical-v2/admin/access-logs/sessions",
        params={"status": "bogus"},
    )
    assert bad_status.status_code == 422

    over_q = client.get(
        "/api/canonical-v2/admin/access-logs/sessions",
        params={"q": "x" * 201},
    )
    assert over_q.status_code == 422

    over_window = client.get(
        "/api/canonical-v2/admin/access-logs/sessions",
        params={"limit": 100, "offset": 9950},
    )
    assert over_window.status_code == 422

    over_limit = client.get(
        "/api/canonical-v2/admin/access-logs/sessions",
        params={"limit": 101},
    )
    assert over_limit.status_code == 422


def test_sessions_returns_503_without_store() -> None:
    assert not hasattr(app.state, _STATE_NAME)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/canonical-v2/admin/access-logs/sessions")
    assert response.status_code == 503
    assert response.json()["detail"] == "canonical_v2_access_log_unavailable"


def test_sessions_pagination_window(client, store) -> None:
    for index in range(3):
        store.record_turn(
            _record(
                turn_id=f"turn:{index}",
                session_id=f"session:chat:{index}",
                query=f"问题 {index}",
                started_at=datetime(2026, 8, 7, 12, index, 0, tzinfo=UTC),
            )
        )
    response = client.get(
        "/api/canonical-v2/admin/access-logs/sessions",
        params={"limit": 2, "offset": 1},
    )
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 3
    assert len(page["sessions"]) == 2
    assert [item["session_id"] for item in page["sessions"]] == [
        "session:chat:1",
        "session:chat:0",
    ]
