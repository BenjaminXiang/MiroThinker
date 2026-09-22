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

    material, origin = store.resolve(
        bocha, environ={"BOCHA_API_KEY": "env-fake-key-5555"}
    )
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


def test_credentials_target_the_variables_the_runtime_reads(tmp_path: Path) -> None:
    """A page-saved value must land where the serving process looks for it."""

    from src.data_agents.canonical_v2.managed_secrets import SECRET_SPECS

    by_field = {spec.field: spec for spec in SECRET_SPECS}

    # knowledge_build_isolated.py:6570 -> providers/local_api_key.py:8-11
    assert by_field["embedding.api_key"].env_var_for({}) == "SGLANG_API_KEY"
    assert by_field["embedding.api_key"].extra_env_names == (
        "API_KEY",
        "OPENAI_API_KEY",
    )
    # canonical_v2/rerank_client.py:33-38
    assert by_field["rerank.api_key"].env_var_for({}) == "CANONICAL_V2_RERANK_API_KEY"
    # professor/llm_profiles.py:273 + knowledge_serving_isolated.py:2087
    assert (
        by_field["llm.api_key"].env_var_for({"CHAT_LLM_PROFILE": "deepseekv4flash"})
        == "DEEPSEEK_API_KEY"
    )
    assert (
        by_field["llm.api_key"].env_var_for({"CHAT_LLM_PROFILE": "gemma4"}) == "API_KEY"
    )


def test_llm_credential_projection_follows_the_chat_profile(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.patch({"llm.api_key": _FAKE_BOCHA})

    default_target: dict[str, str] = {}
    store.apply_to_environ(default_target)
    deepseek_target: dict[str, str] = {"CHAT_LLM_PROFILE": "deepseekv4flash"}
    store.apply_to_environ(deepseek_target)

    assert default_target["API_KEY"] == _FAKE_BOCHA  # gemma4 default profile
    assert deepseek_target["DEEPSEEK_API_KEY"] == _FAKE_BOCHA


def test_the_embedding_key_targets_both_authority_slots() -> None:
    """One page field, the two variables this fleet's embedding lines read.

    ``SGLANG_API_KEY`` is what the recorded (self-hosted) authority reads through
    ``load_local_api_key()``; ``CANONICAL_V2_EMBEDDING_API_KEY`` is the slot the
    candidate (gateway) bundle declares as its ``api_key_source``. The page cannot
    know which line a site runs, and the delivery promise is one key, so the field
    fills both.
    """

    spec = next(spec for spec in SECRET_SPECS if spec.field == "embedding.api_key")

    assert spec.env_var_for({}) == "SGLANG_API_KEY"
    assert spec.mirror_env_vars == ("CANONICAL_V2_EMBEDDING_API_KEY",)
    assert spec.extra_env_names == ("API_KEY", "OPENAI_API_KEY")


def test_projection_fills_the_mirror_slot_under_the_same_rules(tmp_path: Path) -> None:
    fake_key = "sk-fake-embedding-4444-5555-6e1b"
    store = _store(tmp_path)
    store.patch({"embedding.api_key": fake_key})

    target: dict[str, str] = {}
    receipt = store.apply_to_environ(target)

    assert target["SGLANG_API_KEY"] == fake_key
    assert target["CANONICAL_V2_EMBEDDING_API_KEY"] == fake_key
    assert receipt["applied"] == ("SGLANG_API_KEY", "CANONICAL_V2_EMBEDDING_API_KEY")
    # An environment value wins in either slot, so the service unit stays the
    # authority; the primary keeps its enumerated position in the receipt.
    pinned: dict[str, str] = {"CANONICAL_V2_EMBEDDING_API_KEY": "unit-9999"}
    second = store.apply_to_environ(pinned)
    assert pinned["SGLANG_API_KEY"] == fake_key
    assert pinned["CANONICAL_V2_EMBEDDING_API_KEY"] == "unit-9999"
    assert second["skipped_env"] == ("CANONICAL_V2_EMBEDDING_API_KEY",)
    assert fake_key not in json.dumps(second)
