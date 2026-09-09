# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import fields

from src.data_agents.professor import summary_generator
from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.vectorizer import build_professor_profile_payload


FIELD = "evaluation_summary"


def _profile() -> EnrichedProfessorProfile:
    return EnrichedProfessorProfile(
        name="张三",
        institution="南方科技大学",
        department="计算机系",
        title="教授",
        research_directions=["大语言模型"],
        profile_summary="张三教授专注于大语言模型研究。",
        profile_url="https://example.com/prof",
        roster_source="https://example.com/roster",
        extraction_status="structured",
    )


def test_retired_summary_helpers_stay_removed() -> None:
    assert FIELD not in {item.name for item in fields(summary_generator.GeneratedSummaries)}
    assert not hasattr(summary_generator, f"build_{FIELD}_prompt")
    assert not hasattr(summary_generator, f"validate_{FIELD}")
    assert not hasattr(summary_generator, f"_build_fallback_{FIELD}")


def test_professor_vector_payload_excludes_retired_field() -> None:
    payload = build_professor_profile_payload(
        prof_id="PROF-001",
        profile=_profile(),
        quality_status="ready",
        profile_vector=[0.1],
        direction_vector=[0.2],
    )

    assert FIELD not in payload
