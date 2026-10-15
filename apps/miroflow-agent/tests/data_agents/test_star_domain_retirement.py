"""Retirement guard: no *default* endpoint may resolve to the star gateway.

Context — openspec/changes/retire-star-domain-couplings (2026-10-15). The
``star.sustech.edu.cn`` gateway is being retired; both live lines are already
star-free. What remains are dormant defaults (collection/seed scripts, the
monthly medium-rescan guard, the legacy reranker), which this suite pins to our
own model host. The only star endpoints allowed to remain are the explicit,
never-defaulted profile options listed in ``ALLOWED_STAR_PROFILES``.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.data_agents.professor.llm_profiles import (
    _LLM_PROFILES,
    resolve_professor_llm_settings,
)
from src.data_agents.providers.rerank import _DEFAULT_RERANK_URL

STAR_HOST = "star.sustech.edu.cn"
LOCAL_QWEN36 = "http://100.64.0.27:1231/v1"
LOCAL_RERANK = "http://100.64.0.27:18006"

# Profiles that may keep a star endpoint: no verified equivalent exists on our
# own host, and nothing defaults to them. They are repointed or deleted on the
# day the school turns the domain off (see the change's follow-ups).
ALLOWED_STAR_PROFILES = {"ark", "qwen35", "mirothinker"}

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
_PROFILE_CONSTANT_RE = re.compile(r"""_DEFAULT_LLM_PROFILE\s*=\s*["']([^"']+)["']""")
_DEFAULT_KWARG_RE = re.compile(r"""default\s*=\s*["']([^"']+)["']""")


def _script_default_profiles() -> dict[str, str]:
    """Map every script-level LLM-profile default to the file that sets it."""
    found: dict[str, str] = {}
    for path in sorted(_SCRIPTS_DIR.glob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            constant = _PROFILE_CONSTANT_RE.search(line)
            if constant:
                found.setdefault(constant.group(1), path.name)
            if "--llm-profile" not in line:
                continue
            window = " ".join(lines[index : index + 3])
            kwarg = _DEFAULT_KWARG_RE.search(window)
            if kwarg:
                found.setdefault(kwarg.group(1), path.name)
    return found


def _local_base_url(profile_name: str) -> str:
    settings = resolve_professor_llm_settings(
        profile_name=profile_name, apply_endpoint_env_overrides=False
    )
    return settings["local_llm_base_url"]


def test_gemma4_default_resolves_off_star() -> None:
    assert _local_base_url("gemma4") == LOCAL_QWEN36
    assert STAR_HOST not in _local_base_url("gemma4")


def test_rerank_default_is_not_star() -> None:
    assert _DEFAULT_RERANK_URL == LOCAL_RERANK
    assert STAR_HOST not in _DEFAULT_RERANK_URL


def test_script_default_profiles_resolve_off_star() -> None:
    defaults = _script_default_profiles()
    assert defaults, "no script-level LLM profile default found — scan is broken"
    offenders = {
        f"{name} ({origin})": _local_base_url(name)
        for name, origin in defaults.items()
        if STAR_HOST in _local_base_url(name)
    }
    assert not offenders, f"script defaults still resolve to star: {offenders}"


def test_only_allowlisted_profiles_point_at_star() -> None:
    star_profiles = {
        name for name, profile in _LLM_PROFILES.items() if STAR_HOST in profile.local.base_url
    }
    assert star_profiles == ALLOWED_STAR_PROFILES
