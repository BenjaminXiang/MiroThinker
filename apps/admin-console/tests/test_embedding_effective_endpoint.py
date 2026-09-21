"""F2.3/F2.4 — the admin surface reports the *effective* embedding endpoint.

Cluster E of
`.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/verification-contract.md`.

Fixture sources: the real resolver over constructed ``environ`` mappings, the
real FastAPI route graph over scratch managed files, and the shipped connection
spec table. No provider is dialled and nothing reads the live state directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from backend.api.canonical_v2_admin_config import (
    get_managed_secrets_store,
    get_managed_settings_store,
)
from backend.main import app
from backend.services import canonical_v2_runtime_sources
from backend.services.canonical_v2_connection_tests import SPEC_BY_KEY
from backend.services.canonical_v2_runtime_sources import resolve_embedding
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore
from src.data_agents.canonical_v2.managed_secrets import ManagedSecretsStore

ENV = "CANONICAL_V2_EMBEDDING_BASE_URL"
RECORDED_BASE_URL = "http://100.64.0.27:18005/v1"
_SETTINGS_STATE = "canonical_v2_managed_settings_store"
_SECRETS_STATE = "canonical_v2_managed_secrets_store"
_STATIC = Path(__file__).resolve().parents[1] / "backend" / "static"


def test_the_resolver_points_at_the_single_resolution_point() -> None:
    """A reader must be able to follow the docstring to the one reader of the var."""

    text = Path(canonical_v2_runtime_sources.__file__ or "").read_text(encoding="utf-8")

    assert "resolve_embedding_base_url" in text
    assert "release embedding bundle 冻结" not in text


def test_the_managed_address_is_the_effective_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV, raising=False)

    connection = resolve_embedding(
        environ={
            ENV: "http://10.20.30.40:9000/v1",
            "API_KEY": "test-key",
            "CANONICAL_V2_MANAGED_ENV_APPLIED": ENV,
        },
        secrets_store=None,
        key_file_roots=(),
    )

    assert connection.base_url == "http://10.20.30.40:9000/v1"
    assert connection.endpoint_origin == (
        "managed-file(env:CANONICAL_V2_EMBEDDING_BASE_URL)"
    )
    assert "运行期 base_url" in connection.runtime_note
    assert "冻结" not in connection.runtime_note


def test_without_the_managed_address_the_recorded_default_is_reported() -> None:
    connection = resolve_embedding(
        environ={"API_KEY": "test-key"}, secrets_store=None, key_file_roots=()
    )

    assert connection.base_url == RECORDED_BASE_URL
    assert connection.endpoint_origin == "release-bundle-default"


def test_the_service_unit_variable_is_reported_as_an_environment_source() -> None:
    connection = resolve_embedding(
        environ={ENV: "https://embed.customer.example/v1", "API_KEY": "test-key"},
        secrets_store=None,
        key_file_roots=(),
    )

    assert connection.base_url == "https://embed.customer.example/v1"
    assert connection.endpoint_origin == f"env:{ENV}"


def test_the_connection_spec_probes_the_runtime_effective_endpoint() -> None:
    """Without a request override the test uses ``runtime.base_url`` — the
    effective address — and the page edits that address through the managed
    field rather than through this card."""

    spec = SPEC_BY_KEY["embedding"]
    assert spec.default_base_url is None
    assert spec.base_url_editable is False
    assert spec.base_url_field is None


@pytest.fixture()
def stores(tmp_path: Path) -> tuple[ManagedSettingsStore, ManagedSecretsStore]:
    return (
        ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={}),
        ManagedSecretsStore(tmp_path / "managed" / "secrets.json", environ={}),
    )


def _client(stores: tuple[ManagedSettingsStore, ManagedSecretsStore]) -> TestClient:
    settings, secrets = stores
    app.dependency_overrides[get_managed_settings_store] = lambda: settings
    app.dependency_overrides[get_managed_secrets_store] = lambda: secrets
    app.state.__dict__[_SETTINGS_STATE] = settings
    app.state.__dict__[_SECRETS_STATE] = secrets
    from tests.conftest import authorized_client

    return authorized_client()


def _presets(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
) -> dict[str, Any]:
    client = _client(stores)
    try:
        response = client.get("/api/canonical-v2/admin/connections/presets")
        assert response.status_code == 200
        return response.json()
    finally:
        app.dependency_overrides.clear()


def test_the_presets_endpoint_reports_the_effective_address(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV, "http://10.20.30.40:9000/v1")

    reported = _presets(stores)["embedding_frozen"]

    assert reported["base_url"] == "http://10.20.30.40:9000/v1"
    assert reported["model"] == "Qwen/Qwen3-Embedding-8B"
    assert "运行期生效地址" in reported["note"]
    assert f"env:{ENV}" in reported["note"]
    # The *model* identity is still frozen; the *address* is not claimed to be.
    assert "模型身份仍由发布包冻结" in reported["note"]
    assert "地址由发布包冻结" not in reported["note"]
    assert "必须等于钉死的 base_url" not in reported["note"]


def test_the_presets_endpoint_falls_back_to_the_recorded_address(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV, raising=False)

    reported = _presets(stores)["embedding_frozen"]

    assert reported["base_url"] == RECORDED_BASE_URL
    assert "release-bundle-default" in reported["note"]


def test_the_page_copy_stops_claiming_the_address_is_frozen() -> None:
    page = "\n".join(
        (path).read_text(encoding="utf-8")
        for path in (_STATIC / "admin.html", _STATIC / "admin.js")
    )

    assert "发布包冻结（presets.embedding_frozen）" not in page
    assert "只读：服务线冻结值" not in page
    assert "可设地址：模型身份仍由发布包冻结" in page
