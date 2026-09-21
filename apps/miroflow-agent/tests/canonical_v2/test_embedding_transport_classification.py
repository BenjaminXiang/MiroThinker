"""Transport-vs-integrity classification at the embedding HTTP seam (F1.1/F1.2).

Cluster A of
`.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/verification-contract.md`.

Fixture sources: A1/A2/A3 are constructed scenarios driven against a real
loopback socket (a server that never answers, a refused port, a 503 responder),
so the httpx exception types are the real ones. A4/A5 use stub delegates.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
import socket
import threading
from typing import Any

import pytest

VECTORIZER_MODULE = "src.data_agents.company.vectorizer"
ISOLATED_READ_MODULE = "src.data_agents.canonical_v2.knowledge_read_isolated"


def _vectorizer() -> Any:
    return import_module(VECTORIZER_MODULE)


def _closed_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class _SilentSocketServer:
    """Accepts connections and never replies — a real read timeout, not a mock."""

    def __init__(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(4)
        self.port = self._socket.getsockname()[1]
        self._stop = threading.Event()
        self._connections: list[socket.socket] = []
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._socket.accept()
            except OSError:
                return
            self._connections.append(connection)

    def __enter__(self) -> _SilentSocketServer:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        for connection in self._connections:
            connection.close()
        self._socket.close()
        self._thread.join(timeout=2.0)


class _StatusHandler(BaseHTTPRequestHandler):
    status = 503

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *_: object) -> None:
        return


def _status_server(status: int) -> tuple[ThreadingHTTPServer, str]:
    handler = type("_Handler", (_StatusHandler,), {"status": status})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/v1"


def test_a_timeout_from_the_endpoint_becomes_builtin_timeouterror() -> None:
    import httpx

    client = _vectorizer().EmbeddingClient
    with _SilentSocketServer() as server:
        embedding = client(base_url=f"http://127.0.0.1:{server.port}/v1", timeout=0.3)
        with pytest.raises(TimeoutError) as failure:
            embedding.embed_batch(["深圳有哪些芯片企业"])

    assert isinstance(failure.value.__cause__, httpx.TimeoutException)
    assert not isinstance(failure.value, ValueError)


def test_a_refused_endpoint_becomes_builtin_connectionerror() -> None:
    import httpx

    client = _vectorizer().EmbeddingClient
    embedding = client(
        base_url=f"http://127.0.0.1:{_closed_loopback_port()}/v1", timeout=1.0
    )
    with pytest.raises(ConnectionError) as failure:
        embedding.embed_batch(["深圳有哪些芯片企业"])

    assert isinstance(failure.value.__cause__, httpx.TransportError)
    assert not isinstance(failure.value, TimeoutError)


def test_a_non_2xx_endpoint_answer_becomes_builtin_connectionerror() -> None:
    import httpx

    client = _vectorizer().EmbeddingClient
    server, base_url = _status_server(503)
    try:
        embedding = client(base_url=base_url, timeout=2.0)
        with pytest.raises(ConnectionError) as failure:
            embedding.embed_batch(["深圳有哪些芯片企业"])
    finally:
        server.shutdown()
        server.server_close()

    assert isinstance(failure.value.__cause__, httpx.HTTPError)
    assert not isinstance(failure.value, TimeoutError)


class _StubEmbedding:
    model_id = "Qwen/Qwen3-Embedding-8B"
    dimension = 3

    def __init__(self, vector: tuple[float, ...] = (1.0, 0.0, 0.0)) -> None:
        self._vector = vector
        self.calls = 0

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls += 1
        return tuple(self._vector for _ in texts)


class _RaisingEmbedding(_StubEmbedding):
    def __init__(self, error: BaseException) -> None:
        super().__init__()
        self._error = error

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls += 1
        raise self._error


def test_the_validating_adapter_passes_transport_failures_through() -> None:
    adapter_type = import_module(ISOLATED_READ_MODULE)._ValidatingEmbeddingAdapter
    for error in (TimeoutError("read timed out"), ConnectionError("unreachable")):
        validating = adapter_type(
            _RaisingEmbedding(error), expected_model_id="Qwen/Qwen3-Embedding-8B"
        )
        with pytest.raises(type(error)) as failure:
            validating.embed_batch(("深圳",))

        assert failure.value is error


def test_the_validating_adapter_still_fails_closed_on_integrity() -> None:
    module = import_module(ISOLATED_READ_MODULE)
    adapter_type = module._ValidatingEmbeddingAdapter
    integrity = module.IsolatedKnowledgeReadIntegrityError
    cases: tuple[tuple[str, Any], ...] = (
        ("wrong dimension", _StubEmbedding((1.0, 0.0))),
        ("non-finite", _StubEmbedding((1.0, float("nan"), 0.0))),
        ("model mismatch", _StubEmbedding()),
        ("non-deterministic", _StubEmbedding()),
    )
    for name, delegate in cases:
        expected_model = (
            "some-other-model" if name == "model mismatch" else delegate.model_id
        )
        with pytest.raises(integrity):
            validating = adapter_type(delegate, expected_model_id=expected_model)
            if name == "non-deterministic":
                validating.embed_batch(("深圳",))
                delegate._vector = (0.0, 1.0, 0.0)
            validating.embed_batch(("深圳",))
