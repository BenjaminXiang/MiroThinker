from __future__ import annotations

from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.vectorizer import (
    build_professor_identity_text,
    build_professor_research_text,
)


def _profile(**overrides) -> EnrichedProfessorProfile:
    defaults = {
        "name": "张三",
        "name_en": "San Zhang",
        "institution": "南方科技大学",
        "department": "计算机系",
        "title": "教授",
        "email": "zhangsan@example.edu",
        "homepage": "https://example.edu/zhangsan",
        "research_directions": ["具身智能", "机器人学习"],
        "profile_summary": "Focuses on embodied intelligence and robot learning.",
        "paper_summary": "Recent papers study graph policies for robot manipulation.",
        "patent_summary": "Patents cover force-control calibration for robots.",
        "profile_url": "https://example.edu/profile/zhangsan",
        "roster_source": "https://example.edu/roster",
        "extraction_status": "structured",
    }
    defaults.update(overrides)
    return EnrichedProfessorProfile(**defaults)


def test_identity_text_builder_uses_stable_identity_fields() -> None:
    text = build_professor_identity_text(_profile())

    assert "张三" in text
    assert "San Zhang" in text
    assert "南方科技大学" in text
    assert "计算机系" in text
    assert "教授" in text
    assert "zhangsan@example.edu" in text
    assert "https://example.edu/zhangsan" in text
    assert "Recent papers study graph policies" not in text
    assert "Patents cover force-control" not in text


def test_research_text_builder_uses_research_summaries_without_identity_dominance() -> None:
    text = build_professor_research_text(_profile())

    assert "具身智能" in text
    assert "机器人学习" in text
    assert "Focuses on embodied intelligence" in text
    assert "Recent papers study graph policies" in text
    assert "Patents cover force-control" in text
    assert "张三" not in text
    assert "南方科技大学" not in text
    assert "计算机系" not in text
    assert "教授" not in text
    assert "zhangsan@example.edu" not in text


def test_research_text_builder_falls_back_to_profile_summary_when_topics_missing() -> None:
    text = build_professor_research_text(
        _profile(
            research_directions=[],
            paper_summary=None,
            patent_summary=None,
        )
    )

    assert text == "Profile summary: Focuses on embodied intelligence and robot learning."
