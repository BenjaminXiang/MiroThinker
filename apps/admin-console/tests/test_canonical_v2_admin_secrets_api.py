from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

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
from src.data_agents.canonical_v2.managed_runtime import applied_env_names

# Locally generated fakes only: no fixture in this file carries a real key.
_SENTINEL = "sk-fake-sentinel-4f8e21ab-cd34"
_SETTINGS_STATE = "canonical_v2_managed_settings_store"
_SECRETS_STATE = "canonical_v2_managed_secrets_store"


def _redact(value: Any) -> Any:
    """Never keep a credential that did not come from this test file in a recorder.

    The resolution chain may legitimately pick up an ambient key; a pytest failure
    message must not become a place where such a value is printed.
    """

    if isinstance(value, str) and value and not value.startswith(("sk-fake", "fake-")):
        return "<redacted-non-fixture-value>"
    return value


class _RecordingTransport:
    def __init__(self, *, ok: bool = True, latency_note: str = "") -> None:
        self.calls: list[dict[str, Any]] = []
        self.ok = ok

    def __call__(self, spec: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(
            {
                key: (_redact(value) if key == "api_key" else value)
                for key, value in {"spec": spec, **kwargs}.items()
            }
        )
        if kwargs.get("disabled_reason") and not kwargs.get("base_url"):
            # The real service short-circuits here; mirror it so the route contract
            # (no call, honest reason) is what gets asserted.
            return {
                "ok": False,
                "latency_ms": 0,
                "http_status": None,
                "detail": str(kwargs["disabled_reason"]),
                "called": False,
            }
        return {
            "ok": self.ok,
            "latency_ms": 12,
            "http_status": 200 if self.ok else 401,
            "detail": "HTTP 200" if self.ok else "HTTP 401：端点可达，凭据被拒绝",
            "called": True,
        }


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


# Ambient credential variables are removed for every test in this file: the
# resolution chain mirrors the runtime, so a stray host variable would otherwise
# decide the outcome (and could end up in a failure message).
_AMBIENT_CREDENTIAL_VARS = (
    "API_KEY",
    "OPENAI_API_KEY",
    "SGLANG_API_KEY",
    "BOCHA_API_KEY",
    "SERPER_API_KEY",
    "DEEPSEEK_API_KEY",
    "LOCAL_LLM_API_KEY",
    "EMBEDDING_API_KEY",
    "CANONICAL_V2_RERANK_API_KEY",
    "CANONICAL_V2_RERANK_API_KEY_FILE",
    "CANONICAL_V2_RERANK_BASE_URL",
)


@pytest.fixture(autouse=True)
def _scrub_ambient_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _AMBIENT_CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def transport(monkeypatch: pytest.MonkeyPatch) -> _RecordingTransport:
    """Install a fake transport and a fresh rate limiter for the test route."""

    from backend.api import canonical_v2_admin_config as module
    from backend.services.canonical_v2_connection_tests import ConnectionTestRateLimiter

    fake = _RecordingTransport()
    monkeypatch.setattr(module, "test_connection", fake)
    monkeypatch.setattr(
        module,
        "_TEST_LIMITER",
        ConnectionTestRateLimiter(per_minute=3, min_interval_seconds=1.0),
    )
    return fake


def _client() -> TestClient:
    return authorized_client(raise_server_exceptions=False)


def test_read_endpoint_never_returns_plaintext(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
) -> None:
    """R1: a written credential is never returned, in any casing."""

    client = _client()
    patched = client.patch(
        "/api/canonical-v2/admin/secrets",
        json={"values": {"bocha.api_key": _SENTINEL}},
        headers={"X-Remote-User": "ops-secret"},
    )
    assert patched.status_code == 200
    assert patched.json()["changed"] == ["bocha.api_key"]
    assert _SENTINEL not in patched.text

    read = client.get("/api/canonical-v2/admin/secrets")
    assert read.status_code == 200
    assert _SENTINEL not in read.text
    body = read.json()
    bocha = next(item for item in body["secrets"] if item["field"] == "bocha.api_key")
    assert bocha["configured"] is True
    assert bocha["origin"] == "managed-file"
    assert bocha["mask"] == "sk-…cd34"
    assert len(bocha["mask"]) <= 12
    assert _SENTINEL[:8] not in json.dumps(body)
    assert body["restart_required"]
    assert len(body["connections"]) == 5


def test_audit_and_health_payload_stay_value_free(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
) -> None:
    settings, secrets = stores
    client = _client()

    client.patch(
        "/api/canonical-v2/admin/secrets",
        json={"values": {"serper.api_key": _SENTINEL}},
    )
    health = client.post("/api/canonical-v2/admin/providers/health-check")

    assert _SENTINEL not in (secrets.audit_path.read_text(encoding="utf-8"))
    assert _SENTINEL not in health.text
    assert _SENTINEL not in json.dumps(
        [state.as_dict() for state in secrets.describe(environ=dict(os.environ))]
    )
    assert settings.path.exists() is False


def test_set_requires_restart_and_is_not_hot_read(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
) -> None:
    """R6: the value lands in the file, and the running process ignores it."""

    settings, secrets = stores
    env_before = dict(os.environ)
    client = _client()

    response = client.patch(
        "/api/canonical-v2/admin/secrets",
        json={"values": {"bocha.api_key": _SENTINEL}},
    )

    assert response.status_code == 200
    assert "重启" in response.json()["restart_required"]
    # The carrier is the file: a fresh process reads it (this is the restart path).
    restarted = ManagedSecretsStore(
        secrets.path, environ={}, key_file_roots=(), repo_root=secrets.path.parents[2]
    )
    material, origin = restarted.resolve_field("bocha.api_key", environ={})
    assert material == _SENTINEL and origin == "managed-file"
    # Nothing was hot-read: the live environment is unchanged and nothing was
    # adopted by this process.
    assert os.environ.get("BOCHA_API_KEY", "") == env_before.get("BOCHA_API_KEY", "")
    assert "BOCHA_API_KEY" not in applied_env_names(os.environ)
    assert settings.path.exists() is False


def test_clear_and_overwrite_paths(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
) -> None:
    settings, secrets = stores
    client = _client()

    first = client.patch(
        "/api/canonical-v2/admin/secrets",
        json={"values": {"rerank.api_key": _SENTINEL}},
    )
    assert first.status_code == 200
    tail = next(
        item for item in first.json()["secrets"] if item["field"] == "rerank.api_key"
    )["mask"]
    assert tail.endswith(_SENTINEL[-4:])

    overwritten = client.patch(
        "/api/canonical-v2/admin/secrets",
        json={"values": {"rerank.api_key": "sk-fake-second-value-9988"}},
    )
    new_mask = next(
        item
        for item in overwritten.json()["secrets"]
        if item["field"] == "rerank.api_key"
    )["mask"]
    assert new_mask != tail and new_mask.endswith("9988")

    cleared = client.patch(
        "/api/canonical-v2/admin/secrets", json={"values": {"rerank.api_key": None}}
    )
    cleared_entry = next(
        item for item in cleared.json()["secrets"] if item["field"] == "rerank.api_key"
    )
    assert cleared.json()["changed"] == ["rerank.api_key"]
    assert cleared_entry["configured"] is False
    assert cleared_entry["mask"] is None
    assert secrets.raw() == {}
    assert _SENTINEL not in (secrets.audit_path.read_text(encoding="utf-8"))


def test_secrets_router_rejects_unknown_fields_and_bad_bodies(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
) -> None:
    settings, secrets = stores
    client = _client()

    unknown = client.patch(
        "/api/canonical-v2/admin/secrets", json={"values": {"milvus.uri": "x"}}
    )
    no_values = client.patch("/api/canonical-v2/admin/secrets", json={})
    wrong_type = client.patch(
        "/api/canonical-v2/admin/secrets", json={"values": {"bocha.api_key": 42}}
    )

    assert unknown.status_code == 422 and "whitelist" in unknown.text
    assert no_values.status_code == 422
    assert wrong_type.status_code == 422
    assert secrets.exists() is False


def test_connection_test_uses_unsaved_values_and_calls_once(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _RecordingTransport,
) -> None:
    """R4: test-before-save; exactly one minimal call; nothing persisted."""

    settings, secrets = stores
    client = _client()

    response = client.post(
        "/api/canonical-v2/admin/connections/test",
        json={
            "connection": "rerank",
            "api_key": _SENTINEL,
            "base_url": "http://127.0.0.1:18006",
            "model": "qwen3-reranker-8b",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True and payload["latency_ms"] == 12
    assert payload["called"] is True
    assert payload["used"]["api_key_source"] == "request"
    assert payload["used"]["base_url"] == "http://127.0.0.1:18006"
    assert _SENTINEL not in response.text
    assert len(transport.calls) == 1
    assert transport.calls[0]["api_key"] == _SENTINEL
    assert transport.calls[0]["base_url"] == "http://127.0.0.1:18006"
    # Test-before-save never persists the probed value.
    assert secrets.exists() is False
    assert settings.path.exists() is False


def test_connection_test_falls_back_to_the_stored_value(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _RecordingTransport,
) -> None:
    settings, secrets = stores
    secrets.patch({"bocha.api_key": _SENTINEL}, operator="ops")
    client = _client()

    response = client.post(
        "/api/canonical-v2/admin/connections/test", json={"connection": "bocha"}
    )

    assert response.status_code == 200
    payload = response.json()
    # The just-saved value is what the operator wants to verify; it is labelled
    # as pending so it is never confused with the running process's source.
    assert payload["used"]["api_key_source"] == "managed-file(pending-restart)"
    assert (
        payload["used"]["effective_api_key_source"] != "managed-file(pending-restart)"
    )
    assert payload["runtime"]["pending_restart"] is True
    assert len(transport.calls) == 1
    assert transport.calls[0]["api_key"] == _SENTINEL


def test_connection_test_is_rate_limited(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _RecordingTransport,
) -> None:
    """R5: the second immediate attempt is rejected without another call."""

    client = _client()
    body = {"connection": "embedding", "base_url": "http://100.64.0.27:18005/v1"}

    first = client.post("/api/canonical-v2/admin/connections/test", json=body)
    second = client.post("/api/canonical-v2/admin/connections/test", json=body)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["error"] == "rate_limited"
    assert second.json()["detail"]["retry_after_seconds"] >= 1
    assert int(second.headers["retry-after"]) >= 1
    assert len(transport.calls) == 1


def test_connection_test_rejects_unknown_connection_and_unsafe_endpoint(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _RecordingTransport,
) -> None:
    client = _client()

    unknown = client.post(
        "/api/canonical-v2/admin/connections/test", json={"connection": "milvus"}
    )
    unsafe = client.post(
        "/api/canonical-v2/admin/connections/test",
        json={"connection": "embedding", "base_url": "file:///etc/passwd"},
    )

    assert unknown.status_code == 422
    assert unsafe.status_code == 422
    assert transport.calls == []


def test_serving_fields_are_in_the_managed_whitelist_with_a_readonly_policy(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
) -> None:
    """A8: new switches join the managed list; debug switches are display-only."""

    settings, secrets = stores
    client = _client()

    editable = client.patch(
        "/api/canonical-v2/admin/config",
        json={"serving": {"web_topical_floor": False, "rerank_timeout_seconds": 2.5}},
    )
    assert editable.status_code == 200
    assert editable.json()["settings"]["serving"]["web_topical_floor"] is False

    readonly = client.patch(
        "/api/canonical-v2/admin/config", json={"serving": {"full_verify": True}}
    )
    assert readonly.status_code == 422
    assert "display-only" in readonly.text

    payload = client.get("/api/canonical-v2/admin/config").json()
    by_path = {field["path"]: field for field in payload["fields"]}
    assert by_path["serving.web_topical_floor"]["editable"] is True
    assert by_path["serving.full_verify"]["editable"] is False
    assert by_path["serving.full_verify"]["readonly_reason"]
    assert by_path["serving.turn_debug_dir"]["editable"] is False
    settings_document = payload["settings"]["serving"]
    assert settings_document["web_topical_floor"] is False
    assert settings_document["rerank_timeout_seconds"] == 2.5
    assert settings_document["full_verify"] is None


def test_admin_page_renders_the_credentials_card() -> None:
    """Five role blocks, built by `admin.js` with the probe inside each of them."""

    client = _client()
    page = client.get("/admin")
    script = client.get("/static/admin.js")

    assert page.status_code == 200
    assert script.status_code == 200
    assert "模型与连接" in page.text
    assert 'id="roleBlocks"' in page.text
    assert ">测试连通性<" not in page.text  # 每块角色里的探针按钮由 admin.js 生成
    assert "api/canonical-v2/admin/secrets" in script.text
    assert "api/canonical-v2/admin/connections/test" in script.text
    assert "需重启生效" in script.text


def test_disabled_connection_reports_disabled_and_never_calls(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _RecordingTransport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rerank without a configured endpoint: honest "not enabled", zero calls."""

    monkeypatch.delenv("CANONICAL_V2_RERANK_BASE_URL", raising=False)
    client = _client()

    response = client.post(
        "/api/canonical-v2/admin/connections/test", json={"connection": "rerank"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["called"] is False
    assert payload["http_status"] is None
    assert payload["runtime"]["enabled"] is False
    assert "未启用" in payload["detail"]
    assert "CANONICAL_V2_RERANK_BASE_URL" in payload["detail"]
    # The route reaches the (fake) test seam with the disabled gate set and no
    # endpoint: the real implementation returns before any outbound call.
    assert len(transport.calls) == 1
    assert transport.calls[0]["base_url"] is None
    assert transport.calls[0]["disabled_reason"]


def test_supplied_endpoint_is_tested_even_when_the_runtime_has_it_disabled(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    transport: _RecordingTransport,
) -> None:
    """Test-before-save: an operator-supplied endpoint still gets probed (one call)."""

    client = _client()

    response = client.post(
        "/api/canonical-v2/admin/connections/test",
        json={
            "connection": "rerank",
            "base_url": "http://127.0.0.1:18006",
            "api_key": _SENTINEL,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["called"] is True
    assert payload["ok"] is True
    assert payload["used"]["endpoint_source"] == "request"
    assert len(transport.calls) == 1
    assert _SENTINEL not in response.text


def test_secrets_payload_exposes_runtime_state_per_connection(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
) -> None:
    """The page needs runtime truth: enabled/disabled plus the resolved origins."""

    response = _client().get("/api/canonical-v2/admin/secrets")

    assert response.status_code == 200
    connections = {item["key"]: item for item in response.json()["connections"]}
    assert set(connections) == {"bocha", "serper", "rerank", "embedding", "llm"}
    for item in connections.values():
        assert "runtime" in item
        assert item["runtime"]["runtime_note"]
        assert "api_key" not in item["runtime"]  # origins only, never a value
    assert (
        connections["embedding"]["runtime"]["base_url"] == "http://100.64.0.27:18005/v1"
    )
    entry = next(
        item
        for item in response.json()["secrets"]
        if item["field"] == "embedding.api_key"
    )
    assert entry["env_var"] == "SGLANG_API_KEY"
    # The page must name every variable this credential fills: the candidate
    # (gateway) bundle reads its own slot, and one page field fills both.
    assert entry["mirror_env_vars"] == ["CANONICAL_V2_EMBEDDING_API_KEY"]
