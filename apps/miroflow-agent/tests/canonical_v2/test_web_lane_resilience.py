"""Task 1.3 — web-lane resilience unit + adapter tests (RED-first per contract).

Adapter-level rows (retry / cache / breaker / quota engaging through
``_merged_results`` with the trace reporter attached) are the RED surface:
they fail against the pre-1.3 adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any

import pytest

serving = import_module(
    "src.data_agents.canonical_v2.knowledge_serving_isolated"
)
trace_context = import_module(
    "src.data_agents.canonical_v2.turn_trace_context"
)
resilience = import_module(
    "src.data_agents.canonical_v2.web_lane_resilience"
)


class RecordingReporter:
    def __init__(self) -> None:
        self.web_outcomes: list[dict[str, Any]] = []
        self.degradations: list[str] = []

    def record_gate_drop(self, gate_name: str, count: int) -> None: ...

    def record_web_outcome(self, **kwargs: Any) -> None:
        self.web_outcomes.append(kwargs)

    def set_degradation(self, token: str) -> None:
        self.degradations.append(token)

    def record_lane_counts(self, lane: str, **_: Any) -> None: ...

    def outcomes_for(self, provider: str) -> list[dict[str, Any]]:
        return [row for row in self.web_outcomes if row["provider"] == provider]


class _CountingProvider:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.calls = 0
        self._results = results if results is not None else [
            {"title": "云迹科技", "link": "https://example.com/1", "snippet": "s"}
        ]

    def search(self, query: str) -> dict[str, Any]:
        self.calls += 1
        return {"organic": list(self._results)}


class _FlakyProvider(_CountingProvider):
    """Raises a transport error on the first `failures` calls."""

    def __init__(self, failures: int = 1) -> None:
        super().__init__()
        self._remaining_failures = failures

    def search(self, query: str) -> dict[str, Any]:
        self.calls += 1
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise ConnectionError("connection reset by peer")
        return {"organic": list(self._results)}


class _DeadProvider:
    def __init__(self, message: str = "connection refused") -> None:
        self.calls = 0
        self._message = message

    def search(self, query: str) -> dict[str, Any]:
        self.calls += 1
        raise RuntimeError(self._message)


def _adapter(*, bocha: Any, serper: Any, tmp_path: Any = None) -> Any:
    kwargs: dict[str, Any] = dict(
        timeout_ms=8000,
        max_snapshot_bytes=1024,
        clock=lambda: datetime.now(UTC),
        bocha=bocha,
        serper=serper,
    )
    if tmp_path is not None:
        kwargs["resilience_store"] = resilience._WebLaneStore(root=tmp_path)
    return serving._DualWebLaneAdapter(**kwargs)


def _run(adapter: Any, reporter: RecordingReporter, query: str = "云迹科技") -> Any:
    token = trace_context.set_turn_trace_reporter(reporter)
    try:
        return adapter._merged_results(query)
    finally:
        trace_context.reset_turn_trace_reporter(token)


def test_transport_error_retried_once_and_serves(tmp_path) -> None:
    bocha = _FlakyProvider(failures=1)
    serper = _CountingProvider()
    adapter = _adapter(bocha=bocha, serper=serper, tmp_path=tmp_path)
    reporter = RecordingReporter()
    merged = _run(adapter, reporter)
    assert len(merged) >= 1  # bocha recovered via retry
    assert bocha.calls == 2
    bocha_rows = reporter.outcomes_for("bocha-v1")
    assert any(row["retried"] == 1 and row["errored"] == 0 for row in bocha_rows)


def test_auth_quota_errors_not_retried(tmp_path) -> None:
    bocha = _CountingProvider()
    serper = _DeadProvider("Serper API error: not enough credits")
    adapter = _adapter(bocha=bocha, serper=serper, tmp_path=tmp_path)
    reporter = RecordingReporter()
    merged = _run(adapter, reporter)
    assert serper.calls == 1  # no retry on quota errors
    row = reporter.outcomes_for("serper-v1")[0]
    assert row["retried"] == 0 and row["errored"] == 1


def test_cache_hit_on_second_identical_view(tmp_path) -> None:
    bocha = _CountingProvider()
    serper = _CountingProvider(results=[])
    adapter = _adapter(bocha=bocha, serper=serper, tmp_path=tmp_path)
    reporter = RecordingReporter()
    _run(adapter, reporter)
    first_calls = bocha.calls
    _run(adapter, RecordingReporter())
    assert bocha.calls == first_calls  # served from cache
    rows = RecordingReporter()
    _run(adapter, rows)
    assert any(row["cache_hit"] == 1 for row in rows.outcomes_for("bocha-v1"))


def test_breaker_opens_after_consecutive_failures_and_skips(tmp_path) -> None:
    bocha = _DeadProvider()
    serper = _CountingProvider()
    adapter = _adapter(bocha=bocha, serper=serper, tmp_path=tmp_path)
    reporter = RecordingReporter()
    for _ in range(3):
        _run(adapter, reporter)
    # Transport errors retry once, so each failed turn costs two provider
    # calls; three turns then trip the breaker (three recorded failures).
    calls_after_three = bocha.calls
    assert calls_after_three == 6
    assert adapter._breaker.state("bocha-v1") == "open"
    # 4th turn: breaker open — bocha not attempted at all
    _run(adapter, RecordingReporter())
    assert bocha.calls == calls_after_three
    rows = reporter.outcomes_for("bocha-v1")
    assert len(rows) >= 1


def test_breaker_probe_recovers_after_cooldown(tmp_path) -> None:
    flaky = _FlakyProvider(failures=1)
    bocha = _CountingProvider()
    serper = _CountingProvider(results=[])
    adapter = _adapter(bocha=bocha, serper=serper, tmp_path=tmp_path)
    # force the breaker open with a dead provider injected directly
    dead = _DeadProvider()
    for _ in range(3):
        adapter._breaker.record("bocha-v1", False, "transport")
    assert adapter._breaker.state("bocha-v1") == "open"
    # user turns skip while open
    _run(adapter, RecordingReporter())
    assert bocha.calls == 0
    # after cooldown, a probe runs and success closes the breaker
    adapter._breaker._cooldown_seconds = 0.0
    _run(adapter, RecordingReporter())
    assert bocha.calls == 1
    assert adapter._breaker.state("bocha-v1") == "closed"


def test_quota_watermark_blocks_keepwarm_not_user_turns(tmp_path) -> None:
    import os

    store = resilience._WebLaneStore(root=tmp_path)
    adapter = _adapter(bocha=_CountingProvider(), serper=_CountingProvider())
    adapter._resilience_store = store
    # Watermark semantics: keepwarm stops ABOVE the watermark (count 2 > 1).
    adapter._quota_watermark = 1
    day = resilience._utc_day(None)
    store.quota_incr("bocha-v1", day)
    store.quota_incr("bocha-v1", day)
    assert not adapter.keepwarm_allowed("bocha-v1")
    reporter = RecordingReporter()
    _run(adapter, reporter)  # user turn still searches
    assert any(
        row["provider"] == "bocha-v1" and row["attempted"] == 1
        for row in reporter.web_outcomes
    )


def test_serper_provider_no_longer_sticky_disables(monkeypatch) -> None:
    provider_module = import_module(
        "src.data_agents.providers.web_search"
    )

    class _RaisingSession:
        def post(self, *_: Any, **__: Any) -> Any:
            raise RuntimeError("not enough credits")

        def close(self) -> None: ...

    provider = provider_module.WebSearchProvider(api_key="k")
    provider.session = _RaisingSession()
    with pytest.raises(RuntimeError, match="credit"):
        provider.search("query")
    # second call still attempts (no process-lifetime disable)
    with pytest.raises(RuntimeError):
        provider.search("query")


def test_bocha_provider_raises_on_error_payload() -> None:
    provider_module = import_module(
        "src.data_agents.providers.bocha_search"
    )

    class _ErrorPayloadSession:
        def post(self, *_: Any, **__: Any) -> Any:
            class _Response:
                def raise_for_status(self) -> None: ...

                def json(self) -> dict[str, Any]:
                    return {"code": "401", "msg": "invalid api key"}

            return _Response()

        def close(self) -> None: ...

    provider = provider_module.BochaSearchProvider(api_key="k")
    provider.session = _ErrorPayloadSession()
    with pytest.raises(RuntimeError, match="401"):
        provider.search("query")


def test_classify_search_error() -> None:
    assert resilience.classify_search_error(RuntimeError("not enough credits")) == (False, "quota")
    assert resilience.classify_search_error(RuntimeError("401 Unauthorized"))[1] == "auth"
    assert resilience.classify_search_error(ConnectionError("reset"))[0] is True
