"""I2/I3 — the model-configuration surface behind `/admin`'s role cards.

Fixture source: the real FastAPI route graph over scratch managed files, a fake
HTTP transport (no provider, no outbound call) and the shipped preset / profile
tables; one test additionally drives a loopback endpoint so the un-stubbed urllib
path is exercised for real. Nothing here reads or writes the live state directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, Iterator
from urllib import error as urllib_error

from fastapi.testclient import TestClient
import pytest

from backend.api.canonical_v2_admin_config import (
    get_managed_secrets_store,
    get_managed_settings_store,
)
from backend.main import app
from tests.conftest import authorized_client
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore
from src.data_agents.canonical_v2.managed_secrets import ManagedSecretsStore

_KEY = "sk-fake-models-0000-1111-77aa"
_SETTINGS_STATE = "canonical_v2_managed_settings_store"
_SECRETS_STATE = "canonical_v2_managed_secrets_store"

# A preset table is deployment-agnostic: these markers are this installation's
# hosts (the frozen embedding authority, the model gateway, the serving ports).
_DEPLOYMENT_MARKERS = ("100.64.", "sustech", "18188", "18189", "18294", "18296")

# Ambient credentials/base URLs are scrubbed: the resolution chain mirrors the
# runtime, so a stray host variable would decide the outcome of a test here.
_AMBIENT_VARS = (
    "API_KEY",
    "OPENAI_API_KEY",
    "SGLANG_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "LOCAL_LLM_API_KEY",
    "BOCHA_API_KEY",
    "SERPER_API_KEY",
    "CANONICAL_V2_RERANK_BASE_URL",
    "CANONICAL_V2_RERANK_API_KEY",
    "CANONICAL_V2_RERANK_API_KEY_FILE",
    "CANONICAL_V2_EMBEDDING_BASE_URL",
    "CANONICAL_V2_EMBEDDING_MODEL",
)


class _FakeTransport:
    """The one stub between the route and the network: records, never dials."""

    def __init__(
        self, *, status: int = 200, body: bytes = b"", raises: Exception | None = None
    ) -> None:
        self.status = status
        self.body = body
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, **kwargs: Any) -> tuple[int, bytes]:
        self.calls.append({"url": url, **kwargs})
        if self.raises is not None:
            raise self.raises
        return self.status, self.body


@pytest.fixture(autouse=True)
def _scrub_ambient_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _AMBIENT_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def stores(
    tmp_path: Path,
) -> Iterator[tuple[ManagedSettingsStore, ManagedSecretsStore]]:
    settings = ManagedSettingsStore(
        tmp_path / "managed" / "settings.json",
        environ=dict(os.environ),
        repo_root=tmp_path,
    )
    secrets = ManagedSecretsStore(
        tmp_path / "managed" / "secrets.json",
        environ=dict(os.environ),
        key_file_roots=(),
        repo_root=tmp_path,
    )
    prior_settings = getattr(app.state, _SETTINGS_STATE, None)
    prior_secrets = getattr(app.state, _SECRETS_STATE, None)
    setattr(app.state, _SETTINGS_STATE, settings)
    setattr(app.state, _SECRETS_STATE, secrets)
    app.dependency_overrides[get_managed_settings_store] = lambda: settings
    app.dependency_overrides[get_managed_secrets_store] = lambda: secrets
    try:
        yield settings, secrets
    finally:
        app.dependency_overrides.pop(get_managed_settings_store, None)
        app.dependency_overrides.pop(get_managed_secrets_store, None)
        for name, prior in (
            (_SETTINGS_STATE, prior_settings),
            (_SECRETS_STATE, prior_secrets),
        ):
            if prior is not None:
                setattr(app.state, name, prior)
            elif hasattr(app.state, name):
                delattr(app.state, name)


@pytest.fixture()
def fresh_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-test rate limiter: the module one is process-global by design."""

    from backend.api import canonical_v2_admin_config as module
    from backend.services.canonical_v2_connection_tests import ConnectionTestRateLimiter

    monkeypatch.setattr(
        module,
        "_TEST_LIMITER",
        ConnectionTestRateLimiter(per_minute=30, min_interval_seconds=0.0),
    )


@pytest.fixture()
def transport(monkeypatch: pytest.MonkeyPatch, fresh_limiter: None) -> _FakeTransport:
    """Stub the one HTTP seam (the service module's `get_json`)."""

    from backend.services import canonical_v2_connection_tests as service

    fake = _FakeTransport()
    monkeypatch.setattr(service, "get_json", fake)
    return fake


class _LocalModelsHandler(BaseHTTPRequestHandler):
    """A loopback OpenAI-compatible `/v1/models` for the one un-stubbed test."""

    def _respond(self, status: int, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - http.server's interface
        if self.path != "/v1/models":
            self._respond(404, b"no such path")
            return
        if self.headers.get("Authorization") == "Bearer bad-key":
            self._respond(401, b'{"error": "invalid api key bad-key"}')
            return
        self._respond(
            200,
            json.dumps({"object": "list", "data": [{"id": "local-model"}]}).encode(),
        )

    def log_message(self, *args: Any) -> None:  # pragma: no cover - silence the server
        pass


@pytest.fixture()
def local_endpoint() -> Iterator[str]:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _LocalModelsHandler)
    except OSError as exc:  # pragma: no cover - no loopback sockets here
        pytest.skip(f"loopback socket unavailable: {type(exc).__name__}")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _client() -> TestClient:
    return authorized_client(raise_server_exceptions=False)


def _list_models(client: TestClient, *body: dict[str, Any], key: str = "llm") -> Any:
    payload: dict[str, Any] = {}
    for chunk in body:
        payload.update(chunk)
    return client.post(
        f"/api/canonical-v2/admin/connections/{key}/models", json=payload
    )


# -- I2: presets -------------------------------------------------------------


def test_presets_table_is_generic_and_carries_the_profile_view(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
) -> None:
    response = _client().get("/api/canonical-v2/admin/connections/presets")

    assert response.status_code == 200
    payload = response.json()

    presets = payload["presets"]
    assert presets, "the page needs a preset table to offer"
    ids = [preset["id"] for preset in presets]
    assert ids == [
        "local-openai",
        "deepseek",
        "dashscope",
        "openai",
        "siliconflow",
        "custom",
    ]
    for preset in presets:
        assert set(preset) == {
            "id",
            "label",
            "base_url",
            "needs_key",
            "docs_url",
            "note",
        }
        assert preset["label"].strip()
        assert isinstance(preset["needs_key"], bool)
        if preset["base_url"]:
            assert preset["base_url"].startswith(("http://", "https://"))
        joined = json.dumps(preset, ensure_ascii=False)
        for marker in _DEPLOYMENT_MARKERS:
            assert marker not in joined, (preset["id"], marker)
    # The local entry points at an operator's own host, not at this deployment's.
    local = presets[0]
    assert local["base_url"] == "http://127.0.0.1:8000/v1"
    assert local["note"]

    profiles = payload["llm_profiles"]
    names = [profile["name"] for profile in profiles]
    assert names == sorted(names)
    from src.data_agents.professor.llm_profiles import _LLM_PROFILES

    assert names == sorted(_LLM_PROFILES)
    for profile in profiles:
        endpoint = _LLM_PROFILES[profile["name"]].local
        assert profile["base_url"] == endpoint.base_url
        assert profile["model"] == endpoint.model
        assert profile["key_env"] == endpoint.api_key_env
        assert profile["label"].strip()
    assert payload["chat_profile"] in names

    frozen = payload["embedding_frozen"]
    assert frozen["base_url"] and frozen["model"] and frozen["note"]


def test_presets_report_the_profile_this_process_would_use(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAT_LLM_PROFILE", "deepseekv4flash")

    payload = _client().get("/api/canonical-v2/admin/connections/presets").json()

    assert payload["chat_profile"] == "deepseekv4flash"
    selected = next(
        item for item in payload["llm_profiles"] if item["name"] == "deepseekv4flash"
    )
    assert selected["key_env"] == "DEEPSEEK_API_KEY"


def test_model_config_routes_require_a_session() -> None:
    anonymous = TestClient(app, raise_server_exceptions=False)

    presets = anonymous.get("/api/canonical-v2/admin/connections/presets")
    models = anonymous.post("/api/canonical-v2/admin/connections/llm/models", json={})

    assert presets.status_code == 401
    assert models.status_code == 401
    assert presets.json()["detail"] == "authentication_required"


# -- I3: model discovery -----------------------------------------------------


def test_model_list_sorts_dedupes_and_reports_the_request_url(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _FakeTransport,
) -> None:
    transport.status = 200
    transport.body = json.dumps(
        {
            "object": "list",
            "data": [{"id": "b-model"}, {"id": "a-model"}, {"id": "b-model"}],
        }
    ).encode()

    response = _list_models(
        _client(),
        {"base_url": "http://127.0.0.1:18006/v1", "api_key": _KEY},
        key="llm",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["connection"] == "llm"
    assert [item["id"] for item in payload["models"]] == ["a-model", "b-model"]
    assert payload["count"] == 2
    assert "truncated" not in payload
    # The base URL already ends in /v1: the shared `_join` must not double it.
    assert payload["request_url"] == "http://127.0.0.1:18006/v1/models"
    assert isinstance(payload["elapsed_ms"], int) and payload["elapsed_ms"] >= 0
    assert _KEY not in response.text

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["headers"]["Authorization"] == f"Bearer {_KEY}"
    # Shorter than the connection probe: a model list is a convenience, not a test.
    from backend.services.canonical_v2_connection_tests import DEFAULT_TIMEOUT_SECONDS

    assert call["timeout"] == 3.0
    assert call["timeout"] < DEFAULT_TIMEOUT_SECONDS
    assert call["max_bytes"] == 512 * 1024


def test_model_list_caps_the_page_list_and_marks_the_cut(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _FakeTransport,
) -> None:
    transport.status = 200
    transport.body = json.dumps(
        {"data": [{"id": f"model-{index:04d}"} for index in range(600)]}
    ).encode()

    payload = _list_models(
        _client(), {"base_url": "http://127.0.0.1:18006"}, key="llm"
    ).json()

    assert payload["count"] == 500
    assert len(payload["models"]) == 500
    assert payload["truncated"] is True
    assert payload["models"][0]["id"] == "model-0000"


@pytest.mark.parametrize(
    ("status", "body", "raises", "expected"),
    [
        (401, b'{"error":"invalid api key"}', None, "unauthorized"),
        (403, b"forbidden", None, "unauthorized"),
        (404, b"not found", None, "not_supported"),
        (500, b"upstream exploded", None, "bad_response"),
        (200, b"<html>hello</html>", None, "bad_response"),
        (200, b'{"data": []}', None, "bad_response"),
        (
            None,
            b"",
            urllib_error.URLError(ConnectionRefusedError("no route to host")),
            "unreachable",
        ),
        (None, b"", TimeoutError(), "timeout"),
        (
            None,
            b"",
            urllib_error.URLError(TimeoutError("timed out")),
            "timeout",
        ),
    ],
)
def test_model_list_failures_stay_structured(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _FakeTransport,
    status: int | None,
    body: bytes,
    raises: Exception | None,
    expected: str,
) -> None:
    if status is not None:
        transport.status = status
    transport.body = body
    transport.raises = raises

    response = _list_models(
        _client(), {"base_url": "http://127.0.0.1:18006/v1", "api_key": _KEY}
    )

    assert response.status_code == 200, "a failed probe is never a 5xx"
    payload = response.json()
    assert payload["error"] == expected
    assert payload["connection"] == "llm"
    assert payload["status"] == status
    assert payload["request_url"] == "http://127.0.0.1:18006/v1/models"
    assert isinstance(payload["elapsed_ms"], int) and payload["elapsed_ms"] >= 0
    assert _KEY not in response.text
    if expected == "bad_response" and body:
        assert payload["body_excerpt"]
        assert len(payload["body_excerpt"]) <= 200


def test_model_list_never_echoes_the_key_even_when_upstream_does(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _FakeTransport,
) -> None:
    transport.status = 401
    transport.body = json.dumps({"error": f"bad key {_KEY}"}).encode()

    response = _list_models(
        _client(), {"base_url": "http://127.0.0.1:18006/v1", "api_key": _KEY}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] == "unauthorized"
    assert _KEY not in response.text
    assert "[redacted]" in payload["body_excerpt"]


def test_model_list_falls_back_to_the_runtime_effective_values(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _FakeTransport,
) -> None:
    """An empty body resolves like `/connections/test`: runtime endpoint + credential."""

    settings, secrets = stores
    settings.patch(
        {"extraction_endpoints": {"rerank_base_url": "http://127.0.0.1:28099"}}
    )
    secrets.patch({"rerank.api_key": _KEY}, operator="ops")
    transport.status = 200
    transport.body = b'{"data": [{"id": "qwen3-reranker-8b"}]}'
    client = _client()

    response = client.post("/api/canonical-v2/admin/connections/rerank/models", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_url"] == "http://127.0.0.1:28099/v1/models"
    assert [item["id"] for item in payload["models"]] == ["qwen3-reranker-8b"]
    assert len(transport.calls) == 1
    # Unsaved values are never stored; saved ones are never rewritten by a probe.
    before = settings.raw()
    assert client.get("/api/canonical-v2/admin/config").json()["settings"] == before
    assert _KEY not in response.text


def test_model_list_rejects_an_unsafe_endpoint_without_calling(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _FakeTransport,
) -> None:
    client = _client()

    unsafe = _list_models(client, {"base_url": "file:///etc/passwd"})
    unknown = client.post("/api/canonical-v2/admin/connections/milvus/models", json={})

    assert unsafe.status_code == 422
    assert unknown.status_code == 422
    assert "connection must be one of" in unknown.text
    assert transport.calls == []


def test_model_list_is_rate_limited_like_the_connection_test(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _FakeTransport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.api import canonical_v2_admin_config as module
    from backend.services.canonical_v2_connection_tests import ConnectionTestRateLimiter

    monkeypatch.setattr(
        module,
        "_TEST_LIMITER",
        ConnectionTestRateLimiter(per_minute=1, min_interval_seconds=1.0),
    )
    transport.status = 200
    transport.body = b'{"data": [{"id": "a-model"}]}'
    client = _client()

    first = _list_models(client, {"base_url": "http://127.0.0.1:18006/v1"})
    second = _list_models(client, {"base_url": "http://127.0.0.1:18006/v1"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["error"] == "rate_limited"
    assert second.json()["detail"]["connection"] == "llm"
    assert int(second.headers["retry-after"]) >= 1
    assert len(transport.calls) == 1


def test_model_list_needs_no_console_database(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _FakeTransport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The console DB is irrelevant here: no DSN, no gate, still a model list."""

    for name in ("DATABASE_URL", "DATABASE_URL_TEST", "CANONICAL_V2_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    had_dsn = hasattr(app.state, "console_dsn")
    prior_dsn = getattr(app.state, "console_dsn", None)
    app.state.console_dsn = None
    transport.status = 200
    transport.body = b'{"data": [{"id": "a-model"}]}'
    try:
        response = _list_models(
            _client(), {"base_url": "http://127.0.0.1:18006/v1", "api_key": _KEY}
        )
    finally:
        if had_dsn:
            app.state.console_dsn = prior_dsn
        else:
            delattr(app.state, "console_dsn")

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_model_list_against_a_real_local_endpoint(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    local_endpoint: str,
    fresh_limiter: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The un-stubbed path: real urllib GET, real JSON, real 401, real redaction."""

    for name in (
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    client = _client()

    ok = _list_models(client, {"base_url": local_endpoint, "api_key": "good-key"})
    bad = _list_models(
        client, {"base_url": local_endpoint, "api_key": "bad-key"}, key="rerank"
    )

    assert ok.status_code == 200
    assert ok.json()["request_url"] == f"{local_endpoint}/models"
    assert [item["id"] for item in ok.json()["models"]] == ["local-model"]
    assert ok.json()["count"] == 1

    assert bad.status_code == 200
    assert bad.json()["error"] == "unauthorized"
    assert bad.json()["status"] == 401
    assert bad.json()["request_url"] == f"{local_endpoint}/models"
    assert "bad-key" not in bad.text
    assert "[redacted]" in bad.json()["body_excerpt"]
