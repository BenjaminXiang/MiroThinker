# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Shared LLM profile resolver used by data_agents entrypoints."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_KEY_FILE_BY_ENV: dict[str, str] = {
    "API_KEY": ".sglang_api_key",
    "LOCAL_LLM_API_KEY": ".sglang_api_key",
    "DASHSCOPE_API_KEY": ".dashscope_api_key",
    "ONLINE_LLM_API_KEY": ".dashscope_api_key",
    "ARK_API_KEY": ".ark_api_key",
}


def _candidate_key_roots() -> tuple[Path, ...]:
    here = Path(__file__).resolve()
    app_root = here.parents[3]
    repo_root = here.parents[5]
    return (repo_root, app_root)


def _read_key_file(filename: str) -> str:
    for root in _candidate_key_roots():
        path = root / filename
        try:
            value = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
        if value:
            return value
    return ""


@dataclass(frozen=True)
class _LLMEndpoint:
    base_url: str
    model: str
    api_key_env: str

    def resolve_api_key(self, override_env: str) -> str:
        for env_name in (override_env, self.api_key_env):
            api_key = os.getenv(env_name, "").strip()
            if api_key:
                return api_key
        for env_name in (override_env, self.api_key_env):
            filename = _KEY_FILE_BY_ENV.get(env_name)
            if not filename:
                continue
            api_key = _read_key_file(filename)
            if api_key:
                return api_key
        return ""


@dataclass(frozen=True)
class _LLMProfile:
    local: _LLMEndpoint
    online: _LLMEndpoint


_LLM_PROFILES: dict[str, _LLMProfile] = {
    "gemma4": _LLMProfile(
        local=_LLMEndpoint(
            base_url="https://star.sustech.edu.cn/service/model/gemma4/v1",
            model="gemma-4-26b-a4b-it",
            api_key_env="API_KEY",
        ),
        online=_LLMEndpoint(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen3.6-plus",
            api_key_env="DASHSCOPE_API_KEY",
        ),
    ),
    "qwen35": _LLMProfile(
        local=_LLMEndpoint(
            base_url="https://star.sustech.edu.cn/service/model/qwen35/v1",
            model="qwen3.5-35b-a3b",
            api_key_env="API_KEY",
        ),
        online=_LLMEndpoint(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen3.6-plus",
            api_key_env="DASHSCOPE_API_KEY",
        ),
    ),
    "mirothinker": _LLMProfile(
        local=_LLMEndpoint(
            base_url="https://star.sustech.edu.cn/service/model/mirothinker/v1",
            model="mirothinker-1.7-235b-fp8",
            api_key_env="API_KEY",
        ),
        online=_LLMEndpoint(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen3.6-plus",
            api_key_env="DASHSCOPE_API_KEY",
        ),
    ),
    "ark": _LLMProfile(
        local=_LLMEndpoint(
            base_url="https://star.sustech.edu.cn/service/model/gemma4/v1",
            model="gemma-4-26b-a4b-it",
            api_key_env="API_KEY",
        ),
        online=_LLMEndpoint(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            model="ep-20260331213507-8db88",
            api_key_env="ARK_API_KEY",
        ),
    ),
}


_PROFILE_ALIASES: dict[str, str] = {
    "gemma": "gemma4",
    "gemma4a4b": "gemma4",
    "qwen": "qwen35",
    "qwen35b": "qwen35",
    "qwen-35": "qwen35",
    "qwen3.5": "qwen35",
    "miro": "mirothinker",
    "volc": "ark",
    "volces": "ark",
    "doubao": "ark",
}

_DEFAULT_PROFILE = "gemma4"


def _normalize_profile_name(profile_name: str | None) -> str:
    if not profile_name:
        return _DEFAULT_PROFILE
    normalized = profile_name.strip().replace("_", "").replace("-", "").lower()
    return _PROFILE_ALIASES.get(normalized, normalized)


def list_professor_llm_profile_names() -> list[str]:
    """Return canonical profile names in deterministic order."""
    return sorted(_LLM_PROFILES)


def render_professor_llm_profile_names() -> str:
    """Return a deterministic, user-facing profile list."""
    return ", ".join(list_professor_llm_profile_names())


def resolve_professor_llm_profile_name(
    profile_name: str | None = None,
    *,
    default_profile: str = _DEFAULT_PROFILE,
    strict: bool = False,
) -> str:
    """Resolve and normalize requested profile names.

    Precedence order:
    1) `profile_name` argument
    2) `LLM_PROFILE` environment variable
    3) `default_profile` argument

    If an unknown profile is requested and `strict=True`, raise ``ValueError``.
    Otherwise, silently fall back to the default profile.
    """
    raw_profile = profile_name if profile_name is not None else os.getenv("LLM_PROFILE")
    requested_profile = _normalize_profile_name(raw_profile)
    default_profile_key = _normalize_profile_name(default_profile)

    profile = _LLM_PROFILES.get(requested_profile)
    if profile is None:
        if strict:
            available = ", ".join(list_professor_llm_profile_names())
            raise ValueError(
                f"Unknown LLM profile '{requested_profile}'. "
                f"Available profiles: {available}."
            )
        requested_profile = default_profile_key if default_profile_key in _LLM_PROFILES else _DEFAULT_PROFILE

    return requested_profile


def resolve_professor_llm_settings(
    profile_name: str | None = None,
    *,
    default_profile: str = _DEFAULT_PROFILE,
    strict: bool = False,
    include_profile: bool = False,
) -> dict[str, str]:
    """Resolve local and online LLM defaults with env override support."""
    resolved_profile = resolve_professor_llm_profile_name(
        profile_name=profile_name,
        default_profile=default_profile,
        strict=strict,
    )
    profile = _LLM_PROFILES[resolved_profile]

    local = profile.local
    online = profile.online

    settings = {
        "local_llm_base_url": os.getenv(
            "LOCAL_LLM_BASE_URL", local.base_url
        ),
        "local_llm_model": os.getenv("LOCAL_LLM_MODEL", local.model),
        "local_llm_api_key": local.resolve_api_key("LOCAL_LLM_API_KEY"),
        "online_llm_base_url": os.getenv(
            "ONLINE_LLM_BASE_URL", online.base_url
        ),
        "online_llm_model": os.getenv("ONLINE_LLM_MODEL", online.model),
        "online_llm_api_key": online.resolve_api_key("ONLINE_LLM_API_KEY"),
    }
    if include_profile:
        settings["llm_profile"] = resolved_profile
    return settings
