"""The embedding fan-out against a provider that rate limits a batch (HTTP 429).

The fembed rebuild of 2026-09-22 lost four hours to one HTTP 429: the native
client wrapped the status error in ``ConnectionError("... is unreachable")``, the
provider's answer *was* an answer (probed live: 200, 1024 dimensions), and the
pool's ``executor.map`` took the first refusal as fatal — the build raised
``physical index materialization/parity failed: embedding endpoint ... is
unreachable`` about an endpoint that was healthy and merely rate limiting a pool
that had burst past the account's per-minute budget.

This module locks the two halves of the repair:

* **the classification** — 429 is ``EmbeddingEndpointRateLimitedError``: a builtin
  ``ConnectionError`` subclass, so F1's lane-level capture is untouched, carrying
  the status code and the provider's ``Retry-After``; no status is described as
  "unreachable" any more (400 is "refused the request (HTTP 400)", 503 "answered
  a transient server error (HTTP 503)");
* **the pool's response** — a rate-limited batch is retried behind one cooldown
  shared by every worker of the fan-out, the cooldown grows once per round while
  the pressure lasts, the provider's ``Retry-After`` is honoured as a floor (and
  capped, so one absurd ask cannot park a rebuild), and the attempts are bounded
  so a provider that never relents fails the build loudly instead of being
  hammered.

Everything else still fails the pass immediately and for the reason it always
did: a deterministic refusal (400) is not retried, and a 5xx stays a plain
``ConnectionError`` — a server fault is not this pass's own over-budget signal,
and F1's breaker counts one provider call per refused attempt
(``test_embedding_model_switch_v2.test_f1_lane_breaker_sees_the_gateway_client_failures``).

Fixture source: constructed scenarios against a loopback stand-in for the native
route (``127.0.0.1``, no key, no network), the technique
``test_embedding_model_switch_v2.py`` already uses for the same route. The
stand-in stamps each request on its own thread, so the gaps asserted below are
measured at the provider, not reported by the client under test. The cooldown
constants are compressed by monkeypatch to keep the suite fast; what is asserted
is the *shape* of the policy (grow per round, floor at ``Retry-After``, cap it,
bound the attempts), never the production numbers themselves.

The repaired names are imported inside the tests that use them: with the fix
absent, the headline test must fail on the *behaviour* (a refused batch that the
provider then serves), not on a module-level ImportError.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
from itertools import pairwise
import json
import threading
import time
from typing import Any

import pytest

from src.data_agents.canonical_v2.embedding_lane_resilience import EmbeddingLaneBreaker

BUILD_MODULE = "src.data_agents.canonical_v2.knowledge_build_isolated"
READ_MODULE = "src.data_agents.canonical_v2.knowledge_read_isolated"
PROVIDER_MODULE = "src.data_agents.providers.dashscope_embeddings"

GATEWAY_KEY_ENV = "CANONICAL_V2_EMBEDDING_API_KEY"
WIDTH_ENV = "CANONICAL_V2_EMBEDDING_MAX_WORKERS"
MODEL_ID = "qwen3.7-text-embedding-flash"
DIMENSION = 4
#: The versioned prefix the bundle records; the client appends the native path.
NATIVE_BASE_PATH = "/api/v1"

#: ``respond(call_number, body) -> (status, payload, extra_headers)``.
Responder = Callable[[int, Any], "tuple[int, bytes, dict[str, str]]"]


def _build_module() -> Any:
    return import_module(BUILD_MODULE)


def _rate_limit_error_type() -> Any:
    module = import_module(PROVIDER_MODULE)
    error_type = getattr(module, "EmbeddingEndpointRateLimitedError", None)
    assert error_type is not None, "the rate-limited refusal type is missing"
    return error_type


def _native_body(texts: list[str], *, index_key: str = "index") -> bytes:
    """The route's measured answer shape, rows in the reverse of input order.

    ``text-N`` answers ``N + 1`` in the first element, so a vector that lands at
    the wrong position is visible in the value the test reads.
    """

    rows = [
        {
            index_key: index,
            "embedding": [float(index) + 1.0, *([0.5] * (DIMENSION - 1))],
            "type": "text",
        }
        for index in reversed(range(len(texts)))
    ]
    return json.dumps(
        {"output": {"embeddings": rows}, "usage": {"total_tokens": len(texts)}}
    ).encode("utf-8")


class _ThrottlingGateway:
    """A local stand-in for the native route that can script every answer.

    ``delay`` holds each request open before answering, which is what makes
    "how many calls were in flight together" observable; every request's arrival
    is stamped with ``time.monotonic()`` on the server thread.
    """

    def __init__(self, respond: Responder, *, delay: float = 0.0) -> None:
        self.calls: list[float] = []
        self.bodies: list[Any] = []
        self.max_inflight = 0
        self._inflight = 0
        self._respond = respond
        self._delay = delay
        self._lock = threading.Lock()
        gateway = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # noqa: N802 - http.server
                return

            def do_POST(self) -> None:  # noqa: N802 - http.server
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                try:
                    body: Any = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    body = raw
                with gateway._lock:
                    gateway.calls.append(time.monotonic())
                    gateway.bodies.append(body)
                    gateway._inflight += 1
                    gateway.max_inflight = max(gateway.max_inflight, gateway._inflight)
                    call = len(gateway.calls)
                try:
                    status, payload, headers = gateway._respond(call, body)
                    if gateway._delay:
                        time.sleep(gateway._delay)
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    for name, value in headers.items():
                        self.send_header(name, value)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    try:
                        self.wfile.write(payload)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                finally:
                    with gateway._lock:
                        gateway._inflight -= 1

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = (
            f"http://127.0.0.1:{self._server.server_address[1]}{NATIVE_BASE_PATH}"
        )

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def gaps(self) -> list[float]:
        """The measured wait between consecutive requests, in arrival order."""

        return [later - earlier for earlier, later in pairwise(self.calls)]


@contextmanager
def _gateway(respond: Responder, *, delay: float = 0.0) -> Any:
    gateway = _ThrottlingGateway(respond, delay=delay)
    try:
        yield gateway
    finally:
        gateway.close()


def _adapter(gateway: _ThrottlingGateway, **overrides: Any) -> Any:
    """The document-role native adapter the rebuild's materialization uses."""

    module = _build_module()
    fields: dict[str, Any] = {
        "model_id": MODEL_ID,
        "dimension": DIMENSION,
        "authority_sha256": "0" * 64,
        "base_url": gateway.base_url,
        "batch_size": 4,
        "max_workers": 1,
        "timeout_seconds": 2,
        "role": module.EMBEDDING_ROLE_DOCUMENT,
        "query_text_type": module.EMBEDDING_ROLE_QUERY,
        "query_instruct": "unused by the document role",
        # The lane breaker is process-scoped: a test that provokes transport
        # failures must not leave the shared breaker open for the next one.
        "breaker": EmbeddingLaneBreaker(),
    }
    fields.update(overrides)
    return module._DashScopeNativeEmbeddingAdapter(**fields)


def _compress_cooldowns(
    monkeypatch: pytest.MonkeyPatch,
    *,
    base: float = 0.15,
    factor: float = 3.0,
    attempts: int = 4,
    retry_after_cap: float = 0.05,
) -> None:
    """Shrink the production policy to the same shape at test speed.

    ``raising=False`` on purpose: before the repair these names do not exist, and
    the tests below must fail on the refused batch's *behaviour* rather than on a
    missing constant. The production names and their values are pinned by
    ``test_the_production_cooldown_policy_is_what_this_module_compresses``, so a
    rename or a drift cannot hide behind a test that quietly used production
    numbers.
    """

    module = _build_module()
    for name, value in (
        ("_EMBEDDING_THROTTLE_BASE_COOLDOWN_SECONDS", base),
        ("_EMBEDDING_THROTTLE_COOLDOWN_FACTOR", factor),
        ("_EMBEDDING_THROTTLE_MAX_ATTEMPTS", attempts),
        ("_EMBEDDING_THROTTLE_RETRY_AFTER_CAP_SECONDS", retry_after_cap),
    ):
        monkeypatch.setattr(module, name, value, raising=False)


def test_the_production_cooldown_policy_is_what_this_module_compresses() -> None:
    """The numbers the rebuild rides on, pinned so the compressed tests stay honest.

    Worst case for one batch, if the provider never relents:
    ``1 + 2 + 4 + 8 + 16 + 32 + 60`` seconds of cooldown over eight attempts (the
    cap bounds rounds five to eight), or one capped ``Retry-After`` per round —
    minutes, against the four hours a single 429 cost on 2026-09-22.
    """

    module = _build_module()
    assert module._EMBEDDING_THROTTLE_BASE_COOLDOWN_SECONDS == 1.0
    assert module._EMBEDDING_THROTTLE_COOLDOWN_FACTOR == 2.0
    assert module._EMBEDDING_THROTTLE_COOLDOWN_CAP_SECONDS == 60.0
    assert module._EMBEDDING_THROTTLE_COOLDOWN_JITTER == 0.25
    assert module._EMBEDDING_THROTTLE_RETRY_AFTER_CAP_SECONDS == 60.0
    assert module._EMBEDDING_THROTTLE_MAX_ATTEMPTS == 8


def _throttle_response(call: int, body: Any) -> tuple[int, bytes, dict[str, str]]:
    return 429, b'{"message":"Requests rate limit exceeded"}', {}


# --- the refused batch is retried, not lost ----------------------------------


def test_a_throttled_batch_is_retried_and_the_provider_serves_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One 429, then a normal answer: the fan-out must survive it.

    Before the repair this raised ``ConnectionError: embedding endpoint ... is
    unreachable`` after a single refused call, which is the failure that cost the
    rebuild its four hours.
    """

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    _compress_cooldowns(monkeypatch, base=0.1, retry_after_cap=5.0)
    monkeypatch.setattr(
        _build_module(), "_EMBEDDING_THROTTLE_COOLDOWN_JITTER", 0.0, raising=False
    )

    def respond(call: int, body: Any) -> tuple[int, bytes, dict[str, str]]:
        if call == 1:
            return 429, b'{"message":"rate limit"}', {"Retry-After": "1"}
        return 200, _native_body(body["input"]["texts"]), {}

    with _gateway(respond) as gateway:
        adapter = _adapter(gateway, batch_size=2, max_workers=2)
        vectors = adapter.embed_batch(("text-0", "text-1"))

    assert [vector[0] for vector in vectors] == [1.0, 2.0]
    assert len(gateway.calls) == 2, "the refused batch was not retried once"
    gap = gateway.gaps()[0]
    print(f"\n[evidence] retry gap after Retry-After: 1 = {gap:.3f}s")
    assert gap >= 0.8, (
        "the provider's Retry-After (1s) was not honoured as a floor: "
        f"the retry came after {gap:.3f}s behind a {0.1}s base cooldown"
    )


def test_an_absurd_retry_after_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """One silly header must not park the rebuild for hours."""

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    _compress_cooldowns(monkeypatch, base=0.05, retry_after_cap=0.1)
    monkeypatch.setattr(
        _build_module(), "_EMBEDDING_THROTTLE_COOLDOWN_JITTER", 0.0, raising=False
    )

    def respond(call: int, body: Any) -> tuple[int, bytes, dict[str, str]]:
        if call == 1:
            return 429, b'{"message":"rate limit"}', {"Retry-After": "3600"}
        return 200, _native_body(body["input"]["texts"]), {}

    with _gateway(respond) as gateway:
        adapter = _adapter(gateway, batch_size=2)
        adapter.embed_batch(("text-0", "text-1"))

    gap = gateway.gaps()[0]
    print(f"\n[evidence] Retry-After 3600 capped to: {gap:.3f}s")
    assert gap <= 0.5, f"the cap did not apply: waited {gap:.3f}s"


# --- what the refusal says, and how long the pool keeps trying ---------------


def test_a_refusal_is_reported_as_rate_limiting_not_as_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The message names the status and the provider's own back-off ask."""

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    _compress_cooldowns(monkeypatch, base=0.05, attempts=2, retry_after_cap=0.05)

    def respond(call: int, body: Any) -> tuple[int, bytes, dict[str, str]]:
        return 429, b'{"message":"rate limit"}', {"Retry-After": "7"}

    with _gateway(respond) as gateway:
        adapter = _adapter(gateway, batch_size=4)
        with pytest.raises(ConnectionError) as failure:
            adapter.embed_batch(("text-0",))

    exc = failure.value
    assert isinstance(exc, _rate_limit_error_type())
    # F1: the serving lane captures the builtin, so the repair must stay inside it.
    assert isinstance(exc, ConnectionError)
    assert not isinstance(exc, TimeoutError)
    assert exc.status_code == 429
    assert exc.retry_after == 7.0
    message = str(exc)
    print(f"\n[evidence] message: {message}")
    assert "429" in message
    assert "rate limited" in message
    assert "Retry-After" in message
    assert "unreachable" not in message
    assert len(gateway.calls) == 2, "the attempt cap was not enforced"


def test_a_provider_that_never_relents_backs_off_and_gives_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every retry waits longer than the last, and the attempts end."""

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    _compress_cooldowns(monkeypatch, base=0.15, factor=3.0, attempts=4)
    monkeypatch.setattr(
        _build_module(), "_EMBEDDING_THROTTLE_COOLDOWN_JITTER", 0.25, raising=False
    )

    with _gateway(_throttle_response) as gateway:
        adapter = _adapter(gateway, batch_size=4)
        with pytest.raises(ConnectionError) as failure:
            adapter.embed_batch(("text-0",))

    assert getattr(failure.value, "status_code", None) == 429
    assert len(gateway.calls) == 4, "the pool kept hammering past its attempt cap"
    gaps = gateway.gaps()
    first, second, third = gaps
    print(
        "\n[evidence] measured gaps between retries: "
        + ", ".join(f"{gap:.3f}s" for gap in gaps)
    )
    assert first >= 0.15, f"the first retry did not wait the base step: {first:.3f}s"
    assert first < 0.15 * 1.3, f"the first step overshot its jitter: {first:.3f}s"
    assert second > first * 1.5, f"the second retry did not grow: {gaps}"
    assert third > second * 1.5, f"the third retry did not grow: {gaps}"


def test_the_whole_pool_waits_out_one_cooldown_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Four workers, three refusals in one burst, one shared wait.

    The design decision this locks: a worker that is refused does not back off
    alone. If each worker escalated on its own, the three refused batches would
    come back after 0.3s, 0.9s and 2.7s — still knocking while the provider has
    asked for quiet — where the shared gate parks all three at the same boundary
    and lifts them together.
    """

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    _compress_cooldowns(monkeypatch, base=0.3, factor=3.0, attempts=4)
    monkeypatch.setattr(
        _build_module(), "_EMBEDDING_THROTTLE_COOLDOWN_JITTER", 0.0, raising=False
    )

    def respond(call: int, body: Any) -> tuple[int, bytes, dict[str, str]]:
        if call <= 3:
            return 429, b'{"message":"rate limit"}', {}
        return 200, _native_body(body["input"]["texts"]), {}

    with _gateway(respond) as gateway:
        adapter = _adapter(gateway, batch_size=1, max_workers=4)
        vectors = adapter.embed_batch(tuple(f"text-{index}" for index in range(4)))

    # One text per batch, so the vectors say "served", not which text is which
    # (input ordering is pinned by the tests above).
    assert len(vectors) == 4
    assert all(len(vector) == DIMENSION for vector in vectors)
    gaps = gateway.gaps()
    print(
        "\n[evidence] four workers, three refusals: "
        f"calls={len(gateway.calls)} gaps=" + ", ".join(f"{gap:.3f}s" for gap in gaps)
    )
    assert len(gateway.calls) == 7, "3 refused + 4 served is the whole fan-out"
    # The first four calls are the burst: nobody waited yet.
    assert max(gaps[:3]) < 0.15, f"the first round was paced, not burst: {gaps}"
    # Then one wait — the shared cooldown — and the three retries together.
    assert gaps[3] >= 0.25, f"the refusals did not open a cooldown: {gaps}"
    assert max(gaps[4:]) < 0.15, f"the retries did not come back together: {gaps}"


def test_a_deterministic_refusal_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A batch too large for the route will not become smaller by asking again."""

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    _compress_cooldowns(monkeypatch)

    def respond(call: int, body: Any) -> tuple[int, bytes, dict[str, str]]:
        return 400, b'{"message":"batch size is invalid"}', {}

    with _gateway(respond) as gateway:
        adapter = _adapter(gateway, batch_size=4)
        with pytest.raises(ConnectionError) as failure:
            adapter.embed_batch(("text-0",))

    exc = failure.value
    assert not isinstance(exc, _rate_limit_error_type()), "a 400 must not be retried"
    assert len(gateway.calls) == 1
    print(f"\n[evidence] 400 message: {exc}")
    assert "400" in str(exc)
    assert "unreachable" not in str(exc)


def test_a_server_fault_is_reported_honestly_and_still_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 5xx is not the rate signal: it names itself and the pool does not wait.

    The decision the message has to make visible: the endpoint *answered* (so
    "unreachable" is wrong), but only the 429 is this pass's own over-budget
    signal and only the 429 is waited out.
    """

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    _compress_cooldowns(monkeypatch)

    def respond(call: int, body: Any) -> tuple[int, bytes, dict[str, str]]:
        return 503, b"{}", {}

    with _gateway(respond) as gateway:
        adapter = _adapter(gateway, batch_size=4)
        with pytest.raises(ConnectionError) as failure:
            adapter.embed_batch(("text-0",))

    exc = failure.value
    assert not isinstance(exc, _rate_limit_error_type())
    assert len(gateway.calls) == 1, "a server fault must not be waited out here"
    print(f"\n[evidence] 503 message: {exc}")
    message = str(exc)
    assert "503" in message and "transient server error" in message
    assert "unreachable" not in message


# --- F1's serving capture path is untouched ----------------------------------


def test_the_serving_wrapper_passes_the_rate_limited_refusal_through() -> None:
    """The serving wrapper must not turn a refusal into a release-integrity error.

    ``_ValidatingEmbeddingAdapter`` is what the serving read engine wraps the
    adapter in, and it re-raises exactly two builtins fail-open; the read engine's
    ``_invoke_lane`` then records ``connection_failure`` and keeps the turn
    (``test_embedding_lane_fail_open``). If the repaired type stopped being one of
    those builtins it would silently become "the release is wrong" — the failure
    mode F1 exists to prevent.
    """

    isolated_read = import_module(READ_MODULE)
    error_type = _rate_limit_error_type()
    error = error_type(
        "embedding endpoint https://gateway.invalid/api/v1 rate limited the batch "
        "(HTTP 429)",
        status_code=429,
        retry_after=7.0,
    )

    class _RefusingEmbedding:
        model_id = MODEL_ID
        dimension = DIMENSION

        def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            raise error

    wrapper = isolated_read._ValidatingEmbeddingAdapter(
        _RefusingEmbedding(), expected_model_id=MODEL_ID
    )
    with pytest.raises(error_type) as failure:
        wrapper.embed_batch(("深圳",))

    assert failure.value is error
    assert isinstance(failure.value, ConnectionError)
    assert not isinstance(failure.value, TimeoutError)


# --- the operator's throttle knob (bundle identity untouched) ----------------


def test_the_pool_width_setting_overrides_without_touching_the_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _build_module()
    resolver = getattr(module, "resolve_embedding_max_workers", None)
    assert resolver is not None, "the width knob is missing"

    monkeypatch.delenv(WIDTH_ENV, raising=False)
    assert resolver(32) == 32, "an unset knob must leave the bundle's width alone"
    monkeypatch.setenv(WIDTH_ENV, "3")
    assert resolver(32) == 3
    for bad in ("0", "-1", "eight", ""):
        monkeypatch.setenv(WIDTH_ENV, bad)
        if bad == "":
            assert resolver(32) == 32
            continue
        with pytest.raises(ValueError):
            resolver(32)


def test_the_width_setting_bounds_the_calls_the_provider_sees_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The knob is the rate lever: fewer workers, fewer simultaneous refusals."""

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    texts = tuple(f"text-{index}" for index in range(4))

    def respond(call: int, body: Any) -> tuple[int, bytes, dict[str, str]]:
        return 200, _native_body(body["input"]["texts"]), {}

    monkeypatch.setenv(WIDTH_ENV, "1")
    with _gateway(respond, delay=0.2) as gateway:
        _adapter(gateway, batch_size=1, max_workers=4).embed_batch(texts)
        serial_inflight = gateway.max_inflight

    monkeypatch.setenv(WIDTH_ENV, "4")
    with _gateway(respond, delay=0.2) as gateway:
        _adapter(gateway, batch_size=1, max_workers=4).embed_batch(texts)
        wide_inflight = gateway.max_inflight

    print(
        f"\n[evidence] max calls in flight: width=1 -> {serial_inflight}, "
        f"width=4 -> {wide_inflight}"
    )
    assert serial_inflight == 1
    assert wide_inflight >= 2
