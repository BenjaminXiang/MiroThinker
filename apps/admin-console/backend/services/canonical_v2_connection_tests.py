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

The same module owns the two other page-facing tables that must not drift from
the runtime: the generic provider preset list (what an operator can pick *before*
typing a key — I2) and the bounded model-list fetch that lets them pick a model id
from the endpoint (I3). Neither table contains a host of this deployment.
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

# The model list is a convenience for the operator, not a proof of life, so it
# gets a shorter budget than the connectivity probe: one slow endpoint must not
# hold the page's "获取模型列表" button for the probe's full timeout.
MODEL_LIST_TIMEOUT_SECONDS = 3.0
MODEL_LIST_PATH = "/v1/models"
MODEL_LIST_MAX_BYTES = 512 * 1024
MODEL_LIST_MAX_MODELS = 500
MODEL_LIST_EXCERPT_CHARS = 200

_RERANK_PATH = "/v1/rerank"
_EMBEDDING_PATH = "/v1/embeddings"
# The OpenAI-compatible SDK the serving line uses posts to ``{base_url}/chat/completions``
# (knowledge_serving_isolated.py:2087-2096 builds an OpenAI client from the chat profile), so
# the probe uses the same path instead of forcing a /v1 prefix.
_CHAT_PATH = "/chat/completions"


@dataclass(frozen=True, slots=True)
class ConnectionSpec:
    """One testable connection: how to reach it, and what it needs.

    ``default_base_url`` is intentionally ``None`` for the connections the runtime
    does *not* pin: an invented default would make a disabled connection look
    reachable (live evidence: a rerank probe against a fabricated default returned
    401 and read as "reachable but rejected" while rerank is in fact not enabled).
    The effective endpoint always comes from
    :mod:`backend.services.canonical_v2_runtime_sources`, i.e. from the same code
    the serving process runs.
    """

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
        default_base_url=None,  # pinned by the provider; resolved at runtime
        base_url_editable=False,
    ),
    ConnectionSpec(
        key="serper",
        label="Serper Web 搜索",
        kind="web_search",
        secret_field="serper.api_key",
        requires_key=True,
        default_base_url=None,  # pinned by the provider; resolved at runtime
        base_url_editable=False,
    ),
    ConnectionSpec(
        key="rerank",
        label="Rerank 模型端点",
        kind="rerank",
        secret_field="rerank.api_key",
        requires_key=False,
        default_base_url=None,  # runtime default: disabled without CANONICAL_V2_RERANK_BASE_URL
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
        default_base_url=None,  # frozen release-bundle authority, resolved at runtime
        default_model="Qwen/Qwen3-Embedding-8B",
        base_url_editable=False,
    ),
    ConnectionSpec(
        key="llm",
        label="LLM 档位",
        kind="llm",
        secret_field="llm.api_key",
        requires_key=False,
        default_base_url=None,  # the active chat profile owns base_url/model
        base_url_editable=True,
    ),
)

SPEC_BY_KEY: dict[str, ConnectionSpec] = {spec.key: spec for spec in CONNECTIONS}


# -- provider presets (I2: pick a provider before typing a key) --------------


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    """One provider an operator can start from.

    ``base_url`` is an *example* endpoint and never a host of this deployment: a
    preset list is shipped code, so baking one installation's gateway into it
    would hand every other installation a URL it cannot reach — and would leak
    where this one runs. ``needs_key`` describes the provider's usual shape; a
    self-hosted OpenAI-compatible server may still require (or ignore) a key.
    """

    id: str
    label: str
    base_url: str
    needs_key: bool
    docs_url: str | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "base_url": self.base_url,
            "needs_key": self.needs_key,
            "docs_url": self.docs_url,
            "note": self.note,
        }


PROVIDER_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        id="local-openai",
        label="本机 OpenAI 兼容服务（vLLM / SGLang）",
        base_url="http://127.0.0.1:8000/v1",
        needs_key=True,
        note="把主机与端口换成你自己的服务；本机部署常见端口见下",
    ),
    ProviderPreset(
        id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        needs_key=True,
        docs_url="https://platform.deepseek.com/api-docs/",
    ),
    ProviderPreset(
        id="dashscope",
        label="阿里云百炼（OpenAI 兼容模式）",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        needs_key=True,
        docs_url="https://help.aliyun.com/zh/model-studio/",
    ),
    ProviderPreset(
        id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        needs_key=True,
        docs_url="https://platform.openai.com/docs/api-reference",
    ),
    ProviderPreset(
        id="siliconflow",
        label="硅基流动 SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        needs_key=True,
        docs_url="https://docs.siliconflow.cn/",
    ),
    ProviderPreset(
        id="custom",
        label="自定义端点",
        base_url="",
        needs_key=True,
        note="直接填完整 base_url（含 /v1）",
    ),
)


# Pretty labels for the profile picker. A profile added to ``_LLM_PROFILES``
# without a label here still renders (the name is used), so the table can lag the
# profile list without hiding a choice from the operator.
_LLM_PROFILE_LABELS: dict[str, str] = {
    "gemma4": "本地 qwen3.6-35b-a3b（gemma4）",
    "qwen35": "本地 qwen3.5-35b-a3b（qwen35）",
    "mirothinker": "MiroThinker 1.7 235B（mirothinker）",
    "ark": "火山方舟 Ark / 豆包",
    "deepseekv4flash": "DeepSeek V4 Flash",
    "deepseekv4lite": "DeepSeek V4 Lite",
    "deepseekv4pro": "DeepSeek V4 Pro",
}


def llm_profile_options() -> list[dict[str, Any]]:
    """Every chat profile the serving line can be switched to, with its endpoint.

    Read from the same table the serving process resolves through
    ``CHAT_LLM_PROFILE``, and from each profile's **local** endpoint — that is the
    one ``chat_llm_profile()`` (and therefore the answer/rewrite path) uses. The
    import is deferred so this module stays importable without the agent app.
    """

    from src.data_agents.professor.llm_profiles import _LLM_PROFILES

    return [
        {
            "name": name,
            "model": profile.local.model,
            "base_url": profile.local.base_url,
            "key_env": profile.local.api_key_env,
            "label": _LLM_PROFILE_LABELS.get(name, name),
        }
        for name, profile in sorted(_LLM_PROFILES.items())
    ]


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
    disabled_reason: str | None = None,
) -> dict[str, Any]:
    """Perform exactly one minimal call and report status + latency only.

    ``disabled_reason`` short-circuits a connection the runtime has not enabled
    (and for which the caller supplied no endpoint of its own): the honest answer
    is "not enabled", and it costs zero outbound calls.
    """

    if disabled_reason and not base_url:
        return {
            "ok": False,
            "latency_ms": 0,
            "http_status": None,
            "detail": disabled_reason,
            "called": False,
        }
    if spec.requires_key and not api_key.strip():
        return {
            "ok": False,
            "latency_ms": 0,
            "http_status": None,
            "detail": "未配置凭据：请先在页面填入并保存（或直接填入后点测试）",
            "called": False,
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
            "called": False,
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
            "called": True,
        }
    except Exception as exc:  # noqa: BLE001 - any transport failure is a result
        return {
            "ok": False,
            "latency_ms": int((monotonic() - started) * 1000),
            "http_status": None,
            "detail": f"传输失败（{type(exc).__name__}）",
            "called": True,
        }
    latency_ms = int((monotonic() - started) * 1000)
    status = int(status)
    if 200 <= status < 300:
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "http_status": status,
            "detail": f"HTTP {status}",
            "called": True,
        }
    if status in {401, 403}:
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "http_status": status,
            "detail": f"HTTP {status}：端点可达，凭据被拒绝",
            "called": True,
        }
    if status in {404, 405}:
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "http_status": status,
            "detail": f"HTTP {status}：端点可达，但路径或方法不被接受",
            "called": True,
        }
    return {
        "ok": False,
        "latency_ms": latency_ms,
        "http_status": status,
        "detail": f"HTTP {status}",
        "called": True,
    }


# -- model list (I3: pick a model id from the endpoint) ----------------------

ModelListTransport = Callable[..., tuple[int, bytes]]


def get_json(
    url: str, *, headers: Mapping[str, str], timeout: float, max_bytes: int
) -> tuple[int, bytes]:
    """One bounded GET; the body is read only up to ``max_bytes``.

    Redirects follow urllib's default policy — a gateway that redirects once is
    normal, and an operator-typed endpoint is not a trust boundary we can settle
    by refusing them. The body is never logged and never trusted beyond the model
    ids parsed out of it.
    """

    request = urllib_request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read(max_bytes)
    except urllib_error.HTTPError as exc:
        try:
            payload = exc.read(max_bytes)
        except OSError:
            payload = b""
        finally:
            exc.close()
        return int(exc.code), payload


def _model_ids(payload: Any) -> list[str]:
    """Sorted, de-duplicated ids from an OpenAI-compatible model list body.

    ``data`` is the OpenAI shape (``{"object": "list", "data": [{"id": …}]}``) and
    ``models`` the older/other one; anything else — HTML, an error envelope, an
    empty list — yields no ids and is reported as an unusable response.
    """

    entries: Sequence[Any] | None = None
    if isinstance(payload, Mapping):
        for field in ("data", "models"):
            candidate = payload.get(field)
            if isinstance(candidate, Sequence) and not isinstance(
                candidate, (str, bytes)
            ):
                entries = candidate
                break
    if entries is None:
        return []
    ids: list[str] = []
    for entry in entries:
        if isinstance(entry, Mapping):
            raw = entry.get("id") or entry.get("name")
        else:
            raw = entry
        text = str(raw).strip() if raw is not None else ""
        if text:
            ids.append(text)
    return sorted(set(ids))


def _body_excerpt(body: bytes | str | None, *, secret: str = "") -> str | None:
    """A short one-line excerpt with any echoed credential removed.

    An upstream body is not a trusted place: a misconfigured proxy can echo the
    Authorization header back, so the resolved key is redacted before the excerpt
    is returned to the page.
    """

    if not body:
        return None
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    if secret:
        text = text.replace(secret, "[redacted]")
    collapsed = " ".join(text.split())
    return collapsed[:MODEL_LIST_EXCERPT_CHARS] or None


def _model_failure(
    error: str,
    status: int | None,
    url: str,
    started: float,
    body: bytes = b"",
    secret: str = "",
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": error,
        "status": status,
        "request_url": url,
        "elapsed_ms": int((monotonic() - started) * 1000),
        "body_excerpt": _body_excerpt(body, secret=secret),
    }


def fetch_model_list(
    *,
    base_url: str | None,
    api_key: str = "",
    transport: ModelListTransport | None = None,
    timeout: float = MODEL_LIST_TIMEOUT_SECONDS,
    max_models: int = MODEL_LIST_MAX_MODELS,
) -> dict[str, Any]:
    """One bounded ``GET {base_url}/v1/models``, as an id list or as a reason.

    Every outcome carries the exact ``request_url`` and the elapsed milliseconds,
    so the page can show what it called before it reports what came back. An
    endpoint that already ends in ``/v1`` is honoured (the shared :func:`_join`),
    the credential travels in the ``Authorization`` header only, and the result is
    a value — a failure is never an exception the caller has to catch.
    """

    secret = api_key.strip()
    started = monotonic()
    if not base_url:
        # Nothing to call (e.g. rerank without CANONICAL_V2_RERANK_BASE_URL): the
        # honest answer is an unreachable endpoint, and it costs no request.
        return _model_failure("unreachable", None, "", started)
    url = _join(base_url, MODEL_LIST_PATH)
    headers = {"Accept": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    caller = transport or get_json
    try:
        status, body = caller(
            url, headers=headers, timeout=timeout, max_bytes=MODEL_LIST_MAX_BYTES
        )
    except TimeoutError:
        return _model_failure("timeout", None, url, started)
    except urllib_error.URLError as exc:
        # urllib wraps a connect timeout in URLError, and raises a bare
        # TimeoutError when the timeout happens while reading.
        timed_out = isinstance(getattr(exc, "reason", None), TimeoutError)
        return _model_failure(
            "timeout" if timed_out else "unreachable", None, url, started
        )
    except Exception:  # noqa: BLE001 - any transport failure is a result
        return _model_failure("unreachable", None, url, started)

    status = int(status)
    if status in {401, 403}:
        return _model_failure("unauthorized", status, url, started, body, secret)
    if status == 404:
        return _model_failure("not_supported", status, url, started, body, secret)
    if not 200 <= status < 300:
        # Reachable, but the answer is not a model list (a 5xx, or a request the
        # endpoint rejected): the page shows the status with the body excerpt.
        return _model_failure("bad_response", status, url, started, body, secret)
    try:
        payload = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return _model_failure("bad_response", status, url, started, body, secret)
    ids = _model_ids(payload)
    if not ids:
        return _model_failure("bad_response", status, url, started, body, secret)
    selected = ids[:max_models]
    result: dict[str, Any] = {
        "ok": True,
        "models": [{"id": model_id} for model_id in selected],
        "count": len(selected),
        "request_url": url,
        "elapsed_ms": int((monotonic() - started) * 1000),
    }
    if len(ids) > len(selected):
        result["truncated"] = True
    return result


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
    "MODEL_LIST_MAX_BYTES",
    "MODEL_LIST_MAX_MODELS",
    "MODEL_LIST_PATH",
    "MODEL_LIST_TIMEOUT_SECONDS",
    "PING_TEXT",
    "PROVIDER_PRESETS",
    "SPEC_BY_KEY",
    "ConnectionSpec",
    "ConnectionTestRateLimiter",
    "ModelListTransport",
    "ProviderPreset",
    "RateDecision",
    "Transport",
    "UnsafeEndpointError",
    "build_request",
    "fetch_model_list",
    "get_json",
    "llm_profile_options",
    "normalize_base_url",
    "post_json",
    "test_connection",
]
