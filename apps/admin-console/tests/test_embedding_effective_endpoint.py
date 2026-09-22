"""F2.3/F2.4 — the admin surface reports the *effective* embedding endpoint.

Cluster E of
`.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/verification-contract.md`.

Fixture sources: the real resolver over constructed ``environ`` mappings, the
real FastAPI route graph over scratch managed files, and the shipped connection
spec table. No provider is dialled and nothing reads the live state directory.
"""

from __future__ import annotations

import json
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


def test_the_secrets_card_names_every_variable_the_key_fills() -> None:
    """One page field, two slots: the hint must not name only half of them."""

    page = (_STATIC / "admin.js").read_text(encoding="utf-8")

    assert "entry.mirror_env_vars" in page
    assert "写入受管文件，重启后由环境变量 ${slots.join" in page


# -- the model identity comes from the mounted pack's record ------------------
# The card must validate the endpoint with the model the *serving lane* sends.
# That identity is frozen in the release bundle, which this process cannot read
# (it holds no bundle path), but the pack it serves from records the same value:
# the loader refuses to boot unless the bundle's ``model_id`` equals the pack
# manifest's ``embedding_model_id``. So the record is the source, and neither the
# page nor an environment variable may override it.

PACK_ENV = "CANONICAL_V2_SERVING_PACK"
RECORDED_MODEL = "Qwen/Qwen3-Embedding-8B"
CANDIDATE_MODEL = "qwen3.7-text-embedding-flash"


def _pack_recording(tmp_path: Path, model: Any) -> Path:
    pack = tmp_path / "pack"
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "manifest.json").write_text(
        json.dumps({"embedding_model_id": model}), encoding="utf-8"
    )
    return pack


def test_the_model_comes_from_the_mounted_packs_record(tmp_path: Path) -> None:
    """The card's model is the recorded identity, not a literal in this module."""

    pack = _pack_recording(tmp_path, CANDIDATE_MODEL)

    connection = resolve_embedding(
        environ={PACK_ENV: str(pack), "API_KEY": "test-key"},
        secrets_store=None,
        key_file_roots=(),
    )

    assert connection.model == CANDIDATE_MODEL


def test_without_a_pack_the_frozen_literal_stands() -> None:
    """No pack mounted (a development host): the recorded authority's model."""

    connection = resolve_embedding(
        environ={"API_KEY": "test-key"}, secrets_store=None, key_file_roots=()
    )

    assert connection.model == RECORDED_MODEL


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        json.dumps({"embedding_model_id": ""}),
        json.dumps({"embedding_model_id": 4096}),
        json.dumps({"other": "value"}),
    ],
)
def test_an_unusable_pack_record_falls_back_instead_of_breaking_the_card(
    tmp_path: Path, payload: str
) -> None:
    pack = tmp_path / "pack"
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "manifest.json").write_text(payload, encoding="utf-8")

    connection = resolve_embedding(
        environ={PACK_ENV: str(pack), "API_KEY": "test-key"},
        secrets_store=None,
        key_file_roots=(),
    )

    assert connection.model == RECORDED_MODEL


def test_a_missing_manifest_is_not_an_error(tmp_path: Path) -> None:
    connection = resolve_embedding(
        environ={PACK_ENV: str(tmp_path / "absent"), "API_KEY": "k"},
        secrets_store=None,
        key_file_roots=(),
    )

    assert connection.model == RECORDED_MODEL


def test_the_presets_endpoint_reports_the_records_model(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = _pack_recording(tmp_path, CANDIDATE_MODEL)
    monkeypatch.setenv(PACK_ENV, str(pack))

    reported = _presets(stores)["embedding_frozen"]

    assert reported["model"] == CANDIDATE_MODEL
    assert "模型身份仍由发布包冻结" in reported["note"]
    assert "服务包记录" in reported["note"]
