"""Guard: the seed follow-up publication extractor must not default to star.

Context — openspec/changes/retire-star-domain-couplings (2026-10-15). The
``ADMIN_SEED_LLM_PUBLICATION_PROFILE`` default (``gemma4``) resolves through
``professor/llm_profiles.py``; after the retirement the gemma4 profile points at
our own model host, so this test locks the *resolution*, not the literal name.
"""

from __future__ import annotations

from backend.api import seeds as seeds_api
from src.data_agents.paper import llm_publication_extractor
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings

STAR_HOST = "star.sustech.edu.cn"


def test_seed_publication_profile_default_resolves_off_star(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def _capture_builder(profile_name, **kwargs):  # noqa: ANN001, ANN003
        captured["profile"] = profile_name
        return object()

    monkeypatch.delenv("ADMIN_SEED_LLM_PUBLICATION_PROFILE", raising=False)
    monkeypatch.delenv("ADMIN_SEED_LLM_PUBLICATION_EXTRACTION", raising=False)
    monkeypatch.setattr(
        llm_publication_extractor, "build_llm_publication_extractor", _capture_builder
    )

    extractor = seeds_api._build_seed_followup_publication_extractor()

    assert extractor is not None, "extractor fell back to rules — default path changed"
    resolved = resolve_professor_llm_settings(
        profile_name=captured["profile"], apply_endpoint_env_overrides=False
    )
    assert STAR_HOST not in resolved["local_llm_base_url"]
