"""#3 — the embedding identity probe behind the embedding card's test.

Two arms (reference comparison, index-grounded), one verdict, actionable text.
Fixture sources: a local OpenAI-compatible stub endpoint (real HTTP), a
constructed mini serving pack (lookup.sqlite3 + vector_matrix.npz written with
the repository's own writer), and the real FastAPI route graph over scratch
managed files. No real provider is dialled and nothing reads the live pack.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.api.canonical_v2_admin_config import get_managed_settings_store
from backend.main import app
from backend.services import canonical_v2_embedding_identity as identity
from tests.conftest import authorized_client
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore

_ENV = "CANONICAL_V2_SERVING_PACK"
_MODEL = "Qwen/Qwen3-Embedding-8B"
_STORE_STATE = "canonical_v2_managed_settings_store"


def _vector(seed: int, dimension: int = 8) -> tuple[float, ...]:
    """A deterministic unit vector per seed (a stand-in for one embedding model)."""

    state = np.random.default_rng(seed)
    raw = state.normal(size=dimension)
    return tuple(float(value) for value in raw / np.linalg.norm(raw))


def _orthogonal(seed: int, vector: tuple[float, ...]) -> tuple[float, ...]:
    """A unit vector at cosine 0 to *vector*: "the same dimension, another space"."""

    state = np.random.default_rng(seed)
    raw = state.normal(size=len(vector))
    reference = np.asarray(vector, dtype=np.float64)
    projected = raw - float(raw @ reference) * reference
    return tuple(float(value) for value in projected / np.linalg.norm(projected))


def _make_embedder(table: dict[str, dict[str, tuple[float, ...]]]) -> Any:
    """A stub endpoint that maps text → vector, like a real embedding service."""

    def embed(
        base_url: str, text: str, *, api_key: str, model: str, timeout: float, role: str
    ):
        del api_key, model, timeout, role
        space = table.get(base_url)
        if space is None:
            raise identity.EmbeddingIdentityUnavailable(
                "stub endpoint is not configured"
            )
        vector = space.get(text)
        if vector is None:
            raise identity.EmbeddingIdentityUnavailable(
                "stub endpoint has no vector for the text"
            )
        return vector

    return embed


def _one_text(base_url: str, vector: tuple[float, ...]) -> dict[str, Any]:
    """A stub space that answers the fixed probe text (arm reference)."""

    return {base_url: {identity.PROBE_TEXT: vector}}


def _make_pack(
    tmp_path: Path, *, seed: int, dimension: int = 8
) -> tuple[Path, dict[str, tuple[float, ...]]]:
    """A minimal serving pack (two documents + their stored vectors).

    Returns the pack directory and the ``text -> vector`` map of the space it was
    built in, so a test can stand up an endpoint that either reproduces it or not.
    """

    pack = tmp_path / "pack"
    index_root = tmp_path / "index"
    pack.mkdir(parents=True, exist_ok=True)
    index_root.mkdir(parents=True, exist_ok=True)
    (pack / identity._INDEX_MARKER_FILENAME).write_text(
        json.dumps({"root": str(index_root)}), encoding="utf-8"
    )
    content = (
        "热变形对机床加工精度具有显著影响。本文针对轧辊磨床，提出了一种热性能仿真"
        "模型与实验方法，并给出了热边界条件的计算方法。"
    )
    point_id = "index-point:stub"
    other_id = "index-point:other"
    with sqlite3.connect(pack / identity._LOOKUP_FILENAME) as connection:
        connection.execute(
            "CREATE TABLE index_point (point_id TEXT PRIMARY KEY, point_json TEXT)"
        )
        connection.execute(
            "INSERT INTO index_point VALUES (?, ?)",
            (point_id, json.dumps({"embedded_content": content})),
        )
        connection.execute(
            "INSERT INTO index_point VALUES (?, ?)",
            (other_id, json.dumps({"embedded_content": "无关文档" * 60})),
        )
        connection.commit()
    rows = np.asarray(
        [_vector(seed, dimension), _vector(seed + 500, dimension)], dtype=np.float64
    )
    np.savez(
        index_root / identity._MATRIX_FILENAME,
        point_ids=np.asarray((point_id, other_id), dtype=object),
        matrix=rows,
        norms=np.linalg.norm(rows, axis=1),
        meta=np.asarray(
            json.dumps(
                {
                    "schema_version": "canonical-v2-vector-matrix-v1",
                    "embedding_model_id": _MODEL,
                    "dimension": dimension,
                    "point_count": 2,
                }
            ),
            dtype=object,
        ),
    )
    return pack, {
        text: vector
        for text, vector in zip(
            (content, "无关文档" * 60),
            (_vector(seed, dimension), _vector(seed + 500, dimension)),
            strict=True,
        )
    }


# -- the row reader (the one piece that reads released bytes) ----------------


def test_the_matrix_reader_matches_numpy(tmp_path: Path) -> None:
    """Row seeking must return exactly what np.load would: no header off-by-N."""

    path = tmp_path / "vector_matrix.npz"
    matrix = np.random.default_rng(7).normal(size=(5, 8))
    np.savez(
        path,
        point_ids=np.asarray([f"p{i}" for i in range(5)], dtype=object),
        matrix=matrix,
    )

    ids, read_row = identity._matrix_reader(path)

    assert ids == tuple(f"p{i}" for i in range(5))
    for index in range(5):
        assert np.array_equal(np.asarray(read_row(index)), matrix[index])


def test_the_matrix_reader_refuses_a_row_outside_the_matrix(tmp_path: Path) -> None:
    path = tmp_path / "vector_matrix.npz"
    np.savez(path, point_ids=np.asarray(["p0"], dtype=object), matrix=np.zeros((1, 8)))

    _, read_row = identity._matrix_reader(path)

    with pytest.raises(identity.EmbeddingIdentityUnavailable):
        read_row(1)


# -- arm reference -----------------------------------------------------------


def test_the_reference_arm_passes_when_both_endpoints_share_one_space() -> None:
    same = _vector(1)
    embedder = _make_embedder(
        {**_one_text("http://index/v1", same), **_one_text("http://new/v1", same)}
    )

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://index/v1",
        embedder=embedder,
    )

    assert report.arm == "reference"
    assert report.passed is True
    assert report.cosine == pytest.approx(1.0)
    assert "同源" in report.detail


#: Measured on the candidate gateway 2026-09-21 (30 repeats per text, same route
#: and address; `.agents/runs/embedding-model-switch-v2/`): the band a healthy
#: endpoint's repeat cosine actually lands in, plus the earlier run's lowest pair.
MEASURED_REPEAT_COSINES = (1.0, 0.998829, 0.998772, 0.998004, 0.997556)
#: Measured wrong answers: a sibling route of the same model (0.933/0.860) and an
#: unrelated document pair (0.242).
MEASURED_WRONG_ANSWER_COSINES = (0.932903, 0.86, 0.241886)


def _at_cosine(
    reference: tuple[float, ...], other: tuple[float, ...], target: float
) -> tuple[float, ...]:
    """A unit vector whose cosine against *reference* is exactly *target*."""

    base = np.asarray(reference, dtype=np.float64)
    candidate = np.asarray(other, dtype=np.float64)
    projected = candidate - float(candidate @ base) * base
    perpendicular = projected / np.linalg.norm(projected)
    sine = (max(0.0, 1.0 - target * target)) ** 0.5
    return tuple(float(value) for value in (target * base + sine * perpendicular))


def _reference_report(configured: tuple[float, ...]) -> Any:
    embedder = _make_embedder(
        {
            **_one_text("http://index/v1", _vector(1)),
            **_one_text("http://new/v1", configured),
        }
    )
    return identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://index/v1",
        embedder=embedder,
    )


@pytest.mark.parametrize("cosine", MEASURED_REPEAT_COSINES)
def test_the_reference_arm_tolerates_the_measured_repeat_noise(cosine: float) -> None:
    """A stochastic endpoint must not fail its own identity check.

    The gateway answers the same probe twice at 0.998-1.0; the arm compares
    exactly such a pair when the operator's address setting is empty, so the
    floor has to sit below that band (0.999 did not).
    """

    report = _reference_report(_at_cosine(_vector(1), _vector(2), cosine))

    assert report.arm == "reference"
    assert report.passed is True
    assert report.cosine == pytest.approx(cosine, abs=1e-6)
    assert report.threshold == identity.REFERENCE_COSINE_FLOOR


@pytest.mark.parametrize("cosine", MEASURED_WRONG_ANSWER_COSINES)
def test_the_reference_arm_still_rejects_the_wrong_answer_band(
    cosine: float,
) -> None:
    """Tuning the floor down must not open the door to another space."""

    report = _reference_report(_at_cosine(_vector(1), _vector(2), cosine))

    assert report.passed is False
    assert "不要切换到这个端点" in report.detail


def test_the_reference_floor_is_derived_from_the_measured_noise_band() -> None:
    """The number, and why it cannot be tightened without new measurements."""

    assert identity.REFERENCE_COSINE_FLOOR < min(MEASURED_REPEAT_COSINES)
    assert identity.REFERENCE_COSINE_FLOOR > max(MEASURED_WRONG_ANSWER_COSINES)
    assert identity.REFERENCE_COSINE_FLOOR == 0.99
    assert identity.INDEX_COSINE_FLOOR == 0.99


def test_the_reference_arm_fails_loudly_in_another_space() -> None:
    recorded = _vector(1)
    embedder = _make_embedder(
        {
            **_one_text("http://index/v1", recorded),
            **_one_text("http://new/v1", _orthogonal(2, recorded)),
        }
    )

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://index/v1",
        embedder=embedder,
    )

    assert report.arm == "reference"
    assert report.passed is False
    assert report.cosine is not None and report.cosine < 0.01
    assert report.threshold == identity.REFERENCE_COSINE_FLOOR
    assert "不要切换到这个端点" in report.detail


def test_the_reference_arm_refuses_a_dimension_change() -> None:
    embedder = _make_embedder(
        {
            **_one_text("http://index/v1", _vector(1)),
            **_one_text("http://new/v1", _vector(2, dimension=16)),
        }
    )

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://index/v1",
        embedder=embedder,
    )

    assert report.arm == "index" or report.passed is not True
    assert "未校验" in report.detail


# -- arm index ---------------------------------------------------------------


def test_the_index_arm_passes_when_the_endpoint_reproduces_the_stored_vector(
    tmp_path: Path,
) -> None:
    pack, space = _make_pack(tmp_path, seed=11)
    embedder = _make_embedder({"http://new/v1": space})

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://new/v1",  # same address: the reference arm is vacuous
        embedder=embedder,
        pack_dir=pack,
    )

    assert report.arm == "index"
    assert report.passed is True
    assert report.cosine == pytest.approx(1.0)
    assert report.checks["sample_rows"] >= 1
    assert "与索引同源" in report.detail


def test_the_index_arm_embeds_the_stored_document(tmp_path: Path) -> None:
    """The index arm re-embeds a *document*, so it must declare that role.

    The vector it compares against was written by the build, which embeds
    documents. Asking a role-aware endpoint for the query side here would answer
    with an adjacent-but-different vector and fail a healthy endpoint.
    """

    pack, space = _make_pack(tmp_path, seed=11)
    roles: list[str] = []

    def recording(base_url, text, *, api_key, model, timeout, role):
        del base_url, api_key, model, timeout
        roles.append(role)
        return space[text]

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://new/v1",  # same address: the reference arm is vacuous
        embedder=recording,
        pack_dir=pack,
    )

    assert report.passed is True
    assert roles == [identity.ROLE_DOCUMENT]


def test_the_reference_arm_probes_the_query_side() -> None:
    """Both reference calls are queries, as the serving lane's will be."""

    vector = _vector(1)
    inner = _make_embedder(
        {
            "http://new/v1": {identity.PROBE_TEXT: vector},
            "http://old/v1": {identity.PROBE_TEXT: vector},
        }
    )
    roles: list[str] = []

    def recording(base_url, text, *, api_key, model, timeout, role):
        roles.append(role)
        return inner(
            base_url, text, api_key=api_key, model=model, timeout=timeout, role=role
        )

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://old/v1",
        embedder=recording,
        pack_dir=None,
    )

    assert report.arm == "reference"
    assert report.passed is True
    assert roles == [identity.ROLE_QUERY, identity.ROLE_QUERY]


def test_the_index_arm_fails_and_says_what_to_do(tmp_path: Path) -> None:
    pack, space = _make_pack(tmp_path, seed=11)
    embedder = _make_embedder(
        {"http://new/v1": {text: _orthogonal(99, v) for text, v in space.items()}}
    )

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://new/v1",
        embedder=embedder,
        pack_dir=pack,
    )

    assert report.arm == "index"
    assert report.passed is False
    assert report.cosine is not None and report.cosine < 0.99
    assert "不在同一嵌入空间" in report.detail
    assert "不要切换" in report.detail


def test_the_index_arm_refuses_a_dimension_mismatch(tmp_path: Path) -> None:
    pack, space = _make_pack(tmp_path, seed=11)
    embedder = _make_embedder(
        {"http://new/v1": {text: _vector(3, dimension=16) for text in space}}
    )

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://new/v1",
        embedder=embedder,
        pack_dir=pack,
    )

    assert report.arm is None
    assert report.passed is None
    assert "维度" in report.detail


def test_without_index_assets_the_probe_reports_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_ENV, raising=False)

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://new/v1",
        embedder=_make_embedder(_one_text("http://new/v1", _vector(1))),
        pack_dir=None,
    )

    assert report.arm is None
    assert report.passed is None
    assert _ENV in report.detail


def test_an_unreachable_reference_falls_back_to_the_index(tmp_path: Path) -> None:
    pack, space = _make_pack(tmp_path, seed=21)
    embedder = _make_embedder({"http://new/v1": space})  # the reference never answers

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://index/v1",
        embedder=embedder,
        pack_dir=pack,
    )

    assert report.arm == "index"
    assert report.passed is True


def test_the_probe_never_raises_when_the_endpoint_is_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*_: Any, **__: Any) -> Any:
        raise RuntimeError("embedder blew up")

    report = identity.verify_embedding_identity(
        configured_base_url="http://new/v1",
        recorded_base_url="http://new/v1",
        embedder=explode,
        pack_dir=None,
    )

    assert report.passed is None
    assert "未校验" in report.detail


# -- the one real-HTTP path --------------------------------------------------


def test_the_http_embedder_reads_an_openai_compatible_response() -> None:
    import http.server

    calls: list[dict[str, Any]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - handler API
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            calls.append(
                {
                    "path": self.path,
                    "payload": payload,
                    "auth": bool(self.headers.get("Authorization")),
                }
            )
            body = json.dumps({"data": [{"index": 0, "embedding": [1.0] * 8}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        vector = identity._post_embeddings(
            f"http://127.0.0.1:{server.server_port}/v1",
            identity.PROBE_TEXT,
            api_key="probe-key",
            model=_MODEL,
            timeout=5.0,
            role=identity.ROLE_QUERY,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert vector == (1.0,) * 8
    assert calls[0]["path"] == "/v1/embeddings"
    assert calls[0]["payload"] == {"model": _MODEL, "input": identity.PROBE_TEXT}
    assert calls[0]["auth"] is True
    # The query role adds nothing here: this wire shape has no ``text_type``, and
    # inventing one would make the probe speak a request the endpoint never sees
    # from the serving lane. The native shape is the module docstring's ceiling.
    assert "text_type" not in calls[0]["payload"]


# -- the fleet's two wire shapes ---------------------------------------------
# The probe speaks the shape the endpoint under test answers: the OpenAI
# compatible one (the shape this card has always spoken) and, when that address
# has no such route, the DashScope-native one through the merged client. Each
# address is asked once and the answer is held for the rest of the check.


#: The versioned prefix a real base URL carries (``https://…/api/v1``); each wire
#: shape appends its own path to it.
_ROUTE_PREFIX = "/v1"
_COMPATIBLE_ROUTE = f"{_ROUTE_PREFIX}{identity.EMBEDDINGS_PATH}"
_NATIVE_ROUTE = f"{_ROUTE_PREFIX}{identity.NATIVE_EMBEDDINGS_PATH}"


def _openai_answers(table: dict[str, tuple[float, ...]]) -> Any:
    """The compatible shape's answer: rows under ``data``."""

    def answer(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return 200, {"data": [{"index": 0, "embedding": list(table[payload["input"]])}]}

    return answer


def _native_answers(table: dict[str, tuple[float, ...]]) -> Any:
    """The native shape's answer: rows under ``output.embeddings``."""

    def answer(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        rows = [
            {"index": index, "embedding": list(table[text])}
            for index, text in enumerate(payload["input"]["texts"])
        ]
        return 200, {"output": {"embeddings": rows}}

    return answer


def _refuses(status: int) -> Any:
    """A route that exists in the mock but answers with a status only."""

    return lambda payload: (status, {})


class _ShapeEndpoint:
    """One loopback endpoint whose routes are declared, so the shape is visible.

    ``routes`` maps a request path — *after* the versioned prefix, which is the
    part both shapes share — to an answer function. A path that is not declared
    answers 404 with an empty body, the way the gateway's native prefix refuses
    ``/embeddings`` (measured 2026-09-22). Every call is recorded with its payload
    and its full path, which is how a test reads the shape and the role a call
    carried.
    """

    def __init__(
        self, routes: dict[str, Any], *, base_path: str = _ROUTE_PREFIX
    ) -> None:
        import http.server

        resolved = {f"{base_path}{path}": answer for path, answer in routes.items()}
        self.calls: list[dict[str, Any]] = []
        calls = self.calls

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - handler API
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                answer = resolved.get(self.path)
                status, body = (404, {}) if answer is None else answer(payload)
                calls.append(
                    {
                        "path": self.path,
                        "payload": payload,
                        "auth": bool(self.headers.get("Authorization")),
                    }
                )
                encoded = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_: object) -> None:
                return

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    def paths(self) -> list[str]:
        return [str(call["path"]) for call in self.calls]

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def test_the_native_path_literal_matches_the_merged_client() -> None:
    """One path, two apps: the console's literal and the client's must be one.

    The probe calls the merged client for the request shape, but the connection
    test builds the native URL itself — a drift between the two literals would
    surface as "未校验" on a healthy endpoint instead of a verdict.
    """

    from src.data_agents.providers import dashscope_embeddings

    assert identity.NATIVE_EMBEDDINGS_PATH == dashscope_embeddings._TEXT_EMBEDDINGS_PATH


def test_the_index_arm_validates_a_native_only_endpoint(tmp_path: Path) -> None:
    """The route the switch ships: no compatible route, a native one that answers."""

    pack, space = _make_pack(tmp_path, seed=31)
    _point_id, content = identity._probe_document(pack / identity._LOOKUP_FILENAME)
    endpoint = _ShapeEndpoint(
        {identity.NATIVE_EMBEDDINGS_PATH: _native_answers({content: space[content]})}
    )
    try:
        report = identity.verify_embedding_identity(
            configured_base_url=endpoint.base_url,
            api_key="probe-key",
            recorded_base_url=endpoint.base_url,  # same address: reference is vacuous
            pack_dir=pack,
        )
    finally:
        endpoint.close()

    assert report.arm == "index"
    assert report.passed is True
    assert report.cosine == pytest.approx(1.0)
    assert report.checks["provider"] == identity.PROVIDER_DASHSCOPE_NATIVE
    assert report.checks["role"] == identity.ROLE_DOCUMENT
    assert "404" in str(report.checks["provider_evidence"])
    # The compatible shape was asked first and refused; the native call carried
    # the document side — the route's *absent* ``text_type``, never a guess.
    assert endpoint.paths() == [_COMPATIBLE_ROUTE, _NATIVE_ROUTE]
    assert endpoint.calls[1]["payload"]["input"] == {"texts": [content]}
    assert "text_type" not in endpoint.calls[1]["payload"]
    assert endpoint.calls[1]["auth"] is True


def test_a_compatible_endpoint_stays_one_call_per_address(tmp_path: Path) -> None:
    """The shape in service today keeps exactly the calls it made before."""

    pack, space = _make_pack(tmp_path, seed=32)
    _point_id, content = identity._probe_document(pack / identity._LOOKUP_FILENAME)
    endpoint = _ShapeEndpoint(
        {identity.EMBEDDINGS_PATH: _openai_answers({content: space[content]})}
    )
    try:
        report = identity.verify_embedding_identity(
            configured_base_url=endpoint.base_url,
            recorded_base_url=endpoint.base_url,
            pack_dir=pack,
        )
    finally:
        endpoint.close()

    assert report.passed is True
    assert report.checks["provider"] == identity.PROVIDER_OPENAI_COMPATIBLE
    assert endpoint.paths() == [_COMPATIBLE_ROUTE]


def test_a_native_endpoint_in_another_space_still_fails(tmp_path: Path) -> None:
    """A native route is no easier to pass: the comparison is the same one."""

    pack, space = _make_pack(tmp_path, seed=33)
    _point_id, content = identity._probe_document(pack / identity._LOOKUP_FILENAME)
    endpoint = _ShapeEndpoint(
        {
            identity.NATIVE_EMBEDDINGS_PATH: _native_answers(
                {content: _orthogonal(77, space[content])}
            )
        }
    )
    try:
        report = identity.verify_embedding_identity(
            configured_base_url=endpoint.base_url,
            recorded_base_url=endpoint.base_url,
            pack_dir=pack,
        )
    finally:
        endpoint.close()

    assert report.arm == "index"
    assert report.passed is False
    assert report.cosine is not None and report.cosine < 0.99
    assert "不要切换" in report.detail
    assert report.checks["provider"] == identity.PROVIDER_DASHSCOPE_NATIVE


def test_a_native_route_that_rejects_the_credential_is_unverified(
    tmp_path: Path,
) -> None:
    """A route/credential problem is 未校验: no pass, no crash, the route named."""

    pack, _space = _make_pack(tmp_path, seed=34)
    endpoint = _ShapeEndpoint({identity.NATIVE_EMBEDDINGS_PATH: _refuses(401)})
    try:
        report = identity.verify_embedding_identity(
            configured_base_url=endpoint.base_url,
            recorded_base_url=endpoint.base_url,
            pack_dir=pack,
        )
    finally:
        endpoint.close()

    assert report.arm is None
    assert report.passed is None
    assert report.cosine is None
    assert "未校验" in report.detail
    assert report.checks["provider"] == identity.PROVIDER_DASHSCOPE_NATIVE


def test_a_rejected_compatible_route_never_falls_through_to_the_native_one(
    tmp_path: Path,
) -> None:
    """Only an *absent* route selects the native shape; 401 is an answer."""

    pack, _space = _make_pack(tmp_path, seed=35)
    endpoint = _ShapeEndpoint({identity.EMBEDDINGS_PATH: _refuses(401)})
    try:
        report = identity.verify_embedding_identity(
            configured_base_url=endpoint.base_url,
            recorded_base_url=endpoint.base_url,
            pack_dir=pack,
        )
    finally:
        endpoint.close()

    assert report.passed is None
    assert "401" in report.detail
    assert endpoint.paths() == [_COMPATIBLE_ROUTE]


def test_the_reference_arm_probes_the_query_side_of_a_native_route() -> None:
    """Both arms' roles survive the shape change: reference = the route's query side."""

    vector = _vector(1)
    table = {identity.PROBE_TEXT: vector}
    configured = _ShapeEndpoint(
        {identity.NATIVE_EMBEDDINGS_PATH: _native_answers(table)}
    )
    recorded = _ShapeEndpoint({identity.NATIVE_EMBEDDINGS_PATH: _native_answers(table)})
    try:
        report = identity.verify_embedding_identity(
            configured_base_url=configured.base_url,
            recorded_base_url=recorded.base_url,
        )
    finally:
        configured.close()
        recorded.close()

    assert report.arm == "reference"
    assert report.passed is True
    assert report.checks["provider"] == identity.PROVIDER_DASHSCOPE_NATIVE
    assert report.checks["role"] == identity.ROLE_QUERY
    for endpoint in (configured, recorded):
        assert endpoint.paths() == [_COMPATIBLE_ROUTE, _NATIVE_ROUTE]
        native_call = endpoint.calls[1]
        assert native_call["payload"]["text_type"] == identity.ROLE_QUERY


# -- the route and the page --------------------------------------------------


@pytest.fixture()
def stores(tmp_path: Path) -> tuple[ManagedSettingsStore, Any]:
    from src.data_agents.canonical_v2.managed_secrets import ManagedSecretsStore

    return (
        ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={}),
        ManagedSecretsStore(tmp_path / "managed" / "secrets.json", environ={}),
    )


def _client(stores: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A scratch-managed client with a fresh (generous) connection-test limiter."""

    from backend.api import canonical_v2_admin_config as module
    from backend.api.canonical_v2_admin_config import get_managed_secrets_store
    from backend.services.canonical_v2_connection_tests import ConnectionTestRateLimiter

    monkeypatch.setattr(
        module,
        "_TEST_LIMITER",
        ConnectionTestRateLimiter(per_minute=50, min_interval_seconds=0.0),
    )
    settings, secrets = stores
    app.dependency_overrides[get_managed_settings_store] = lambda: settings
    app.dependency_overrides[get_managed_secrets_store] = lambda: secrets
    app.state.__dict__[_STORE_STATE] = settings
    return authorized_client(raise_server_exceptions=False)


def _probe_route(
    stores: tuple[Any, Any], body: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_probe(**kwargs: Any) -> identity.EmbeddingIdentityReport:
        seen.update(kwargs)
        return identity.EmbeddingIdentityReport(
            arm="reference",
            passed=True,
            cosine=1.0,
            detail="与索引记录的端点同源：固定探针 cos=1.0000",
            threshold=identity.REFERENCE_COSINE_FLOOR,
        )

    monkeypatch.setattr(
        "backend.api.canonical_v2_admin_config.verify_embedding_identity", fake_probe
    )
    client = _client(stores, monkeypatch)
    try:
        response = client.post("/api/canonical-v2/admin/connections/test", json=body)
        assert response.status_code == 200, response.text
        payload = response.json()
    finally:
        app.dependency_overrides.clear()
    payload["_probe_args"] = seen
    return payload


class _AnsweringEndpoint:
    """One loopback OpenAI-compatible endpoint so the transport check passes."""

    def __init__(self) -> None:
        import http.server

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - handler API
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                body = b'{"data": [{"index": 0, "embedding": [1.0, 0.0]}]}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: object) -> None:
                return

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def test_the_embedding_card_receives_the_identity_verdict(
    stores: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    endpoint = _AnsweringEndpoint()
    try:
        payload = _probe_route(
            stores,
            {
                "connection": "embedding",
                "base_url": endpoint.base_url,
                "api_key": "unsaved-key",
                "identity_check": True,
            },
            monkeypatch,
        )
    finally:
        endpoint.close()

    assert payload["ok"] is True
    assert payload["identity"]["passed"] is True
    assert payload["identity"]["arm"] == "reference"
    assert payload["identity"]["cosine"] == 1.0
    assert payload["_probe_args"]["configured_base_url"] == endpoint.base_url
    assert payload["_probe_args"]["api_key"] == "unsaved-key"


def test_the_card_asks_with_the_model_the_mounted_pack_records(
    stores: tuple[Any, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model the lane sends, not a literal: the pack's record decides it."""

    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "manifest.json").write_text(
        json.dumps({"embedding_model_id": "qwen3.7-text-embedding-flash"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CANONICAL_V2_SERVING_PACK", str(pack))
    endpoint = _AnsweringEndpoint()
    try:
        payload = _probe_route(
            stores,
            {
                "connection": "embedding",
                "base_url": endpoint.base_url,
                "identity_check": True,
            },
            monkeypatch,
        )
    finally:
        endpoint.close()

    assert payload["_probe_args"]["model"] == "qwen3.7-text-embedding-flash"


def test_without_the_flag_the_connection_test_stays_one_call(
    stores: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(**_: Any) -> Any:
        raise AssertionError("the probe must not run without the flag")

    monkeypatch.setattr(
        "backend.api.canonical_v2_admin_config.verify_embedding_identity", explode
    )
    client = _client(stores, monkeypatch)
    try:
        response = client.post(
            "/api/canonical-v2/admin/connections/test",
            json={"connection": "embedding", "base_url": "http://10.20.30.40:9000/v1"},
        )
        payload = response.json()
    finally:
        app.dependency_overrides.clear()

    assert payload["identity"] is None
    assert "identity" in payload


def test_other_connections_never_get_an_identity_block(
    stores: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CANONICAL_V2_RERANK_BASE_URL", "http://10.20.30.40:9001")
    payload = _probe_route(
        stores,
        {
            "connection": "rerank",
            "base_url": "http://10.20.30.40:9001",
            "identity_check": True,
        },
        monkeypatch,
    )

    assert payload["identity"] is None


def test_a_failed_connection_skips_the_identity_check(
    stores: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(**_: Any) -> Any:
        raise AssertionError("a failed connection must not be probed further")

    monkeypatch.setattr(
        "backend.api.canonical_v2_admin_config.verify_embedding_identity", explode
    )
    client = _client(stores, monkeypatch)
    try:
        response = client.post(
            "/api/canonical-v2/admin/connections/test",
            json={
                "connection": "embedding",
                "base_url": "http://127.0.0.1:1/v1",
                "identity_check": True,
            },
        )
        payload = response.json()
    finally:
        app.dependency_overrides.clear()

    assert payload["ok"] is False
    assert payload["identity"]["passed"] is None
    assert "跳过" in payload["identity"]["detail"]


def test_the_page_asks_for_the_identity_check_on_the_embedding_card() -> None:
    page = (
        Path(__file__).resolve().parents[1] / "backend" / "static" / "admin.js"
    ).read_text(encoding="utf-8")

    assert 'if (connectionKey === "embedding") body.identity_check = true;' in page
    assert "function identityText(" in page
    assert "向量身份未校验" in page
    # The verdict travels with every other connection-test line.
    assert "const identity = identityText(payload.identity);" in page
    assert 'payload.ok ? "成功" : "失败"' in page
