from __future__ import annotations

import json

import pytest

from backend.services.canonical_v2_connection_tests import (
    CONNECTIONS,
    SPEC_BY_KEY,
    ConnectionTestRateLimiter,
    UnsafeEndpointError,
    build_request,
    normalize_base_url,
)
from backend.services.canonical_v2_connection_tests import (
    test_connection as run_connection_test,
)
from backend.services.canonical_v2_runtime_sources import (
    BOCHA_ENDPOINT,
    SERPER_ENDPOINT,
)

_FAKE_KEY = "sk-fake-connection-0000-1111-4f2a"


class _FakeTransport:
    """Records every call so tests can assert the one-call contract."""

    def __init__(self, *, status: int = 200, raises: Exception | None = None) -> None:
        self.status = status
        self.raises = raises
        self.calls: list[dict[str, object]] = []

    def __call__(self, url, *, payload, headers, timeout):
        self.calls.append(
            {"url": url, "payload": payload, "headers": headers, "timeout": timeout}
        )
        if self.raises is not None:
            raise self.raises
        return self.status, ""


def test_every_connection_declares_one_minimal_request() -> None:
    assert {spec.key for spec in CONNECTIONS} == {
        "bocha",
        "serper",
        "rerank",
        "embedding",
        "llm",
    }
    pinned = {"bocha": BOCHA_ENDPOINT, "serper": SERPER_ENDPOINT}
    for spec in CONNECTIONS:
        url, request_spec = build_request(
            spec,
            api_key=_FAKE_KEY,
            base_url=pinned.get(spec.key) or "http://127.0.0.1:18099/v1",
            model=None,
        )
        assert url.startswith("http")
        assert request_spec["payload"]
        assert request_spec["headers"]
        assert _FAKE_KEY in json.dumps(request_spec["headers"])


def test_success_reports_status_and_latency_only() -> None:
    transport = _FakeTransport(status=200)

    result = run_connection_test(
        SPEC_BY_KEY["bocha"],
        api_key=_FAKE_KEY,
        base_url=BOCHA_ENDPOINT,
        transport=transport,
    )

    assert result["ok"] is True
    assert result["http_status"] == 200
    assert result["latency_ms"] >= 0
    assert result["called"] is True
    assert len(transport.calls) == 1
    assert _FAKE_KEY not in json.dumps(result)
    # Bocha keeps its pinned provider host: a page cannot redirect a credential.
    assert transport.calls[0]["url"] == BOCHA_ENDPOINT


def test_failure_reports_status_without_body() -> None:
    transport = _FakeTransport(status=401)

    result = run_connection_test(
        SPEC_BY_KEY["serper"],
        api_key=_FAKE_KEY,
        base_url=SERPER_ENDPOINT,
        transport=transport,
    )

    assert result["ok"] is False
    assert result["http_status"] == 401
    assert "凭据被拒绝" in result["detail"]
    assert len(transport.calls) == 1


def test_transport_error_and_timeout_are_results_not_exceptions() -> None:
    failing = _FakeTransport(raises=ConnectionRefusedError("boom"))
    timeout = _FakeTransport(raises=TimeoutError())

    refused = run_connection_test(
        SPEC_BY_KEY["rerank"], base_url="http://127.0.0.1:18099", transport=failing
    )
    timed_out = run_connection_test(
        SPEC_BY_KEY["rerank"], base_url="http://127.0.0.1:18099", transport=timeout
    )

    assert refused["ok"] is False and "传输失败" in refused["detail"]
    assert timed_out["ok"] is False and "超时" in timed_out["detail"]


def test_missing_required_key_does_not_call_the_provider() -> None:
    transport = _FakeTransport(status=200)

    result = run_connection_test(
        SPEC_BY_KEY["bocha"], api_key="", base_url=BOCHA_ENDPOINT, transport=transport
    )

    assert result["ok"] is False
    assert result["called"] is False
    assert transport.calls == []
    assert "未配置凭据" in result["detail"]


def test_local_endpoints_accept_an_empty_key() -> None:
    transport = _FakeTransport(status=200)

    result = run_connection_test(
        SPEC_BY_KEY["embedding"],
        api_key="",
        base_url="http://100.64.0.27:18005/v1",
        transport=transport,
    )

    assert result["ok"] is True
    assert len(transport.calls) == 1
    assert transport.calls[0]["url"] == "http://100.64.0.27:18005/v1/embeddings"


@pytest.mark.parametrize(
    "value",
    [
        "ftp://example.com/v1",
        "https://user:pass@example.com/v1",
        "https://example.com/v1?token=abc",
        "/relative/path",
    ],
)
def test_unsafe_endpoints_are_rejected(value: str) -> None:
    with pytest.raises(UnsafeEndpointError):
        normalize_base_url(value)


def test_rate_limiter_enforces_interval_and_minute_cap() -> None:
    now = [1000.0]
    limiter = ConnectionTestRateLimiter(
        per_minute=3, min_interval_seconds=1.0, clock=lambda: now[0]
    )

    first = limiter.check(["conn:bocha", "client:1.2.3.4"])
    assert first.allowed is True
    assert first.remaining == 2

    # Same second → burst interval blocks, with a retry hint.
    blocked = limiter.check(["conn:bocha", "client:1.2.3.4"])
    assert blocked.allowed is False
    assert blocked.retry_after_seconds >= 1

    now[0] += 1.5
    assert limiter.check(["conn:bocha", "client:1.2.3.4"]).allowed is True
    now[0] += 1.5
    assert limiter.check(["conn:bocha", "client:1.2.3.4"]).allowed is True

    now[0] += 1.5
    over_cap = limiter.check(["conn:bocha", "client:1.2.3.4"])
    assert over_cap.allowed is False
    assert over_cap.retry_after_seconds > 30

    # The limiter enforces the connection window as well as the client window:
    # a second client cannot drain the per-connection budget either.
    other_client = limiter.check(["conn:bocha", "client:5.6.7.8"])
    assert other_client.allowed is False
    assert other_client.retry_after_seconds > 30
    # A different client on a different connection has its own window.
    assert limiter.check(["conn:serper", "client:5.6.7.8"]).allowed is True


def test_disabled_connection_is_reported_without_a_call() -> None:
    """Rerank without CANONICAL_V2_RERANK_BASE_URL: honest "not enabled", zero calls."""

    transport = _FakeTransport(status=200)

    result = run_connection_test(
        SPEC_BY_KEY["rerank"],
        api_key=_FAKE_KEY,
        base_url=None,
        transport=transport,
        disabled_reason="运行期未启用：未配置 CANONICAL_V2_RERANK_BASE_URL",
    )

    assert result["ok"] is False
    assert result["called"] is False
    assert result["http_status"] is None
    assert "未启用" in result["detail"]
    assert transport.calls == []


def test_chat_path_matches_the_openai_client_the_runtime_builds() -> None:
    """knowledge_serving_isolated.py:2087-2096 builds an OpenAI client from the profile."""

    url, request_spec = build_request(
        SPEC_BY_KEY["llm"],
        api_key=_FAKE_KEY,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )

    assert url == "https://api.deepseek.com/chat/completions"
    assert request_spec["payload"]["max_tokens"] == 1
