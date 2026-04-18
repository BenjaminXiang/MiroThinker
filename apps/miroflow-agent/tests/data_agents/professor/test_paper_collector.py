# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.data_agents.paper.models import DiscoveredPaper, ProfessorPaperDiscoveryResult
from src.data_agents.professor.academic_tools import RawPaperRecord
from src.data_agents.professor.cross_domain import PaperLink
from src.data_agents.professor.paper_collector import (
    _discover_best_hybrid_result,
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
async def test_enrich_from_papers_uses_hybrid_sources_before_legacy(monkeypatch: pytest.MonkeyPatch):
    hybrid_result = ProfessorPaperDiscoveryResult(
        professor_id="PROF-001",
        professor_name="Yabei Wu",
        institution="南方科技大学",
        author_id="https://openalex.org/A5010162353",
        h_index=15,
        citation_count=708,
        paper_count=70,
        source="openalex",
        school_matched=True,
        fallback_used=False,
        papers=[
            DiscoveredPaper(
                paper_id="https://openalex.org/W1",
                title="Twisted bilayer graphene and emergent phases",
                year=2024,
                publication_date="2024-01-01",
                venue="Nature",
                doi="10.1234/example",
                arxiv_id=None,
                abstract="Graphene moire physics.",
                authors=("Yabei Wu", "Collaborator"),
                professor_ids=("PROF-001",),
                citation_count=88,
                source_url="https://example.org/paper/w1",
            )
        ],
    )

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: hybrid_result,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.collect_papers",
        lambda **_: (_ for _ in ()).throw(AssertionError("legacy collector should not run")),
    )

    llm = _mock_llm('["二维材料", "莫尔超晶格"]')
    result = await enrich_from_papers(
        name="吴亚北",
        name_en="Yabei Wu",
        institution="南方科技大学",
        institution_en=None,
        official_directions=["二维材料"],
        professor_id="PROF-001",
        homepage_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=llm,
        llm_model="test-model",
    )

    assert result.h_index == 15
    assert result.citation_count == 708
    assert result.paper_count == 70
    assert result.paper_source == "openalex"
    assert result.school_matched is True
    assert result.fallback_used is False
    assert result.top_papers[0].title == "Twisted bilayer graphene and emergent phases"
    assert result.staging_records[0].title == "Twisted bilayer graphene and emergent phases"


@pytest.mark.asyncio
async def test_enrich_from_papers_rejects_hybrid_result_conflicting_with_official_anchor(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="Joseph Sifakis",
            institution="南方科技大学",
            author_id="https://openalex.org/A999",
            h_index=57,
            citation_count=14746,
            paper_count=316,
            source="openalex",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id="https://openalex.org/W1",
                    title="Model checking",
                    year=1990,
                    publication_date="1990-01-01",
                    venue="Communications of the ACM",
                    doi=None,
                    arxiv_id=None,
                    abstract="Formal verification methods.",
                    authors=("Joseph Sifakis",),
                    professor_ids=("PROF-001",),
                    citation_count=3186,
                    source_url="https://openalex.org/W1",
                )
            ],
        ),
    )

    result = await enrich_from_papers(
        name="周垚",
        name_en="Yao Zhou",
        institution="南方科技大学",
        institution_en=None,
        official_directions=["学生发展", "高等教育院校影响力", "教师发展"],
        official_anchor_profile={
            "source_url": "https://www.sustech.edu.cn/zh/faculties/zhouyao.html",
            "bio_text": "华中科技大学管理学博士，研究学生发展、高等教育院校影响力与教师发展。",
            "research_topics": ["学生发展", "高等教育院校影响力", "教师发展"],
            "education_lines": ["华中科技大学管理学博士"],
            "english_name_candidates": ["Yao Zhou", "Zhou Yao"],
            "topic_tokens": ["学生发展", "高等教育", "院校影响力", "教师发展", "管理学"],
            "sparse_anchor": False,
        },
        professor_id="PROF-001",
        homepage_url="https://www.sustech.edu.cn/zh/faculties/zhouyao.html",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('[]'),
        llm_model="test-model",
    )

    assert result.research_directions == ["学生发展", "高等教育院校影响力", "教师发展"]
    assert result.paper_count is None
    assert result.top_papers == []
    assert result.paper_source is None


@pytest.mark.asyncio
async def test_enrich_from_papers_filters_offtopic_papers_from_mixed_author_result(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="Yao Zhou",
            institution="南方科技大学",
            author_id="https://openalex.org/A123",
            h_index=3,
            citation_count=12,
            paper_count=4,
            source="openalex",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id="https://openalex.org/W1",
                    title="The peer effect of migrant children on students’ non-cognitive outcomes: Evidence from China",
                    year=2023,
                    publication_date="2023-01-01",
                    venue="International Journal of Educational Development",
                    doi="10.1016/j.ijedudev.2023.102883",
                    arxiv_id=None,
                    abstract="Student development and higher education outcomes.",
                    authors=("Yao Zhou",),
                    professor_ids=("PROF-001",),
                    citation_count=3,
                    source_url="https://openalex.org/W1",
                ),
                DiscoveredPaper(
                    paper_id="https://openalex.org/W2",
                    title="The application of evidence-based nursing in the operating room and it's influence on the changes of patients' emotion",
                    year=2016,
                    publication_date="2016-01-01",
                    venue="International journal of nursing",
                    doi="10.3760/cma.j.issn.1673-4351.2016.21.002",
                    arxiv_id=None,
                    abstract="Clinical nursing and hospital patient outcomes.",
                    authors=("Yao Zhou",),
                    professor_ids=("PROF-001",),
                    citation_count=0,
                    source_url="https://openalex.org/W2",
                ),
                DiscoveredPaper(
                    paper_id="https://openalex.org/W3",
                    title="Awareness of hospital administrators to control of nosocomial infections",
                    year=2012,
                    publication_date="2012-01-01",
                    venue="Zhongguo yiyuan ganranxue zazhi",
                    doi=None,
                    arxiv_id=None,
                    abstract="Hospital infection control and nursing administration.",
                    authors=("Yao Zhou",),
                    professor_ids=("PROF-001",),
                    citation_count=0,
                    source_url="https://openalex.org/W3",
                ),
            ],
        ),
    )

    result = await enrich_from_papers(
        name="周垚",
        name_en="Yao Zhou",
        institution="南方科技大学",
        institution_en=None,
        official_directions=["学生发展", "高等教育院校影响力", "教师发展"],
        official_anchor_profile={
            "source_url": "https://www.sustech.edu.cn/zh/faculties/zhouyao.html",
            "bio_text": "华中科技大学管理学博士，研究学生发展、高等教育院校影响力与教师发展。",
            "research_topics": ["学生发展", "高等教育院校影响力", "教师发展"],
            "education_lines": ["华中科技大学管理学博士"],
            "english_name_candidates": ["Yao Zhou", "Zhou Yao"],
            "topic_tokens": ["学生发展", "高等教育", "院校影响力", "教师发展", "教育", "student", "educational"],
            "sparse_anchor": False,
        },
        professor_id="PROF-001",
        homepage_url="https://www.sustech.edu.cn/zh/faculties/zhouyao.html",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('[]'),
        llm_model="test-model",
    )

    assert result.paper_count == 1
    assert [paper.title for paper in result.top_papers] == [
        "The peer effect of migrant children on students’ non-cognitive outcomes: Evidence from China"
    ]
    assert [record.title for record in result.staging_records] == [
        "The peer effect of migrant children on students’ non-cognitive outcomes: Evidence from China"
    ]
    assert result.research_directions == ["学生发展", "高等教育院校影响力", "教师发展"]


@pytest.mark.asyncio
async def test_enrich_from_papers_prefers_official_publication_over_hybrid_when_official_evidence_exists(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="陈伟津",
            institution="中山大学（深圳）",
            author_id="https://openalex.org/A123",
            h_index=42,
            citation_count=2048,
            paper_count=99,
            source="openalex",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id="https://openalex.org/W1",
                    title="A noisy hybrid paper that should not outrank official evidence",
                    year=2025,
                    publication_date="2025-01-01",
                    venue="Journal of Noise",
                    doi=None,
                    arxiv_id=None,
                    abstract=None,
                    authors=("陈伟津",),
                    professor_ids=("PROF-001",),
                    citation_count=50,
                    source_url="https://openalex.org/W1",
                )
            ],
        ),
    )

    result = await enrich_from_papers(
        name="陈伟津",
        name_en=None,
        institution="中山大学（深圳）",
        institution_en=None,
        official_directions=["功能材料固体力学"],
        official_paper_count=86,
        official_top_papers=[
            PaperLink(
                title="Microstructure-mediated phase transition mechanics in ferroic materials",
                source="official_site",
            ),
            PaperLink(
                title="Elastic coupling in metal-insulator transition functional ceramics",
                source="official_site",
            ),
        ],
        publication_evidence_urls=["http://materials.sysu.edu.cn/teacher/162/publications"],
        professor_id="PROF-001",
        homepage_url="http://materials.sysu.edu.cn/teacher/162",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["功能材料固体力学"]'),
        llm_model="test-model",
    )

    assert result.paper_source == "official_site"
    assert result.paper_count == 86
    assert [paper.title for paper in result.top_papers] == [
        "Microstructure-mediated phase transition mechanics in ferroic materials",
        "Elastic coupling in metal-insulator transition functional ceramics",
    ]
    assert result.staging_records[0].source == "official_site"
    assert result.staging_records[0].source_url == "http://materials.sysu.edu.cn/teacher/162/publications"


@pytest.mark.asyncio
async def test_enrich_from_papers_prefers_official_linked_orcid_over_hybrid_when_orcid_is_present(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="李海文",
            institution="中山大学（深圳）",
            author_id="https://openalex.org/A123",
            h_index=18,
            citation_count=320,
            paper_count=12,
            source="openalex",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id="https://openalex.org/W1",
                    title="Hybrid result that should not outrank officially linked ORCID",
                    year=2024,
                    publication_date="2024-01-01",
                    venue="OpenAlex Venue",
                    doi=None,
                    arxiv_id=None,
                    abstract=None,
                    authors=("李海文",),
                    professor_ids=("PROF-001",),
                    citation_count=12,
                    source_url="https://openalex.org/W1",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_orcid",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="李海文",
            institution="中山大学（深圳）",
            author_id="https://orcid.org/0000-0001-7223-1754",
            h_index=None,
            citation_count=None,
            paper_count=2,
            source="official_linked_orcid",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id="orcid:1",
                    title="Hydride ionic conductors: Bridging ionic transport mechanisms and design strategies for sustainable energy systems",
                    year=2026,
                    publication_date="2026-01-01",
                    venue="Sustainable Materials and Technologies",
                    doi="10.1016/j.susmat.2025.e01820",
                    arxiv_id=None,
                    abstract=None,
                    authors=(),
                    professor_ids=("PROF-001",),
                    citation_count=None,
                    source_url="https://doi.org/10.1016/j.susmat.2025.e01820",
                ),
                DiscoveredPaper(
                    paper_id="orcid:2",
                    title="Another official ORCID-linked work",
                    year=2025,
                    publication_date="2025-01-01",
                    venue="Advanced Energy Materials",
                    doi=None,
                    arxiv_id=None,
                    abstract=None,
                    authors=(),
                    professor_ids=("PROF-001",),
                    citation_count=None,
                    source_url="https://orcid.org/0000-0001-7223-1754",
                ),
            ],
        ),
    )

    result = await enrich_from_papers(
        name="李海文",
        name_en=None,
        institution="中山大学（深圳）",
        institution_en=None,
        official_directions=["能源材料"],
        scholarly_profile_urls=["https://orcid.org/0000-0001-7223-1754"],
        professor_id="PROF-001",
        homepage_url="https://ae.sysu.edu.cn/teacher/lihw",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["储能材料", "离子导体"]'),
        llm_model="test-model",
    )

    assert result.paper_source == "official_linked_orcid"
    assert result.paper_count == 2
    assert [paper.title for paper in result.top_papers] == [
        "Hydride ionic conductors: Bridging ionic transport mechanisms and design strategies for sustainable energy systems",
        "Another official ORCID-linked work",
    ]
    assert result.staging_records[0].source == "official_linked_orcid"


@pytest.mark.asyncio
async def test_enrich_from_papers_prefers_high_quality_official_publication_over_official_linked_orcid(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="李海洲",
            institution="香港中文大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source=None,
            school_matched=False,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=0,
            papers=[],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_orcid",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="李海洲",
            institution="香港中文大学（深圳）",
            author_id="https://orcid.org/0000-0001-0000-0000",
            h_index=None,
            citation_count=None,
            paper_count=2,
            source="official_linked_orcid",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id="orcid:1",
                    title="Fallback ORCID title 1",
                    year=2024,
                    publication_date="2024-01-01",
                    venue="ORCID Venue",
                    doi=None,
                    arxiv_id=None,
                    abstract=None,
                    authors=(),
                    professor_ids=("PROF-001",),
                    citation_count=None,
                    source_url="https://orcid.org/0000-0001-0000-0000",
                )
            ],
        ),
    )

    result = await enrich_from_papers(
        name="李海洲",
        name_en="Haizhou Li",
        institution="香港中文大学（深圳）",
        institution_en=None,
        official_directions=["语音识别"],
        official_top_papers=[
            PaperLink(
                title="Chenglin Xu, Wei Rao, Eng Siong Chng and Haizhou Li, SpEx: Multi-Scale Time Domain Speaker Extraction Network, IEEE/ACM Transaction on Audio, Speech, and Language Processing, vol. 28, pp. 1370-1384, 2020",
                source="official_site",
            ),
            PaperLink(
                title="Tomi Kinnunen, Haizhou Li, An overview of text-independent speaker recognition: From features to supervectors, Speech Communication, Vol. 52, No. 1, pp. 12-40, 2010",
                source="official_site",
            ),
            PaperLink(
                title="Haizhou Li, Kong Aik Lee, and Bin Ma, Spoken Language Recognition: From Fundamentals to Practice, Proceedings of the IEEE, vol. 101, no. 5, pp. 1136-1159, May 2013",
                source="official_site",
            ),
        ],
        publication_evidence_urls=["https://sai.cuhk.edu.cn/teacher/102"],
        scholarly_profile_urls=["https://orcid.org/0000-0001-0000-0000"],
        professor_id="PROF-001",
        homepage_url="https://sai.cuhk.edu.cn/teacher/102",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["语音识别", "说话人识别"]'),
        llm_model="test-model",
    )

    assert result.paper_source == "official_site"
    assert result.paper_count == 3
    assert result.top_papers[0].source == "official_site"


@pytest.mark.asyncio
async def test_enrich_from_papers_prefers_official_linked_orcid_when_official_publication_titles_are_fragmented(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="段成国",
            institution="中山大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source=None,
            school_matched=False,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=0,
            papers=[],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_orcid",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="段成国",
            institution="中山大学（深圳）",
            author_id="https://orcid.org/0000-0003-0527-5866",
            h_index=None,
            citation_count=None,
            paper_count=63,
            source="official_linked_orcid",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id="orcid:1",
                    title="The expanding role of m6A RNA modification in plant-virus dynamics: friend, foe, or both?",
                    year=2026,
                    publication_date="2026-01-01",
                    venue="Advanced Biotechnology",
                    doi="10.1007/s44307-026-00100-3",
                    arxiv_id=None,
                    abstract=None,
                    authors=(),
                    professor_ids=("PROF-001",),
                    citation_count=None,
                    source_url="https://doi.org/10.1007/s44307-026-00100-3",
                ),
                DiscoveredPaper(
                    paper_id="orcid:2",
                    title="A mutually antagonistic mechanism mediated by RNA m6A modification in plant-virus interactions",
                    year=2025,
                    publication_date="2025-01-01",
                    venue="Nature Communications",
                    doi="10.1038/s41467-025-65355-1",
                    arxiv_id=None,
                    abstract=None,
                    authors=(),
                    professor_ids=("PROF-001",),
                    citation_count=None,
                    source_url="https://doi.org/10.1038/s41467-025-65355-1",
                ),
            ],
        ),
    )

    result = await enrich_from_papers(
        name="段成国",
        name_en=None,
        institution="中山大学（深圳）",
        institution_en=None,
        official_directions=["植物病理学"],
        official_paper_count=60,
        official_top_papers=[
            PaperLink(title="The expanding role of m", source="official_site"),
            PaperLink(title="A RNA mod plant", source="official_site"),
            PaperLink(title="Liu JH#, Lin Y#, Li YX, Lang Z, Zhang Z", source="official_site"),
            PaperLink(title="A mutually antagonistic mechanism mediated by RNA m", source="official_site"),
            PaperLink(title="A mod in plant", source="official_site"),
        ],
        publication_evidence_urls=["https://ab.sysu.edu.cn/zh-hans/teacher/1380"],
        scholarly_profile_urls=["https://orcid.org/0000-0003-0527-5866"],
        professor_id="PROF-001",
        homepage_url="https://ab.sysu.edu.cn/zh-hans/teacher/1380",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["植物病理学"]'),
        llm_model="test-model",
    )

    assert result.paper_source == "official_linked_orcid"
    assert result.paper_count == 63
    assert result.top_papers[0].source == "official_linked_orcid"
    assert result.top_papers[0].title == "The expanding role of m6A RNA modification in plant-virus dynamics: friend, foe, or both?"


@pytest.mark.asyncio
async def test_enrich_from_papers_drops_fragmented_official_titles_in_final_fallback_branch(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="段成国",
            institution="中山大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source=None,
            school_matched=False,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=0,
            papers=[],
        ),
    )

    result = await enrich_from_papers(
        name="段成国",
        name_en=None,
        institution="中山大学（深圳）",
        institution_en=None,
        official_directions=["植物病理学"],
        official_paper_count=60,
        official_top_papers=[
            PaperLink(title="The expanding role of m", source="official_site"),
            PaperLink(title="A RNA mod plant", source="official_site"),
            PaperLink(title="Liu JH#, Lin Y#, Li YX, Lang Z, Zhang Z", source="official_site"),
            PaperLink(title="A mutually antagonistic mechanism mediated by RNA m", source="official_site"),
            PaperLink(title="A mod in plant", source="official_site"),
        ],
        publication_evidence_urls=["https://ab.sysu.edu.cn/zh-hans/teacher/1380"],
        professor_id="PROF-001",
        homepage_url="https://ab.sysu.edu.cn/zh-hans/teacher/1380",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('[]'),
        llm_model="test-model",
    )

    assert result.paper_source == "official_site"
    assert result.paper_count == 60
    assert result.top_papers == []
    assert result.staging_records == []


@pytest.mark.asyncio
async def test_enrich_from_papers_does_not_require_orcid_when_official_publication_exists(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="唐博",
            institution="南方科技大学",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source=None,
            school_matched=False,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=0,
            papers=[],
        ),
    )

    result = await enrich_from_papers(
        name="唐博",
        name_en="Bo Tang",
        institution="南方科技大学",
        institution_en=None,
        official_directions=["大数据管理与分析"],
        official_top_papers=[
            PaperLink(
                title="Large-scale data management for modern analytics systems",
                source="official_site",
            )
        ],
        publication_evidence_urls=["https://acm.sustech.edu.cn/btang/publications.html"],
        scholarly_profile_urls=["https://dblp.org/pid/00/1234.html"],
        professor_id="PROF-001",
        homepage_url="https://acm.sustech.edu.cn/btang/",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["大数据管理", "分析系统"]'),
        llm_model="test-model",
    )

    assert result.paper_source == "official_site"
    assert result.paper_count == 1
    assert [paper.title for paper in result.top_papers] == [
        "Large-scale data management for modern analytics systems"
    ]


@pytest.mark.asyncio
async def test_enrich_from_papers_uses_official_publication_fallback_when_external_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="陈伟津",
            institution="中山大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source=None,
            school_matched=False,
            fallback_used=False,
            papers=[],
        ),
    )

    result = await enrich_from_papers(
        name="陈伟津",
        name_en=None,
        institution="中山大学（深圳）",
        institution_en=None,
        official_directions=["功能材料固体力学"],
        official_paper_count=86,
        official_top_papers=[
            PaperLink(
                title="Microstructure-mediated phase transition mechanics in ferroic materials",
                source="official_site",
            ),
            PaperLink(
                title="Elastic coupling in metal-insulator transition functional ceramics",
                source="official_site",
            ),
        ],
        publication_evidence_urls=["http://materials.sysu.edu.cn/teacher/162/publications"],
        professor_id="PROF-001",
        homepage_url="http://materials.sysu.edu.cn/teacher/162",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["功能材料固体力学"]'),
        llm_model="test-model",
    )

    assert result.paper_count == 86
    assert result.paper_source == "official_site"
    assert result.school_matched is True
    assert result.fallback_used is False
    assert [paper.title for paper in result.top_papers] == [
        "Microstructure-mediated phase transition mechanics in ferroic materials",
        "Elastic coupling in metal-insulator transition functional ceramics",
    ]
    assert result.staging_records[0].source == "official_site"
    assert result.staging_records[0].source_url == "http://materials.sysu.edu.cn/teacher/162/publications"


@pytest.mark.asyncio
async def test_enrich_from_papers_does_not_mark_official_source_as_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="陈伟津",
            institution="中山大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source=None,
            school_matched=False,
            fallback_used=False,
            papers=[],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.collect_papers",
        lambda **_: (_ for _ in ()).throw(AssertionError("legacy collector should not run")),
    )

    result = await enrich_from_papers(
        name="陈伟津",
        name_en=None,
        institution="中山大学（深圳）",
        institution_en=None,
        official_directions=["功能材料固体力学"],
        official_paper_count=86,
        official_top_papers=[
            PaperLink(
                title="Microstructure-mediated phase transition mechanics in ferroic materials",
                source="official_site",
            ),
        ],
        publication_evidence_urls=["http://materials.sysu.edu.cn/teacher/162/publications"],
        professor_id="PROF-001",
        homepage_url="http://materials.sysu.edu.cn/teacher/162",
        allow_legacy_fallback=True,
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["功能材料固体力学"]'),
        llm_model="test-model",
    )

    assert result.paper_source == "official_site"
    assert result.school_matched is True
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_enrich_from_papers_uses_official_linked_orcid_when_hybrid_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="李海文",
            institution="中山大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source=None,
            school_matched=False,
            fallback_used=False,
            papers=[],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_orcid",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="李海文",
            institution="中山大学（深圳）",
            author_id="https://orcid.org/0000-0001-7223-1754",
            h_index=None,
            citation_count=None,
            paper_count=2,
            source="official_linked_orcid",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id="orcid:1",
                    title="Hydride ionic conductors: Bridging ionic transport mechanisms and design strategies for sustainable energy systems",
                    year=2026,
                    publication_date="2026-01-01",
                    venue="Sustainable Materials and Technologies",
                    doi="10.1016/j.susmat.2025.e01820",
                    arxiv_id=None,
                    abstract=None,
                    authors=(),
                    professor_ids=("PROF-001",),
                    citation_count=None,
                    source_url="https://doi.org/10.1016/j.susmat.2025.e01820",
                ),
                DiscoveredPaper(
                    paper_id="orcid:2",
                    title="Another official ORCID-linked work",
                    year=2025,
                    publication_date="2025-01-01",
                    venue="Advanced Energy Materials",
                    doi=None,
                    arxiv_id=None,
                    abstract=None,
                    authors=(),
                    professor_ids=("PROF-001",),
                    citation_count=None,
                    source_url="https://orcid.org/0000-0001-7223-1754",
                ),
            ],
        ),
    )

    result = await enrich_from_papers(
        name="李海文",
        name_en=None,
        institution="中山大学（深圳）",
        institution_en=None,
        official_directions=["能源材料"],
        scholarly_profile_urls=["https://orcid.org/0000-0001-7223-1754"],
        professor_id="PROF-001",
        homepage_url="https://ae.sysu.edu.cn/teacher/lihw",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["储能材料", "离子导体"]'),
        llm_model="test-model",
    )

    assert result.paper_count == 2
    assert result.paper_source == "official_linked_orcid"
    assert result.school_matched is True
    assert result.fallback_used is False
    assert [paper.title for paper in result.top_papers] == [
        "Hydride ionic conductors: Bridging ionic transport mechanisms and design strategies for sustainable energy systems",
        "Another official ORCID-linked work",
    ]
    assert result.staging_records[0].source == "official_linked_orcid"
    assert result.staging_records[0].source_url == "https://doi.org/10.1016/j.susmat.2025.e01820"


@pytest.mark.asyncio
async def test_enrich_from_papers_uses_official_linked_cv_when_hybrid_and_orcid_fail(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="黄建伟",
            institution="香港中文大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source=None,
            school_matched=False,
            fallback_used=False,
            papers=[],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_orcid",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="黄建伟",
            institution="香港中文大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source="official_linked_orcid",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=0,
            papers=[],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_cv_pdf",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="黄建伟",
            institution="香港中文大学（深圳）",
            author_id="https://jianwei.cuhk.edu.cn/Files/CV.pdf",
            h_index=71,
            citation_count=20207,
            paper_count=398,
            source="official_linked_cv",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id="cv:1",
                    title="Trading Continuous Queries",
                    year=2025,
                    publication_date="2025-01-01",
                    venue="IEEE/ACM Transactions on Networking",
                    doi=None,
                    arxiv_id=None,
                    abstract=None,
                    authors=("黄建伟",),
                    professor_ids=("PROF-001",),
                    citation_count=None,
                    source_url="https://jianwei.cuhk.edu.cn/Files/CV.pdf",
                ),
            ],
        ),
    )

    result = await enrich_from_papers(
        name="黄建伟",
        name_en="Jianwei Huang",
        institution="香港中文大学（深圳）",
        institution_en=None,
        official_directions=["网络智能"],
        cv_urls=["https://jianwei.cuhk.edu.cn/Files/CV.pdf"],
        professor_id="PROF-001",
        homepage_url="https://jianwei.cuhk.edu.cn/",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["联邦学习", "资源分配"]'),
        llm_model="test-model",
    )

    assert result.paper_count == 398
    assert result.h_index == 71
    assert result.citation_count == 20207
    assert result.paper_source == "official_linked_cv"
    assert result.school_matched is True
    assert result.fallback_used is False
    assert [paper.title for paper in result.top_papers] == ["Trading Continuous Queries"]
    assert result.staging_records[0].source == "official_linked_cv"
    assert result.staging_records[0].source_url == "https://jianwei.cuhk.edu.cn/Files/CV.pdf"


@pytest.mark.asyncio
async def test_enrich_from_papers_uses_official_linked_google_scholar_when_hybrid_and_orcid_fail(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="黄建伟",
            institution="香港中文大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source=None,
            school_matched=False,
            fallback_used=False,
            papers=[],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_orcid",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="黄建伟",
            institution="香港中文大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            source="official_linked_orcid",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=0,
            papers=[],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_google_scholar_profile",
        lambda **_: ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="黄建伟",
            institution="香港中文大学（深圳）",
            author_id="https://scholar.google.com/citations?user=QQq52JcAAAAJ",
            h_index=71,
            citation_count=20820,
            paper_count=2,
            source="official_linked_google_scholar",
            school_matched=True,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id="scholar:1",
                    title="Auction-based spectrum sharing",
                    year=2006,
                    publication_date=None,
                    venue="Mobile Networks and Applications 11 (3), 405-418",
                    doi=None,
                    arxiv_id=None,
                    abstract=None,
                    authors=("黄建伟",),
                    professor_ids=("PROF-001",),
                    citation_count=817,
                    source_url="https://scholar.google.com/citations?user=QQq52JcAAAAJ",
                ),
            ],
        ),
    )

    result = await enrich_from_papers(
        name="黄建伟",
        name_en="Jianwei Huang",
        institution="香港中文大学（深圳）",
        institution_en=None,
        official_directions=["网络智能"],
        scholarly_profile_urls=["https://scholar.google.com/citations?user=QQq52JcAAAAJ"],
        professor_id="PROF-001",
        homepage_url="https://jianwei.cuhk.edu.cn/",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["联邦学习", "资源分配"]'),
        llm_model="test-model",
    )

    assert result.paper_count == 2
    assert result.h_index == 71
    assert result.citation_count == 20820
    assert result.paper_source == "official_linked_google_scholar"
    assert result.school_matched is True
    assert result.fallback_used is False
    assert [paper.title for paper in result.top_papers] == ["Auction-based spectrum sharing"]
    assert result.staging_records[0].source == "official_linked_google_scholar"
    assert result.staging_records[0].source_url == "https://scholar.google.com/citations?user=QQq52JcAAAAJ"


def test_discover_best_hybrid_result_passes_registry_backed_institution_id(
    monkeypatch: pytest.MonkeyPatch,
):
    seen_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.resolve_openalex_institution_id",
        lambda institution: "I3045169105" if institution == "南方科技大学" else None,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **kwargs: seen_calls.append(kwargs)
        or ProfessorPaperDiscoveryResult(
            professor_id=kwargs["professor_id"],
            professor_name=kwargs["professor_name"],
            institution=kwargs["institution"],
            author_id="https://openalex.org/A5010162353",
            h_index=15,
            citation_count=708,
            paper_count=70,
            school_matched=True,
            papers=[],
        ),
    )

    result = _discover_best_hybrid_result(
        name="吴亚北",
        name_en="Yabei Wu",
        institution="南方科技大学",
        institution_en=None,
        professor_id="PROF-001",
        homepage_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
    )

    assert result is not None
    assert seen_calls
    assert seen_calls[0]["institution"] == "Southern University of Science and Technology"
    assert seen_calls[0]["institution_id"] == "I3045169105"


def test_discover_best_hybrid_result_rejects_weak_chinese_only_single_paper_match(
    monkeypatch: pytest.MonkeyPatch,
):
    weak_result = ProfessorPaperDiscoveryResult(
        professor_id="PROF-001",
        professor_name="李海洲",
        institution="香港中文大学（深圳）",
        author_id="https://openalex.org/A5120362700",
        h_index=1,
        citation_count=3,
        paper_count=1,
        papers=[
            DiscoveredPaper(
                paper_id="https://openalex.org/W1",
                title="数字化转型驱动下土木工程专业“三堂融合”教学模型实证研究",
                year=2025,
                publication_date="2025-01-01",
                venue="中国科学与技术学报",
                doi="10.70693/cjst.v1i4.1651",
                arxiv_id=None,
                abstract=None,
                authors=("李海洲",),
                professor_ids=("PROF-001",),
                citation_count=3,
                source_url="https://doi.org/10.70693/cjst.v1i4.1651",
            )
        ],
    )

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.resolve_openalex_institution_id",
        lambda institution: None,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **kwargs: weak_result,
    )

    result = _discover_best_hybrid_result(
        name="李海洲",
        name_en=None,
        institution="香港中文大学（深圳）",
        institution_en=None,
        professor_id="PROF-001",
        homepage_url="https://sai.cuhk.edu.cn/teacher/102",
    )

    assert result is None


def test_discover_best_hybrid_result_rejects_weak_subject_phrase_match(
    monkeypatch: pytest.MonkeyPatch,
):
    weak_result = ProfessorPaperDiscoveryResult(
        professor_id="PROF-001",
        professor_name="Applied Statistics",
        institution="香港中文大学（深圳）",
        author_id="https://openalex.org/A5120362700",
        h_index=0,
        citation_count=0,
        paper_count=1,
        papers=[
            DiscoveredPaper(
                paper_id="https://openalex.org/W1",
                title="County-Level Adult Obesity Disparities",
                year=2025,
                publication_date="2025-01-01",
                venue="Journal of Clinical Medicine & Health Care",
                doi="10.61440/jcmhc.2025.v2.31",
                arxiv_id=None,
                abstract=None,
                authors=("Applied Statistics",),
                professor_ids=("PROF-001",),
                citation_count=0,
                source_url="https://doi.org/10.61440/jcmhc.2025.v2.31",
            )
        ],
    )

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.resolve_openalex_institution_id",
        lambda institution: None,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **kwargs: weak_result,
    )

    result = _discover_best_hybrid_result(
        name="黄建华",
        name_en="Applied Statistics",
        institution="香港中文大学（深圳）",
        institution_en=None,
        professor_id="PROF-001",
        homepage_url="https://sai.cuhk.edu.cn/teacher/108",
    )

    assert result is None


def test_discover_best_hybrid_result_prefers_english_query_before_chinese_volume_only(
    monkeypatch: pytest.MonkeyPatch,
):
    results_by_query = {
        "Haizhou Li": ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="Haizhou Li",
            institution="香港中文大学（深圳）",
            author_id="https://openalex.org/A5032690182",
            h_index=74,
            citation_count=29402,
            paper_count=1639,
            papers=[
                DiscoveredPaper(
                    paper_id="https://openalex.org/W2",
                    title="An overview of text-independent speaker recognition",
                    year=2009,
                    publication_date="2009-09-04",
                    venue="Speech Communication",
                    doi="10.1016/j.specom.2009.08.009",
                    arxiv_id=None,
                    abstract=None,
                    authors=("Tomi Kinnunen", "Haizhou Li"),
                    professor_ids=("PROF-001",),
                    citation_count=2451,
                    source_url="https://doi.org/10.1016/j.specom.2009.08.009",
                )
            ],
        ),
        "李海洲": ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="李海洲",
            institution="香港中文大学（深圳）",
            author_id="https://openalex.org/A5120362700",
            h_index=2,
            citation_count=12,
            paper_count=2,
            papers=[
                DiscoveredPaper(
                    paper_id="https://openalex.org/W1",
                    title="数字化转型驱动下土木工程专业“三堂融合”教学模型实证研究",
                    year=2025,
                    publication_date="2025-01-01",
                    venue="中国科学与技术学报",
                    doi="10.70693/cjst.v1i4.1651",
                    arxiv_id=None,
                    abstract=None,
                    authors=("李海洲",),
                    professor_ids=("PROF-001",),
                    citation_count=3,
                    source_url="https://doi.org/10.70693/cjst.v1i4.1651",
                )
            ],
        ),
    }

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.resolve_openalex_institution_id",
        lambda institution: None,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **kwargs: results_by_query[kwargs["professor_name"]],
    )

    result = _discover_best_hybrid_result(
        name="李海洲",
        name_en="Haizhou Li",
        institution="香港中文大学（深圳）",
        institution_en=None,
        professor_id="PROF-001",
        homepage_url="https://sai.cuhk.edu.cn/teacher/102",
    )

    assert result is not None
    assert result.author_id == "https://openalex.org/A5032690182"


def test_discover_best_hybrid_result_prefers_paper_evidence_over_empty_english_query(
    monkeypatch: pytest.MonkeyPatch,
):
    results_by_query = {
        "Haizhou Li": ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="Haizhou Li",
            institution="香港中文大学（深圳）",
            author_id=None,
            h_index=None,
            citation_count=None,
            paper_count=None,
            papers=[],
        ),
        "李海洲": ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="李海洲",
            institution="香港中文大学（深圳）",
            author_id="https://openalex.org/A5120362700",
            h_index=2,
            citation_count=12,
            paper_count=2,
            papers=[
                DiscoveredPaper(
                    paper_id="https://openalex.org/W1",
                    title="数字化转型驱动下土木工程专业“三堂融合”教学模型实证研究",
                    year=2025,
                    publication_date="2025-01-01",
                    venue="中国科学与技术学报",
                    doi="10.70693/cjst.v1i4.1651",
                    arxiv_id=None,
                    abstract=None,
                    authors=("李海洲",),
                    professor_ids=("PROF-001",),
                    citation_count=3,
                    source_url="https://doi.org/10.70693/cjst.v1i4.1651",
                )
            ],
        ),
    }

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.resolve_openalex_institution_id",
        lambda institution: None,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **kwargs: results_by_query[kwargs["professor_name"]],
    )

    result = _discover_best_hybrid_result(
        name="李海洲",
        name_en="Haizhou Li",
        institution="香港中文大学（深圳）",
        institution_en=None,
        professor_id="PROF-001",
        homepage_url="https://sai.cuhk.edu.cn/teacher/102",
    )

    assert result is not None
    assert result.author_id == "https://openalex.org/A5120362700"
    assert result.paper_count == 2


def test_discover_best_hybrid_result_rejects_non_school_matched_fallback_when_registry_id_exists(
    monkeypatch: pytest.MonkeyPatch,
):
    weak_result = ProfessorPaperDiscoveryResult(
        professor_id="PROF-001",
        professor_name="Chen Shaochuan",
        institution="北京大学深圳研究生院",
        author_id="semantic_scholar:123",
        h_index=4,
        citation_count=12,
        paper_count=3,
        source="semantic_scholar",
        school_matched=False,
        fallback_used=True,
        name_disambiguation_conflict=False,
        papers=[
            DiscoveredPaper(
                paper_id="semantic_scholar:paper-1",
                title="A paper by another 陈少川",
                year=2024,
                publication_date="2024-01-01",
                venue="Unknown Journal",
                doi=None,
                arxiv_id=None,
                abstract=None,
                authors=("陈少川",),
                professor_ids=("PROF-001",),
                citation_count=0,
                source_url="https://example.org/paper-1",
            )
        ],
    )

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.resolve_openalex_institution_id",
        lambda institution: "I20231570" if institution == "北京大学深圳研究生院" else None,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **kwargs: weak_result,
    )

    result = _discover_best_hybrid_result(
        name="陈少川",
        name_en=None,
        institution="北京大学深圳研究生院",
        institution_en=None,
        professor_id="PROF-001",
        homepage_url="https://pkusz.edu.cn/faculty/chensc",
    )

    assert result is None


def test_discover_best_hybrid_result_rejects_strong_openalex_match_without_school_match(
    monkeypatch: pytest.MonkeyPatch,
):
    strong_result = ProfessorPaperDiscoveryResult(
        professor_id="PROF-001",
        professor_name="Xian-En Zhang",
        institution="深圳理工大学",
        author_id="https://openalex.org/A5075843552",
        h_index=6,
        citation_count=120,
        paper_count=7,
        source="openalex",
        school_matched=False,
        fallback_used=False,
        name_disambiguation_conflict=False,
        candidate_count=1,
        papers=[
            DiscoveredPaper(
                paper_id=f"https://openalex.org/W{i}",
                title=f"Paper {i}",
                year=2024,
                publication_date="2024-01-01",
                venue="Nature Biotechnology",
                doi=None,
                arxiv_id=None,
                abstract=None,
                authors=("Xian-En Zhang",),
                professor_ids=("PROF-001",),
                citation_count=20 - i,
                source_url=f"https://example.org/paper-{i}",
            )
            for i in range(1, 6)
        ],
    )

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.resolve_openalex_institution_id",
        lambda institution: "I4405255904" if institution == "深圳理工大学" else None,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **kwargs: strong_result,
    )

    result = _discover_best_hybrid_result(
        name="张先恩",
        name_en="Xian-En Zhang",
        institution="深圳理工大学",
        institution_en=None,
        professor_id="PROF-001",
        homepage_url="https://synbio.suat-sz.edu.cn/info/1151/2122.htm",
    )

    assert result is None


def test_discover_best_hybrid_result_prefers_papers_over_metadata_only_result(
    monkeypatch: pytest.MonkeyPatch,
):
    results_by_query = {
        "Xian-En Zhang": ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="Xian-En Zhang",
            institution="深圳理工大学",
            author_id="https://openalex.org/A5075843552",
            h_index=10,
            citation_count=500,
            paper_count=100,
            source="openalex",
            school_matched=False,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[],
        ),
        "张先恩": ProfessorPaperDiscoveryResult(
            professor_id="PROF-001",
            professor_name="张先恩",
            institution="深圳理工大学",
            author_id="https://openalex.org/A5075843552",
            h_index=6,
            citation_count=120,
            paper_count=7,
            source="openalex",
            school_matched=False,
            fallback_used=False,
            name_disambiguation_conflict=False,
            candidate_count=1,
            papers=[
                DiscoveredPaper(
                    paper_id=f"https://openalex.org/W{i}",
                    title=f"Synthetic biology paper {i}",
                    year=2024,
                    publication_date="2024-01-01",
                    venue="Nature Biotechnology",
                    doi=None,
                    arxiv_id=None,
                    abstract=None,
                    authors=("张先恩",),
                    professor_ids=("PROF-001",),
                    citation_count=30 - i,
                    source_url=f"https://example.org/paper-w{i}",
                )
                for i in range(1, 6)
            ],
        ),
    }

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.resolve_openalex_institution_id",
        lambda institution: None,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.discover_professor_paper_candidates_from_hybrid_sources",
        lambda **kwargs: results_by_query[kwargs["professor_name"]],
    )

    result = _discover_best_hybrid_result(
        name="张先恩",
        name_en="Xian-En Zhang",
        institution="深圳理工大学",
        institution_en=None,
        professor_id="PROF-001",
        homepage_url="https://synbio.suat-sz.edu.cn/info/1151/2122.htm",
    )

    assert result is not None
    assert result.papers
    assert result.papers[0].title == "Synthetic biology paper 1"


@pytest.mark.asyncio
async def test_enrich_from_papers_preserves_hybrid_metrics_without_papers(monkeypatch: pytest.MonkeyPatch):
    hybrid_result = ProfessorPaperDiscoveryResult(
        professor_id="PROF-001",
        professor_name="Arieh Warshel",
        institution="香港中文大学（深圳）",
        author_id="https://openalex.org/A5088665303",
        h_index=40,
        citation_count=10000,
        paper_count=592,
        source="openalex",
        school_matched=False,
        fallback_used=False,
        name_disambiguation_conflict=False,
        papers=[],
    )

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector._discover_best_hybrid_result",
        lambda **_: hybrid_result,
    )

    result = await enrich_from_papers(
        name="WARSHEL, Arieh",
        name_en="WARSHEL, Arieh",
        institution="香港中文大学（深圳）",
        institution_en=None,
        official_directions=["计算机模拟和复杂生物大分子研究"],
        professor_id="PROF-001",
        homepage_url="https://med.cuhk.edu.cn/teacher/110",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["计算生物物理"]'),
        llm_model="test-model",
    )

    assert result.paper_count == 592
    assert result.h_index == 40
    assert result.citation_count == 10000
    assert result.paper_source == "openalex"


@pytest.mark.asyncio
async def test_enrich_from_papers_prefers_official_source_when_hybrid_only_has_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    hybrid_result = ProfessorPaperDiscoveryResult(
        professor_id="PROF-001",
        professor_name="陈伟津",
        institution="中山大学（深圳）",
        author_id="https://openalex.org/A123456789",
        h_index=12,
        citation_count=456,
        paper_count=999,
        source="openalex",
        school_matched=True,
        fallback_used=False,
        name_disambiguation_conflict=False,
        papers=[],
    )

    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector._discover_best_hybrid_result",
        lambda **_: hybrid_result,
    )

    result = await enrich_from_papers(
        name="陈伟津",
        name_en=None,
        institution="中山大学（深圳）",
        institution_en=None,
        official_directions=["功能材料固体力学"],
        official_paper_count=86,
        official_top_papers=[
            PaperLink(
                title="Microstructure-mediated phase transition mechanics in ferroic materials",
                source="official_site",
            ),
            PaperLink(
                title="Elastic coupling in metal-insulator transition functional ceramics",
                source="official_site",
            ),
        ],
        publication_evidence_urls=["http://materials.sysu.edu.cn/teacher/162/publications"],
        professor_id="PROF-001",
        homepage_url="http://materials.sysu.edu.cn/teacher/162",
        fetch_html=lambda *_args, **_kwargs: "",
        llm_client=_mock_llm('["功能材料固体力学"]'),
        llm_model="test-model",
    )

    assert result.h_index == 12
    assert result.citation_count == 456
    assert result.paper_count == 86
    assert result.paper_source == "official_site"
    assert [paper.title for paper in result.top_papers] == [
        "Microstructure-mediated phase transition mechanics in ferroic materials",
        "Elastic coupling in metal-insulator transition functional ceramics",
    ]
    assert result.staging_records[0].source == "official_site"


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
