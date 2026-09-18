"""R1/R2 — one server-side field catalogue drives the `/config` payload.

Fixture source: the shipped `ManagedSettings` schema (the whitelist is derived
from the model itself, never re-typed here) plus the real FastAPI route graph
over a scratch settings file. No test touches the live state directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

from fastapi.testclient import TestClient
import pytest

from backend.api.canonical_v2_admin_config import get_managed_settings_store
from backend.main import app
from tests.conftest import authorized_client
from src.data_agents.canonical_v2.managed_config import (
    FIELD_CATALOG,
    FIELD_ENV_VARS,
    PAGE_READONLY_FIELDS,
    ManagedSettings,
    ManagedSettingsError,
    ManagedSettingsStore,
    ManagedSettingsUnsupportedError,
    flatten_settings,
)

_STORE_STATE = "canonical_v2_managed_settings_store"

_CARD_GROUPS = {"collection", "serving", "paths"}
_CONNECTION_GROUP = "endpoints"
_CONNECTION_KEYS = {"llm", "embedding", "rerank"}
_KINDS = {"bool", "int", "float", "text", "url"}

# Anchors, not a second catalogue: enough rows to prove the defaults come from
# `ManagedSettings()` rather than from a hand-written table.
_DEFAULT_ANCHORS = {
    "schema_version": 1,
    "collection.max_web_searches_per_run": 200,
    "collection.enabled.company": True,
    "extraction_endpoints.rerank_model": None,
    "paths.access_log_retention_days": 90,
    "serving.rerank_timeout_seconds": None,
}


@pytest.fixture
def store(tmp_path: Path) -> Iterator[ManagedSettingsStore]:
    scratch = tmp_path / "managed" / "settings.json"
    instance = ManagedSettingsStore(scratch, environ=dict(os.environ))
    had_prior = hasattr(app.state, _STORE_STATE)
    prior = getattr(app.state, _STORE_STATE, None)
    setattr(app.state, _STORE_STATE, instance)
    app.dependency_overrides[get_managed_settings_store] = lambda: instance
    try:
        yield instance
    finally:
        app.dependency_overrides.pop(get_managed_settings_store, None)
        if had_prior:
            setattr(app.state, _STORE_STATE, prior)
        elif hasattr(app.state, _STORE_STATE):
            delattr(app.state, _STORE_STATE)


def _client() -> TestClient:
    return authorized_client(raise_server_exceptions=False)


def _whitelist() -> set[str]:
    return set(flatten_settings(ManagedSettings().model_dump(mode="json")))


def test_every_whitelisted_path_has_a_catalogue_row() -> None:
    missing = sorted(_whitelist() - set(FIELD_CATALOG))

    assert not missing, f"whitelisted paths without a catalogue row: {missing}"


def test_no_catalogue_row_points_outside_the_whitelist() -> None:
    orphans = sorted(set(FIELD_CATALOG) - _whitelist())

    assert not orphans, f"catalogue rows that are not whitelisted: {orphans}"


def test_every_row_is_render_ready() -> None:
    for path, spec in FIELD_CATALOG.items():
        assert path == spec.path
        assert spec.label.strip(), path
        assert spec.kind in _KINDS, path
        assert spec.group in _CARD_GROUPS | {_CONNECTION_GROUP, "meta"}, path
        assert isinstance(spec.order, int) and spec.order >= 0, path
        assert spec.consumer.strip(), path


def test_bounded_kinds_carry_their_bounds() -> None:
    for path, spec in FIELD_CATALOG.items():
        if spec.kind in {"int", "float"}:
            assert spec.min is not None and spec.max is not None, path
            assert spec.min <= spec.max, path
            assert spec.step, path
        if spec.kind == "url":
            assert spec.min is None and spec.max is None, path


def test_orders_are_unique_within_a_group() -> None:
    seen: dict[str, list[int]] = {}
    for spec in FIELD_CATALOG.values():
        seen.setdefault(spec.group, []).append(spec.order)

    for group, orders in seen.items():
        assert len(orders) == len(set(orders)), group


def test_endpoint_rows_name_their_connection_and_others_do_not() -> None:
    for path, spec in FIELD_CATALOG.items():
        if spec.group == _CONNECTION_GROUP:
            assert spec.connection in _CONNECTION_KEYS, path
        else:
            assert spec.connection is None, path
            assert spec.test_arg is None, path


def test_each_endpoint_connection_has_one_endpoint_and_one_model_row() -> None:
    for connection in sorted(_CONNECTION_KEYS):
        rows = [
            spec for spec in FIELD_CATALOG.values() if spec.connection == connection
        ]

        assert sorted(spec.test_arg for spec in rows) == ["base_url", "model"], (
            connection
        )


def test_endpoint_rows_cover_the_managed_endpoint_fields() -> None:
    endpoint_paths = {
        path for path in _whitelist() if path.startswith("extraction_endpoints.")
    }

    assert endpoint_paths == {
        path for path, spec in FIELD_CATALOG.items() if spec.group == _CONNECTION_GROUP
    }


def test_row_defaults_come_from_the_schema() -> None:
    for path, expected in _DEFAULT_ANCHORS.items():
        assert FIELD_CATALOG[path].default == expected, path


def test_effective_field_payload_carries_the_catalogue_columns(
    store: ManagedSettingsStore,
) -> None:
    response = _client().get("/api/canonical-v2/admin/config")

    assert response.status_code == 200
    fields = {field["path"]: field for field in response.json()["fields"]}
    assert set(fields) == _whitelist()
    for path, field in fields.items():
        spec = FIELD_CATALOG[path]
        assert field["label"] == spec.label
        assert field["kind"] == spec.kind
        assert field["group"] == spec.group
        assert field["order"] == spec.order
        assert field["consumer"] == spec.consumer
        assert field["connection"] == spec.connection
        assert field["test_arg"] == spec.test_arg
        assert field["min"] == spec.min
        assert field["max"] == spec.max
        assert field["step"] == spec.step
        assert field["default"] == spec.default


def test_payload_stays_free_of_credential_material(
    store: ManagedSettingsStore,
) -> None:
    import json

    payload: dict[str, Any] = _client().get("/api/canonical-v2/admin/config").json()

    assert "api_key" not in json.dumps(payload).casefold()


# -- I4: the chat profile becomes a catalogue field --------------------------


def test_chat_profile_row_travels_the_save_and_boot_path(tmp_path: Path) -> None:
    """One text row, projected as `CHAT_LLM_PROFILE`, editable from the page."""

    spec = FIELD_CATALOG["serving.chat_llm_profile"]

    assert spec.path == "serving.chat_llm_profile"
    assert spec.kind == "text"
    assert spec.group == "serving"
    assert spec.label.strip()
    assert spec.consumer.strip()
    assert spec.connection is None
    assert spec.test_arg is None
    assert FIELD_ENV_VARS["serving.chat_llm_profile"] == "CHAT_LLM_PROFILE"

    store = ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={})
    _, fields = store.effective()
    row = next(field for field in fields if field.path == "serving.chat_llm_profile")

    assert row.env_var == "CHAT_LLM_PROFILE"
    assert row.editable is True
    assert row.value is None
    assert row.source == "default"


def test_chat_profile_rejects_an_unknown_name_on_save(tmp_path: Path) -> None:
    """A typo must fail loudly instead of silently falling back at runtime."""

    store = ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={})

    with pytest.raises(ManagedSettingsError) as refusal:
        store.patch({"serving": {"chat_llm_profile": "no-such-profile"}})

    assert "no-such-profile" in str(refusal.value)
    assert "deepseekv4flash" in str(refusal.value), "the refusal lists the choices"
    assert store.exists() is False

    for value in ("deepseekv4flash", "deepseek-v4-pro", "deepseek"):
        result = store.patch({"serving": {"chat_llm_profile": value}})
        assert result["changed"] == ["serving.chat_llm_profile"], value

    document, _ = store.effective()
    assert document.serving.chat_llm_profile == "deepseek"


# -- I5: the frozen embedding rows are display-only --------------------------


def test_the_frozen_embedding_rows_are_display_only(tmp_path: Path) -> None:
    """The serving index freezes the embedding endpoint; the page only shows it."""

    paths = (
        "extraction_endpoints.embedding_base_url",
        "extraction_endpoints.embedding_model",
    )
    for path in paths:
        reason = PAGE_READONLY_FIELDS[path]
        assert reason.strip(), path
        assert "冻结" in reason, path

    store = ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ={})
    _, fields = store.effective()
    rows = {field.path: field for field in fields}
    for path in paths:
        assert rows[path].editable is False, path
        assert rows[path].readonly_reason, path

    with pytest.raises(ManagedSettingsUnsupportedError) as refusal:
        store.patch(
            {
                "extraction_endpoints": {
                    "embedding_base_url": "http://127.0.0.1:18005/v1",
                    "embedding_model": "Qwen/Qwen3-Embedding-8B",
                }
            }
        )

    assert "display-only" in str(refusal.value)
    assert "冻结" in str(refusal.value)
    assert store.exists() is False
