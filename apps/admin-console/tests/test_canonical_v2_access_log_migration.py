"""Migration contract: a pre-W5 access-log database upgrades in place and losslessly.

The fixture database is built with the verbatim pre-W5 DDL and marker, so these tests exercise a
real legacy file rather than a simulation of one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

from backend.services.canonical_v2_access_log import (
    SCHEMA_VERSION,
    AccessLogStore,
    AccessLogTurnRecord,
)

PRE_W5_SCHEMA_VERSION = "canonical-v2-access-log-v1"

PRE_W5_DDL = """
CREATE TABLE IF NOT EXISTS workspace_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    turn_count INTEGER NOT NULL,
    first_query TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_count INTEGER NOT NULL,
    query TEXT NOT NULL,
    query_type TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    answer_style TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    suggested_followups_json TEXT NOT NULL,
    status TEXT NOT NULL,
    error_detail TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    latency_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_session_turn_count
    ON turns (session_id, turn_count);
CREATE INDEX IF NOT EXISTS turns_started_at ON turns (started_at);
CREATE INDEX IF NOT EXISTS turns_status ON turns (status);
"""

_LEGACY_TURNS = (
    {
        "turn_id": "turn:legacy:1",
        "turn_count": 1,
        "query": "深圳有哪些具身智能企业？",
        "query_type": "canonical_v2:A:answer",
        "answer_text": "优必选、众擎等。",
        "status": "completed",
        "error_detail": None,
        "started_at": "2026-08-07T10:00:00.000000+00:00",
        "finished_at": "2026-08-07T10:00:04.000000+00:00",
        "latency_ms": 4000,
    },
    {
        "turn_id": "turn:legacy:2",
        "turn_count": 2,
        "query": "上述企业里总部在南山的有哪些？",
        "query_type": "",
        "answer_text": "",
        "status": "error",
        "error_detail": "canonical_v2_consumer_integrity_error",
        "started_at": "2026-08-07T10:05:00.000000+00:00",
        "finished_at": "2026-08-07T10:05:01.000000+00:00",
        "latency_ms": 1000,
    },
)


def _legacy_database(path: Path, *, session_id: str = "session:chat:legacy") -> Path:
    connection = sqlite3.connect(path)
    with connection:
        connection.executescript(PRE_W5_DDL)
        connection.execute(
            "INSERT INTO workspace_meta (key, value) VALUES ('schema_version', ?)",
            (PRE_W5_SCHEMA_VERSION,),
        )
        for turn in _LEGACY_TURNS:
            connection.execute(
                """
                INSERT INTO turns (
                    turn_id, session_id, turn_count, query, query_type,
                    answer_text, answer_style, citations_json,
                    suggested_followups_json, status, error_detail,
                    started_at, finished_at, latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn["turn_id"],
                    session_id,
                    turn["turn_count"],
                    turn["query"],
                    turn["query_type"],
                    turn["answer_text"],
                    "llm_synthesized",
                    '[{"index": 1, "label": "优必选"}]',
                    '["它们的产品有哪些？"]',
                    turn["status"],
                    turn["error_detail"],
                    turn["started_at"],
                    turn["finished_at"],
                    turn["latency_ms"],
                ),
            )
        connection.execute(
            """
            INSERT INTO sessions (
                session_id, started_at, last_active_at, turn_count, first_query
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                "2026-08-07T10:00:00.000000+00:00",
                "2026-08-07T10:05:01.000000+00:00",
                2,
                "深圳有哪些具身智能企业？",
            ),
        )
    connection.close()
    return path


def _new_turn(*, turn_id: str, session_id: str, user_identity: str) -> AccessLogTurnRecord:
    started = datetime(2026, 8, 8, 10, 0, 0, tzinfo=UTC)
    return AccessLogTurnRecord(
        turn_id=turn_id,
        session_id=session_id,
        turn_count=0,
        query="迁移后写入的问题",
        query_type="canonical_v2:A:answer",
        answer_text="迁移后写入的回答。",
        answer_style="llm_synthesized",
        citations=(),
        suggested_followups=(),
        status="completed",
        error_detail=None,
        started_at=started,
        finished_at=started + timedelta(seconds=2),
        latency_ms=2000,
        user_identity=user_identity,
    )


def _column_names(path: Path, table: str) -> tuple[str, ...]:
    connection = sqlite3.connect(path)
    names = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
    connection.close()
    return names


def test_legacy_database_migrates_in_place_without_data_loss(tmp_path: Path) -> None:
    path = _legacy_database(tmp_path / "access-logs.sqlite3")
    before_rows = sqlite3.connect(path).execute(
        "SELECT turn_id, query, answer_text, status, latency_ms FROM turns"
        " ORDER BY turn_count"
    ).fetchall()

    store = AccessLogStore(path)
    assert "user_identity" in _column_names(path, "turns")

    after_rows = sqlite3.connect(path).execute(
        "SELECT turn_id, query, answer_text, status, latency_ms FROM turns"
        " ORDER BY turn_count"
    ).fetchall()
    assert after_rows == before_rows

    sessions, total = store.list_sessions()
    assert total == 1
    assert sessions[0].session_id == "session:chat:legacy"
    assert sessions[0].identities == ("anonymous",)
    assert sessions[0].statuses == ("completed", "error")

    detail = store.get_session("session:chat:legacy")
    assert detail is not None
    assert [turn.turn_id for turn in detail.turns] == ["turn:legacy:1", "turn:legacy:2"]
    assert [turn.user_identity for turn in detail.turns] == ["anonymous", "anonymous"]
    assert detail.turns[1].error_detail == "canonical_v2_consumer_integrity_error"
    assert detail.turns[0].citations == ({"index": 1, "label": "优必选"},)
    store.close()


def test_migrated_database_stays_readable_by_the_pre_w5_reader(tmp_path: Path) -> None:
    path = _legacy_database(tmp_path / "access-logs.sqlite3")
    store = AccessLogStore(path)
    store.record_turn(
        _new_turn(
            turn_id="turn:new:1",
            session_id="session:chat:legacy",
            user_identity="alice",
        )
    )
    store.close()

    connection = sqlite3.connect(path)
    marker = connection.execute(
        "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
    ).fetchone()[0]
    # The pre-W5 reader refuses any other marker; keeping it is the rollback contract.
    assert marker == PRE_W5_SCHEMA_VERSION == SCHEMA_VERSION
    legacy_read = connection.execute(
        """
        SELECT turn_id, session_id, turn_count, query, query_type, answer_text,
               answer_style, citations_json, suggested_followups_json, status,
               error_detail, started_at, finished_at, latency_ms
        FROM turns ORDER BY turn_count
        """
    ).fetchall()
    connection.close()
    assert len(legacy_read) == 3
    assert [row[0] for row in legacy_read] == [
        "turn:legacy:1",
        "turn:legacy:2",
        "turn:new:1",
    ]
    assert legacy_read[0][3] == "深圳有哪些具身智能企业？"


def test_reopening_a_migrated_database_is_idempotent(tmp_path: Path) -> None:
    path = _legacy_database(tmp_path / "access-logs.sqlite3")
    first = AccessLogStore(path)
    first.close()
    columns_after_first_open = _column_names(path, "turns")

    second = AccessLogStore(path)
    second.record_turn(
        _new_turn(
            turn_id="turn:new:1",
            session_id="session:chat:legacy",
            user_identity="alice",
        )
    )
    sessions, total = second.list_sessions()
    assert total == 1
    assert sessions[0].identities == ("alice", "anonymous")
    second.close()

    assert _column_names(path, "turns") == columns_after_first_open
    assert columns_after_first_open.count("user_identity") == 1


def test_migration_keeps_indexes_and_new_identity_filter_works(tmp_path: Path) -> None:
    path = _legacy_database(tmp_path / "access-logs.sqlite3")
    store = AccessLogStore(path)
    store.record_turn(
        _new_turn(
            turn_id="turn:new:1",
            session_id="session:chat:legacy",
            user_identity="alice",
        )
    )
    connection = sqlite3.connect(path)
    indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    connection.close()
    assert {"turns_session_turn_count", "turns_started_at", "turns_status"} <= indexes

    matched, total = store.list_sessions(identity="alice")
    assert total == 1
    assert matched[0].identities == ("alice", "anonymous")

    anonymous, anonymous_total = store.list_sessions(identity="anonymous")
    assert anonymous_total == 1
    assert anonymous[0].session_id == "session:chat:legacy"
    store.close()
