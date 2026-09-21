"""Embedding-lane breaker and its seam inside the serving embedding adapter (F1.4).

Clusters C of
`.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/verification-contract.md`.

Fixture sources: the breaker unit tests use an injected clock (constructed
scenario); the adapter tests drive the real `_OpenAICompatibleEmbeddingAdapter`
against a counting loopback HTTP server, so "no provider call" is observed as a
real HTTP request count.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
import json
import threading
from typing import Any

import pytest

RESILIENCE_MODULE = "src.data_agents.canonical_v2.embedding_lane_resilience"
BUILD_MODULE = "src.data_agents.canonical_v2.knowledge_build_isolated"


def _resilience() -> Any:
    return import_module(RESILIENCE_MODULE)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 21, 3, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def test_two_consecutive_failures_open_the_breaker_and_the_window_closes_it() -> None:
    breaker = _resilience().EmbeddingLaneBreaker(clock=_Clock())

    assert breaker.state("vector") == "closed"
    assert breaker.attempt_allowed("vector") == (True, "closed")

    breaker.record("vector", ok=False, reason="connection_failure")
    assert breaker.attempt_allowed("vector") == (True, "closed")

    breaker.record("vector", ok=False, reason="connection_failure")
    assert breaker.state("vector") == "open"
    assert breaker.attempt_allowed("vector") == (False, "open")
    assert breaker.reason("vector") == "connection_failure"


def test_the_window_reopens_the_lane_and_a_success_closes_it() -> None:
    clock = _Clock()
    breaker = _resilience().EmbeddingLaneBreaker(clock=clock)
    breaker.record("vector", ok=False)
    breaker.record("vector", ok=False)
    assert breaker.attempt_allowed("vector")[0] is False

    clock.advance(299.0)
    assert breaker.attempt_allowed("vector")[0] is False

    clock.advance(2.0)
    assert breaker.attempt_allowed("vector") == (True, "probe")

    breaker.record("vector", ok=True)
    assert breaker.state("vector") == "closed"
    assert breaker.attempt_allowed("vector") == (True, "closed")


def test_a_success_resets_the_consecutive_failure_count() -> None:
    breaker = _resilience().EmbeddingLaneBreaker(clock=_Clock())
    breaker.record("vector", ok=False)
    breaker.record("vector", ok=True)
    breaker.record("vector", ok=False)

    assert breaker.state("vector") == "closed"
    assert breaker.attempt_allowed("vector") == (True, "closed")


def test_an_outer_wait_expiry_counts_as_one_more_lane_failure() -> None:
    breaker = _resilience().EmbeddingLaneBreaker(clock=_Clock())
    breaker.record("vector", ok=False)
    breaker.note_lane_timeout()

    assert breaker.state("vector") == "open"
    assert breaker.reason("vector") == "timeout"


def test_the_threshold_and_window_are_operator_visible_constants() -> None:
    module = _resilience()
    assert module.BREAKER_FAILURE_THRESHOLD == 2
    assert module.BREAKER_WINDOW_SECONDS == 300.0


class _CountingHandler(BaseHTTPRequestHandler):
    requests = 0
    status = 200
    dimension = 3

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        type(self).requests += 1
        if type(self).status != 200:
            body = b"{}"
            self.send_response(type(self).status)
        else:
            data = [
                {
                    "index": index,
                    "embedding": [1.0] + [0.0] * (type(self).dimension - 1),
                }
                for index, _ in enumerate(payload.get("input", []))
            ]
            body = json.dumps({"data": data}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        return


def _counting_server(status: int) -> tuple[ThreadingHTTPServer, str]:
    handler = type("_Handler", (_CountingHandler,), {"requests": 0, "status": status})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/v1"


def _adapter(base_url: str, breaker: Any) -> Any:
    module = import_module(BUILD_MODULE)
    return module._OpenAICompatibleEmbeddingAdapter(
        model_id="Qwen/Qwen3-Embedding-8B",
        dimension=3,
        authority_sha256="0" * 64,
        base_url=base_url,
        batch_size=4,
        max_workers=2,
        timeout_seconds=2,
        role="document",
        breaker=breaker,
    )


def test_the_open_breaker_skips_the_provider_call_entirely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_KEY", "test-key")
    server, base_url = _counting_server(200)
    try:
        breaker = _resilience().EmbeddingLaneBreaker(
            failure_threshold=2, window_seconds=300.0
        )
        adapter = _adapter(base_url, breaker)

        assert len(adapter.embed_batch(("first",))) == 1
        calls_after_first = server.RequestHandlerClass.requests

        # Two consecutive transport failures open the breaker.
        adapter.base_url = f"http://127.0.0.1:{_dead_port()}/v1"
        for attempt in range(2):
            with pytest.raises(ConnectionError):
                adapter.embed_batch((f"failing-{attempt}",))

        adapter.base_url = base_url
        with pytest.raises(ConnectionError) as skipped:
            adapter.embed_batch(("while-open",))

        assert "breaker" in str(skipped.value).casefold()
        assert server.RequestHandlerClass.requests == calls_after_first
        assert breaker.state("vector") == "open"
    finally:
        server.shutdown()
        server.server_close()


def test_a_healthy_provider_keeps_the_breaker_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_KEY", "test-key")
    server, base_url = _counting_server(200)
    try:
        breaker = _resilience().EmbeddingLaneBreaker()
        adapter = _adapter(base_url, breaker)

        assert adapter.embed_batch(("query",))[0][0] == 1.0
        assert adapter.embed_batch(("other",))[0][0] == 1.0

        assert breaker.state("vector") == "closed"
        assert server.RequestHandlerClass.requests == 2
    finally:
        server.shutdown()
        server.server_close()


def _dead_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
