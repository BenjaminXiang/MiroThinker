"""The v2 embedding-model switch, slice 1: the adapter and the new identity.

The candidate serving model (``qwen3.7-text-embedding-flash`` on the MaaS
gateway) speaks DashScope's *native* embeddings shape, and its 1024-dimensional
space is not the live 4096-dimensional one. These tests lock the parts that must
hold before a rebuild can even be scheduled:

* the wire shape and the answer ordering (``output.embeddings[].text_index``);
* the error classification — a provider that is *unreachable* becomes the
  builtin the lane-level fail-open hook understands, while an answer we cannot
  use stays a validation failure;
* the declared-dimension guard;
* the frozen ``(bundle content hash, dimension)`` authority pair, and the fact
  that a candidate identity is refused by an index that ships another one.

Every HTTP interaction runs against a local stand-in for the gateway: no key, no
network. Nothing here selects the new bundle for the live line.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
import hashlib
import json
from pathlib import Path
import socket
import threading
import time
from typing import Any

import pytest

from src.data_agents.canonical_v2.embedding_lane_resilience import (
    EmbeddingLaneBreaker,
)
from src.data_agents.providers.dashscope_embeddings import (
    DashScopeTextEmbeddingClient,
)

BUILD_MODULE = "src.data_agents.canonical_v2.knowledge_build_isolated"
READ_MODULE = "src.data_agents.canonical_v2.knowledge_read_isolated"

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BUNDLE_DIR = _REPO_ROOT / ".agents/runs/embedding-model-switch-v2"
CANDIDATE_BUNDLE_PATH = (
    _BUNDLE_DIR / "qwen3.7-text-embedding-flash-embedding-bundle-v1.json"
)
CANDIDATE_COMPAT_BUNDLE_PATH = (
    _BUNDLE_DIR / "qwen3.7-text-embedding-flash-embedding-bundle-v1-openai-compat.json"
)

CANDIDATE_MODEL_ID = "qwen3.7-text-embedding-flash"
CANDIDATE_DIMENSION = 1024
LIVE_MODEL_ID = "Qwen/Qwen3-Embedding-8B"
LIVE_DIMENSION = 4096
CANDIDATE_BUNDLE_SHA256 = (
    "67927ea060ec3036927376c7059aaa7d3140c33160b9be440556a19cd8d64ef3"
)
CANDIDATE_COMPAT_BUNDLE_SHA256 = (
    "d5ff0ffb52bdaa70a5103fb9747fa7f320547f21dd8e7b6e3a5ce6bd05a2baf4"
)
GATEWAY_KEY_ENV = "CANONICAL_V2_EMBEDDING_API_KEY"
NATIVE_PATH = "/api/v1/services/embeddings/text-embedding/text-embedding"
GATEWAY_COMPAT_BASE_URL = "https://maas.qianwenaiapi.com/compatible-mode/v1"
#: The model family's *documented* batch cap — what both bundles declare. The
#: gateway currently accepts more (measured 2026-09-21: 25 → 200, 26 → HTTP 400
#: "batch size is invalid, it should not be larger than 25: input.contents"), but
#: a provider that tightens to its documented value would turn a declared 25 into
#: a 400 on every vector-lane call, and F1 turns a 4xx into lane degradation —
#: silent recall loss rather than an error. The rebuild is bound by tokens, not
#: requests, so the smaller batch costs no real time.
DOCUMENTED_MAX_BATCH = 20
#: What this gateway accepted when measured (see the docstring above).
MEASURED_GATEWAY_CEILING = 25
#: The route's query-side treatment, frozen in the native bundle: the build must
#: never send these (it embeds documents), the serving query lane always does.
QUERY_INSTRUCT = (
    "Given a Chinese-language query about Shenzhen technology companies, "
    "professors, research papers or patents, retrieve the relevant records"
)

#: Both candidate variants are one model in two wire shapes: the native route
#: (needs the adapter) and the gateway's OpenAI-compatible route (needs none).
#: Exactly one of them may be used for both the rebuild and serving — the two
#: routes do not agree (measured cosine 0.808–0.920 on the same text).
CANDIDATE_BUNDLES = (
    pytest.param(
        CANDIDATE_BUNDLE_PATH,
        CANDIDATE_BUNDLE_SHA256,
        "_QWEN_FLASH_EMBEDDING_BUNDLE_SHA256",
        "_DashScopeNativeEmbeddingAdapter",
        id="dashscope-native",
    ),
    pytest.param(
        CANDIDATE_COMPAT_BUNDLE_PATH,
        CANDIDATE_COMPAT_BUNDLE_SHA256,
        "_QWEN_FLASH_OPENAI_COMPAT_EMBEDDING_BUNDLE_SHA256",
        "_GatewayOpenAICompatibleEmbeddingAdapter",
        id="openai-compatible",
    ),
)


def _canonical_hash(value: object) -> str:
    import hashlib

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_module() -> Any:
    return import_module(BUILD_MODULE)


def _native_body(
    rows: list[tuple[int, list[float]]],
    *,
    index_key: str = "index",
) -> bytes:
    """One native answer in the gateway's *measured* shape.

    Measured live 2026-09-21: rows carry ``['embedding', 'index', 'type']`` — the
    gateway says ``index`` where DashScope's documentation says ``text_index``.
    ``index_key`` lets a test emit the documented spelling instead.
    """

    return json.dumps(
        {
            "output": {
                "embeddings": [
                    {index_key: index, "embedding": vector, "type": "text"}
                    for index, vector in rows
                ]
            },
            "usage": {"total_tokens": len(rows)},
            "request_id": "local-stand-in",
        }
    ).encode("utf-8")


class _Gateway:
    """A local stand-in for the gateway's DashScope-native embeddings route.

    ``respond`` receives the 1-based call number and the parsed request body and
    returns ``(status, body, content_type, delay_seconds)``, so one test scripts a
    healthy answer and the next a broken one.
    """

    def __init__(
        self,
        respond: Callable[[int, Any], tuple[int, bytes, str, float]],
    ) -> None:
        self.calls: list[tuple[str, Any, dict[str, str]]] = []
        self._respond = respond
        gateway = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def do_POST(self) -> None:  # noqa: N802 - http.server's interface
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                try:
                    body: Any = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    body = raw
                gateway.calls.append((self.path, body, dict(self.headers)))
                status, payload, content_type, delay = gateway._respond(
                    len(gateway.calls), body
                )
                if delay:
                    time.sleep(delay)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    # The client gave up first (its own timeout fired): the
                    # stand-in has nothing left to say.
                    pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()
        port = self._server.server_address[1]
        # The versioned prefix the real bundle records, so the client's full
        # request path is the one the gateway actually serves.
        self.base_url = f"http://127.0.0.1:{port}/api/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@contextmanager
def _gateway(
    respond: Callable[[int, Any], tuple[int, bytes, str, float]],
) -> Iterator[_Gateway]:
    gateway = _Gateway(respond)
    try:
        yield gateway
    finally:
        gateway.close()


def _text_vector(text: str) -> list[float]:
    """A 1024-dimensional vector whose first element names the input text.

    ``text-N`` answers ``N + 1``, so a vector that lands at the wrong position is
    visible in the first element — the test reads order, not just values.
    """

    index = float(text.removeprefix("text-"))
    return [index + 1.0, *([0.5] * (CANDIDATE_DIMENSION - 1))]


def _answered_echo(call: int, body: Any) -> tuple[int, bytes, str, float]:
    """A healthy answer whose rows arrive in the reverse of the input order."""

    texts = body["input"]["texts"]
    rows = [
        (index, _text_vector(text)) for index, text in reversed(list(enumerate(texts)))
    ]
    return 200, _native_body(rows), "application/json", 0.0


def _positional_echo(call: int, body: Any) -> tuple[int, bytes, str, float]:
    """A healthy answer for the client-level tests (no dimension is enforced)."""

    texts = body["input"]["texts"]
    rows = [
        (index, [float(index) + 1.0, 2.0, 3.0]) for index in reversed(range(len(texts)))
    ]
    return 200, _native_body(rows), "application/json", 0.0


def _flash_adapter(gateway: _Gateway, **overrides: Any) -> Any:
    module = _build_module()
    fields: dict[str, Any] = {
        "model_id": CANDIDATE_MODEL_ID,
        "dimension": CANDIDATE_DIMENSION,
        "authority_sha256": CANDIDATE_BUNDLE_SHA256,
        "base_url": gateway.base_url,
        "batch_size": 2,
        "max_workers": 2,
        "timeout_seconds": 5,
        "role": module.EMBEDDING_ROLE_DOCUMENT,
        "query_text_type": module.EMBEDDING_ROLE_QUERY,
        "query_instruct": QUERY_INSTRUCT,
        # F1's lane breaker is process-scoped: a test that provokes transport
        # failures must not leave the shared breaker open for the next one.
        "breaker": EmbeddingLaneBreaker(),
    }
    fields.update(overrides)
    return module._DashScopeNativeEmbeddingAdapter(**fields)


# --- the wire shape ----------------------------------------------------------


def test_native_client_sends_texts_and_restores_input_order() -> None:
    with _gateway(_positional_echo) as gateway:
        client = DashScopeTextEmbeddingClient(
            base_url=gateway.base_url,
            api_key="local-stand-in-key",
            timeout=5.0,
        )
        vectors = client.embed_batch(["first", "second", "third"], model="a-model")

    assert [vector[0] for vector in vectors] == [1.0, 2.0, 3.0]
    assert all(len(vector) == 3 for vector in vectors)
    path, body, headers = gateway.calls[0]
    assert path == NATIVE_PATH
    assert body == {
        "model": "a-model",
        "input": {"texts": ["first", "second", "third"]},
    }
    assert headers["Authorization"] == "Bearer local-stand-in-key"


@pytest.mark.parametrize(
    "rows",
    [
        [(0, [1.0, 2.0])],
        [(0, [1.0, 2.0]), (0, [3.0, 4.0])],
        [(0, [1.0, 2.0]), (2, [3.0, 4.0])],
        [(0, [1.0, 2.0]), (1, [])],
    ],
)
def test_native_client_rejects_an_answer_it_cannot_align(
    rows: list[tuple[int, list[float]]],
) -> None:
    with _gateway(
        lambda call, body: (200, _native_body(rows), "application/json", 0.0)
    ) as gateway:
        client = DashScopeTextEmbeddingClient(
            base_url=gateway.base_url,
            api_key="local-stand-in-key",
            timeout=5.0,
        )
        with pytest.raises(ValueError):
            client.embed_batch(["first", "second"], model="a-model")


def test_native_client_accepts_the_documented_text_index_spelling() -> None:
    """DashScope documents ``text_index``; the gateway answers ``index``.

    Both spellings must work, because the client is the same code for the
    documented API and for this gateway.
    """

    with _gateway(
        lambda call, body: (
            200,
            _native_body([(1, [1.0, 2.0]), (0, [3.0, 4.0])], index_key="text_index"),
            "application/json",
            0.0,
        )
    ) as gateway:
        client = DashScopeTextEmbeddingClient(
            base_url=gateway.base_url,
            api_key="local-stand-in-key",
            timeout=5.0,
        )
        vectors = client.embed_batch(["first", "second"], model="a-model")
    assert vectors == [[3.0, 4.0], [1.0, 2.0]]


def test_native_client_rejects_a_row_without_any_index() -> None:
    with _gateway(
        lambda call, body: (
            200,
            json.dumps(
                {
                    "output": {
                        "embeddings": [
                            {"embedding": [1.0, 2.0], "type": "text"},
                            {"embedding": [3.0, 4.0], "type": "text"},
                        ]
                    }
                }
            ).encode("utf-8"),
            "application/json",
            0.0,
        )
    ) as gateway:
        client = DashScopeTextEmbeddingClient(
            base_url=gateway.base_url,
            api_key="local-stand-in-key",
            timeout=5.0,
        )
        with pytest.raises(ValueError, match="malformed"):
            client.embed_batch(["first", "second"], model="a-model")


def test_native_client_rejects_a_body_without_the_expected_envelope() -> None:
    with _gateway(
        lambda call, body: (
            200,
            json.dumps({"data": [{"embedding": [1.0]}]}).encode("utf-8"),
            "application/json",
            0.0,
        )
    ) as gateway:
        client = DashScopeTextEmbeddingClient(
            base_url=gateway.base_url,
            api_key="local-stand-in-key",
            timeout=5.0,
        )
        with pytest.raises(ValueError):
            client.embed_batch(["first"], model="a-model")


# --- the error classification ------------------------------------------------


@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_native_client_maps_any_http_status_to_a_fail_open_builtin(
    status: int,
) -> None:
    with _gateway(
        lambda call, body: (
            status,
            json.dumps({"message": "denied"}).encode("utf-8"),
            "application/json",
            0.0,
        )
    ) as gateway:
        client = DashScopeTextEmbeddingClient(
            base_url=gateway.base_url,
            api_key="local-stand-in-key",
            timeout=5.0,
        )
        with pytest.raises(ConnectionError):
            client.embed_batch(["first"], model="a-model")


def test_native_client_maps_a_non_json_body_to_a_fail_open_builtin() -> None:
    with _gateway(
        lambda call, body: (200, b"<html>not json</html>", "text/html", 0.0)
    ) as gateway:
        client = DashScopeTextEmbeddingClient(
            base_url=gateway.base_url,
            api_key="local-stand-in-key",
            timeout=5.0,
        )
        with pytest.raises(ConnectionError):
            client.embed_batch(["first"], model="a-model")


def test_native_client_maps_a_stalled_answer_to_timeout() -> None:
    with _gateway(
        lambda call, body: (200, _native_body([(0, [1.0])]), "application/json", 0.5)
    ) as gateway:
        client = DashScopeTextEmbeddingClient(
            base_url=gateway.base_url,
            api_key="local-stand-in-key",
            timeout=0.1,
        )
        with pytest.raises(TimeoutError):
            client.embed_batch(["first"], model="a-model")


def test_native_client_maps_a_refused_connection_to_a_fail_open_builtin() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]
    client = DashScopeTextEmbeddingClient(
        base_url=f"http://127.0.0.1:{dead_port}/api/v1",
        api_key="local-stand-in-key",
        timeout=5.0,
    )
    with pytest.raises(ConnectionError):
        client.embed_batch(["first"], model="a-model")


# --- the adapter: batching, credential slot, dimension guard ----------------


def test_flash_adapter_batches_caches_and_keeps_input_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    with _gateway(_answered_echo) as gateway:
        adapter = _flash_adapter(gateway)
        texts = tuple(f"text-{index}" for index in range(5))
        vectors = adapter.embed_batch(texts)

        assert tuple(vector[0] for vector in vectors) == (1.0, 2.0, 3.0, 4.0, 5.0)
        assert sorted(len(body["input"]["texts"]) for _, body, _ in gateway.calls) == [
            1,
            2,
            2,
        ]
        assert all(body["model"] == CANDIDATE_MODEL_ID for _, body, _ in gateway.calls)
        cached = adapter.embed_batch(("text-0", "text-4", "text-0"))
        assert cached[0] == vectors[0]
        assert cached[0] == cached[2]
        assert cached[1] == vectors[4]
        assert len(gateway.calls) == 3
        assert adapter.embed_batch(("text-4", "text-0")) == (cached[1], cached[0])
        assert len(gateway.calls) == 3


def test_flash_adapter_reads_its_own_credential_slot_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local endpoint's key must never travel to a third-party host."""

    monkeypatch.delenv(GATEWAY_KEY_ENV, raising=False)
    monkeypatch.setenv("SGLANG_API_KEY", "local-endpoint-key")
    monkeypatch.setenv("API_KEY", "local-endpoint-key")
    monkeypatch.setenv("OPENAI_API_KEY", "local-endpoint-key")
    with _gateway(_answered_echo) as gateway:
        adapter = _flash_adapter(gateway)
        with pytest.raises(ValueError, match="credential is unavailable"):
            adapter.embed_batch(("text-0",))
    assert gateway.calls == []


def test_flash_adapter_enforces_the_declared_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    with _gateway(
        lambda call, body: (
            200,
            _native_body([(0, [1.0] * LIVE_DIMENSION), (1, [1.0] * LIVE_DIMENSION)]),
            "application/json",
            0.0,
        )
    ) as gateway:
        adapter = _flash_adapter(gateway)
        with pytest.raises(ValueError, match="invalid vector"):
            adapter.embed_batch(("text-0", "text-1"))


def test_flash_adapter_rejects_a_zero_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    with _gateway(
        lambda call, body: (
            200,
            _native_body(
                [(0, [0.0] * CANDIDATE_DIMENSION), (1, [0.0] * CANDIDATE_DIMENSION)]
            ),
            "application/json",
            0.0,
        )
    ) as gateway:
        adapter = _flash_adapter(gateway)
        with pytest.raises(ValueError, match="invalid vector"):
            adapter.embed_batch(("text-0", "text-1"))


def test_flash_adapter_lets_a_transport_failure_stay_a_builtin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead provider degrades the lane; it must not look like a bad release."""

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    with _gateway(
        lambda call, body: (
            200,
            _native_body([(0, _text_vector("text-0"))]),
            "application/json",
            2.0,
        )
    ) as gateway:
        adapter = _flash_adapter(gateway, timeout_seconds=1)
        with pytest.raises(TimeoutError):
            adapter.embed_batch(("text-0",))

    with _gateway(lambda call, body: (503, b"{}", "application/json", 0.0)) as gateway:
        adapter = _flash_adapter(gateway)
        with pytest.raises(ConnectionError):
            adapter.embed_batch(("text-0",))


# --- F1/F2 integration (release/v1.1) ----------------------------------------


def test_f1_transport_pass_through_covers_the_gateway_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lane's fail-open hole must not launder this client's transport errors.

    F1 opened ``_ValidatingEmbeddingAdapter`` for exactly ``TimeoutError`` and
    ``ConnectionError``; the candidate's client has to raise those, or the
    gateway being unreachable would be reported as release corruption.
    """

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    read_module = import_module(READ_MODULE)

    with _gateway(lambda call, body: (503, b"{}", "application/json", 0.0)) as gateway:
        validating = read_module._ValidatingEmbeddingAdapter(
            _flash_adapter(gateway),
            expected_model_id=CANDIDATE_MODEL_ID,
        )
        with pytest.raises(ConnectionError):
            validating.embed_batch(("text-0",))

    with _gateway(
        lambda call, body: (
            200,
            _native_body([(0, _text_vector("text-0"))]),
            "application/json",
            2.0,
        )
    ) as gateway:
        validating = read_module._ValidatingEmbeddingAdapter(
            _flash_adapter(gateway, timeout_seconds=1),
            expected_model_id=CANDIDATE_MODEL_ID,
        )
        with pytest.raises(TimeoutError):
            validating.embed_batch(("text-0",))

    # A genuinely wrong answer still fails closed through the same validator.
    with _gateway(
        lambda call, body: (
            200,
            _native_body([(0, [1.0] * LIVE_DIMENSION)]),
            "application/json",
            0.0,
        )
    ) as gateway:
        validating = read_module._ValidatingEmbeddingAdapter(
            _flash_adapter(gateway),
            expected_model_id=CANDIDATE_MODEL_ID,
        )
        with pytest.raises(read_module.IsolatedKnowledgeReadIntegrityError):
            validating.embed_batch(("text-0",))


def test_f1_lane_breaker_sees_the_gateway_client_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two transport failures from the gateway must open F1's breaker."""

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    breaker = EmbeddingLaneBreaker()
    with _gateway(lambda call, body: (503, b"{}", "application/json", 0.0)) as gateway:
        adapter = _flash_adapter(gateway, breaker=breaker)
        for _ in range(2):
            with pytest.raises(ConnectionError):
                adapter.embed_batch(("text-0",))
        # Third call: the breaker answers before any provider call.
        with pytest.raises(ConnectionError, match="breaker"):
            adapter.embed_batch(("text-1",))
        assert breaker.state() == "open"
        assert len(gateway.calls) == 2


# --- the query side of the native route ---------------------------------------
#
# One authority, two roles: the route answers a *query* differently from a
# *document* (DashScope's ``text_type``, qualified by ``instruct``), and only the
# query role may carry that treatment. The role is a constructor argument, so
# neither role can reach the other's wire shape by accident.


def test_the_document_role_adapter_cannot_emit_query_shaped_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The build embeds documents: its requests stay on the route's default.

    ``instruct`` is the vendor's way of pairing a short query with long records.
    A document-role adapter that sent it would embed all 51,026 points as if they
    were queries, and no check downstream could see the difference.
    """

    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    with _gateway(_answered_echo) as gateway:
        adapter = _flash_adapter(gateway, role="document")
        adapter.embed_batch(("text-0", "text-1"))

    _path, body, _headers = gateway.calls[0]
    assert body == {
        "model": CANDIDATE_MODEL_ID,
        "input": {"texts": ["text-0", "text-1"]},
    }


def test_the_query_role_adapter_sends_the_frozen_query_treatment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(GATEWAY_KEY_ENV, "local-stand-in-key")
    with _gateway(_answered_echo) as gateway:
        adapter = _flash_adapter(gateway, role="query")
        adapter.embed_batch(("text-7",))

    _path, body, _headers = gateway.calls[0]
    assert body["text_type"] == "query"
    assert body["instruct"] == QUERY_INSTRUCT
    assert body["input"]["texts"] == ["text-7"]


def test_the_native_bundle_carries_the_query_treatment() -> None:
    """The treatment is frozen in the bundle, not hardcoded in the adapter."""

    native = json.loads(CANDIDATE_BUNDLE_PATH.read_bytes())
    compat = json.loads(CANDIDATE_COMPAT_BUNDLE_PATH.read_bytes())

    assert native["query_text_type"] == "query"
    assert native["query_instruct"] == QUERY_INSTRUCT
    # The OpenAI shape has no role dimension, so the fallback twin declares none:
    # its two roles answer identically and it can serve a query lane unchanged.
    assert "query_text_type" not in compat
    assert "query_instruct" not in compat


def test_a_native_bundle_that_demotes_its_query_role_is_refused(
    tmp_path: Path,
) -> None:
    """``query_text_type`` is part of the frozen identity, not a free field."""

    module = _build_module()
    document = json.loads(CANDIDATE_BUNDLE_PATH.read_bytes())
    document["query_text_type"] = "document"
    document.pop("content_sha256")
    document["content_sha256"] = _canonical_hash(document)
    path = tmp_path / "demoted-query-role-embedding-bundle.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="differs from frozen authority"):
        module.load_content_addressed_embedding_adapter(path, role="query")


def test_the_role_travels_from_the_loader_to_the_adapter() -> None:
    module = _build_module()

    for role in (module.EMBEDDING_ROLE_QUERY, module.EMBEDDING_ROLE_DOCUMENT):
        adapter = module.load_content_addressed_embedding_adapter(
            CANDIDATE_BUNDLE_PATH, role=role
        )
        assert adapter.role == role

    with pytest.raises(ValueError, match="role is not known"):
        module.load_content_addressed_embedding_adapter(
            CANDIDATE_BUNDLE_PATH, role="either"
        )


# --- the new identity --------------------------------------------------------


@pytest.mark.parametrize(
    ("bundle_path", "bundle_sha256", "constant_name", "adapter_class"),
    CANDIDATE_BUNDLES,
)
def test_candidate_bundle_is_self_hashed_and_frozen(
    bundle_path: Path,
    bundle_sha256: str,
    constant_name: str,
    adapter_class: str,
) -> None:
    module = _build_module()
    document = json.loads(bundle_path.read_bytes())
    payload = {key: value for key, value in document.items() if key != "content_sha256"}

    assert document["content_sha256"] == _canonical_hash(payload)
    assert document["content_sha256"] == bundle_sha256
    assert document["content_sha256"] == getattr(module, constant_name)
    assert document["dimension"] == CANDIDATE_DIMENSION
    assert module._QWEN_FLASH_EMBEDDING_DIMENSION == CANDIDATE_DIMENSION
    assert document["api_key_source"] == f"env:{GATEWAY_KEY_ENV}"

    adapter = module.load_content_addressed_embedding_adapter(
        bundle_path, role="document"
    )
    assert type(adapter).__name__ == adapter_class
    assert adapter.model_id == CANDIDATE_MODEL_ID
    assert adapter.dimension == CANDIDATE_DIMENSION
    assert adapter.authority_sha256 == bundle_sha256


def test_the_candidate_bundles_declare_the_documented_batch_cap() -> None:
    """Both bundles declare the family's documented cap, not today's measured one.

    The vendor's table documents ``batch_size`` 20 for this model family; this
    gateway accepted 25 when measured (2026-09-21: 25 → 200, 26 → HTTP 400
    ``batch size is invalid, it should not be larger than 25: input.contents``).
    Declaring 20 keeps the value the customer's procurement rests on: if the
    provider later tightens to its documented cap, a declared 25 would make every
    vector-lane call a 400, and F1 turns a 4xx into lane degradation — silent
    recall loss rather than an error. The rebuild is bound by tokens (1M TPM),
    not by requests: ≈2,550 calls at 20 versus ≈2,040 at 25, same token volume.
    """

    for bundle_path in (CANDIDATE_BUNDLE_PATH, CANDIDATE_COMPAT_BUNDLE_PATH):
        document = json.loads(bundle_path.read_bytes())
        assert document["batch_size"] == DOCUMENTED_MAX_BATCH
        assert document["batch_size"] <= MEASURED_GATEWAY_CEILING
        adapter = _build_module().load_content_addressed_embedding_adapter(
            bundle_path, role="document"
        )
        assert adapter.batch_size == DOCUMENTED_MAX_BATCH

    # The live authority keeps its own value: this cap is the gateway's, not a
    # policy change for the self-hosted endpoint.
    live_document, _ = _build_module()._OPENAI_COMPATIBLE_EMBEDDING_AUTHORITIES[0]
    assert live_document["batch_size"] == 32


def test_the_two_candidate_routes_are_distinct_authorities() -> None:
    """Same model, two routes: separate bundles, because the routes differ.

    The compatible and native routes answer the same text with cosines of
    0.860–0.933 (measured 2026-09-21), so they are not one authority: an index
    built through one route may only be served through that route, and each
    variant keeps its own frozen hash and address.
    """

    module = _build_module()
    native = json.loads(CANDIDATE_BUNDLE_PATH.read_bytes())
    compat = json.loads(CANDIDATE_COMPAT_BUNDLE_PATH.read_bytes())

    assert native["model_id"] == compat["model_id"] == CANDIDATE_MODEL_ID
    assert native["dimension"] == compat["dimension"] == CANDIDATE_DIMENSION
    assert native["provider"] == "dashscope-native"
    assert compat["provider"] == "openai-compatible"
    assert native["base_url"] == "https://maas.qianwenaiapi.com/api/v1"
    assert compat["base_url"] == GATEWAY_COMPAT_BASE_URL
    assert native["content_sha256"] != compat["content_sha256"]
    # Both are usable, and both are run through the same credential slot.
    assert native["api_key_source"] == compat["api_key_source"]
    accepted = module._ACCEPTED_EMBEDDING_AUTHORITIES
    assert (CANDIDATE_BUNDLE_SHA256, CANDIDATE_DIMENSION) in accepted
    assert (CANDIDATE_COMPAT_BUNDLE_SHA256, CANDIDATE_DIMENSION) in accepted


def test_the_authority_pair_is_atomic_across_the_two_spaces() -> None:
    """A hash and a dimension are one authority: neither half travels alone."""

    module = _build_module()
    accepted = module._ACCEPTED_EMBEDDING_AUTHORITIES

    for candidate in (CANDIDATE_BUNDLE_SHA256, CANDIDATE_COMPAT_BUNDLE_SHA256):
        assert (candidate, CANDIDATE_DIMENSION) in accepted
        # The candidate's hash with the live dimension is absent — the pair is a
        # unit, whichever route the candidate takes.
        assert (candidate, LIVE_DIMENSION) not in accepted
    assert (module._QWEN_EMBEDDING_BUNDLE_SHA256, LIVE_DIMENSION) in accepted
    assert (module._QWEN_EMBEDDING_BUNDLE_SHA256, CANDIDATE_DIMENSION) not in accepted


_NATIVE_ONLY_KEYS = ("query_text_type", "query_instruct")


def _reshape_for_provider(document: dict[str, Any]) -> None:
    """Give *document* the key shape of the provider it now claims.

    The two provider schemas are exact-key schemas, and the native one carries
    the query-side treatment. A mutation that flips the provider without
    reshaping the keys would fail on the schema check instead of on the identity
    check this test is about.
    """

    if document["provider"] == "dashscope-native":
        document.setdefault("query_text_type", "query")
        document.setdefault("query_instruct", QUERY_INSTRUCT)
    else:
        for key in _NATIVE_ONLY_KEYS:
            document.pop(key, None)


@pytest.mark.parametrize(
    ("bundle_path", "mutation", "expected"),
    [
        (CANDIDATE_BUNDLE_PATH, "dimension", "frozen authority"),
        (CANDIDATE_BUNDLE_PATH, "model_id", "frozen authority"),
        (CANDIDATE_BUNDLE_PATH, "base_url", "frozen authority"),
        (CANDIDATE_BUNDLE_PATH, "api_key_source", "frozen authority"),
        (CANDIDATE_BUNDLE_PATH, "provider_and_schema", "frozen authority"),
        (CANDIDATE_BUNDLE_PATH, "provider", "not a known embedding provider"),
        (CANDIDATE_BUNDLE_PATH, "provider_without_schema", "version differs"),
        (CANDIDATE_BUNDLE_PATH, "schema_version", "version differs"),
        # The compatible variant: same gates, and the ones that matter for the
        # zero-code route — the candidate must not be loadable through the live
        # authority, nor through the live credential slot.
        (CANDIDATE_COMPAT_BUNDLE_PATH, "dimension", "frozen authority"),
        (CANDIDATE_COMPAT_BUNDLE_PATH, "model_id", "frozen authority"),
        (CANDIDATE_COMPAT_BUNDLE_PATH, "base_url", "frozen authority"),
        (CANDIDATE_COMPAT_BUNDLE_PATH, "base_url_to_native", "frozen authority"),
        (CANDIDATE_COMPAT_BUNDLE_PATH, "api_key_source", "frozen authority"),
        (CANDIDATE_COMPAT_BUNDLE_PATH, "provider_and_schema", "frozen authority"),
        (CANDIDATE_COMPAT_BUNDLE_PATH, "provider", "not a known embedding provider"),
        (CANDIDATE_COMPAT_BUNDLE_PATH, "schema_version", "version differs"),
    ],
)
def test_candidate_bundle_mutations_are_refused(
    tmp_path: Path,
    bundle_path: Path,
    mutation: str,
    expected: str,
) -> None:
    module = _build_module()
    document = json.loads(bundle_path.read_bytes())
    if mutation == "dimension":
        document["dimension"] = LIVE_DIMENSION
    elif mutation == "model_id":
        document["model_id"] = LIVE_MODEL_ID
    elif mutation == "base_url":
        document["base_url"] = "http://100.64.0.27:18005/v1"
    elif mutation == "base_url_to_native":
        document["base_url"] = "https://maas.qianwenaiapi.com/api/v1"
    elif mutation == "api_key_source":
        document["api_key_source"] = "local_api_key"
    elif mutation == "provider_and_schema":
        document["provider"] = (
            "dashscope-native"
            if document["provider"] == "openai-compatible"
            else "openai-compatible"
        )
        document["schema_version"] = {
            "dashscope-native": "canonical-v2-dashscope-native-embedding-bundle-v1",
            "openai-compatible": ("canonical-v2-openai-compatible-embedding-bundle-v1"),
        }[document["provider"]]
        _reshape_for_provider(document)
    elif mutation == "provider":
        document["provider"] = "some-other-gateway"
    elif mutation == "provider_without_schema":
        document["provider"] = "openai-compatible"
        _reshape_for_provider(document)
    elif mutation == "schema_version":
        document["schema_version"] = (
            "canonical-v2-dashscope-native-embedding-bundle-v1"
            if document["provider"] == "openai-compatible"
            else "canonical-v2-openai-compatible-embedding-bundle-v1"
        )
    document.pop("content_sha256")
    document["content_sha256"] = _canonical_hash(document)
    path = tmp_path / "candidate-embedding-bundle.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match=expected):
        module.load_content_addressed_embedding_adapter(path, role="document")


@pytest.mark.parametrize(
    "bundle_path", [CANDIDATE_BUNDLE_PATH, CANDIDATE_COMPAT_BUNDLE_PATH]
)
def test_candidate_bundle_cannot_be_reloaded_against_the_local_provider(
    bundle_path: Path,
) -> None:
    """The two identities are not interchangeable in either direction."""

    module = _build_module()
    adapter = module.load_content_addressed_embedding_adapter(
        bundle_path, role="document"
    )
    read_module = import_module(READ_MODULE)

    with pytest.raises(
        read_module.IsolatedKnowledgeReadIntegrityError,
        match="model differs from the release",
    ):
        read_module._ValidatingEmbeddingAdapter(
            adapter,
            expected_model_id=LIVE_MODEL_ID,
        )


def test_the_compatible_candidate_reads_the_gateway_slot_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero-code route, same credential rule: the local key must not travel.

    The compatible variant reuses the live OpenAI client, so the only thing that
    separates it from the live authority is the slot it reads — and that has to
    hold through the loader, not by convention.
    """

    module = _build_module()
    calls: list[tuple[str, str, str]] = []

    class _RecordingClient:
        def __init__(self, *, base_url: str, api_key: str, timeout: float) -> None:
            calls.append((base_url, api_key, str(timeout)))

        def embed_batch(self, texts: list[str], *, model: str) -> list[list[float]]:
            assert model == CANDIDATE_MODEL_ID
            return [[1.0] * CANDIDATE_DIMENSION for _ in texts]

    monkeypatch.setattr(module, "_OpenAIEmbeddingClient", _RecordingClient)
    monkeypatch.setenv("SGLANG_API_KEY", "local-endpoint-key")
    monkeypatch.setenv("API_KEY", "local-endpoint-key")
    monkeypatch.delenv(GATEWAY_KEY_ENV, raising=False)

    adapter = module.load_content_addressed_embedding_adapter(
        CANDIDATE_COMPAT_BUNDLE_PATH, role="document"
    )
    assert type(adapter).__name__ == "_GatewayOpenAICompatibleEmbeddingAdapter"
    with pytest.raises(ValueError, match="credential is unavailable"):
        adapter.embed_batch(("text-0",))
    assert calls == []

    monkeypatch.setenv(GATEWAY_KEY_ENV, "gateway-slot-key")
    vectors = adapter.embed_batch(("text-0",))
    assert len(vectors) == 1 and len(vectors[0]) == CANDIDATE_DIMENSION
    assert [call[:2] for call in calls] == [
        (GATEWAY_COMPAT_BASE_URL, "gateway-slot-key")
    ]


@pytest.mark.parametrize(
    ("bundle_path", "bundle_sha256", "constant_name", "adapter_class"),
    CANDIDATE_BUNDLES,
)
def test_f2_address_override_applies_to_the_candidate_bundles(
    bundle_path: Path,
    bundle_sha256: str,
    constant_name: str,
    adapter_class: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F2's rule reaches the new branches: the address is operational everywhere.

    Without this, the candidate bundles would pin their gateway host while the
    live authority lets the operator move — the interaction flagged when the
    native slice was written.
    """

    module = _build_module()
    recorded = json.loads(bundle_path.read_bytes())["base_url"]

    monkeypatch.delenv("CANONICAL_V2_EMBEDDING_BASE_URL", raising=False)
    assert (
        module.load_content_addressed_embedding_adapter(bundle_path, role="document").base_url
        == recorded
    )

    monkeypatch.setenv(
        "CANONICAL_V2_EMBEDDING_BASE_URL", "http://127.0.0.1:9/alternate/v1"
    )
    assert (
        module.load_content_addressed_embedding_adapter(bundle_path, role="document").base_url
        == "http://127.0.0.1:9/alternate/v1"
    )


def test_the_live_bundle_still_loads_to_the_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Inertness: the provider dispatch leaves the live authority untouched."""

    module = _build_module()
    live = {
        "schema_version": "canonical-v2-openai-compatible-embedding-bundle-v1",
        "provider": "openai-compatible",
        "model_id": LIVE_MODEL_ID,
        "dimension": LIVE_DIMENSION,
        "base_url": "http://100.64.0.27:18005/v1",
        "api_key_source": "local_api_key",
        "batch_size": 32,
        "max_workers": 32,
        "timeout_seconds": 180,
    }
    live["content_sha256"] = _canonical_hash(live)
    assert live["content_sha256"] == module._QWEN_EMBEDDING_BUNDLE_SHA256
    monkeypatch.setattr(
        module,
        "_OpenAIEmbeddingClient",
        lambda **kwargs: pytest.fail("the loader must not call the provider"),
    )
    adapter = module.load_content_addressed_embedding_adapter(
        _write_bundle(live, "live-embedding-bundle.json", tmp_path), role="document"
    )
    assert type(adapter).__name__ == "_OpenAICompatibleEmbeddingAdapter"
    assert adapter.model_id == LIVE_MODEL_ID
    assert adapter.dimension == LIVE_DIMENSION


def _write_bundle(document: dict[str, Any], name: str, tmp_path: Path) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_an_unknown_provider_is_refused(tmp_path: Path) -> None:
    module = _build_module()
    document = json.loads(CANDIDATE_BUNDLE_PATH.read_bytes())
    document["provider"] = "yet-another-gateway"
    document.pop("content_sha256")
    document["content_sha256"] = _canonical_hash(document)
    path = tmp_path / "unknown-provider-embedding-bundle.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="not a known embedding provider"):
        module.load_content_addressed_embedding_adapter(path, role="document")


# --- the rebuild audit's cosine floor (Task C.1) -----------------------------
#
# `index_projection_isolated._validate_physical_point_rows` re-embeds each
# point's content and compares it with the vector the index stored — per point,
# ~51k times per rebuild. Its floor was 0.999, calibrated for a deterministic
# endpoint, while the candidate gateway's measured repeat noise bottoms out at
# 0.997556. These tests drive the real audit function with vectors placed at
# chosen cosines: the measured-noise band must pass, and every genuinely wrong
# vector must still fail closed.

INDEX_MODULE = "src.data_agents.canonical_v2.index_projection_isolated"
POINT_DIMENSION = 8
#: Measured 2026-09-21 (`.agents/runs/embedding-model-switch-v2/repeat-noise-measurement.json`):
#: the low mode over three texts plus the earlier run's lowest single pair.
MEASURED_REPEAT_COSINES = (1.0, 0.998829, 0.998772, 0.998004, 0.997556)
#: Measured wrong answers: the sibling route of the same model (0.933/0.860), an
#: unrelated document pair (0.242), a zero vector, and another space (−0.03).
WRONG_VECTOR_COSINES = (0.932903, 0.86, 0.241886, 0.0, -0.03)


def _unit(vector: list[float]) -> list[float]:
    norm = sum(value * value for value in vector) ** 0.5
    return [value / norm for value in vector]


def _at_cosine(base: list[float], other: list[float], target: float) -> list[float]:
    """A unit vector whose cosine against ``base`` is ``target``."""

    unit_base = _unit(base)
    unit_other = _unit(other)
    projection = sum(o * b for o, b in zip(unit_other, unit_base, strict=True))
    perpendicular = [
        o - projection * b for o, b in zip(unit_other, unit_base, strict=True)
    ]
    unit_perpendicular = _unit(perpendicular)
    sine = (max(0.0, 1.0 - target * target)) ** 0.5
    return [
        target * b + sine * p
        for b, p in zip(unit_base, unit_perpendicular, strict=True)
    ]


def _audit_row(index: int, *, stored: list[float]) -> tuple[dict[str, Any], str]:
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    projection_module = import_module("src.data_agents.canonical_v2.index_projection")
    text = f"深圳市示例科技公司 {index}"
    point = projection_module.IndexProjectionPoint(
        point_id=f"point:audit-{index}",
        canonical_object_id=f"company:audit-{index}",
        release_id="candidate-audit",
        projection_id=f"projection:audit-{index}",
        projection_scope=contracts_module.ProjectionScope.public_domain,
        domain="company",
        reference_type=None,
        projection_view=projection_module.ProjectionView.default,
        projection_version="projection-v1",
        schema_version="index-projection-point-v1",
        embedding_model=CANDIDATE_MODEL_ID,
        eligibility_policy_version="path-eligibility-v1",
        eligibility_decision_id=f"decision:audit-{index}",
        eligibility_outcome="admitted",
        source_projection_content_sha256=hashlib.sha256(
            f"source:{index}".encode()
        ).hexdigest(),
        embedded_content=text,
        embedded_content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        source_evidence_ids=(f"evidence:audit-{index}",),
    )
    row = {
        "point_id": point.point_id,
        "release_id": point.release_id,
        "projection_id": point.projection_id,
        "canonical_object_id": point.canonical_object_id,
        "embedded_content_sha256": point.embedded_content_sha256,
        "point_json": point.model_dump_json(),
        "vector": list(stored),
    }
    return row, text


class _FixedAdapter:
    """Answers every point with the vector the test chose for it."""

    def __init__(self, expected: dict[str, list[float]], *, dimension: int) -> None:
        self.model_id = CANDIDATE_MODEL_ID
        self.dimension = dimension
        self._expected = expected

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(tuple(self._expected[text]) for text in texts)


def _run_audit(cosines: tuple[float, ...]) -> tuple[Any, ...]:
    index_module = import_module(INDEX_MODULE)
    rows: list[dict[str, Any]] = []
    expected: dict[str, list[float]] = {}
    for index, target in enumerate(cosines):
        base = [1.0, 0.5 - index / 100.0, 0.25, 0.125, 0.0625, 0.03125, 0.015, 0.0075]
        other = [0.1, 0.9, 0.2, 0.05, 0.4, 0.3, 0.25, 0.6 + index / 50.0]
        row, text = _audit_row(index, stored=_at_cosine(base, other, target))
        rows.append(row)
        expected[text] = _unit(base)
    return index_module._validate_physical_point_rows(
        rows,
        expected_point_ids=None,
        embedding_adapter=_FixedAdapter(expected, dimension=POINT_DIMENSION),
    )


def test_rebuild_audit_passes_the_measured_repeat_band() -> None:
    """The floor must not false-fail a healthy gateway, tail included."""

    index_module = import_module(INDEX_MODULE)
    points = _run_audit(MEASURED_REPEAT_COSINES)

    assert len(points) == len(MEASURED_REPEAT_COSINES)
    # The floor really is the tuned one, not a test-local constant.
    assert index_module._MIN_VECTOR_COSINE_SIMILARITY == 0.99
    assert index_module._MIN_VECTOR_COSINE_SIMILARITY < min(MEASURED_REPEAT_COSINES)


@pytest.mark.parametrize("cosine", WRONG_VECTOR_COSINES)
def test_rebuild_audit_still_refuses_a_wrong_vector(cosine: float) -> None:
    """Corruption is caught: wrong point, wrong space, or a dead vector."""

    index_module = import_module(INDEX_MODULE)
    with pytest.raises(index_module.IndexProjectionIntegrityError):
        _run_audit((cosine,))


def test_rebuild_audit_still_refuses_a_wrong_dimension() -> None:
    """The dimension check is separate from the cosine floor and stays strict."""

    index_module = import_module(INDEX_MODULE)
    row, text = _audit_row(0, stored=[1.0] * (POINT_DIMENSION + 1))
    with pytest.raises(index_module.IndexProjectionIntegrityError):
        index_module._validate_physical_point_rows(
            [row],
            expected_point_ids=None,
            embedding_adapter=_FixedAdapter(
                {text: [1.0] * POINT_DIMENSION}, dimension=POINT_DIMENSION
            ),
        )
