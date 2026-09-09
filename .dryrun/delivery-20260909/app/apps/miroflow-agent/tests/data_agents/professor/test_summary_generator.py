# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.cross_domain import PaperLink
from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.summary_generator import (
    _build_fallback_profile_summary,
    _coerce_summary_length,
    build_profile_summary_prompt,
    generate_summaries,
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
            PaperLink(
                title="Safety Alignment",
                year=2024,
                venue="NeurIPS",
                citation_count=500,
                source="s2",
            ),
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


OPERATOR_META_MARKERS = (
    "摘要仅汇总",
    "人工复核",
    "细粒度检索",
    "该摘要基于",
    "当前画像",
    "可核验事实字段",
    "不对缺失经历",
    "后续检索",
)


class TestValidateProfileSummary:
    def test_rejects_too_short(self):
        assert not validate_profile_summary("太短了")

    def test_rejects_too_long(self):
        assert not validate_profile_summary("a" * 301)

    def test_rejects_boilerplate(self):
        text = _pad("张三教授已整理5条可追溯来源", 250)
        assert not validate_profile_summary(text)

    def test_rejects_refusal_style_output(self):
        text = _pad(
            "由于您提供的原始信息中缺乏研究方向、职称、代表论文及教育背景等核心学术维度，"
            "无法构建符合学术规范且达到要求的专业简介。若要生成高质量的学术摘要，请补充以下关键维度信息。",
            250,
        )
        assert not validate_profile_summary(text)

    def test_rejects_operator_meta_language(self):
        text = _pad(
            "吴日现任南方科技大学先进光源科学中心与化学系助理教授。"
            "摘要仅汇总当前已验证的身份、方向与成果信息，不对缺失经历做推断。"
            "现阶段可直接支撑按学校、院系与研究方向的细粒度检索与人工复核。",
            250,
        )
        assert not validate_profile_summary(text)

    def test_rejects_english_dominant_bilingual_paragraph(self):
        text = (
            "Ahmed Elazab is an Assistant Professor (助理教授) and Doctoral Supervisor "
            "(博士生导师) at Tsinghua SIGS. His research focuses on trustworthy "
            "artificial intelligence for medical image analysis, brain disease "
            "diagnosis and prognosis, with emphasis on multimodal neuroimaging "
            "and clinical AI systems."
        )
        assert 200 <= len(text) <= 300

        assert not validate_profile_summary(text)

    def test_accepts_valid_summary(self):
        text = _pad(
            "张三现任南方科技大学计算机系教授，研究方向聚焦大语言模型安全对齐", 250
        )
        assert validate_profile_summary(text)


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


def test_fallback_profile_summary_excludes_operator_meta_language():
    summary = _build_fallback_profile_summary(
        _profile(
            name="吴日",
            department="先进光源科学中心与化学系",
            title="助理教授",
            research_directions=[],
            h_index=None,
            citation_count=None,
            paper_count=None,
            top_papers=[],
            awards=[],
            academic_positions=[],
            profile_raw_text=(
                "吴日博士，南方科技大学先进光源科学中心与化学系双聘助理教授、课题组长、博士生导师。"
                "2025年加入南方科技大学，入选海外高层次人才计划青年项目，主要从事以生物大分子"
                "结构解析为导向的质谱仪器研制与方法学研究。"
                "我们致力于自主搭建多种类型的高端质谱仪器和开发质谱-荧光光谱联用新技术。"
            ),
        )
    )

    assert "吴日" in summary
    assert "质谱仪器" in summary
    assert not any(marker in summary for marker in OPERATOR_META_MARKERS)
    assert len(summary) <= 300


def test_fallback_profile_summary_drops_operator_meta_structured_parts():
    summary = _build_fallback_profile_summary(
        _profile(
            name="吴日",
            department="先进光源科学中心与化学系",
            title="助理教授",
            research_directions=[],
            h_index=None,
            citation_count=None,
            paper_count=None,
            top_papers=[],
            awards=["该摘要基于当前已核验的身份、研究方向与成果字段生成"],
            academic_positions=[],
            profile_raw_text=(
                "吴日博士，南方科技大学先进光源科学中心与化学系双聘助理教授、课题组长、博士生导师。"
                "2025年加入南方科技大学，主要从事以生物大分子结构解析为导向的质谱仪器研制与方法学研究。"
            ),
        )
    )

    assert "质谱仪器" in summary
    assert not any(marker in summary for marker in OPERATOR_META_MARKERS)


@pytest.mark.asyncio
class TestGenerateSummaries:
    async def test_with_valid_llm_response(self):
        profile_text = _pad(
            "张三现任南方科技大学计算机系教授，研究大语言模型安全对齐", 250
        )

        mock = MagicMock()
        mock.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=profile_text))]
        )

        result = await generate_summaries(
            profile=_profile(),
            llm_client=mock,
            llm_model="test",
        )
        assert validate_profile_summary(result.profile_summary)
        mock.chat.completions.create.assert_called_once()

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

        assert result.profile_summary
        assert "课程与教学论" in result.profile_summary
        assert not any(
            marker in result.profile_summary for marker in OPERATOR_META_MARKERS
        )
        assert len(result.profile_summary) <= 300

    async def test_falls_back_when_llm_returns_invalid_length_outputs(self):
        mock = MagicMock()
        mock.chat.completions.create.side_effect = [
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="太短"))]
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="仍然太短"))]
            ),
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

        assert result.profile_summary
        assert "流行病学" in result.profile_summary
        assert not any(
            marker in result.profile_summary for marker in OPERATOR_META_MARKERS
        )
        assert len(result.profile_summary) <= 300
