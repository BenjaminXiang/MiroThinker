"""Bounded connectivity tests for the operator-visible model/search connections.

Requirement R16 (2026-09-15): every connection on the admin page gets a
"connectivity test" button, and the test may run **before** anything is saved —
the operator types an endpoint or a key, presses test, and sees success/failure
plus latency. Three properties make that safe:

1. **One minimal call.** Each connection has one fixed, cheap request shape
   (a one-token completion, a single-document rerank, a one-word embedding, a
   one-result search). Nothing here walks a corpus or streams.
2. **Rate limiting.** The button is cheap for a human and expensive if hammered,
   so the limiter is server-side, per connection and per client, and a rejected
   call never reaches the network.
3. **No credential, no upstream body.** The result carries a status, a latency
   and a sanitized reason. Response bodies are discarded, and the key is never
   echoed, logged or returned.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from threading import Lock
from time import monotonic
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit

DEFAULT_TIMEOUT_SECONDS = 5.0
PING_TEXT = "ping"

_RERANK_PATH = "/v1/rerank"
_EMBEDDING_PATH = "/v1/embeddings"
_CHAT_PATH = "/v1/chat/completions"


@dataclass(frozen=True, slots=True)
class ConnectionSpec:
    """One testable connection: how to reach it, and what it needs."""

    key: str
    label: str
    kind: str
    secret_field: str
    requires_key: bool
    default_base_url: str | None
    default_model: str | None = None
    base_url_field: str | None = None
    model_field: str | None = None
    base_url_editable: bool = True


CONNECTIONS: tuple[ConnectionSpec, ...] = (
    ConnectionSpec(
        key="bocha",
        label="Bocha 博查 Web 搜索",
        kind="web_search",
        secret_field="bocha.api_key",
        requires_key=True,
        default_base_url="https://api.bochaai.com/v1/web-search",
        # The provider host is pinned: a page that could redirect a credential to
        # an arbitrary host would be a credential-exfiltration surface.
        base_url_editable=False,
    ),
    ConnectionSpec(
        key="serper",
        label="Serper Web 搜索",
        kind="web_search",
        secret_field="serper.api_key",
        requires_key=True,
        default_base_url="https://google.serper.dev/search",
        base_url_editable=False,
    ),
    ConnectionSpec(
        key="rerank",
        label="Rerank 模型端点",
        kind="rerank",
        secret_field="rerank.api_key",
        requires_key=False,
        default_base_url="http://100.64.0.27:18006",
        default_model="qwen3-reranker-8b",
        base_url_field="extraction_endpoints.rerank_base_url",
        model_field="extraction_endpoints.rerank_model",
    ),
    ConnectionSpec(
        key="embedding",
        label="Embedding 模型端点",
        kind="embedding",
        secret_field="embedding.api_key",
        requires_key=False,
        default_base_url="http://100.64.0.27:18005/v1",
        default_model="Qwen/Qwen3-Embedding-8B",
        base_url_field="extraction_endpoints.embedding_base_url",
        model_field="extraction_endpoints.embedding_model",
    ),
    ConnectionSpec(
        key="llm",
        label="LLM 档位（本地/校内）",
        kind="llm",
        secret_field="llm.api_key",
        requires_key=False,
        default_base_url=None,
        base_url_field="extraction_endpoints.llm_base_url",
        model_field="extraction_endpoints.llm_model",
    ),
)

SPEC_BY_KEY: dict[str, ConnectionSpec] = {spec.key: spec for spec in CONNECTIONS}


class UnsafeEndpointError(ValueError):
    """The submitted endpoint is not an acceptable absolute http(s) URL."""


def normalize_base_url(value: str | None, *, default: str | None = None) -> str | None:
    """Validate an operator-submitted endpoint and strip the trailing slash."""

    text = "" if value is None else str(value).strip()
    if not text:
        return default
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise UnsafeEndpointError("endpoint must be an absolute http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeEndpointError("endpoint must not embed credentials")
    if parsed.query or parsed.fragment:
        raise UnsafeEndpointError("endpoint must not carry a query or fragment")
    return text.rstrip("/")


def _join(base_url: str, path: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith(path):
        return root
    if root.endswith("/v1") and path.startswith("/v1/"):
        return root + path[len("/v1") :]
    return root + path


def build_request(
    spec: ConnectionSpec,
    *,
    api_key: str,
    base_url: str | None,
    model: str | None,
) -> tuple[str, dict[str, Any]]:
    """Return the single minimal request ``(url, {payload, headers})`` for a connection."""

    key = api_key.strip()
    resolved_base = base_url or spec.default_base_url
    resolved_model = model or spec.default_model
    if spec.kind == "web_search":
        if spec.key == "bocha":
            url = resolved_base or ""
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            payload: dict[str, Any] = {"query": PING_TEXT, "count": 1}
        else:
            url = resolved_base or ""
            headers = {"X-API-KEY": key, "Content-Type": "application/json"}
            payload = {"q": PING_TEXT, "num": 1}
        return url, {"payload": payload, "headers": headers}
    if not resolved_base:
        raise UnsafeEndpointError("endpoint is not configured")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if spec.kind == "rerank":
        payload = {
            "model": resolved_model,
            "query": PING_TEXT,
            "documents": [PING_TEXT],
            "top_n": 1,
        }
        return _join(resolved_base, _RERANK_PATH), {
            "payload": payload,
            "headers": headers,
        }
    if spec.kind == "embedding":
        payload = {"model": resolved_model, "input": PING_TEXT}
        return _join(resolved_base, _EMBEDDING_PATH), {
            "payload": payload,
            "headers": headers,
        }
    payload = {
        "model": resolved_model,
        "messages": [{"role": "user", "content": PING_TEXT}],
        "max_tokens": 1,
    }
    return _join(resolved_base, _CHAT_PATH), {"payload": payload, "headers": headers}


def post_json(
    url: str, *, payload: Mapping[str, Any], headers: Mapping[str, str], timeout: float
) -> tuple[int, str]:
    """One bounded POST. The body is read but never returned to the caller."""

    request = urllib_request.Request(
        url,
        data=json.dumps(dict(payload), ensure_ascii=False).encode("utf-8"),
        headers=dict(headers),
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            return int(response.status), ""
    except urllib_error.HTTPError as exc:
        return int(exc.code), ""


Transport = Callable[..., tuple[int, str]]


def test_connection(
    spec: ConnectionSpec,
    *,
    api_key: str = "",
    base_url: str | None = None,
    model: str | None = None,
    transport: Transport | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Perform exactly one minimal call and report status + latency only."""

    if spec.requires_key and not api_key.strip():
        return {
            "ok": False,
            "latency_ms": 0,
            "http_status": None,
            "detail": "未配置凭据：请先在页面填入并保存（或直接填入后点测试）",
        }
    try:
        url, request_spec = build_request(
            spec, api_key=api_key, base_url=base_url, model=model
        )
    except UnsafeEndpointError as exc:
        return {
            "ok": False,
            "latency_ms": 0,
            "http_status": None,
            "detail": f"端点不合法：{exc}",
        }
    caller = transport or post_json
    started = monotonic()
    try:
        status, _body = caller(
            url,
            payload=request_spec["payload"],
            headers=request_spec["headers"],
            timeout=timeout,
        )
    except TimeoutError:
        return {
            "ok": False,
            "latency_ms": int((monotonic() - started) * 1000),
            "http_status": None,
            "detail": f"超时（>{timeout:g}s）",
        }
    except Exception as exc:  # noqa: BLE001 - any transport failure is a result
        return {
            "ok": False,
            "latency_ms": int((monotonic() - started) * 1000),
            "http_status": None,
            "detail": f"传输失败（{type(exc).__name__}）",
        }
    latency_ms = int((monotonic() - started) * 1000)
    status = int(status)
    if 200 <= status < 300:
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "http_status": status,
            "detail": f"HTTP {status}",
        }
    if status in {401, 403}:
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "http_status": status,
            "detail": f"HTTP {status}：端点可达，凭据被拒绝",
        }
    if status in {404, 405}:
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "http_status": status,
            "detail": f"HTTP {status}：端点可达，但路径或方法不被接受",
        }
    return {
        "ok": False,
        "latency_ms": latency_ms,
        "http_status": status,
        "detail": f"HTTP {status}",
    }


# -- rate limiting -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: int
    remaining: int


class ConnectionTestRateLimiter:
    """Sliding-window limiter enforcing both a burst interval and a per-minute cap."""

    def __init__(
        self,
        *,
        per_minute: int = 6,
        min_interval_seconds: float = 1.0,
        clock: Callable[[], float] | None = None,
        max_scopes: int = 2048,
    ) -> None:
        self.per_minute = int(per_minute)
        self.min_interval_seconds = float(min_interval_seconds)
        self._clock = clock or monotonic
        self._max_scopes = int(max_scopes)
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _prune(self, scope: str, now: float) -> deque[float]:
        events = self._events.setdefault(scope, deque())
        cutoff = now - 60.0
        while events and events[0] <= cutoff:
            events.popleft()
        return events

    def check(self, scopes: Sequence[str], *, record: bool = True) -> RateDecision:
        """Return the decision for one test attempt; records it when allowed."""

        now = self._clock()
        retry_after = 0.0
        remaining = self.per_minute
        with self._lock:
            for scope in scopes:
                events = self._prune(scope, now)
                if events:
                    since_last = now - events[-1]
                    if since_last < self.min_interval_seconds:
                        retry_after = max(
                            retry_after, self.min_interval_seconds - since_last
                        )
                if len(events) >= self.per_minute:
                    retry_after = max(retry_after, 60.0 - (now - events[0]))
                remaining = min(remaining, max(0, self.per_minute - len(events)))
            if retry_after > 0:
                return RateDecision(
                    allowed=False,
                    retry_after_seconds=max(1, int(retry_after + 0.999)),
                    remaining=remaining,
                )
            if record:
                if len(self._events) > self._max_scopes:
                    self._events.clear()
                for scope in scopes:
                    self._events.setdefault(scope, deque()).append(now)
                remaining = min(remaining, self.per_minute - 1)
        return RateDecision(
            allowed=True, retry_after_seconds=0, remaining=max(0, remaining)
        )


__all__ = [
    "CONNECTIONS",
    "DEFAULT_TIMEOUT_SECONDS",
    "PING_TEXT",
    "SPEC_BY_KEY",
    "ConnectionSpec",
    "ConnectionTestRateLimiter",
    "RateDecision",
    "Transport",
    "UnsafeEndpointError",
    "build_request",
    "normalize_base_url",
    "post_json",
    "test_connection",
]
