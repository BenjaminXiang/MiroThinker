from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.data_agents.canonical_v2.managed_config import (
    APPLIED_ENV_VAR,
    PAGE_READONLY_FIELDS,
    ManagedSettings,
    ManagedSettingsError,
    ManagedSettingsStore,
    ManagedSettingsUnsupportedError,
)


def _store(tmp_path: Path, **environ: str) -> ManagedSettingsStore:
    return ManagedSettingsStore(tmp_path / "managed" / "settings.json", environ=environ)


def test_defaults_when_file_missing(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert store.exists() is False
    document, fields = store.effective()

    assert document.schema_version == 1
    assert document.collection.enabled == {
        "company": True,
        "paper": True,
        "patent": True,
        "professor": True,
    }
    assert document.paths.access_log_retention_days == 90
    assert all(field.source == "default" for field in fields)
    assert store.raw() == ManagedSettings().model_dump(mode="json")


def test_partial_file_fills_missing_keys_with_defaults(tmp_path: Path) -> None:
    path = tmp_path / "managed" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"collection": {"max_llm_calls_per_run": 40}}))

    store = ManagedSettingsStore(path)
    document, _ = store.effective()

    assert document.collection.max_llm_calls_per_run == 40
    assert document.collection.max_web_searches_per_run == 200
    assert document.paths.access_log_retention_days == 90


def test_corrupt_file_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "managed" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json")

    document, fields = ManagedSettingsStore(path).effective()

    assert document == ManagedSettings()
    assert all(field.source == "default" for field in fields)


@pytest.mark.parametrize(
    "payload",
    [
        {"nope": 1},
        {"collection": {"max_web_searches_per_run": 1, "unknown_toggle": True}},
        {"paths": {"serving_pack_dir": "/var/tmp/x", "index_root": "/var/tmp/y"}},
    ],
)
def test_unknown_and_secret_keys_are_rejected(tmp_path: Path, payload: dict) -> None:
    store = _store(tmp_path)
    store.patch({"collection": {"max_llm_calls_per_run": 11}}, operator="seed")
    before = store.path.read_bytes()
    audit_before = store.audit_records()

    with pytest.raises(ManagedSettingsUnsupportedError):
        store.patch(payload)

    assert store.path.read_bytes() == before
    assert store.audit_records() == audit_before


@pytest.mark.parametrize(
    "payload",
    [
        {"collection": {"api_key": "sk-secret-value"}},
        {"extraction_endpoints": {"llm_base_url": "https://x", "token": "abc"}},
        {"paths": {"database_url": "postgresql://u:p@host/db"}},
        {"collection": {"enabled": {"company": True}}, "credential_file": "/tmp/k"},
    ],
)
def test_secret_shaped_keys_are_rejected(tmp_path: Path, payload: dict) -> None:
    store = _store(tmp_path)

    with pytest.raises(ManagedSettingsUnsupportedError):
        store.patch(payload)

    assert store.exists() is False
    assert store.audit_records() == ()


def test_secret_shaped_key_in_a_preexisting_file_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "managed" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"collection": {"api_key": "leaked"}}))

    document, _ = ManagedSettingsStore(path).effective()

    assert document == ManagedSettings()
    assert "leaked" not in json.dumps(document.model_dump(mode="json"))


def test_atomic_write_leaves_no_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    replacements: list[tuple[str, str]] = []
    real_replace = os.replace

    def _observed_replace(source, destination, **kwargs):  # noqa: ANN001
        replacements.append((str(source), str(destination)))
        return real_replace(source, destination, **kwargs)

    monkeypatch.setattr(os, "replace", _observed_replace)
    store.patch({"paths": {"access_log_retention_days": 30}}, operator="alice")

    assert len(replacements) == 1
    temp_name, destination = replacements[0]
    assert destination == str(store.path)
    assert Path(temp_name).parent == store.path.parent
    assert Path(temp_name).name.startswith(".settings-")
    assert not Path(temp_name).exists()
    assert sorted(item.name for item in store.path.parent.iterdir()) == [
        "audit.jsonl",
        "settings.json",
    ]
    assert (
        json.loads(store.path.read_text())["paths"]["access_log_retention_days"] == 30
    )


def test_audit_records_before_after_and_operator(tmp_path: Path) -> None:
    store = _store(tmp_path)

    result = store.patch(
        {
            "collection": {"max_llm_calls_per_run": 750},
            "paths": {"access_log_retention_days": 120},
        },
        operator="operator-zhang",
    )

    assert result["changed"] == [
        "collection.max_llm_calls_per_run",
        "paths.access_log_retention_days",
    ]
    assert result["audit_written"] is True
    records = store.audit_records()
    assert len(records) == 1
    record = records[0]
    assert record["action"] == "patch"
    assert record["operator"] == "operator-zhang"
    assert record["before"]["paths"]["access_log_retention_days"] == 90
    assert record["after"]["paths"]["access_log_retention_days"] == 120
    assert record["changed"] == result["changed"]
    assert record["at"].endswith("+00:00")


def test_audit_is_append_only(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.patch({"paths": {"access_log_retention_days": 91}}, operator="a")
    store.patch({"paths": {"access_log_retention_days": 92}}, operator="b")

    records = store.audit_records()

    assert [record["operator"] for record in records] == ["a", "b"]
    assert len(store.audit_path.read_text().splitlines()) == 2


def test_no_op_patch_writes_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.patch({"paths": {"access_log_retention_days": 45}}, operator="a")

    result = store.patch({"paths": {"access_log_retention_days": 45}}, operator="a")

    assert result["changed"] == []
    assert result["audit_written"] is False
    assert len(store.audit_records()) == 1


def test_env_overrides_file(tmp_path: Path) -> None:
    store = _store(
        tmp_path,
        WEB_LANE_DAILY_QUOTA="99",
        LOCAL_LLM_MODEL="env-model",
        LOCAL_LLM_BASE_URL="https://env.example/v1",
    )
    store.patch(
        {
            "collection": {"max_web_searches_per_run": 7, "max_llm_calls_per_run": 8},
            "extraction_endpoints": {
                "llm_model": "file-model",
                "llm_base_url": "https://file.example/v1",
            },
        },
        operator="a",
    )

    document, fields = store.effective()
    by_path = {field.path: field for field in fields}

    assert document.collection.max_web_searches_per_run == 99
    assert by_path["collection.max_web_searches_per_run"].source == "env"
    assert by_path["collection.max_web_searches_per_run"].editable is False
    assert document.collection.max_llm_calls_per_run == 8
    assert by_path["collection.max_llm_calls_per_run"].source == "file"
    assert by_path["collection.max_llm_calls_per_run"].editable is True
    assert document.extraction_endpoints.llm_model == "env-model"
    assert by_path["extraction_endpoints.llm_model"].source == "env"
    assert (
        by_path["extraction_endpoints.llm_base_url"].value == "https://env.example/v1"
    )


def test_env_value_of_the_wrong_type_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path, WEB_LANE_DAILY_QUOTA="not-a-number")

    with pytest.raises(ManagedSettingsError):
        store.effective()


# --- our own projection vs an external pin (the saved field stays editable) --


def _row(fields, path: str):  # noqa: ANN001, ANN202 - one-liner test helper
    return {field.path: field for field in fields}[path]


def test_a_projected_env_variable_is_reported_as_the_file_and_stays_editable(
    tmp_path: Path,
) -> None:
    """`apply_managed_runtime_config` writes the file's values into the env at boot.

    The value still resolves from the environment (unchanged), but the field's
    origin is the managed file — the format the page may keep saving.
    """

    store = _store(
        tmp_path,
        WEB_LANE_DAILY_QUOTA="99",
        **{APPLIED_ENV_VAR: "WEB_LANE_DAILY_QUOTA"},
    )
    store.patch({"collection": {"max_web_searches_per_run": 7}}, operator="ops")

    document, fields = store.effective()
    row = _row(fields, "collection.max_web_searches_per_run")

    assert document.collection.max_web_searches_per_run == 99
    assert row.value == 99
    assert row.source == "file"
    assert row.editable is True
    assert row.env_var == "WEB_LANE_DAILY_QUOTA"
    assert row.readonly_reason is None


def test_an_env_variable_the_boot_did_not_set_is_an_external_pin(
    tmp_path: Path,
) -> None:
    """The systemd/serve-command environment stays read-only, as it always was."""

    store = _store(
        tmp_path,
        WEB_LANE_DAILY_QUOTA="99",
        CANONICAL_V2_SERVING_FULL_VERIFY="1",
    )
    store.patch({"collection": {"max_web_searches_per_run": 7}}, operator="ops")

    document, fields = store.effective()

    assert document.collection.max_web_searches_per_run == 99
    row = _row(fields, "collection.max_web_searches_per_run")
    assert row.value == 99
    assert row.source == "env"
    assert row.editable is False
    pinned = _row(fields, "serving.full_verify")
    assert pinned.source == "env"
    assert pinned.editable is False
    assert pinned.readonly_reason is None


def test_an_unset_env_variable_keeps_file_and_default_sources(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path, **{APPLIED_ENV_VAR: "WEB_LANE_DAILY_QUOTA"})
    store.patch({"collection": {"max_web_searches_per_run": 7}}, operator="ops")

    document, fields = store.effective()

    assert document.collection.max_web_searches_per_run == 7
    file_row = _row(fields, "collection.max_web_searches_per_run")
    assert file_row.source == "file"
    assert file_row.editable is True
    default_row = _row(fields, "collection.max_llm_calls_per_run")
    assert default_row.source == "default"
    assert default_row.editable is True


def test_a_projected_page_readonly_field_keeps_its_reason(tmp_path: Path) -> None:
    path = tmp_path / "managed" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"serving": {"full_verify": True}}))
    store = ManagedSettingsStore(
        path,
        environ={
            "CANONICAL_V2_SERVING_FULL_VERIFY": "1",
            APPLIED_ENV_VAR: "CANONICAL_V2_SERVING_FULL_VERIFY",
        },
    )

    document, fields = store.effective()
    row = _row(fields, "serving.full_verify")

    assert document.serving.full_verify is True
    assert row.source == "file"
    assert row.editable is False
    assert row.readonly_reason == PAGE_READONLY_FIELDS["serving.full_verify"]


def test_validation_failures_are_bounded_and_do_not_touch_the_file(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.patch({"collection": {"window_start_hour_utc": 20}}, operator="a")
    before = store.path.read_bytes()

    with pytest.raises(ManagedSettingsError):
        store.patch({"collection": {"window_end_hour_utc": 18}})

    assert store.path.read_bytes() == before
    assert len(store.audit_records()) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"extraction_endpoints": {"llm_base_url": "not-a-url"}},
        {"extraction_endpoints": {"llm_base_url": "https://user:pw@example.com/v1"}},
        {"paths": {"serving_pack_dir": "relative/path"}},
        {"collection": {"max_web_searches_per_run": -1}},
        {"paths": {"access_log_retention_days": 0}},
    ],
)
def test_ill_typed_values_are_rejected(tmp_path: Path, payload: dict) -> None:
    store = _store(tmp_path)

    with pytest.raises(ManagedSettingsError):
        store.patch(payload)

    assert store.exists() is False


def test_restart_reads_the_patched_value(tmp_path: Path) -> None:
    first = _store(tmp_path)
    first.patch({"collection": {"max_llm_calls_per_run": 321}}, operator="a")

    second = ManagedSettingsStore(first.path)

    document, _ = second.effective()
    assert document.collection.max_llm_calls_per_run == 321


def test_settings_path_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from src.data_agents.canonical_v2.managed_config import default_settings_path

    target = tmp_path / "elsewhere" / "settings.json"
    monkeypatch.setenv("CANONICAL_V2_MANAGED_SETTINGS", str(target))

    assert default_settings_path() == target


def test_committed_template_matches_the_schema() -> None:
    root = Path(__file__).resolve().parents[3]
    template = root / "config" / "managed" / "settings.example.json"

    payload = json.loads(template.read_text(encoding="utf-8"))
    document = ManagedSettings.model_validate(payload)

    assert document.schema_version == 1


# --- three-state saves (redesign-admin-config-page R3/R4) --------------------


def test_null_clears_a_bool_override_back_to_the_default(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.patch({"serving": {"web_topical_floor": True}}, operator="ops")
    assert json.loads(store.path.read_text(encoding="utf-8")) == {
        "serving": {"web_topical_floor": True}
    }

    result = store.patch({"serving": {"web_topical_floor": None}}, operator="ops")

    assert result["changed"] == ["serving.web_topical_floor"]
    assert result["audit_written"] is True
    document, fields = store.effective()
    by_path = {field.path: field for field in fields}
    assert document.serving.web_topical_floor is None
    assert by_path["serving.web_topical_floor"].source == "default"
    assert json.loads(store.path.read_text(encoding="utf-8")) == {}
    assert store.audit_records()[-1]["changed"] == ["serving.web_topical_floor"]


def test_null_clears_text_and_non_nullable_numeric_overrides(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.patch(
        {
            "extraction_endpoints": {"llm_base_url": "https://llm.example/v1"},
            "paths": {"access_log_retention_days": 30},
        },
        operator="ops",
    )

    result = store.patch(
        {
            "extraction_endpoints": {"llm_base_url": None},
            "paths": {"access_log_retention_days": None},
        },
        operator="ops",
    )

    assert result["changed"] == [
        "extraction_endpoints.llm_base_url",
        "paths.access_log_retention_days",
    ]
    document, fields = store.effective()
    by_path = {field.path: field for field in fields}
    assert document.extraction_endpoints.llm_base_url is None
    assert document.paths.access_log_retention_days == 90
    assert by_path["extraction_endpoints.llm_base_url"].source == "default"
    assert by_path["paths.access_log_retention_days"].source == "default"
    assert json.loads(store.path.read_text(encoding="utf-8")) == {}


def test_null_clears_one_domain_toggle_and_keeps_the_others(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.patch(
        {"collection": {"enabled": {"company": False, "paper": False}}}, operator="ops"
    )

    store.patch({"collection": {"enabled": {"company": None}}}, operator="ops")

    document, fields = store.effective()
    by_path = {field.path: field for field in fields}
    assert document.collection.enabled == {
        "company": True,
        "paper": False,
        "patent": True,
        "professor": True,
    }
    assert json.loads(store.path.read_text(encoding="utf-8")) == {
        "collection": {"enabled": {"paper": False}}
    }
    assert by_path["collection.enabled.company"].source == "default"
    assert by_path["collection.enabled.paper"].source == "file"


def test_clearing_a_field_that_has_no_override_is_a_no_op(tmp_path: Path) -> None:
    store = _store(tmp_path)

    result = store.patch({"serving": {"web_topical_floor": None}}, operator="ops")

    assert result["changed"] == []
    assert result["audit_written"] is False
    assert store.exists() is False
    assert store.audit_records() == ()


def test_diff_patch_writes_only_the_changed_keys(tmp_path: Path) -> None:
    store = _store(tmp_path)

    store.patch(
        {
            "collection": {"max_llm_calls_per_run": 750},
            "paths": {"access_log_retention_days": 30},
        },
        operator="ops",
    )

    assert json.loads(store.path.read_text(encoding="utf-8")) == {
        "collection": {"max_llm_calls_per_run": 750},
        "paths": {"access_log_retention_days": 30},
    }
    # The resolved view still fills in every untouched default.
    assert store.raw()["collection"]["max_web_searches_per_run"] == 200
    assert store.raw()["serving"]["full_verify"] is None

    store.patch({"serving": {"rerank_max_documents": 40}}, operator="ops")

    assert json.loads(store.path.read_text(encoding="utf-8")) == {
        "collection": {"max_llm_calls_per_run": 750},
        "paths": {"access_log_retention_days": 30},
        "serving": {"rerank_max_documents": 40},
    }


def test_resending_the_same_patch_writes_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    body = {
        "collection": {"max_llm_calls_per_run": 750},
        "paths": {"access_log_retention_days": 30},
    }
    store.patch(body, operator="ops")
    before = store.path.read_bytes()
    audit_before = store.audit_records()

    result = store.patch(body, operator="ops")

    assert result["changed"] == []
    assert result["audit_written"] is False
    assert store.path.read_bytes() == before
    assert store.audit_records() == audit_before


def test_patch_preserves_an_operators_hand_written_file(tmp_path: Path) -> None:
    path = tmp_path / "managed" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"paths": {"serving_pack_dir": "/srv/pack"}}))

    ManagedSettingsStore(path).patch(
        {"paths": {"access_log_retention_days": 30}}, operator="ops"
    )

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "paths": {"serving_pack_dir": "/srv/pack", "access_log_retention_days": 30}
    }


def test_a_corrupt_file_is_replaced_by_the_patch_alone(tmp_path: Path) -> None:
    path = tmp_path / "managed" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json")

    ManagedSettingsStore(path).patch(
        {"paths": {"access_log_retention_days": 30}}, operator="ops"
    )

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "paths": {"access_log_retention_days": 30}
    }
