# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.academic_tools import RawPaperRecord
from src.data_agents.professor.paper_collector import (
    _merge_directions,
    _parse_directions_response,
    build_staging_records,
    generate_research_directions,
    select_top_papers,
)


def _paper(
    title: str = "Test Paper",
    year: int | None = 2024,
    citation_count: int | None = 10,
    **kwargs,
) -> RawPaperRecord:
    defaults = {
        "title": title,
        "authors": ["Author A"],
        "year": year,
        "venue": "NeurIPS",
        "abstract": "Some abstract text.",
        "doi": None,
        "citation_count": citation_count,
        "keywords": ["ML"],
        "source_url": "https://example.com",
        "source": "semantic_scholar",
    }
    defaults.update(kwargs)
    return RawPaperRecord(**defaults)


def _mock_llm(response_text: str) -> MagicMock:
    mock = MagicMock()
    choice = SimpleNamespace(message=SimpleNamespace(content=response_text))
    mock.chat.completions.create.return_value = SimpleNamespace(choices=[choice])
    return mock


class TestSelectTopPapers:
    def test_returns_top_5_by_citation(self):
        papers = [_paper(title=f"P{i}", citation_count=i * 10) for i in range(10)]
        top = select_top_papers(papers, limit=5)
        assert len(top) == 5
        assert top[0].citation_count == 90
        assert top[1].citation_count == 80

    def test_fewer_than_limit(self):
        papers = [_paper(title="Only One")]
        top = select_top_papers(papers, limit=5)
        assert len(top) == 1

    def test_empty_papers(self):
        assert select_top_papers([]) == []

    def test_includes_recent_paper(self):
        papers = [
            _paper(title="Old High", year=2015, citation_count=1000),
            _paper(title="Old High2", year=2016, citation_count=900),
            _paper(title="Old High3", year=2017, citation_count=800),
            _paper(title="Old High4", year=2018, citation_count=700),
            _paper(title="Old High5", year=2019, citation_count=600),
            _paper(title="Recent Low", year=2025, citation_count=5),
        ]
        top = select_top_papers(papers, limit=5)
        titles = [p.title for p in top]
        assert "Recent Low" in titles


class TestBuildStagingRecords:
    def test_produces_valid_records(self):
        papers = [_paper(title="Paper A"), _paper(title="Paper B")]
        staging = build_staging_records(
            papers,
            professor_id="PROF-001",
            professor_name="张三",
            institution="南方科技大学",
        )
        assert len(staging) == 2
        assert staging[0].anchoring_professor_id == "PROF-001"
        assert staging[0].anchoring_institution == "南方科技大学"
        assert staging[0].title == "Paper A"


class TestParseDirectionsResponse:
    def test_plain_json_array(self):
        result = _parse_directions_response('["方向A", "方向B", "方向C"]')
        assert result == ["方向A", "方向B", "方向C"]

    def test_json_in_fence(self):
        result = _parse_directions_response(
            '```json\n["大语言模型", "RLHF"]\n```'
        )
        assert result == ["大语言模型", "RLHF"]

    def test_no_json_array(self):
        result = _parse_directions_response("这不是JSON")
        assert result == []

    def test_array_in_text(self):
        result = _parse_directions_response(
            '研究方向如下：["计算机视觉", "目标检测"]。以上是分析结果。'
        )
        assert result == ["计算机视觉", "目标检测"]


class TestMergeDirections:
    def test_paper_first_official_supplement(self):
        merged = _merge_directions(
            ["大语言模型安全", "RLHF"],
            ["人工智能", "机器学习"],
        )
        assert merged[0] == "大语言模型安全"
        assert merged[1] == "RLHF"
        assert "人工智能" in merged
        assert "机器学习" in merged

    def test_dedup_exact_match(self):
        merged = _merge_directions(
            ["大语言模型", "RLHF"],
            ["大语言模型", "深度学习"],
        )
        assert merged.count("大语言模型") == 1

    def test_caps_at_7(self):
        paper = [f"方向{i}" for i in range(6)]
        official = [f"官方{i}" for i in range(5)]
        merged = _merge_directions(paper, official)
        assert len(merged) <= 7


@pytest.mark.asyncio
class TestGenerateResearchDirections:
    async def test_with_papers_returns_paper_driven(self):
        papers = [_paper(title="Safety Alignment for LLMs")]
        llm = _mock_llm('["大语言模型安全对齐", "RLHF训练策略"]')
        directions, source = await generate_research_directions(
            papers=papers,
            official_directions=[],
            llm_client=llm,
            llm_model="test-model",
        )
        assert source == "paper_driven"
        assert "大语言模型安全对齐" in directions

    async def test_no_papers_returns_official(self):
        directions, source = await generate_research_directions(
            papers=[],
            official_directions=["人工智能"],
            llm_client=MagicMock(),
            llm_model="test",
        )
        assert source == "official_only"
        assert directions == ["人工智能"]

    async def test_with_official_returns_merged(self):
        papers = [_paper(title="LLM Safety")]
        llm = _mock_llm('["大语言模型安全"]')
        directions, source = await generate_research_directions(
            papers=papers,
            official_directions=["机器学习"],
            llm_client=llm,
            llm_model="test",
        )
        assert source == "merged"

    async def test_llm_failure_falls_back_to_official(self):
        papers = [_paper()]
        llm = MagicMock()
        llm.chat.completions.create.side_effect = RuntimeError("LLM error")
        directions, source = await generate_research_directions(
            papers=papers,
            official_directions=["人工智能"],
            llm_client=llm,
            llm_model="test",
        )
        assert source == "official_only"
        assert directions == ["人工智能"]
