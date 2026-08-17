# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.data_agents.paper.models import DiscoveredPaper
from src.data_agents.professor import paper_collector as paper_collector_module
from src.data_agents.professor.academic_tools import RawPaperRecord
from src.data_agents.professor.cross_domain import PaperLink
from src.data_agents.professor.paper_collector import (
    _discovered_to_raw_paper,
    _merge_directions,
    _parse_directions_response,
    build_staging_records,
    enrich_from_papers,
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


def test_discovered_to_raw_paper_cleans_markup_polluted_titles():
    raw = _discovered_to_raw_paper(
        DiscoveredPaper(
            paper_id="https://openalex.org/W1",
            title=(
                "Manipulation of valley pseudospin in "
                "<mml:math xmlns:mml=\"http://www.w3.org/1998/Math/MathML\">"
                "<mml:msub><mml:mi>WSe</mml:mi><mml:mn>2</mml:mn></mml:msub>"
                "<mml:mo>/</mml:mo>"
                "<mml:msub><mml:mi>CrI</mml:mi><mml:mn>3</mml:mn></mml:msub>"
                "</mml:math> heterostructures by the magnetic proximity effect"
            ),
            year=2024,
            publication_date="2024-01-01",
            venue="Nature",
            doi=None,
            arxiv_id=None,
            abstract=None,
            authors=("Yabei Wu",),
            professor_ids=("PROF-001",),
            citation_count=10,
            source_url="https://openalex.org/W1",
        ),
        source="openalex",
    )

    assert raw.title == (
        "Manipulation of valley pseudospin in WSe2/CrI3 heterostructures by the magnetic proximity effect"
    )


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


@pytest.mark.asyncio
async def test_enrich_from_papers_uses_official_publications_as_page_first_source():
    result = await enrich_from_papers(
        name="吴亚北",
        name_en="Yabei Wu",
        institution="南方科技大学",
        institution_en=None,
        official_directions=["二维材料"],
        official_paper_count=2,
        official_top_papers=[
            PaperLink(
                title="Twisted bilayer graphene and emergent phases",
                year=2024,
                venue="Nature",
                doi="10.1234/example",
                citation_count=88,
                source="official_site",
            ),
            PaperLink(
                title="Moiré materials for quantum devices",
                year=2025,
                venue="Science",
                doi=None,
                citation_count=12,
                source="official_site",
            ),
        ],
        publication_evidence_urls=["https://faculty.example.edu/papers"],
        scholarly_profile_urls=["https://orcid.org/0000-0000-0000-0000"],
        cv_urls=["https://faculty.example.edu/cv.pdf"],
        professor_id="PROF-001",
        homepage_url="https://faculty.example.edu",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["二维材料", "莫尔超晶格"]'),
        llm_model="test-model",
    )

    assert result.h_index is None
    assert result.citation_count is None
    assert result.paper_count == 2
    assert result.paper_source == "official_site"
    assert result.school_matched is True
    assert result.fallback_used is False
    assert result.top_papers[0].title == "Twisted bilayer graphene and emergent phases"
    assert result.staging_records[0].source == "official_site"
    assert result.staging_records[0].source_url == "https://faculty.example.edu/papers"


@pytest.mark.asyncio
async def test_enrich_from_papers_does_not_use_profile_links_as_discovery_fallback():
    result = await enrich_from_papers(
        name="黄建伟",
        name_en="Jianwei Huang",
        institution="香港中文大学（深圳）",
        institution_en=None,
        official_directions=["网络智能"],
        official_top_papers=[],
        scholarly_profile_urls=["https://scholar.google.com/citations?user=QQq52JcAAAAJ"],
        cv_urls=["https://jianwei.cuhk.edu.cn/Files/CV.pdf"],
        professor_id="PROF-002",
        homepage_url="https://jianwei.cuhk.edu.cn/",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('[]'),
        llm_model="test-model",
    )

    assert result.research_directions == ["网络智能"]
    assert result.research_directions_source == "official_only"
    assert result.paper_count is None
    assert result.paper_source is None
    assert result.top_papers == []
    assert result.staging_records == []


@pytest.mark.asyncio
async def test_enrich_from_papers_ignores_legacy_fallback_flag(monkeypatch):
    def fail_if_legacy_collection_is_called(**_kwargs):
        raise AssertionError("legacy author/database paper discovery must stay retired")

    monkeypatch.setattr(
        paper_collector_module,
        "collect_papers",
        fail_if_legacy_collection_is_called,
        raising=False,
    )

    result = await paper_collector_module.enrich_from_papers(
        name="黄建伟",
        name_en="Jianwei Huang",
        institution="香港中文大学（深圳）",
        institution_en=None,
        official_directions=["网络智能"],
        official_top_papers=[],
        professor_id="PROF-002",
        homepage_url="https://jianwei.cuhk.edu.cn/",
        allow_legacy_fallback=True,
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('[]'),
        llm_model="test-model",
    )

    assert result.research_directions == ["网络智能"]
    assert result.research_directions_source == "official_only"
    assert result.paper_source is None
    assert result.staging_records == []


@pytest.mark.asyncio
async def test_enrich_from_papers_drops_fragmented_official_titles_without_external_lookup():
    result = await enrich_from_papers(
        name="张三",
        name_en="San Zhang",
        institution="南方科技大学",
        institution_en=None,
        official_directions=["材料力学"],
        official_paper_count=None,
        official_top_papers=[
            PaperLink(
                title="A. Zhang, B. Li, C. Wang",
                year=None,
                venue=None,
                doi=None,
                citation_count=None,
                source="official_site",
            )
        ],
        publication_evidence_urls=["https://faculty.example.edu/papers"],
        professor_id="PROF-003",
        homepage_url="https://faculty.example.edu",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('[]'),
        llm_model="test-model",
    )

    assert result.research_directions == ["材料力学"]
    assert result.paper_count is None
    assert result.paper_source is None
    assert result.top_papers == []
    assert result.staging_records == []


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
