from __future__ import annotations

import json
from pathlib import Path

from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore
from src.data_agents.canonical_v2.managed_runtime import (
    APPLIED_ENV_VAR,
    applied_env_names,
    apply_managed_runtime_config,
)
from src.data_agents.canonical_v2.managed_secrets import ManagedSecretsStore

_FAKE_KEY = "sk-fake-runtime-0000-1111-9a7b"


def _stores(tmp_path: Path) -> tuple[ManagedSettingsStore, ManagedSecretsStore]:
    settings = ManagedSettingsStore(
        tmp_path / "managed" / "settings.json", environ={}, repo_root=tmp_path
    )
    secrets = ManagedSecretsStore(
        tmp_path / "managed" / "secrets.json",
        environ={},
        key_file_roots=(),
        repo_root=tmp_path,
    )
    return settings, secrets


def test_bootstrap_projects_file_owned_values_and_never_overrides_env(
    tmp_path: Path,
) -> None:
    settings, secrets = _stores(tmp_path)
    settings.patch({"serving": {"web_topical_floor": False}}, operator="ops")
    settings.patch({"serving": {"rerank_timeout_seconds": 2.5}}, operator="ops")
    secrets.patch({"bocha.api_key": _FAKE_KEY}, operator="ops")
    environ = {"CANONICAL_V2_RERANK_TIMEOUT_SECONDS": "9.0"}

    receipt = apply_managed_runtime_config(
        environ=environ, settings_store=settings, secrets_store=secrets
    )

    # Set by the file, absent from the environment → projected.
    assert environ["CANONICAL_V2_WEB_TOPICAL_FLOOR"] == "0"
    assert environ["BOCHA_API_KEY"] == _FAKE_KEY
    # Already in the environment → the environment stays the winner.
    assert environ["CANONICAL_V2_RERANK_TIMEOUT_SECONDS"] == "9.0"
    assert "serving.rerank_timeout_seconds" not in receipt["settings_applied"]
    assert "CANONICAL_V2_RERANK_TIMEOUT_SECONDS" in receipt["settings_skipped_env"]
    assert receipt["settings_applied"] == ("serving.web_topical_floor",)
    assert receipt["secrets_applied_env"] == ("BOCHA_API_KEY",)
    assert environ[APPLIED_ENV_VAR] == "BOCHA_API_KEY,CANONICAL_V2_WEB_TOPICAL_FLOOR"
    assert applied_env_names(environ) == frozenset(
        {"BOCHA_API_KEY", "CANONICAL_V2_WEB_TOPICAL_FLOOR"}
    )


def test_bootstrap_receipt_carries_no_values(tmp_path: Path) -> None:
    settings, secrets = _stores(tmp_path)
    secrets.patch({"serper.api_key": _FAKE_KEY}, operator="ops")
    environ: dict[str, str] = {}

    receipt = apply_managed_runtime_config(
        environ=environ, settings_store=settings, secrets_store=secrets
    )

    assert _FAKE_KEY not in json.dumps(receipt)
    assert _FAKE_KEY not in environ.get(APPLIED_ENV_VAR, "")


def test_bootstrap_never_projects_defaults(tmp_path: Path) -> None:
    settings, secrets = _stores(tmp_path)
    environ: dict[str, str] = {}

    apply_managed_runtime_config(
        environ=environ, settings_store=settings, secrets_store=secrets
    )

    # Nothing was written to a file, so nothing may be projected: a shipped
    # default must never masquerade as an operator decision.
    assert environ == {}

    # A page save writes the complete document (defaults included); only the
    # field the operator actually changed may reach the environment.
    settings.patch({"collection": {"max_llm_calls_per_run": 640}})
    environ = {}

    apply_managed_runtime_config(
        environ=environ, settings_store=settings, secrets_store=secrets
    )

    assert environ == {}


def test_bootstrap_is_fail_open_for_missing_or_corrupt_files(tmp_path: Path) -> None:
    settings, secrets = _stores(tmp_path)
    secrets.path.parent.mkdir(parents=True, exist_ok=True)
    secrets.path.write_text("{not json")
    environ: dict[str, str] = {"UNRELATED": "1"}

    receipt = apply_managed_runtime_config(
        environ=environ, settings_store=settings, secrets_store=secrets
    )

    assert environ == {"UNRELATED": "1"}
    assert receipt["secrets_applied_env"] == ()
    assert receipt["settings_applied"] == ()


def test_bootstrap_is_the_only_reader_no_hot_path(tmp_path: Path) -> None:
    """A stored secret is invisible until the process reads it at startup."""

    settings, secrets = _stores(tmp_path)
    environ: dict[str, str] = {}
    secrets.patch({"llm.api_key": _FAKE_KEY}, operator="ops")

    # Before the bootstrap runs, the process environment has nothing.
    assert "API_KEY" not in environ

    apply_managed_runtime_config(
        environ=environ, settings_store=settings, secrets_store=secrets
    )

    # The LLM credential goes to the variable the ACTIVE chat profile reads
    # (professor/llm_profiles.py:273): API_KEY for the default gemma4 profile.
    assert environ["API_KEY"] == _FAKE_KEY

    # With the live profile the same stored value targets DEEPSEEK_API_KEY.
    live = {"CHAT_LLM_PROFILE": "deepseekv4flash"}
    apply_managed_runtime_config(
        environ=live, settings_store=settings, secrets_store=secrets
    )

    assert live["DEEPSEEK_API_KEY"] == _FAKE_KEY
    assert "API_KEY" not in live


def test_bootstrap_projects_the_chat_profile_choice(tmp_path: Path) -> None:
    """I4: the profile the page saves reaches `CHAT_LLM_PROFILE` at boot."""

    settings, secrets = _stores(tmp_path)
    settings.patch({"serving": {"chat_llm_profile": "gemma4"}}, operator="ops")
    environ: dict[str, str] = {}

    receipt = apply_managed_runtime_config(
        environ=environ, settings_store=settings, secrets_store=secrets
    )

    assert environ["CHAT_LLM_PROFILE"] == "gemma4"
    assert receipt["settings_applied"] == ("serving.chat_llm_profile",)

    # The service unit stays the authority: an existing value is never replaced.
    live = {"CHAT_LLM_PROFILE": "deepseekv4flash"}
    receipt = apply_managed_runtime_config(
        environ=live, settings_store=settings, secrets_store=secrets
    )

    assert live["CHAT_LLM_PROFILE"] == "deepseekv4flash"
    assert receipt["settings_applied"] == ()
    assert receipt["settings_skipped_env"] == ("CHAT_LLM_PROFILE",)
