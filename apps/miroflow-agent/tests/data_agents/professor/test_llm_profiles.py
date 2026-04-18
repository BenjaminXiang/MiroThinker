# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from src.data_agents.professor.llm_profiles import (
    list_professor_llm_profile_names,
    resolve_professor_llm_profile_name,
    resolve_professor_llm_settings,
)


def test_list_professor_llm_profiles_is_sorted_and_predictable():
    """Canonical profile names should be deterministic and include known aliases."""
    names = ["ark", "gemma4", "mirothinker", "qwen35"]
    assert resolve_professor_llm_profile_name("gemma4") == "gemma4"

    assert list_professor_llm_profile_names() == names


def test_resolve_profile_name_supports_aliases():
    """Common aliases should resolve to canonical profile names."""
    assert resolve_professor_llm_profile_name("gemma") == "gemma4"
    assert resolve_professor_llm_profile_name("qwen") == "qwen35"
    assert resolve_professor_llm_profile_name("miro") == "mirothinker"
    assert resolve_professor_llm_profile_name("volces") == "ark"


def test_resolve_profile_name_uses_env_when_not_explicit(monkeypatch: pytest.MonkeyPatch):
    """LLM_PROFILE environment variable should participate in resolution."""
    monkeypatch.setenv("LLM_PROFILE", "qwen35")
    assert resolve_professor_llm_profile_name() == "qwen35"


def test_resolve_profile_name_fallbacks_in_non_strict_mode():
    """Invalid profile names should silently fallback when strict=False."""
    assert resolve_professor_llm_profile_name(
        profile_name="not-a-profile",
        default_profile="qwen35",
        strict=False,
    ) == "qwen35"


def test_resolve_profile_name_raises_in_strict_mode():
    """Strict profile resolution should reject unknown names."""
    with pytest.raises(ValueError, match="Unknown LLM profile"):
        resolve_professor_llm_profile_name("not-a-profile", strict=True)


def test_resolve_professor_llm_settings_apply_aliases_and_env_overrides(monkeypatch: pytest.MonkeyPatch):
    """Settings should resolve canonical profile and apply direct env overrides."""
    monkeypatch.setenv("LOCAL_LLM_MODEL", "overridden-local-model")
    monkeypatch.setenv("ONLINE_LLM_MODEL", "overridden-online-model")
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "local-key")
    monkeypatch.setenv("ONLINE_LLM_API_KEY", "online-key")

    settings = resolve_professor_llm_settings("miro", strict=True, include_profile=True)

    assert settings["llm_profile"] == "mirothinker"
    assert settings["local_llm_model"] == "overridden-local-model"
    assert settings["online_llm_model"] == "overridden-online-model"
    assert settings["local_llm_api_key"] == "local-key"
    assert settings["online_llm_api_key"] == "online-key"


def test_resolve_professor_llm_settings_hides_profile_when_not_requested():
    settings = resolve_professor_llm_settings("qwen35", strict=True, include_profile=False)
    assert "llm_profile" not in settings


def test_resolve_professor_llm_settings_falls_back_to_key_file(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.data_agents.professor import llm_profiles

    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_LLM_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_profiles,
        "_read_key_file",
        lambda filename: "file-key" if filename == ".sglang_api_key" else "",
    )

    settings = resolve_professor_llm_settings("gemma4", strict=True, include_profile=True)

    assert settings["llm_profile"] == "gemma4"
    assert settings["local_llm_api_key"] == "file-key"


@pytest.mark.parametrize(
    ("profile_name", "expected_prefix"),
    [
        ("gemma4", "https://star.sustech.edu.cn/service/model/gemma4/v1"),
        ("qwen35", "https://star.sustech.edu.cn/service/model/qwen35/v1"),
        ("mirothinker", "https://star.sustech.edu.cn/service/model/mirothinker/v1"),
        ("ark", "https://star.sustech.edu.cn/service/model/gemma4/v1"),
    ],
)
def test_resolve_professor_llm_settings_uses_https_for_star_profiles(
    profile_name: str,
    expected_prefix: str,
):
    settings = resolve_professor_llm_settings(profile_name, strict=True, include_profile=True)

    assert settings["local_llm_base_url"] == expected_prefix
