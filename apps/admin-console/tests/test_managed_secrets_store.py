from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.data_agents.canonical_v2.managed_secrets import (
    SECRET_SPECS,
    ManagedSecretsError,
    ManagedSecretsStore,
    ManagedSecretsUnsupportedError,
    mask_secret,
    suffix4,
)

# Every credential in this file is a locally generated fake. No fixture ever
# carries a real key, and no test reads one from the environment.
_FAKE_BOCHA = "sk-fake-bocha-0000-1111-4f2a"
_FAKE_SERPER = "fake-serper-2222-3333-9c7d"


def _store(tmp_path: Path, **environ: str) -> ManagedSecretsStore:
    return ManagedSecretsStore(
        tmp_path / "managed" / "secrets.json",
        environ=environ,
        key_file_roots=(),
    )


def test_mask_reveals_at_most_three_leading_and_four_trailing_characters() -> None:
    assert mask_secret("sk-fake-bocha-0000-1111-4f2a") == "sk-…4f2a"
    assert len(mask_secret("sk-fake-bocha-0000-1111-4f2a")) <= 12
    assert mask_secret("abcdefghijklmnop") == "abc…mnop"
    # Short material degrades further: never the whole value.
    assert mask_secret("abcdefghij") == "•••ghij"
    assert mask_secret("abc") == "•••"
    assert mask_secret("") == ""


def test_missing_file_is_not_configured_and_never_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert store.exists() is False
    assert store.raw() == {}
    states = store.describe(environ={})
    assert [state.field for state in states] == [spec.field for spec in SECRET_SPECS]
    assert all(state.configured is False for state in states)
    assert all(state.mask is None for state in states)


def test_atomic_write_is_0600_and_leaves_no_temp_files(tmp_path: Path) -> None:
    store = _store(tmp_path)
    path = store.path

    result = store.patch({"bocha.api_key": _FAKE_BOCHA}, operator="ops-1")

    assert result["changed"] == ["bocha.api_key"]
    assert path.is_file()
    assert (path.stat().st_mode & 0o777) == 0o600
    assert store.permissions_ok() is True
    assert [item.name for item in path.parent.iterdir() if item.suffix == ".tmp"] == []
    assert json.loads(path.read_text())["secrets"]["bocha.api_key"] == _FAKE_BOCHA


def test_overwrite_and_clear_paths(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.patch({"bocha.api_key": _FAKE_BOCHA})

    overwritten = store.patch({"bocha.api_key": _FAKE_SERPER})

    assert overwritten["changed"] == ["bocha.api_key"]
    assert store.raw()["bocha.api_key"] == _FAKE_SERPER
    assert suffix4(store.raw()["bocha.api_key"]) == "9c7d"

    cleared = store.patch({"bocha.api_key": None})

    assert cleared["changed"] == ["bocha.api_key"]
    assert store.raw() == {}
    assert store.path.is_file()  # the file survives; the field is gone


def test_audit_records_never_contain_plaintext(tmp_path: Path) -> None:
    store = _store(tmp_path)

    store.patch({"bocha.api_key": _FAKE_BOCHA}, operator="ops-2")
    store.patch({"bocha.api_key": None}, operator="ops-2")

    raw_audit = store.audit_path.read_text(encoding="utf-8")
    assert _FAKE_BOCHA not in raw_audit
    records = store.audit_records()
    assert [record["operator"] for record in records] == ["ops-2", "ops-2"]
    assert [change["action"] for record in records for change in record["changes"]] == [
        "set",
        "clear",
    ]
    assert records[0]["changes"][0]["suffix4"] == "4f2a"


def test_whitelist_rejects_unknown_and_credential_shaped_fields(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(ManagedSecretsUnsupportedError):
        store.patch({"milvus.uri": "x"})
    with pytest.raises(ManagedSecretsError):
        store.patch({"bocha.api_key": "line1\nline2"})
    with pytest.raises(ManagedSecretsError):
        store.patch({})
    # A blank value is a clear request, not an error: nothing stored, nothing written.
    assert store.patch({"bocha.api_key": "   "}) == {
        "changed": [],
        "audit_written": False,
    }
    assert store.exists() is False


def test_resolution_prefers_env_then_managed_file(tmp_path: Path) -> None:
    store = _store(
        tmp_path, BOCHA_API_KEY="env-fake-key-5555", CANONICAL_V2_MANAGED_ENV_APPLIED=""
    )
    store.patch({"bocha.api_key": _FAKE_BOCHA})
    bocha = next(spec for spec in SECRET_SPECS if spec.field == "bocha.api_key")

    material, origin = store.resolve(bocha, environ={"BOCHA_API_KEY": "env-fake-key-5555"})
    assert material == "env-fake-key-5555"
    assert origin == "env:BOCHA_API_KEY"

    material, origin = store.resolve(bocha, environ={})
    assert material == _FAKE_BOCHA
    assert origin == "managed-file"


def test_apply_to_environ_never_overrides_an_existing_variable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.patch({"bocha.api_key": _FAKE_BOCHA, "serper.api_key": _FAKE_SERPER})

    target = {"SERPER_API_KEY": "env-wins-7777"}
    receipt = store.apply_to_environ(target)

    assert target["BOCHA_API_KEY"] == _FAKE_BOCHA
    assert target["SERPER_API_KEY"] == "env-wins-7777"
    assert receipt["applied"] == ("BOCHA_API_KEY",)
    assert receipt["skipped_env"] == ("SERPER_API_KEY",)
    # The receipt carries names only.
    assert _FAKE_BOCHA not in json.dumps(receipt)


def test_legacy_key_file_is_reported_as_an_origin(tmp_path: Path) -> None:
    key_root = tmp_path / "repo"
    key_root.mkdir()
    (key_root / ".bocha_api_key").write_text("legacy-file-fake-8888\n")
    store = ManagedSecretsStore(
        tmp_path / "managed" / "secrets.json",
        environ={},
        key_file_roots=(key_root,),
    )
    bocha = next(spec for spec in SECRET_SPECS if spec.field == "bocha.api_key")

    material, origin = store.resolve(bocha, environ={})

    assert material == "legacy-file-fake-8888"
    assert origin == "legacy-file:.bocha_api_key"
    # The managed store never writes to the legacy file.
    assert not store.exists()


def test_corrupt_file_is_not_configured(tmp_path: Path) -> None:
    path = tmp_path / "managed" / "secrets.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")

    store = ManagedSecretsStore(path, environ={}, key_file_roots=())

    assert store.raw() == {}
    assert all(state.configured is False for state in store.describe(environ={}))


def test_describe_marks_adopted_values(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.patch({"bocha.api_key": _FAKE_BOCHA})
    environ = dict(os.environ)
    environ.pop("BOCHA_API_KEY", None)
    receipt = store.apply_to_environ(environ)

    states = store.describe(environ=environ, applied_env=frozenset(receipt["applied"]))
    bocha = next(state for state in states if state.field == "bocha.api_key")

    assert bocha.origin == "managed-file"
    assert bocha.applied_to_process_env is True
    assert _FAKE_BOCHA not in json.dumps([state.as_dict() for state in states])
