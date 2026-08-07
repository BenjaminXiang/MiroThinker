from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from backend.services.canonical_v2_access_log import (
    SCHEMA_VERSION,
    AccessLogStore,
    AccessLogTurnRecord,
)


def _record(
    *,
    turn_id: str,
    session_id: str = "session:chat:alpha",
    turn_count: int = 1,
    query: str = "深圳有哪些具身智能企业？",
    query_type: str = "enumeration",
    answer_text: str = "优必选、众擎等。",
    answer_style: str = "llm_synthesized",
    citations: tuple[dict, ...] = (
        {"index": 1, "label": "优必选", "url": "https://example.com/ubtech"},
    ),
    suggested_followups: tuple[str, ...] = ("它们的产品有哪些？",),
    status: str = "completed",
    error_detail: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    latency_ms: int = 1234,
) -> AccessLogTurnRecord:
    started = started_at or datetime(2026, 8, 7, 10, 0, 0, tzinfo=UTC)
    finished = finished_at or started + timedelta(milliseconds=latency_ms)
    return AccessLogTurnRecord(
        turn_id=turn_id,
        session_id=session_id,
        turn_count=turn_count,
        query=query,
        query_type=query_type,
        answer_text=answer_text,
        answer_style=answer_style,
        citations=citations,
        suggested_followups=suggested_followups,
        status=status,  # type: ignore[arg-type]
        error_detail=error_detail,
        started_at=started,
        finished_at=finished,
        latency_ms=latency_ms,
    )


def test_store_records_and_reads_back_one_session(tmp_path: Path) -> None:
    store = AccessLogStore(tmp_path / "access-logs.sqlite3")
    store.record_turn(_record(turn_id="turn:1"))
    store.record_turn(
        _record(
            turn_id="turn:2",
            turn_count=2,
            query="上述企业里总部在南山的有哪些？",
            answer_text="筛选后剩 3 家。",
            started_at=datetime(2026, 8, 7, 10, 5, 0, tzinfo=UTC),
        )
    )

    sessions, total = store.list_sessions()
    assert total == 1
    assert len(sessions) == 1
    summary = sessions[0]
    assert summary.session_id == "session:chat:alpha"
    assert summary.turn_count == 2
    assert summary.first_query == "深圳有哪些具身智能企业？"
    assert summary.statuses == ("completed",)
    assert summary.last_active_at > summary.started_at

    detail = store.get_session("session:chat:alpha")
    assert detail is not None
    assert [turn.turn_id for turn in detail.turns] == ["turn:1", "turn:2"]
    first = detail.turns[0]
    assert first.query == "深圳有哪些具身智能企业？"
    assert first.answer_text == "优必选、众擎等。"
    assert first.answer_style == "llm_synthesized"
    assert first.citations == (
        {"index": 1, "label": "优必选", "url": "https://example.com/ubtech"},
    )
    assert first.suggested_followups == ("它们的产品有哪些？",)
    assert first.status == "completed"
    assert first.error_detail is None
    assert first.latency_ms == 1234
    store.close()


def test_list_sessions_orders_by_recent_activity(tmp_path: Path) -> None:
    store = AccessLogStore(tmp_path / "access-logs.sqlite3")
    store.record_turn(_record(turn_id="turn:1", session_id="session:chat:a"))
    store.record_turn(
        _record(
            turn_id="turn:2",
            session_id="session:chat:b",
            started_at=datetime(2026, 8, 7, 11, 0, 0, tzinfo=UTC),
        )
    )
    sessions, total = store.list_sessions()
    assert total == 2
    assert [item.session_id for item in sessions] == [
        "session:chat:b",
        "session:chat:a",
    ]
    store.close()


def test_list_sessions_filters_by_query_text_and_status(tmp_path: Path) -> None:
    store = AccessLogStore(tmp_path / "access-logs.sqlite3")
    store.record_turn(_record(turn_id="turn:1", session_id="session:chat:ok"))
    store.record_turn(
        _record(
            turn_id="turn:2",
            session_id="session:chat:bad",
            query="无效问题导致内部错误",
            answer_text="",
            status="error",
            error_detail="CanonicalV2MappingError: mapping rejected",
        )
    )

    matched, total = store.list_sessions(query_text="无效问题")
    assert total == 1
    assert matched[0].session_id == "session:chat:bad"
    assert matched[0].statuses == ("error",)

    errors, total = store.list_sessions(status="error")
    assert total == 1
    assert errors[0].session_id == "session:chat:bad"

    completed, total = store.list_sessions(status="completed")
    assert total == 1
    assert completed[0].session_id == "session:chat:ok"

    none, total = store.list_sessions(query_text="不存在的关键字")
    assert total == 0
    assert none == ()
    store.close()


def test_list_sessions_paginates(tmp_path: Path) -> None:
    store = AccessLogStore(tmp_path / "access-logs.sqlite3")
    for index in range(5):
        store.record_turn(
            _record(
                turn_id=f"turn:{index}",
                session_id=f"session:chat:{index}",
                started_at=datetime(2026, 8, 7, 10, index, 0, tzinfo=UTC),
            )
        )
    page, total = store.list_sessions(limit=2, offset=1)
    assert total == 5
    assert [item.session_id for item in page] == [
        "session:chat:3",
        "session:chat:2",
    ]
    store.close()


def test_get_session_returns_none_for_unknown(tmp_path: Path) -> None:
    store = AccessLogStore(tmp_path / "access-logs.sqlite3")
    assert store.get_session("session:chat:missing") is None
    store.close()


def test_record_turn_is_fail_open_on_error(tmp_path: Path) -> None:
    store = AccessLogStore(tmp_path / "access-logs.sqlite3")
    bad = _record(turn_id="turn:1", started_at=datetime(2026, 8, 7, 10, 0, 0))
    store.record_turn(bad)  # naive datetime -> must not raise
    sessions, total = store.list_sessions()
    assert total == 0
    store.close()


def test_duplicate_turn_id_is_idempotent(tmp_path: Path) -> None:
    store = AccessLogStore(tmp_path / "access-logs.sqlite3")
    store.record_turn(_record(turn_id="turn:1"))
    store.record_turn(_record(turn_id="turn:1", answer_text="重复写入"))
    detail = store.get_session("session:chat:alpha")
    assert detail is not None
    assert len(detail.turns) == 1
    assert detail.turns[0].answer_text == "优必选、众擎等。"
    assert detail.session.turn_count == 1
    store.close()


def test_store_rejects_symlinked_database(tmp_path: Path) -> None:
    real = tmp_path / "real.sqlite3"
    real.write_bytes(b"")
    link = tmp_path / "link.sqlite3"
    link.symlink_to(real)
    with pytest.raises(OSError, match="regular file|symlink"):
        AccessLogStore(link)


def test_store_rejects_schema_version_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "access-logs.sqlite3"
    store = AccessLogStore(path)
    store.close()
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE workspace_meta SET value = 'other-version'"
        " WHERE key = 'schema_version'"
    )
    connection.commit()
    connection.close()
    with pytest.raises(sqlite3.Error, match="schema version"):
        AccessLogStore(path)


def test_zero_turn_count_auto_assigns_next_ordinal(tmp_path: Path) -> None:
    store = AccessLogStore(tmp_path / "access-logs.sqlite3")
    store.record_turn(_record(turn_id="turn:1", turn_count=0))
    store.record_turn(_record(turn_id="turn:2", turn_count=0))
    store.record_turn(_record(turn_id="turn:other", session_id="session:chat:b",
                               turn_count=0))
    detail = store.get_session("session:chat:alpha")
    assert detail is not None
    assert [turn.turn_count for turn in detail.turns] == [1, 2]
    other = store.get_session("session:chat:b")
    assert other is not None
    assert [turn.turn_count for turn in other.turns] == [1]
    store.close()


def test_schema_version_marker(tmp_path: Path) -> None:
    path = tmp_path / "access-logs.sqlite3"
    store = AccessLogStore(path)
    store.close()
    connection = sqlite3.connect(path)
    row = connection.execute(
        "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
    ).fetchone()
    connection.close()
    assert row is not None
    assert row[0] == SCHEMA_VERSION
