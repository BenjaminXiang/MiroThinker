"""#2 — the vector-lane wait is a managed config row, not a hidden env var.

Covers the whole path the operator walks: catalogue row → save through the API →
startup projection into the environment → the single serving reader. Fixture
sources: the shipped schema/catalogue, the real FastAPI route graph over scratch
managed files, and the real `managed_runtime` projection.
"""

from __future__ import annotations

from pathlib import Path
import os
from typing import Any

from fastapi.testclient import TestClient
import pytest

from backend.api.canonical_v2_admin_config import get_managed_settings_store
from backend.main import app
from tests.conftest import authorized_client
from src.data_agents.canonical_v2.managed_config import (
    FIELD_CATALOG,
    FIELD_ENV_VARS,
    ManagedSettingsError,
    ManagedSettingsStore,
    flatten_settings,
)
from src.data_agents.canonical_v2.managed_runtime import apply_managed_runtime_config

PATH = "serving.vector_lane_timeout_seconds"
ENV = "CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS"
_STORE_STATE = "canonical_v2_managed_settings_store"


def _reader() -> Any:
    from importlib import import_module

    return import_module("src.data_agents.canonical_v2.knowledge_read")


@pytest.fixture(autouse=True)
def _no_ambient_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV, raising=False)


def test_the_row_exists_with_bounds_and_the_serving_default() -> None:
    spec = FIELD_CATALOG[PATH]

    assert FIELD_ENV_VARS[PATH] == ENV
    assert spec.kind == "float"
    assert spec.group == "serving"
    assert spec.label.strip()
    assert spec.consumer.strip()
    assert (spec.min, spec.max, spec.step) == (0.1, 120, 0.1)
    assert spec.connection is None and spec.test_arg is None
    # The page must show the number the serving line really waits.
    assert spec.default == _reader()._VECTOR_LANE_OUTER_WAIT_DEFAULT_SECONDS == 8.0


def test_one_reader_resolves_the_knob() -> None:
    """The env var is named in exactly two places: the field map and the reader."""

    source_root = Path(_reader().__file__).parents[1]  # .../data_agents
    readers = sorted(
        str(path.relative_to(source_root))
        for path in source_root.rglob("*.py")
        if ENV in path.read_text(encoding="utf-8")
    )

    assert readers == [
        "canonical_v2/knowledge_read.py",
        "canonical_v2/managed_config.py",
    ], readers


def test_the_knob_round_trips_save_projection_and_reader(tmp_path: Path) -> None:
    settings_path = tmp_path / "managed" / "settings.json"
    store = ManagedSettingsStore(settings_path, environ={})
    environ: dict[str, str] = {}

    result = store.patch({"serving": {"vector_lane_timeout_seconds": 12.5}})

    assert result["changed"] == [PATH]
    assert result["audit_written"] is True
    receipt = apply_managed_runtime_config(
        environ=environ, settings_store=store, secrets_store=None
    )
    assert environ[ENV] == "12.5"
    assert PATH in receipt["settings_applied"]
    assert ENV in environ["CANONICAL_V2_MANAGED_ENV_APPLIED"]

    # …and the serving reader picks it up from the projected environment.
    os.environ[ENV] = environ[ENV]
    try:
        assert _reader()._vector_lane_outer_wait_seconds() == pytest.approx(12.5)
    finally:
        del os.environ[ENV]


def test_a_file_value_equal_to_the_default_is_not_projected(tmp_path: Path) -> None:
    """Saving 8 s is a no-op, not an environment override (the reader's own default)."""

    store = ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={})
    store.patch({"serving": {"vector_lane_timeout_seconds": 8.0}})
    environ: dict[str, str] = {}

    receipt = apply_managed_runtime_config(
        environ=environ, settings_store=store, secrets_store=None
    )

    assert ENV not in environ
    assert PATH not in receipt["settings_applied"]


def test_the_service_unit_environment_still_wins(tmp_path: Path) -> None:
    store = ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={})
    store.patch({"serving": {"vector_lane_timeout_seconds": 12.5}})
    environ = {ENV: "3.0"}

    receipt = apply_managed_runtime_config(
        environ=environ, settings_store=store, secrets_store=None
    )

    assert environ[ENV] == "3.0"
    assert ENV in receipt["settings_skipped_env"]


@pytest.mark.parametrize("value", [0, -1, 0.0, 121, 1000])
def test_out_of_bounds_values_are_rejected_with_the_field_named(
    tmp_path: Path, value: float
) -> None:
    store = ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={})

    with pytest.raises(ManagedSettingsError) as refusal:
        store.patch({"serving": {"vector_lane_timeout_seconds": value}})

    assert PATH in str(refusal.value)
    assert store.exists() is False


def test_the_page_payload_carries_the_row(tmp_path: Path) -> None:
    store = ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={})
    app.state.__dict__[_STORE_STATE] = store
    app.dependency_overrides[get_managed_settings_store] = lambda: store
    try:
        response = authorized_client(raise_server_exceptions=False).get(
            "/api/canonical-v2/admin/config"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    fields = {field["path"]: field for field in response.json()["fields"]}
    row = fields[PATH]

    assert row["kind"] == "float"
    assert row["group"] == "serving"
    assert row["editable"] is True
    assert row["env_var"] == ENV
    assert row["min"] == 0.1 and row["max"] == 120 and row["step"] == 0.1
    assert row["default"] == 8.0
    assert row["value"] == 8.0
    assert row["source"] == "default"


def test_the_row_survives_a_save_through_the_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={})
    app.state.__dict__[_STORE_STATE] = store
    app.dependency_overrides[get_managed_settings_store] = lambda: store
    try:
        client: TestClient = authorized_client(raise_server_exceptions=False)
        response = client.patch(
            "/api/canonical-v2/admin/config",
            json={"serving": {"vector_lane_timeout_seconds": 15}},
        )
        assert response.status_code == 200, response.text
        assert response.json()["changed"] == [PATH]
        document = store.effective()[0]
    finally:
        app.dependency_overrides.clear()

    assert document.serving.vector_lane_timeout_seconds == 15.0
    assert flatten_settings(document.model_dump(mode="json"))[PATH] == 15.0
