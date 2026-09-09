"""Task 1.1.3 — serving-layer trace reporting via the contextvar bridge.

Hermetic tests with fake providers: provider errors/timeouts surface as web
outcome rows, an all-providers-outage turn sets the web-lane-unavailable
degradation token, and the subject-consistency gate reports its drop count.
Absence of a reporter stays a no-op (build/isolated paths untouched).
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace
from typing import Any

serving = import_module(
    "src.data_agents.canonical_v2.knowledge_serving_isolated"
)
trace_context = import_module("src.data_agents.canonical_v2.turn_trace_context")


class RecordingReporter:
    def __init__(self) -> None:
        self.gate_drops: dict[str, int] = {}
        self.web_outcomes: list[dict[str, Any]] = []
        self.degradations: list[str] = []
        self.lanes: dict[str, dict[str, int]] = {}

    def record_gate_drop(self, gate_name: str, count: int) -> None:
        self.gate_drops[gate_name] = self.gate_drops.get(gate_name, 0) + count

    def record_web_outcome(self, **kwargs: Any) -> None:
        self.web_outcomes.append(kwargs)

    def set_degradation(self, token: str) -> None:
        self.degradations.append(token)

    def record_lane_counts(
        self, lane: str, *, in_: int, retained: int, filtered: int
    ) -> None:
        self.lanes[lane] = {"in": in_, "retained": retained, "filtered": filtered}


class _RaisingProvider:
    def search(self, query: str) -> dict[str, Any]:
        raise RuntimeError("channel down")


class _EmptyProvider:
    def search(self, query: str) -> dict[str, Any]:
        return {"organic": []}


class _SlowProvider:
    import time as _time

    def search(self, query: str) -> dict[str, Any]:
        import time

        time.sleep(1.0)
        return {"organic": []}


def _adapter(*, bocha: Any, serper: Any, timeout_ms: int = 8000) -> Any:
    return serving._DualWebLaneAdapter(
        timeout_ms=timeout_ms,
        max_snapshot_bytes=1024,
        clock=lambda: datetime.now(UTC),
        bocha=bocha,
        serper=serper,
    )


def test_all_providers_error_sets_web_lane_unavailable() -> None:
    reporter = RecordingReporter()
    adapter = _adapter(bocha=_RaisingProvider(), serper=_RaisingProvider())
    token = trace_context.set_turn_trace_reporter(reporter)
    try:
        merged = adapter._merged_results("云迹科技")
    finally:
        trace_context.reset_turn_trace_reporter(token)
    assert merged == ()
    errors = {
        (row["provider"], row["errored"], row["timed_out"])
        for row in reporter.web_outcomes
    }
    assert ("bocha-v1", 1, 0) in errors
    assert ("serper-v1", 1, 0) in errors
    assert "web-lane-unavailable" in reporter.degradations


def test_partial_failure_reports_error_without_degradation() -> None:
    reporter = RecordingReporter()
    adapter = _adapter(bocha=_EmptyProvider(), serper=_RaisingProvider())
    token = trace_context.set_turn_trace_reporter(reporter)
    try:
        merged = adapter._merged_results("云迹科技")
    finally:
        trace_context.reset_turn_trace_reporter(token)
    assert merged == ()
    assert any(row["provider"] == "serper-v1" and row["errored"] == 1
               for row in reporter.web_outcomes)
    assert reporter.degradations == []


def test_provider_timeout_reported_as_timed_out() -> None:
    reporter = RecordingReporter()
    adapter = _adapter(bocha=_EmptyProvider(), serper=_SlowProvider(),
                       timeout_ms=400)
    token = trace_context.set_turn_trace_reporter(reporter)
    try:
        adapter._merged_results("云迹科技")
    finally:
        trace_context.reset_turn_trace_reporter(token)
    assert any(row["provider"] == "serper-v1" and row["timed_out"] == 1
               for row in reporter.web_outcomes)
    # Bocha answered (empty but successful): the channel was reachable, so no
    # channel-outage token may be set.
    assert reporter.degradations == []


def test_subject_consistency_gate_reports_drop_count() -> None:
    def result(title: str, url: str) -> Any:
        return serving._NormalizedWebResult(
            title=title,
            url=url,
            snippet="",
            summary="",
            primary_provider_version="bocha-v1",
            corroborating_provider_versions=("bocha-v1",),
        )

    matching = [
        result(f"云迹科技 新闻 {index}", f"https://example.com/good/{index}")
        for index in range(3)
    ]
    unrelated = [
        result("某无关公司甲", "https://example.com/bad/1"),
        result("另一个无关条目", "https://example.com/bad/2"),
    ]
    request = SimpleNamespace(
        bound_entity_names=("云迹科技",),
        soft_context_subject=None,
        original_query="介绍云迹科技",
    )
    reporter = RecordingReporter()
    token = trace_context.set_turn_trace_reporter(reporter)
    try:
        filtered = serving._apply_web_subject_consistency(
            results=tuple(matching + unrelated), request=request
        )
    finally:
        trace_context.reset_turn_trace_reporter(token)
    assert len(filtered) == 3
    assert reporter.gate_drops == {"web_subject_consistency": 2}


def test_absent_reporter_is_noop() -> None:
    adapter = _adapter(bocha=_EmptyProvider(), serper=_RaisingProvider())
    assert adapter._merged_results("云迹科技") == ()
