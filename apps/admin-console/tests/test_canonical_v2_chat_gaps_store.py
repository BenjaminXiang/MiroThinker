"""The durable chat-gap ledger: one row per filed feedback signal.

The serving composition installs the in-process ephemeral gap feedback in pack
mode, so a filed signal only survives in this ledger. These tests pin the
storage contract the admin read surface is built on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.storage.chat_gaps import (
    DEFAULT_STATE_DIR,
    DB_FILENAME,
    ChatGapStore,
    chat_gaps_database_path,
)


_NOW = datetime(2026, 9, 20, 3, 30, tzinfo=UTC)


def _entry(
    signal_id: str,
    *,
    feedback_type: str = "incorrect_answer",
    note: str | None = None,
    minutes: int = 0,
) -> dict[str, Any]:
    return {
        "signal_id": signal_id,
        "session_id": "session:chat:1",
        "turn_id": "turn:chat:1",
        "release_id": "candidate-v2-20260920-r1",
        "feedback_type": feedback_type,
        "note": note,
        "query_trace_id": "query:trace:1",
        "answer_trace_id": "answer:trace:1",
        "observed_at": _NOW,
        "recorded_at": _NOW + timedelta(minutes=minutes),
    }


def _store(tmp_path: Path) -> ChatGapStore:
    return ChatGapStore(tmp_path / DB_FILENAME)


def test_a_recorded_signal_is_listed_counted_and_totalled(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        assert store.record(_entry("gap-signal:chat-feedback:sha256:aaa")) is True

        rows = store.list_recent()
        assert len(rows) == 1
        assert rows[0] == {
            "signal_id": "gap-signal:chat-feedback:sha256:aaa",
            "session_id": "session:chat:1",
            "turn_id": "turn:chat:1",
            "release_id": "candidate-v2-20260920-r1",
            "feedback_type": "incorrect_answer",
            "note": None,
            "query_trace_id": "query:trace:1",
            "answer_trace_id": "answer:trace:1",
            "observed_at": _NOW.isoformat(),
            "recorded_at": _NOW.isoformat(),
        }
        assert store.counts_by_type() == {"incorrect_answer": 1}
        assert store.total() == 1
    finally:
        store.close()


def test_the_same_signal_twice_stays_one_row(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        assert store.record(_entry("gap-signal:chat-feedback:sha256:aaa")) is True

        assert store.record(_entry("gap-signal:chat-feedback:sha256:aaa")) is False

        assert store.total() == 1
        assert len(store.list_recent()) == 1
    finally:
        store.close()


def test_the_ledger_survives_a_reopened_file(tmp_path: Path) -> None:
    first = _store(tmp_path)
    try:
        first.record(_entry("gap-signal:chat-feedback:sha256:aaa"))
    finally:
        first.close()

    second = _store(tmp_path)
    try:
        assert second.total() == 1
        assert second.record(_entry("gap-signal:chat-feedback:sha256:aaa")) is False
    finally:
        second.close()


def test_the_newest_signal_is_listed_first(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.record(_entry("gap-signal:chat-feedback:sha256:aaa", minutes=0))
        store.record(
            _entry(
                "gap-signal:chat-feedback:sha256:bbb",
                feedback_type="missing_source",
                minutes=5,
            )
        )
        store.record(_entry("gap-signal:chat-feedback:sha256:ccc", minutes=1))

        assert [row["signal_id"] for row in store.list_recent()] == [
            "gap-signal:chat-feedback:sha256:bbb",
            "gap-signal:chat-feedback:sha256:ccc",
            "gap-signal:chat-feedback:sha256:aaa",
        ]
        assert [row["signal_id"] for row in store.list_recent(limit=2)] == [
            "gap-signal:chat-feedback:sha256:bbb",
            "gap-signal:chat-feedback:sha256:ccc",
        ]
    finally:
        store.close()


def test_the_feedback_type_filter_narrows_only_the_listed_rows(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.record(
            _entry(
                "gap-signal:chat-feedback:sha256:aaa",
                feedback_type="missing_source",
                minutes=1,
            )
        )
        store.record(
            _entry(
                "gap-signal:chat-feedback:sha256:bbb",
                feedback_type="incorrect_answer",
                note="企业不相关",
                minutes=2,
            )
        )

        filtered = store.list_recent(feedback_type="incorrect_answer")
        assert [row["signal_id"] for row in filtered] == [
            "gap-signal:chat-feedback:sha256:bbb"
        ]
        assert filtered[0]["note"] == "企业不相关"
        assert store.list_recent(feedback_type="never_seen") == []
        assert store.counts_by_type() == {
            "incorrect_answer": 1,
            "missing_source": 1,
        }
        assert store.total() == 2
    finally:
        store.close()


def test_the_ledger_sits_in_the_state_directory_the_other_ledgers_use() -> None:
    state = Path("/var/tmp/scratch-state")
    assert (
        chat_gaps_database_path(
            {"CANONICAL_V2_CHAT_GAPS_DB": str(state / "own.sqlite3")}
        )
        == state / "own.sqlite3"
    )
    assert (
        chat_gaps_database_path(
            {
                "CANONICAL_V2_JOBS_DB": str(state / "jobs.sqlite3"),
                "CANONICAL_V2_ACCESS_LOG_DB": str(state / "access-logs.sqlite3"),
            }
        )
        == state / DB_FILENAME
    )
    assert (
        chat_gaps_database_path(
            {"CANONICAL_V2_ACCESS_LOG_DB": str(state / "access-logs.sqlite3")}
        )
        == state / DB_FILENAME
    )
    assert chat_gaps_database_path({}) == DEFAULT_STATE_DIR / DB_FILENAME


def test_a_missing_state_directory_is_created_for_the_ledger(tmp_path: Path) -> None:
    nested = tmp_path / "state" / "nested"
    assert chat_gaps_database_path(
        {"CANONICAL_V2_JOBS_DB": str(nested / "jobs.sqlite3")}
    ) == (nested / DB_FILENAME)

    store = ChatGapStore(nested / DB_FILENAME)
    try:
        assert store.record(_entry("gap-signal:chat-feedback:sha256:aaa")) is True
    finally:
        store.close()
    assert (nested / DB_FILENAME).is_file()
