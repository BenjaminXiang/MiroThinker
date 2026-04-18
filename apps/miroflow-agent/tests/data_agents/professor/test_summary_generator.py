# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.cross_domain import PaperLink
from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.summary_generator import (
    _coerce_summary_length,
    build_evaluation_summary_prompt,
    build_profile_summary_prompt,
    generate_summaries,
    validate_evaluation_summary,
    validate_profile_summary,
)


def _profile(**overrides) -> EnrichedProfessorProfile:
    defaults = {
        "name": "张三",
        "institution": "南方科技大学",
        "department": "计算机系",
        "title": "教授",
        "research_directions": ["大语言模型安全对齐", "RLHF训练策略"],
        "h_index": 45,
        "citation_count": 12000,
        "paper_count": 150,
        "top_papers": [
            PaperLink(title="Safety Alignment", year=2024, venue="NeurIPS", citation_count=500, source="s2"),
        ],
        "awards": ["国家杰青"],
        "profile_url": "https://example.com",
        "roster_source": "https://example.com",
        "extraction_status": "structured",
    }
    defaults.update(overrides)
    return EnrichedProfessorProfile(**defaults)


def _pad(text: str, target: int) -> str:
    while len(text) < target:
        text += "。"
    return text[:target]


class TestValidateProfileSummary:
    def test_rejects_too_short(self):
        assert not validate_profile_summary("太短了")

    def test_rejects_too_long(self):
        assert not validate_profile_summary("a" * 301)

    def test_rejects_boilerplate(self):
        text = _pad("张三教授已整理5条可追溯来源", 250)
        assert not validate_profile_summary(text)

    def test_accepts_valid_summary(self):
        text = _pad("张三现任南方科技大学计算机系教授，研究方向聚焦大语言模型安全对齐", 250)
        assert validate_profile_summary(text)


class TestValidateEvaluationSummary:
    def test_rejects_too_short(self):
        assert not validate_evaluation_summary("太短")

    def test_rejects_too_long(self):
        assert not validate_evaluation_summary("a" * 151)

    def test_accepts_valid(self):
        text = _pad("张三h-index为45，总引用12000次，发表论文150篇。国家杰青获得者", 120)
        assert validate_evaluation_summary(text)


def test_coerce_summary_length_trims_overlong_profile_summary():
    text = _pad("张三现任南方科技大学教授，长期从事二维材料电子结构研究。", 330)
    coerced = _coerce_summary_length(text, min_length=200, max_length=300)
    assert 200 <= len(coerced) <= 300


class TestBuildPrompts:
    def test_profile_prompt_includes_directions(self):
        profile = _profile()
        prompt = build_profile_summary_prompt(profile)
        assert "大语言模型安全对齐" in prompt
        assert "RLHF训练策略" in prompt

    def test_eval_prompt_includes_hindex(self):
        profile = _profile()
        prompt = build_evaluation_summary_prompt(profile)
        assert "45" in prompt

    def test_eval_prompt_without_hindex(self):
        profile = _profile(h_index=None)
        prompt = build_evaluation_summary_prompt(profile)
        assert "未知" in prompt


@pytest.mark.asyncio
class TestGenerateSummaries:
    async def test_with_valid_llm_response(self):
        profile_text = _pad("张三现任南方科技大学计算机系教授，研究大语言模型安全对齐", 250)
        eval_text = _pad("张三h-index 45，总引用12000次，国家杰青", 120)

        mock = MagicMock()
        # First call returns profile_summary, second returns evaluation_summary
        mock.chat.completions.create.side_effect = [
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=profile_text))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=eval_text))]),
        ]

        result = await generate_summaries(
            profile=_profile(),
            llm_client=mock,
            llm_model="test",
        )
        assert validate_profile_summary(result.profile_summary)
        assert validate_evaluation_summary(result.evaluation_summary)

    async def test_falls_back_to_rule_based_summaries_when_llm_raises(self):
        mock = MagicMock()
        mock.chat.completions.create.side_effect = RuntimeError("connection error")

        result = await generate_summaries(
            profile=_profile(
                name="靳玉乐",
                institution="深圳大学",
                department="教育学部",
                title="文科资深教授、博士生导师",
                research_directions=["课程与教学论"],
                paper_count=350,
                top_papers=[],
                awards=["国务院政府特殊津贴获得者"],
                academic_positions=["深圳大学教育学部主任"],
            ),
            llm_client=mock,
            llm_model="test",
        )

        assert validate_profile_summary(result.profile_summary)
        assert "课程与教学论" in result.profile_summary
        assert validate_evaluation_summary(result.evaluation_summary)
        assert "350" in result.evaluation_summary

    async def test_falls_back_when_llm_returns_invalid_length_outputs(self):
        mock = MagicMock()
        mock.chat.completions.create.side_effect = [
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="太短"))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="仍然太短"))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="很短"))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="还是很短"))]),
        ]

        result = await generate_summaries(
            profile=_profile(
                name="陈维清",
                institution="中山大学（深圳）",
                department="公共卫生学院（深圳）",
                title="教授",
                research_directions=["流行病学", "公共卫生"],
                paper_count=324,
                h_index=44,
                citation_count=7255,
                awards=["国家杰青"],
                academic_positions=["学院教授委员会委员"],
            ),
            llm_client=mock,
            llm_model="test",
        )

        assert validate_profile_summary(result.profile_summary)
        assert "流行病学" in result.profile_summary
        assert validate_evaluation_summary(result.evaluation_summary)
        assert "324" in result.evaluation_summary
