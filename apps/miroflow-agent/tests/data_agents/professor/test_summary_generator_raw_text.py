# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.data_agents.professor.models import (
    EnrichedProfessorProfile,
    OfficialAnchorProfile,
)
from src.data_agents.professor.summary_generator import build_profile_summary_prompt


def _profile(**overrides) -> EnrichedProfessorProfile:
    defaults = {
        "name": "丁文伯",
        "institution": "深圳大学",
        "department": "电子与信息工程学院",
        "title": "教授",
        "research_directions": ["信号处理"],
        "profile_url": "https://example.edu.cn/prof/ding",
        "roster_source": "https://example.edu.cn/professors",
        "extraction_status": "structured",
    }
    defaults.update(overrides)
    return EnrichedProfessorProfile(**defaults)


def _anchor_profile(bio_text: str) -> OfficialAnchorProfile:
    return OfficialAnchorProfile(
        source_url="https://example.edu.cn/prof/ding",
        bio_text=bio_text,
    )


def test_prompt_includes_raw_text_when_anchor_profile_has_bio_text():
    bio_text = "长期从事谱估计、阵列信号处理与Group Website相关研究。"
    profile = _profile(official_anchor_profile=_anchor_profile(bio_text))

    prompt = build_profile_summary_prompt(profile)

    assert "个人主页正文摘录（请提取关键信号补充上述结构化字段不足之处）" in prompt
    assert bio_text in prompt


def test_prompt_truncates_raw_text_to_4000_chars():
    profile = _profile(official_anchor_profile=_anchor_profile("甲" * 8000))

    prompt = build_profile_summary_prompt(profile)

    assert "甲" * 4000 in prompt
    assert "甲" * 4001 not in prompt


def test_prompt_omits_raw_text_section_when_anchor_profile_is_none():
    prompt = build_profile_summary_prompt(_profile(official_anchor_profile=None))

    assert "个人主页正文摘录" not in prompt


def test_prompt_omits_raw_text_section_when_bio_text_empty():
    prompt = build_profile_summary_prompt(
        _profile(official_anchor_profile=_anchor_profile("   "))
    )

    assert "个人主页正文摘录" not in prompt
