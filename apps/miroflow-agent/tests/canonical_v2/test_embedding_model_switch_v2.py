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
import json
from pathlib import Path
import socket
import threading
import time
from typing import Any

import pytest

from src.data_agents.providers.dashscope_embeddings import (
    DashScopeTextEmbeddingClient,
)

BUILD_MODULE = "src.data_agents.canonical_v2.knowledge_build_isolated"
READ_MODULE = "src.data_agents.canonical_v2.knowledge_read_isolated"

_REPO_ROOT = Path(__file__).resolve().parents[4]
CANDIDATE_BUNDLE_PATH = (
    _REPO_ROOT
    / ".agents/runs/embedding-model-switch-v2"
    / "qwen3.7-text-embedding-flash-embedding-bundle-v1.json"
)

CANDIDATE_MODEL_ID = "qwen3.7-text-embedding-flash"
CANDIDATE_DIMENSION = 1024
LIVE_MODEL_ID = "Qwen/Qwen3-Embedding-8B"
LIVE_DIMENSION = 4096
CANDIDATE_BUNDLE_SHA256 = (
    "cdddcdfd998e6c9e6147f735fd71370f209045636f3b2f3efa15e7e73a8e96ad"
)
GATEWAY_KEY_ENV = "CANONICAL_V2_EMBEDDING_API_KEY"
NATIVE_PATH = "/api/v1/services/embeddings/text-embedding/text-embedding"


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


def _native_body(rows: list[tuple[int, list[float]]]) -> bytes:
    """One DashScope-native answer: positional rows carrying their own index."""

    return json.dumps(
        {
            "output": {
                "embeddings": [
                    {"text_index": index, "embedding": vector} for index, vector in rows
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


# --- the new identity --------------------------------------------------------


def test_candidate_bundle_is_self_hashed_and_frozen() -> None:
    module = _build_module()
    document = json.loads(CANDIDATE_BUNDLE_PATH.read_bytes())
    payload = {key: value for key, value in document.items() if key != "content_sha256"}

    assert document["content_sha256"] == _canonical_hash(payload)
    assert document["content_sha256"] == CANDIDATE_BUNDLE_SHA256
    assert document["content_sha256"] == module._QWEN_FLASH_EMBEDDING_BUNDLE_SHA256
    assert document["dimension"] == CANDIDATE_DIMENSION
    assert module._QWEN_FLASH_EMBEDDING_DIMENSION == CANDIDATE_DIMENSION

    adapter = module.load_content_addressed_embedding_adapter(CANDIDATE_BUNDLE_PATH)
    assert type(adapter).__name__ == "_DashScopeNativeEmbeddingAdapter"
    assert adapter.model_id == CANDIDATE_MODEL_ID
    assert adapter.dimension == CANDIDATE_DIMENSION
    assert adapter.authority_sha256 == CANDIDATE_BUNDLE_SHA256


def test_the_authority_pair_is_atomic_across_the_two_spaces() -> None:
    """A hash and a dimension are one authority: neither half travels alone."""

    module = _build_module()
    accepted = module._ACCEPTED_EMBEDDING_AUTHORITIES

    assert (CANDIDATE_BUNDLE_SHA256, CANDIDATE_DIMENSION) in accepted
    assert (module._QWEN_EMBEDDING_BUNDLE_SHA256, LIVE_DIMENSION) in accepted
    # The candidate's hash with the live dimension, and the live hash with the
    # candidate's dimension, are both absent — the pair is a unit.
    assert (CANDIDATE_BUNDLE_SHA256, LIVE_DIMENSION) not in accepted
    assert (module._QWEN_EMBEDDING_BUNDLE_SHA256, CANDIDATE_DIMENSION) not in accepted


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("dimension", "frozen authority"),
        ("model_id", "frozen authority"),
        ("base_url", "frozen authority"),
        ("api_key_source", "frozen authority"),
        ("provider_and_schema", "frozen authority"),
        ("provider", "not a known embedding provider"),
        ("provider_without_schema", "version differs"),
        ("schema_version", "version differs"),
    ],
)
def test_candidate_bundle_mutations_are_refused(
    tmp_path: Path,
    mutation: str,
    expected: str,
) -> None:
    module = _build_module()
    document = json.loads(CANDIDATE_BUNDLE_PATH.read_bytes())
    if mutation == "dimension":
        document["dimension"] = LIVE_DIMENSION
    elif mutation == "model_id":
        document["model_id"] = LIVE_MODEL_ID
    elif mutation == "base_url":
        document["base_url"] = "http://100.64.0.27:18005/v1"
    elif mutation == "api_key_source":
        document["api_key_source"] = "local_api_key"
    elif mutation == "provider_and_schema":
        document["provider"] = "openai-compatible"
        document["schema_version"] = (
            "canonical-v2-openai-compatible-embedding-bundle-v1"
        )
    elif mutation == "provider":
        document["provider"] = "some-other-gateway"
    elif mutation == "provider_without_schema":
        document["provider"] = "openai-compatible"
    elif mutation == "schema_version":
        document["schema_version"] = (
            "canonical-v2-openai-compatible-embedding-bundle-v1"
        )
    document.pop("content_sha256")
    document["content_sha256"] = _canonical_hash(document)
    path = tmp_path / "candidate-embedding-bundle.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match=expected):
        module.load_content_addressed_embedding_adapter(path)


def test_candidate_bundle_cannot_be_reloaded_against_the_local_provider() -> None:
    """The two identities are not interchangeable in either direction."""

    module = _build_module()
    adapter = module.load_content_addressed_embedding_adapter(CANDIDATE_BUNDLE_PATH)
    read_module = import_module(READ_MODULE)

    with pytest.raises(
        read_module.IsolatedKnowledgeReadIntegrityError,
        match="model differs from the release",
    ):
        read_module._ValidatingEmbeddingAdapter(
            adapter,
            expected_model_id=LIVE_MODEL_ID,
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
        _write_bundle(live, "live-embedding-bundle.json", tmp_path)
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
        module.load_content_addressed_embedding_adapter(path)
