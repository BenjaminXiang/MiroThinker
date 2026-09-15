from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services.canonical_v2_runtime_sources import (
    BOCHA_ENDPOINT,
    SERPER_ENDPOINT,
    resolve_connections,
)
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore
from src.data_agents.canonical_v2.managed_secrets import ManagedSecretsStore

# Every credential in this file is a locally generated fake, supplied through the
# environment or a fixture key-file root. The resolvers are always given explicit
# ``key_file_roots`` so no test can reach the checkout's real key files.
_FAKE = "sk-fake-runtime-0000-1111-9a7b"
_FAKE_LOCAL = "fake-local-key-0000-4321"
_FAKE_BOCHA = "fake-bocha-key-0000-1111"
_FAKE_SERPER = "fake-serper-key-2222"
_FAKE_DEEPSEEK = "fake-deepseek-key-0000-7777"


@pytest.fixture()
def fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "key-root"
    root.mkdir()
    return root


def _stores(
    tmp_path: Path, fixture_root: Path, **environ: str
) -> tuple[ManagedSettingsStore, ManagedSecretsStore]:
    settings = ManagedSettingsStore(
        tmp_path / "managed" / "settings.json", environ=environ, repo_root=tmp_path
    )
    secrets = ManagedSecretsStore(
        tmp_path / "managed" / "secrets.json",
        environ=environ,
        key_file_roots=(fixture_root,),
        repo_root=tmp_path,
    )
    return settings, secrets


def _resolve(
    tmp_path: Path,
    fixture_root: Path,
    environ: dict[str, str],
    **key_files: str,
):
    for name, value in key_files.items():
        (fixture_root / f".{name}_api_key").write_text(value + "\n", encoding="utf-8")
    settings, secrets = _stores(tmp_path, fixture_root, **environ)
    return (
        resolve_connections(
            environ=environ,
            settings_store=settings,
            secrets_store=secrets,
            key_file_roots=(fixture_root,),
        ),
        settings,
        secrets,
    )


def test_rerank_is_reported_as_not_enabled_not_as_401(
    tmp_path: Path, fixture_root: Path
) -> None:
    """The live line has no CANONICAL_V2_RERANK_BASE_URL: that is "disabled", not "401".

    Runtime rule: canonical_v2/rerank_client.py:224-236 — ``configured_reranker()``
    returns ``None`` when the base URL is unset, so the serving process never calls
    rerank and there is no default endpoint a probe could honestly use.
    """

    resolved, _settings, _secrets = _resolve(
        tmp_path, fixture_root, {"CHAT_LLM_PROFILE": "deepseekv4flash"}
    )

    rerank = resolved["rerank"]

    assert rerank.enabled is False
    assert rerank.base_url is None
    assert "CANONICAL_V2_RERANK_BASE_URL" in rerank.runtime_note
    assert "未启用" in rerank.runtime_note


def test_rerank_reports_its_endpoint_when_configured(
    tmp_path: Path, fixture_root: Path
) -> None:
    resolved, settings, _secrets = _resolve(tmp_path, fixture_root, {})
    settings.patch(
        {"extraction_endpoints": {"rerank_base_url": "http://127.0.0.1:28099"}},
        operator="ops",
    )
    rerank = resolve_connections(
        environ={},
        settings_store=settings,
        secrets_store=_secrets,
        key_file_roots=(fixture_root,),
    )["rerank"]

    assert rerank.enabled is True
    assert rerank.base_url == "http://127.0.0.1:28099"


def test_embedding_uses_the_frozen_bundle_endpoint_and_the_local_credential(
    tmp_path: Path, fixture_root: Path
) -> None:
    """company/vectorizer.py:22,40-53 + providers/local_api_key.py:8-31."""

    resolved, _settings, _secrets = _resolve(
        tmp_path, fixture_root, {}, sglang=_FAKE_LOCAL
    )

    embedding = resolved["embedding"]

    assert embedding.enabled is True
    assert embedding.base_url == "http://100.64.0.27:18005/v1"
    assert embedding.endpoint_origin == "release-bundle-frozen"
    assert embedding.model == "Qwen/Qwen3-Embedding-8B"
    assert embedding.api_key == _FAKE_LOCAL
    assert embedding.api_key_origin == "legacy-file:.sglang_api_key"


def test_embedding_ignores_a_variable_nothing_reads_at_runtime(
    tmp_path: Path, fixture_root: Path
) -> None:
    """``EMBEDDING_API_KEY`` is not in the runtime chain; the local key is."""

    resolved, _settings, _secrets = _resolve(
        tmp_path,
        fixture_root,
        {"EMBEDDING_API_KEY": "fake-never-read-9999"},
        sglang=_FAKE_LOCAL,
    )

    embedding = resolved["embedding"]

    assert embedding.api_key_origin == "legacy-file:.sglang_api_key"
    assert embedding.api_key == _FAKE_LOCAL


def test_llm_follows_the_active_chat_profile(
    tmp_path: Path, fixture_root: Path
) -> None:
    """knowledge_serving_isolated.py:2087-2096 → llm_profiles.py:273."""

    resolved, _settings, _secrets = _resolve(
        tmp_path,
        fixture_root,
        {"CHAT_LLM_PROFILE": "deepseekv4flash", "DEEPSEEK_API_KEY": _FAKE_DEEPSEEK},
    )

    llm = resolved["llm"]

    assert llm.enabled is True
    assert llm.base_url == "https://api.deepseek.com"
    assert llm.model == "deepseek-v4-flash"
    assert llm.endpoint_origin == "chat-profile:deepseekv4flash"
    assert llm.api_key == _FAKE_DEEPSEEK
    assert llm.api_key_origin == "env:DEEPSEEK_API_KEY"


def test_llm_profile_switch_changes_the_reported_source(
    tmp_path: Path, fixture_root: Path
) -> None:
    resolved, _settings, _secrets = _resolve(
        tmp_path, fixture_root, {"CHAT_LLM_PROFILE": "gemma4"}
    )

    llm = resolved["llm"]

    assert llm.endpoint_origin == "chat-profile:gemma4"
    assert llm.base_url == "https://star.sustech.edu.cn/service/model/qwen36/v1"


def test_llm_reports_a_missing_credential_instead_of_a_401(
    tmp_path: Path, fixture_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No profile key anywhere → "credential missing", not a probe that cannot work."""

    from src.data_agents.professor import llm_profiles

    monkeypatch.setattr(llm_profiles, "_read_key_file", lambda filename: "")

    resolved, _settings, _secrets = _resolve(
        tmp_path, fixture_root, {"CHAT_LLM_PROFILE": "deepseekv4flash"}
    )

    llm = resolved["llm"]

    assert llm.enabled is False
    assert llm.api_key == ""
    assert "凭据缺失" in llm.runtime_note


def test_web_search_connections_report_the_pinned_host_and_key_file(
    tmp_path: Path, fixture_root: Path
) -> None:
    resolved, _settings, _secrets = _resolve(
        tmp_path, fixture_root, {}, bocha=_FAKE_BOCHA, serper=_FAKE_SERPER
    )

    assert resolved["bocha"].base_url == BOCHA_ENDPOINT
    assert resolved["bocha"].endpoint_origin == "pinned-provider-host"
    assert resolved["bocha"].api_key_origin == "legacy-file:.bocha_api_key"
    assert resolved["bocha"].api_key == _FAKE_BOCHA
    assert resolved["serper"].base_url == SERPER_ENDPOINT
    assert resolved["serper"].api_key_origin == "legacy-file:.serper_api_key"
    assert resolved["bocha"].enabled is True


def test_environment_wins_over_key_file(tmp_path: Path, fixture_root: Path) -> None:
    resolved, _settings, _secrets = _resolve(
        tmp_path,
        fixture_root,
        {"BOCHA_API_KEY": "fake-bocha-env-key-9999"},
        bocha=_FAKE_BOCHA,
    )

    bocha = resolved["bocha"]

    assert bocha.api_key == "fake-bocha-env-key-9999"
    assert bocha.api_key_origin == "env:BOCHA_API_KEY"


def test_managed_value_is_pending_until_the_restart(
    tmp_path: Path, fixture_root: Path
) -> None:
    """A page-saved key is stored, not hot-read: the running process still uses the file."""

    resolved, _settings, secrets = _resolve(
        tmp_path, fixture_root, {}, sglang=_FAKE_LOCAL
    )
    secrets.patch({"embedding.api_key": _FAKE}, operator="ops")
    embedding = resolve_connections(
        environ={},
        settings_store=_settings,
        secrets_store=secrets,
        key_file_roots=(fixture_root,),
    )["embedding"]

    assert embedding.api_key == _FAKE_LOCAL
    assert embedding.api_key_origin == "legacy-file:.sglang_api_key"
    assert embedding.pending_restart is True
    assert "重启服务后生效" in embedding.runtime_note


def test_adopted_managed_value_is_reported_as_effective(
    tmp_path: Path, fixture_root: Path
) -> None:
    """After the restart the projection puts it in the environment: that is effective."""

    resolved, _settings, secrets = _resolve(
        tmp_path, fixture_root, {}, sglang=_FAKE_LOCAL
    )
    secrets.patch({"embedding.api_key": _FAKE}, operator="ops")
    environ = {"SGLANG_API_KEY": _FAKE}
    from src.data_agents.canonical_v2.managed_runtime import APPLIED_ENV_VAR

    environ[APPLIED_ENV_VAR] = "SGLANG_API_KEY"
    embedding = resolve_connections(
        environ=environ,
        settings_store=_settings,
        secrets_store=secrets,
        key_file_roots=(fixture_root,),
    )["embedding"]

    assert embedding.api_key == _FAKE
    assert embedding.api_key_origin == "managed-file(env:SGLANG_API_KEY)"
    assert embedding.pending_restart is False


def test_runtime_public_view_never_carries_the_credential(
    tmp_path: Path, fixture_root: Path
) -> None:
    resolved, _settings, _secrets = _resolve(
        tmp_path, fixture_root, {}, bocha=_FAKE_BOCHA, sglang=_FAKE_LOCAL
    )

    for connection in resolved.values():
        public = json.dumps(connection.as_public_dict())
        assert "fake-" not in public
        assert "api_key" not in connection.as_public_dict()
        if connection.api_key:
            assert connection.api_key not in public


def test_profile_resolution_matches_the_serving_path(
    tmp_path: Path, fixture_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anti-drift: same profile name, endpoint, model and credential as the runtime.

    ``resolve_professor_llm_settings`` reads ``os.environ`` and walks real key-file
    roots, so this cross-check pins the ambient environment to fakes and disables
    the file walk; both paths must then agree on every field.
    """

    from src.data_agents.professor import llm_profiles

    monkeypatch.setenv("CHAT_LLM_PROFILE", "deepseekv4flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", _FAKE_DEEPSEEK)
    monkeypatch.setattr(llm_profiles, "_read_key_file", lambda filename: "")

    official = llm_profiles.resolve_professor_llm_settings(
        "deepseekv4flash", apply_endpoint_env_overrides=False
    )
    resolved, _settings, _secrets = _resolve(
        tmp_path,
        fixture_root,
        {"CHAT_LLM_PROFILE": "deepseekv4flash", "DEEPSEEK_API_KEY": _FAKE_DEEPSEEK},
    )
    llm = resolved["llm"]

    assert llm.base_url == official["local_llm_base_url"]
    assert llm.model == official["local_llm_model"]
    assert llm.api_key == official["local_llm_api_key"] == _FAKE_DEEPSEEK
