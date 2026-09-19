"""`GET /api/canonical-v2/admin/chat-gaps` and the write path behind it.

The console's own SQLite ledger is the only durable record of the knowledge-gap
signals a user files here (pack mode installs the in-process ephemeral
`gap_operations`), so the read surface must answer without Postgres and the
feedback path must keep answering when the ledger cannot be written.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
import pytest

from backend.canonical_v2_deps import get_canonical_v2_admin_runtime
from backend.main import app
from backend.services.canonical_v2_chat import ChatFeedbackCheckpoint
from backend.storage.chat_gaps import DB_FILENAME, ChatGapStore
from tests.conftest import authorized_client


_ENDPOINT = "/api/canonical-v2/admin/chat-gaps"
_FEEDBACK_ENDPOINT = "/api/chat/feedback"
_SESSION_COOKIE = "miroflow_chat_session"
_SESSION_ID = "session:chat:gaps"
_TURN_ID = "turn:chat:gaps:1"
_RELEASE_ID = "candidate-v2-20260920-r1"
_GAP_ID = "gap:chat-feedback:test"
_NOW = datetime(2026, 9, 20, 3, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every ledger read and write in tmp_path, never the serving state dir."""

    monkeypatch.setenv("CANONICAL_V2_CHAT_GAPS_DB", str(tmp_path / DB_FILENAME))


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / DB_FILENAME


def _row(
    signal_id: str,
    *,
    feedback_type: str = "incorrect_answer",
    note: str | None = None,
    minute: int = 0,
) -> dict[str, Any]:
    return {
        "signal_id": signal_id,
        "session_id": _SESSION_ID,
        "turn_id": _TURN_ID,
        "release_id": _RELEASE_ID,
        "feedback_type": feedback_type,
        "note": note,
        "query_trace_id": "query:chat:gaps",
        "answer_trace_id": "answer:chat:gaps",
        "observed_at": _NOW,
        "recorded_at": _NOW.replace(minute=minute),
    }


def _seed(path: Path, *rows: dict[str, Any]) -> None:
    store = ChatGapStore(path)
    try:
        for row in rows:
            store.record(row)
    finally:
        store.close()


class _ChatAdapter:
    def __init__(self, checkpoint: ChatFeedbackCheckpoint) -> None:
        self._checkpoint = checkpoint

    def get_feedback_checkpoint(self, session_id: str) -> ChatFeedbackCheckpoint | None:
        del session_id
        return self._checkpoint


class _GapOperations:
    """The ephemeral shape: it records a signal and returns the filed gap."""

    def __init__(self) -> None:
        self.signals: list[Any] = []

    def record(self, signal: Any) -> Any:
        self.signals.append(signal)
        return SimpleNamespace(gap_id=_GAP_ID, created_at=_NOW)


def _checkpoint() -> ChatFeedbackCheckpoint:
    return ChatFeedbackCheckpoint(
        session_id=_SESSION_ID,
        turn_id=_TURN_ID,
        release_id=_RELEASE_ID,
        query_trace_id="query:chat:gaps",
        answer_trace_id="answer:chat:gaps",
        evidence_ids=("company:c1",),
        affected_domains=("company",),
        affected_paths=("company_has_patent",),
        limitation_codes=(),
        observed_at=_NOW,
    )


def _runtime_with_feedback(*, gap_operations: Any, chat_adapter: Any = None) -> Any:
    from backend.services.canonical_v2_admin import CanonicalV2AdminRuntime

    return CanonicalV2AdminRuntime(
        release_id=_RELEASE_ID,
        manifest=SimpleNamespace(),
        candidate_projection=SimpleNamespace(),
        relationship_authority=SimpleNamespace(),
        planner=SimpleNamespace(),
        knowledge_read=SimpleNamespace(),
        chat_adapter=_ChatAdapter(_checkpoint())
        if chat_adapter is None
        else chat_adapter,
        gap_operations=gap_operations,
    )


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    prior = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(prior)


def _feedback_client(runtime: Any) -> TestClient:
    app.dependency_overrides[get_canonical_v2_admin_runtime] = lambda: runtime
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(_SESSION_COOKIE, _SESSION_ID)
    return client


def _feedback_body() -> dict[str, Any]:
    return {
        "query": "深圳哪些公司做激光雷达",
        "query_type": "canonical_v2:B",
        "answer_text": "共找到 6 个企业。",
        "feedback_type": "incorrect_answer",
        "note": "结果里有不相关企业",
    }


def test_an_empty_ledger_answers_200_without_a_console_database(
    ledger_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("DATABASE_URL", "DATABASE_URL_TEST", "CANONICAL_V2_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    had_dsn = hasattr(app.state, "console_dsn")
    prior_dsn = getattr(app.state, "console_dsn", None)
    app.state.console_dsn = None
    try:
        response = authorized_client().get(_ENDPOINT)
    finally:
        if had_dsn:
            app.state.console_dsn = prior_dsn
        else:
            delattr(app.state, "console_dsn")

    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "total": 0, "counts": {}}
    # The ledger file is created empty by the read itself; nothing was filed yet.
    assert ledger_path.is_file()


def test_recorded_signals_are_listed_with_their_counts(ledger_path: Path) -> None:
    _seed(
        ledger_path,
        _row("gap-signal:chat-feedback:sha256:aaa", minute=0),
        _row(
            "gap-signal:chat-feedback:sha256:bbb",
            feedback_type="missing_source",
            note="没有找到来源",
            minute=1,
        ),
        _row("gap-signal:chat-feedback:sha256:ccc", minute=2),
    )

    response = authorized_client().get(_ENDPOINT)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    assert payload["counts"] == {"incorrect_answer": 2, "missing_source": 1}
    assert [item["signal_id"] for item in payload["items"]] == [
        "gap-signal:chat-feedback:sha256:ccc",
        "gap-signal:chat-feedback:sha256:bbb",
        "gap-signal:chat-feedback:sha256:aaa",
    ]
    assert payload["items"][1] == {
        "signal_id": "gap-signal:chat-feedback:sha256:bbb",
        "session_id": _SESSION_ID,
        "turn_id": _TURN_ID,
        "release_id": _RELEASE_ID,
        "feedback_type": "missing_source",
        "note": "没有找到来源",
        "query_trace_id": "query:chat:gaps",
        "answer_trace_id": "answer:chat:gaps",
        "observed_at": _NOW.isoformat(),
        "recorded_at": _NOW.replace(minute=1).isoformat(),
    }


def test_the_type_filter_narrows_the_items_but_not_the_ledger_totals(
    ledger_path: Path,
) -> None:
    _seed(
        ledger_path,
        _row("gap-signal:chat-feedback:sha256:aaa", minute=0),
        _row(
            "gap-signal:chat-feedback:sha256:bbb",
            feedback_type="missing_source",
            minute=1,
        ),
    )

    response = authorized_client().get(
        _ENDPOINT, params={"feedback_type": "missing_source"}
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["signal_id"] for item in payload["items"]] == [
        "gap-signal:chat-feedback:sha256:bbb"
    ]
    assert payload["total"] == 2
    assert payload["counts"] == {"incorrect_answer": 1, "missing_source": 1}
    assert sum(payload["counts"].values()) == payload["total"]


@pytest.mark.parametrize("limit", [0, 201])
def test_a_limit_outside_one_to_two_hundred_is_refused(limit: int) -> None:
    response = authorized_client().get(_ENDPOINT, params={"limit": limit})

    assert response.status_code == 422


def test_the_limit_caps_the_listed_items(ledger_path: Path) -> None:
    _seed(
        ledger_path,
        _row("gap-signal:chat-feedback:sha256:aaa", minute=0),
        _row("gap-signal:chat-feedback:sha256:bbb", minute=1),
    )

    response = authorized_client().get(_ENDPOINT, params={"limit": 1})

    assert response.status_code == 200, response.text
    assert [item["signal_id"] for item in response.json()["items"]] == [
        "gap-signal:chat-feedback:sha256:bbb"
    ]


def test_the_surface_is_session_gated() -> None:
    response = TestClient(app, raise_server_exceptions=False).get(_ENDPOINT)

    assert response.status_code == 401


def test_filed_feedback_lands_in_the_ledger(ledger_path: Path) -> None:
    gap_operations = _GapOperations()
    client = _feedback_client(_runtime_with_feedback(gap_operations=gap_operations))

    response = client.post(_FEEDBACK_ENDPOINT, json=_feedback_body())

    assert response.status_code == 200, response.text
    assert response.json()["issue_id"] == _GAP_ID
    assert len(gap_operations.signals) == 1
    signal_id = gap_operations.signals[0].signal_id
    assert signal_id.startswith("gap-signal:chat-feedback:sha256:")
    store = ChatGapStore(ledger_path)
    try:
        rows = store.list_recent()
    finally:
        store.close()
    assert rows == [
        {
            "signal_id": signal_id,
            "session_id": _SESSION_ID,
            "turn_id": _TURN_ID,
            "release_id": _RELEASE_ID,
            "feedback_type": "incorrect_answer",
            "note": "结果里有不相关企业",
            "query_trace_id": "query:chat:gaps",
            "answer_trace_id": "answer:chat:gaps",
            "observed_at": _NOW.isoformat(),
            "recorded_at": rows[0]["recorded_at"],
        }
    ]


def test_filing_the_same_feedback_twice_leaves_one_row(ledger_path: Path) -> None:
    client = _feedback_client(_runtime_with_feedback(gap_operations=_GapOperations()))

    first = client.post(_FEEDBACK_ENDPOINT, json=_feedback_body())
    second = client.post(_FEEDBACK_ENDPOINT, json=_feedback_body())

    assert (first.status_code, second.status_code) == (200, 200)
    store = ChatGapStore(ledger_path)
    try:
        assert store.total() == 1
    finally:
        store.close()


def test_a_broken_ledger_leaves_the_feedback_response_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    healthy = _feedback_client(_runtime_with_feedback(gap_operations=_GapOperations()))
    expected = healthy.post(_FEEDBACK_ENDPOINT, json=_feedback_body())
    assert expected.status_code == 200, expected.text

    # The ledger's parent is a file: the store cannot even be created.
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setenv("CANONICAL_V2_CHAT_GAPS_DB", str(blocker / "chat-gaps.sqlite3"))

    broken = _feedback_client(_runtime_with_feedback(gap_operations=_GapOperations()))
    response = broken.post(_FEEDBACK_ENDPOINT, json=_feedback_body())

    assert response.status_code == expected.status_code
    assert response.json() == expected.json()
    assert json.loads(json.dumps(response.json()))["status"] == "filed"
