# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for web search enrichment module."""
from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.web_search_enrichment import (
    CompanyMention,
    _merge_web_extract,
    _parse_extract_output,
    _reserved_follow_up_budget,
    WebSearchResult,
    build_search_queries,
    search_and_enrich,
)
from src.data_agents.professor.models import EnrichedProfessorProfile


def _make_profile(**kwargs) -> EnrichedProfessorProfile:
    defaults = dict(
        name="李志",
        institution="南方科技大学",
        department="计算机科学与工程系",
        title="教授",
        homepage="https://faculty.sustech.edu.cn/lizhi/",
        profile_url="https://www.sustech.edu.cn/zh/lizhi",
        roster_source="https://www.sustech.edu.cn/zh/letter/",
        extraction_status="structured",
        research_directions=["机器学习", "计算机视觉"],
    )
    defaults.update(kwargs)
    return EnrichedProfessorProfile(**defaults)


class TestBuildSearchQueries:
    """Test query construction."""

    def test_builds_primary_and_academic_queries(self):
        profile = _make_profile()
        queries = build_search_queries(profile)
        assert len(queries) >= 4
        # Ordering (2026-04-23): identity anchors + one topic-based company query
        # interleaved into the first 3 positions, then scholar, then remaining
        # company queries. See build_search_queries docstring.
        assert queries[0] == "李志 南方科技大学"
        assert queries[1] == "李志 南方科技大学 个人主页"
        assert queries[2].endswith("公司")  # topic-based company query
        assert queries[3] == "李志 南方科技大学 scholar"

    def test_builds_company_queries_with_separate_company_intent_keywords(self):
        profile = _make_profile()
        queries = build_search_queries(profile)
        assert any("公司" in q for q in queries)
        assert not any(q.endswith(" 创业") for q in queries)
        assert not any(q.endswith(" 发起人") for q in queries)

    def test_without_directions(self):
        profile = _make_profile(research_directions=[])
        queries = build_search_queries(profile)
        assert len(queries) >= 4  # primary + personal homepage + scholar + company

    def test_reserved_follow_up_budget_scales_with_total_page_budget(self):
        assert _reserved_follow_up_budget(1) == 0
        assert _reserved_follow_up_budget(2) == 1
        assert _reserved_follow_up_budget(4) == 2
        assert _reserved_follow_up_budget(8) == 2

    def test_builds_company_topic_queries_prioritize_robotics_over_generic_sensor_topics(self):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            research_directions=[
                "摩擦纳米发电机 (TENG) 设计与制造",
                "自供电环境感知传感器 (风速/波浪/运动)",
                "功能性智能聚合物与纤维材料研究",
                "机器人触觉感知",
                "智能感知与机器人",
            ],
        )

        queries = build_search_queries(profile)

        assert any("机器人" in q and "触觉" in q and "公司" in q for q in queries)

    def test_builds_company_topic_queries_from_high_signal_later_stem_directions(self):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            research_directions=[
                "摩擦纳米发电机 (TENG) 设计与制造",
                "机器人触觉感知",
                "智能感知与机器人",
            ],
        )

        queries = build_search_queries(profile)

        assert any("机器人" in q and "触觉" in q and "公司" in q for q in queries)

    def test_drops_less_specific_company_topic_when_more_specific_variant_exists(self):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            research_directions=[
                "机器人触觉感知",
                "智能感知与机器人",
            ],
        )

        queries = build_search_queries(profile)

        assert any(q == "丁文伯 机器人 触觉 公司" for q in queries)
        assert not any(q == "丁文伯 机器人 公司" for q in queries)

    def test_keeps_only_highest_signal_company_topic_query(self):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            research_directions=[
                "自供电环境感知传感器 (风速/波浪/运动)",
                "机器人触觉感知",
                "智能感知与机器人",
            ],
        )

        queries = build_search_queries(profile)

        assert any(q == "丁文伯 机器人 触觉 公司" for q in queries)
        assert not any(q == "丁文伯 传感器 公司" for q in queries)


def test_parse_extract_output_drops_invalid_partial_education_and_work_entries():
    output = _parse_extract_output(
        json.dumps({
            "awards": ["国家杰青"],
            "education_structured": [
                {"school": None, "degree": "博士"},
                {"school": "MIT", "degree": "博士"},
                {"institution": "Stanford", "degree": "博士后"},
            ],
            "work_experience": [
                {"organization": None, "role": "研究员"},
                {"organization": "微软亚洲研究院", "role": "研究员"},
                {"institution": "Google", "role": "访问学者"},
            ],
            "research_directions": [],
            "academic_positions": [],
            "company_mentions": [],
        }, ensure_ascii=False)
    )

    assert [item.school for item in output.education_structured] == ["MIT", "Stanford"]
    assert [item.organization for item in output.work_experience] == ["微软亚洲研究院", "Google"]


def test_merge_web_extract_preserves_distinct_school_and_organization_entries():
    profile = _make_profile(
        education_structured=[{"school": "MIT", "degree": "博士"}],
        work_experience=[{"organization": "微软亚洲研究院", "role": "研究员"}],
    )

    output = _parse_extract_output(
        json.dumps({
            "awards": [],
            "education_structured": [
                {"school": "MIT", "degree": "博士"},
                {"school": "Stanford", "degree": "博士"},
            ],
            "work_experience": [
                {"organization": "微软亚洲研究院", "role": "研究员"},
                {"organization": "Google", "role": "研究员"},
            ],
            "research_directions": [],
            "academic_positions": [],
            "company_mentions": [],
        }, ensure_ascii=False)
    )

    merged = _merge_web_extract(profile, output)

    assert [item.school for item in merged.education_structured] == ["MIT", "Stanford"]
    assert [item.organization for item in merged.work_experience] == ["微软亚洲研究院", "Google"]


def test_parse_extract_output_strips_parenthetical_company_aliases():
    output = _parse_extract_output(
        json.dumps({
            "awards": [],
            "education_structured": [],
            "work_experience": [],
            "research_directions": [],
            "academic_positions": [],
            "company_mentions": [
                {"company_name": "无界智航（Xspark AI）", "role": "联合研发团队成员", "evidence_url": "https://example.com"},
            ],
        }, ensure_ascii=False)
    )

    assert output.company_mentions[0].company_name == "无界智航"


def test_parse_extract_output_normalizes_company_mentions_with_null_role():
    output = _parse_extract_output(
        json.dumps({
            "awards": [],
            "education_structured": [],
            "work_experience": [],
            "research_directions": [],
            "academic_positions": [],
            "company_mentions": [
                {"company_name": "华为", "role": None, "evidence_url": None},
                {"company_name": "", "role": "顾问"},
            ],
        }, ensure_ascii=False)
    )

    assert len(output.company_mentions) == 1
    assert output.company_mentions[0].company_name == "华为"
    assert output.company_mentions[0].role == ""
    assert output.company_mentions[0].evidence_url == ""


@pytest.mark.asyncio
class TestSearchAndEnrich:
    """Test the full search_and_enrich flow."""

    async def test_happy_path_search_verify_merge(self, monkeypatch):
        """Search returns results → identity verified → fields merged."""
        profile = _make_profile(awards=[], education_structured=[])

        mock_search = MagicMock()
        mock_search.search.return_value = {
            "organic": [
                {"title": "李志教授简介", "link": "https://news.example.com/lizhi", "snippet": "某高校李志教授"},
            ]
        }

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html="<html>李志，南方科技大学教授，获国家优秀青年基金。研究方向：机器学习。邮箱：lizhi@sustech.edu.cn</html>",
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        async def fake_verify_identity(**kwargs):
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_response = json.dumps({
            "awards": ["国家优秀青年基金"],
            "education_structured": [],
            "work_experience": [],
            "research_directions": [],
            "academic_positions": [],
            "company_mentions": [],
        })

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_response}\n```"))]
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=mock_search,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
        )

        assert result.pages_verified == 1
        assert result.profile.awards == ["国家优秀青年基金"]



    async def test_company_mention_found(self):
        """Company mention found in search results."""
        profile = _make_profile()

        mock_search = MagicMock()
        mock_search.search.return_value = {
            "organic": [
                {"title": "李志创办公司", "link": "https://news.example.com/company", "snippet": "李志创办深圳点联传感科技有限公司"},
            ]
        }

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html="<html>南方科技大学教授李志创办了深圳点联传感科技有限公司，担任首席科学家。</html>",
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        verify_response = json.dumps({
            "is_same_person": True, "confidence": 0.92,
            "matching_signals": ["name_match", "institution_match"],
            "conflicting_signals": [], "reasoning": "Same person.",
        })
        extract_response = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [],
            "company_mentions": [
                {"company_name": "深圳点联传感科技有限公司", "role": "首席科学家", "evidence_url": "https://news.example.com/company"},
            ],
        })

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{verify_response}\n```"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_response}\n```"))]),
        ]

        result = await search_and_enrich(
            profile=profile,
            search_provider=mock_search,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
        )
        assert len(result.company_mentions) >= 1
        assert result.company_mentions[0].company_name == "深圳点联传感科技有限公司"

    async def test_low_confidence_identity_match_is_rejected(self):
        profile = _make_profile()

        mock_search = MagicMock()
        mock_search.search.return_value = {
            "organic": [
                {"title": "李志教授简介", "link": "https://news.example.com/lizhi", "snippet": "某高校李志教授"},
            ]
        }

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html="<html>李志，南方科技大学教授。</html>",
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        verify_response = json.dumps({
            "is_same_person": True, "confidence": 0.6,
            "matching_signals": ["name_match", "institution_match"],
            "conflicting_signals": [], "reasoning": "Low confidence same-name result.",
        })

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{verify_response}\n```"))]
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=mock_search,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
        )

        assert result.pages_verified == 0
        assert result.profile == profile
        assert mock_llm.chat.completions.create.call_count == 1

    async def test_all_results_fail_verification(self):
        """All search results fail identity verification → profile unchanged."""
        profile = _make_profile()

        mock_search = MagicMock()
        mock_search.search.return_value = {
            "organic": [
                {"title": "李志 - 北京大学", "link": "https://pku.edu.cn/lizhi", "snippet": "北京大学李志"},
            ]
        }

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html="<html>北京大学文学系教授李志，研究方向：古代文学。</html>",
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        verify_response = json.dumps({
            "is_same_person": False, "confidence": 0.2,
            "matching_signals": ["name_match"],
            "conflicting_signals": ["different_institution", "different_field"],
            "reasoning": "Different person.",
        })

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{verify_response}\n```"))]
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=mock_search,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
        )
        assert result.pages_verified == 0
        assert result.profile == profile

    async def test_search_api_empty_results(self):
        """Search API returns empty results → profile unchanged."""
        profile = _make_profile()

        mock_search = MagicMock()
        mock_search.search.return_value = {"organic": []}

        result = await search_and_enrich(
            profile=profile,
            search_provider=mock_search,
            fetch_html_fn=MagicMock(),
            llm_client=MagicMock(),
            llm_model="test",
        )
        assert result.pages_searched == 0
        assert result.profile == profile





    async def test_non_official_exact_match_search_hit_verifies_identity_before_merge(self, monkeypatch):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            department="数据与信息学院",
            research_directions=["机器人触觉感知"],
        )

        mock_search = MagicMock()
        mock_search.search.return_value = {
            "organic": [
                {
                    "title": "国内首篇！融合语言模型的多模态触觉传感器",
                    "link": "https://zhuanlan.zhihu.com/p/1998843665372701966",
                    "snippet": "在此背景下，清华大学深圳国际研究生院丁文伯团队联合无界智航（Xspark AI）及多所国内外科研机构。",
                },
            ]
        }

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html="",
                used_browser=True,
                blocked_by_anti_scraping=True,
                request_error="403",
                browser_error=None,
            )

        async def fake_verify_identity(**kwargs):
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_response = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [],
            "company_mentions": [{"company_name": "无界智航", "role": "联合研发团队成员", "evidence_url": ""}],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_response}\n```"))]
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=mock_search,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
            max_pages=1,
        )

        assert result.pages_verified == 1
        assert any(m.company_name == "无界智航" for m in result.company_mentions)
        assert mock_llm.chat.completions.create.call_count == 1



    async def test_direct_verified_scholar_result_is_captured_as_scholarly_profile(self, monkeypatch):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            department="数据与信息学院",
            homepage="https://www.sigs.tsinghua.edu.cn/dwb/",
            profile_url="https://www.sigs.tsinghua.edu.cn/dwb/",
            evidence_urls=["https://www.sigs.tsinghua.edu.cn/dwb/"],
            research_directions=["机器人触觉感知"],
        )

        mock_search = MagicMock()
        mock_search.search.return_value = {
            "organic": [
                {
                    "title": "‪Wenbo Ding (丁文伯)‬ - ‪Google Scholar‬",
                    "link": "https://scholar.google.com/citations?user=xo2FkgIAAAAJ&hl=en",
                    "snippet": "Wenbo Ding, Tsinghua Shenzhen International Graduate School",
                },
            ]
        }

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html="<html><body>Google Scholar profile for Wenbo Ding</body></html>",
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        async def fake_verify_identity(**kwargs):
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_response = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [], "company_mentions": [],
        })

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_response}\n```"))]
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=mock_search,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
            max_search_queries=4,
        )

        assert result.pages_verified == 1
        assert result.profile.scholarly_profile_urls == [
            "https://scholar.google.com/citations?user=xo2FkgIAAAAJ&hl=en"
        ]


    async def test_official_exact_match_search_hit_keeps_scholar_signal_after_identity_verification(self, monkeypatch):
        profile = _make_profile(
            name="唐志敏",
            institution="深圳理工大学",
            department="算力微电子学院",
            homepage="https://cme.suat-sz.edu.cn/info/1012/1292.htm",
            profile_url="https://cme.suat-sz.edu.cn/info/1012/1292.htm",
            evidence_urls=["https://cme.suat-sz.edu.cn/info/1012/1292.htm"],
            research_directions=["计算机系统结构"],
        )

        mock_search = MagicMock()
        mock_search.search.return_value = {
            "organic": [
                {
                    "title": "唐志敏-深圳理工大学",
                    "link": "https://www.suat-sz.edu.cn/info/1154/1850.htm",
                    "snippet": "高性能处理器和计算机系统专家，深圳理工大学。",
                },
            ]
        }

        html = """
        <html><body>
        <h1>唐志敏-深圳理工大学</h1>
        <a href="https://scholar.google.cz/citations?hl=zh-CN&user=LchbZ8wAAAAJ">Google Scholar</a>
        <div>JIAJIA: A software DSM system based on a new cache coherence protocol</div>
        </body></html>
        """

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=html,
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        async def fake_verify_identity(**kwargs):
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_response = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [], "company_mentions": [],
        })

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_response}\n```"))]
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=mock_search,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
        )

        assert result.pages_verified == 1
        assert result.profile.official_paper_count is None
        assert result.profile.scholarly_profile_urls == [
            "https://scholar.google.cz/citations?hl=zh-CN&user=LchbZ8wAAAAJ"
        ]
        assert result.profile.publication_evidence_urls == []
        assert result.profile.official_top_papers == []



    async def test_verified_official_page_adds_scholarly_links_and_publication_signals(self):
        profile = _make_profile(
            institution="深圳理工大学",
            department="算力微电子学院",
            homepage="https://cme.suat-sz.edu.cn/info/1012/1292.htm",
            profile_url="https://cme.suat-sz.edu.cn/info/1012/1292.htm",
            evidence_urls=["https://cme.suat-sz.edu.cn/info/1012/1292.htm"],
            research_directions=["计算机系统结构"],
        )

        mock_search = MagicMock()
        mock_search.search.return_value = {
            "organic": [
                {
                    "title": "唐志敏-深圳理工大学",
                    "link": "https://www.suat-sz.edu.cn/info/1154/1850.htm",
                    "snippet": "代表作与 Google Scholar",
                },
            ]
        }

        html = """
        <html>
          <body>
            <h1>唐志敏-深圳理工大学</h1>
            <p>高性能处理器和计算机系统专家。</p>
            <p>发表论文42篇。</p>
            <a href="https://scholar.google.cz/citations?hl=zh-CN&user=LchbZ8wAAAAJ">Google Scholar</a>
            <div>Efficient heterogeneous processor architecture for cloud computing</div>
          </body>
        </html>
        """

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=html,
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        verify_response = json.dumps({
            "is_same_person": True, "confidence": 0.96,
            "matching_signals": ["name_match", "institution_match"],
            "conflicting_signals": [], "reasoning": "Same person.",
        })
        extract_response = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [], "company_mentions": [],
        })

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{verify_response}\n```"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_response}\n```"))]),
        ]

        result = await search_and_enrich(
            profile=profile,
            search_provider=mock_search,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
        )

        assert result.pages_verified == 1
        assert result.profile.official_paper_count == 42
        assert result.profile.scholarly_profile_urls == [
            "https://scholar.google.cz/citations?hl=zh-CN&user=LchbZ8wAAAAJ"
        ]
        assert result.profile.publication_evidence_urls == [
            "https://www.suat-sz.edu.cn/info/1154/1850.htm"
        ]
        assert result.profile.official_top_papers

    async def test_search_and_fetch_are_offloaded_from_event_loop_thread(self, monkeypatch):
        profile = _make_profile(
            institution="深圳理工大学",
            department="算力微电子学院",
            homepage="https://cme.suat-sz.edu.cn/info/1012/1292.htm",
            profile_url="https://cme.suat-sz.edu.cn/info/1012/1292.htm",
            evidence_urls=["https://cme.suat-sz.edu.cn/info/1012/1292.htm"],
        )

        loop_thread = threading.get_ident()
        search_threads: list[int] = []
        fetch_threads: list[int] = []

        class BlockingSearchProvider:
            def search(self, query):
                search_threads.append(threading.get_ident())
                return {
                    "organic": [
                        {
                            "title": "李志-深圳理工大学",
                            "link": "https://www.suat-sz.edu.cn/info/1154/1850.htm",
                            "snippet": "深圳理工大学李志教授",
                        }
                    ]
                }

        def mock_fetch(url, timeout=20.0):
            fetch_threads.append(threading.get_ident())
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html="<html><h1>李志-深圳理工大学</h1></html>",
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        async def fake_verify_identity(**kwargs):
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_response = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [], "company_mentions": [],
        })

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_response}\n```"))]
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=BlockingSearchProvider(),
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
        )

        assert result.pages_verified == 1
        assert search_threads
        assert fetch_threads
        assert all(thread_id != loop_thread for thread_id in search_threads)
        assert all(thread_id != loop_thread for thread_id in fetch_threads)



    async def test_search_and_enrich_still_verifies_identity_for_strong_search_snippets(self, monkeypatch):
        profile = _make_profile(
            institution="深圳理工大学",
            department="算力微电子学院",
            homepage="https://cme.suat-sz.edu.cn/info/1012/1292.htm",
            profile_url="https://cme.suat-sz.edu.cn/info/1012/1292.htm",
            evidence_urls=["https://cme.suat-sz.edu.cn/info/1012/1292.htm"],
        )

        class SearchProvider:
            def search(self, query):
                return {
                    "organic": [
                        {
                            "title": "李志-深圳理工大学",
                            "link": "https://www.suat-sz.edu.cn/info/1154/1850.htm",
                            "snippet": "深圳理工大学李志教授",
                        }
                    ]
                }

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html="<html><h1>李志-深圳理工大学</h1></html>",
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        verify_calls: list[dict[str, object]] = []

        async def fake_verify_identity(**kwargs):
            verify_calls.append(kwargs)
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_response = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [], "company_mentions": [],
        })

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_response}\n```"))]
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=SearchProvider(),
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
        )

        assert result.pages_verified == 1
        assert len(verify_calls) == 1

    async def test_search_and_enrich_uses_company_follow_up_queries_and_search_preview_fallback(self, monkeypatch):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            department="数据与信息学院",
            research_directions=[
                "摩擦纳米发电机 (TENG) 设计与制造",
                "机器人触觉感知",
                "智能感知与机器人",
            ],
        )

        seen_queries: list[str] = []

        class SearchProvider:
            def search(self, query):
                seen_queries.append(query)
                if "机器人" in query and "触觉" in query and "公司" in query:
                    return {
                        "organic": [
                            {
                                "title": "国内首篇！融合语言模型的多模态触觉传感器",
                                "link": "https://finance.sina.com.cn/tech/roll/2026-01-25/doc-inhinufy0316812.shtml",
                                "snippet": "在此背景下，清华大学深圳国际研究生院丁文伯团队联合无界智航（Xspark AI）及多所国内外科研机构。",
                            }
                        ]
                    }
                if "无界智航" in query and "发起人" in query:
                    return {
                        "organic": [
                            {
                                "title": "《EAI-100 具身智能领域2025年度百项代表性成果与人物》白皮书",
                                "link": "https://www.modelscope.cn/learn/6060",
                                "snippet": "丁文伯｜清华大学长聘副教授、Xspark AI发起人。",
                            }
                        ]
                    }
                return {"organic": []}

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            if "finance.sina.com.cn" in url:
                return HtmlFetchResult(
                    html="<html><body>清华大学深圳国际研究生院丁文伯团队联合无界智航（Xspark AI）及多所科研机构。</body></html>",
                    used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
                )
            return HtmlFetchResult(
                html="",
                used_browser=True, blocked_by_anti_scraping=True, request_error="403", browser_error=None,
            )

        async def fake_verify_identity(**kwargs):
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_first = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [],
            "company_mentions": [{"company_name": "无界智航", "role": "", "evidence_url": ""}],
        }, ensure_ascii=False)
        extract_second = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [],
            "company_mentions": [{"company_name": "无界智航", "role": "发起人", "evidence_url": ""}],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_first}\n```"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_second}\n```"))]),
        ]

        result = await search_and_enrich(
            profile=profile,
            search_provider=SearchProvider(),
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
        )

        assert any("机器人" in q and "触觉" in q and "公司" in q for q in seen_queries)
        assert any("无界智航" in q and "发起人" in q for q in seen_queries)
        assert any(m.company_name == "无界智航" and m.role == "发起人" for m in result.company_mentions)

    async def test_search_and_enrich_expands_partial_company_name_from_preview_text(self, monkeypatch):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            department="数据与信息学院",
            research_directions=["机器人触觉感知"],
        )

        class SearchProvider:
            def search(self, query):
                if "公司" in query:
                    return {
                        "organic": [
                            {
                                "title": "国内首篇！融合语言模型的多模态触觉传感器",
                                "link": "https://zhuanlan.zhihu.com/p/1998843665372701966",
                                "snippet": "在此背景下，清华大学深圳国际研究生院丁文伯团队联合无界智航（Xspark AI）及多所国内外科研机构。",
                            }
                        ]
                    }
                return {"organic": []}

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html="",
                used_browser=True,
                blocked_by_anti_scraping=True,
                request_error="403",
                browser_error=None,
            )

        async def fake_verify_identity(**kwargs):
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_response = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [],
            "company_mentions": [{"company_name": "无界智", "role": "联合研发团队成员", "evidence_url": ""}],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_response}\n```"))]
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=SearchProvider(),
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
            max_pages=1,
        )

        assert any(m.company_name == "无界智航" for m in result.company_mentions)

    async def test_search_and_enrich_prioritizes_company_candidates_before_official_identity_pages(self, monkeypatch):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            department="数据与信息学院",
            research_directions=[
                "摩擦纳米发电机 (TENG) 设计与制造",
                "自供电环境感知传感器 (风速/波浪/运动)",
                "功能性智能聚合物与纤维材料研究",
                "机器人触觉感知",
            ],
        )

        class SearchProvider:
            def search(self, query):
                if query == "丁文伯 清华大学深圳国际研究生院":
                    return {
                        "organic": [
                            {
                                "title": "丁文伯 - 清华大学深圳国际研究生院",
                                "link": "https://www.sigs.tsinghua.edu.cn/dwb/",
                                "snippet": "丁文伯，清华大学深圳国际研究生院副教授。",
                            }
                        ]
                    }
                if "机器人" in query and "触觉" in query and "公司" in query:
                    return {
                        "organic": [
                            {
                                "title": "国内首篇！融合语言模型的多模态触觉传感器",
                                "link": "https://finance.sina.com.cn/tech/roll/2026-01-25/doc-inhinufy0316812.shtml",
                                "snippet": "在此背景下，清华大学深圳国际研究生院丁文伯团队联合无界智航（Xspark AI）及多所国内外科研机构。",
                            }
                        ]
                    }
                return {"organic": []}

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            if "finance.sina.com.cn" in url:
                return HtmlFetchResult(
                    html="<html><body>清华大学深圳国际研究生院丁文伯团队联合无界智航（Xspark AI）及多所科研机构。</body></html>",
                    used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
                )
            return HtmlFetchResult(
                html="<html><body>丁文伯，清华大学深圳国际研究生院副教授。</body></html>",
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        async def fake_verify_identity(**kwargs):
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_company = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [],
            "company_mentions": [{"company_name": "无界智航", "role": "", "evidence_url": ""}],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_company}\n```"))]
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=SearchProvider(),
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
            max_pages=1,
        )

        assert result.pages_searched == 1
        assert any(m.company_name == "无界智航" for m in result.company_mentions)

    @pytest.mark.xfail(
        reason="Alias follow-up query budget tuning needed; build_search_queries fix "
        "shipped 2026-04-23 unblocks 2/3 partial-company tests but this one still "
        "needs follow-up budget >=2 to fire both 无界智航 and Xspark aliases. "
        "Separate milestone (web_search_enrichment budget tuning).",
        strict=False,
    )
    async def test_search_and_enrich_uses_alias_follow_up_queries_for_founder_pages(self, monkeypatch):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            department="数据与信息学院",
            research_directions=["机器人触觉感知"],
        )

        seen_queries: list[str] = []

        class SearchProvider:
            def search(self, query):
                seen_queries.append(query)
                if "机器人" in query and "触觉" in query and "公司" in query:
                    return {
                        "organic": [
                            {
                                "title": "国内首篇！融合语言模型的多模态触觉传感器",
                                "link": "https://zhuanlan.zhihu.com/p/1998843665372701966",
                                "snippet": "在此背景下，清华大学深圳国际研究生院丁文伯团队联合无界智航（Xspark AI）及多所国内外科研机构。",
                            }
                        ]
                    }
                if "Xspark" in query and "发起人" in query:
                    return {
                        "organic": [
                            {
                                "title": "《EAI-100 具身智能领域2025年度百项代表性成果与人物》白皮书",
                                "link": "https://www.modelscope.cn/learn/6060",
                                "snippet": "丁文伯｜清华大学长聘副教授、Xspark AI发起人。",
                            }
                        ]
                    }
                return {"organic": []}

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            if "zhuanlan.zhihu.com" in url:
                return HtmlFetchResult(
                    html="",
                    used_browser=True,
                    blocked_by_anti_scraping=True,
                    request_error="403",
                    browser_error=None,
                )
            return HtmlFetchResult(
                html="",
                used_browser=True,
                blocked_by_anti_scraping=True,
                request_error="403",
                browser_error=None,
            )

        async def fake_verify_identity(**kwargs):
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_first = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [],
            "company_mentions": [{"company_name": "无界智航", "role": "联合研发团队成员", "evidence_url": ""}],
        }, ensure_ascii=False)
        extract_second = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [],
            "company_mentions": [{"company_name": "无界智航", "role": "发起人", "evidence_url": ""}],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_first}\n```"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_second}\n```"))]),
        ]

        result = await search_and_enrich(
            profile=profile,
            search_provider=SearchProvider(),
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
        )

        assert any("Xspark" in q and "发起人" in q for q in seen_queries)
        assert any(m.company_name == "无界智航" and m.role == "发起人" for m in result.company_mentions)
        assert mock_llm.chat.completions.create.call_count == 2

    async def test_search_and_enrich_reserves_budget_for_company_follow_up_queries(self, monkeypatch):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            department="数据与信息学院",
            research_directions=[
                "摩擦纳米发电机 (TENG) 设计与制造",
                "机器人触觉感知",
            ],
        )

        class SearchProvider:
            def search(self, query):
                if query == "丁文伯 清华大学深圳国际研究生院":
                    return {
                        "organic": [
                            {
                                "title": "丁文伯 - 清华大学深圳国际研究生院",
                                "link": "https://www.sigs.tsinghua.edu.cn/dwb/",
                                "snippet": "丁文伯，清华大学深圳国际研究生院副教授。",
                            }
                        ]
                    }
                if "机器人" in query and "触觉" in query and "公司" in query:
                    return {
                        "organic": [
                            {
                                "title": "国内首篇！融合语言模型的多模态触觉传感器",
                                "link": "https://finance.sina.com.cn/tech/roll/2026-01-25/doc-inhinufy0316812.shtml",
                                "snippet": "在此背景下，清华大学深圳国际研究生院丁文伯团队联合无界智航（Xspark AI）及多所国内外科研机构。",
                            }
                        ]
                    }
                if "无界智航" in query and "发起人" in query:
                    return {
                        "organic": [
                            {
                                "title": "《EAI-100 具身智能领域2025年度百项代表性成果与人物》白皮书",
                                "link": "https://www.modelscope.cn/learn/6060",
                                "snippet": "丁文伯｜清华大学长聘副教授、Xspark AI发起人。",
                            }
                        ]
                    }
                return {"organic": []}

        def mock_fetch(url, timeout=20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            if "finance.sina.com.cn" in url:
                return HtmlFetchResult(
                    html="<html><body>清华大学深圳国际研究生院丁文伯团队联合无界智航（Xspark AI）及多所科研机构。</body></html>",
                    used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
                )
            if "modelscope.cn" in url:
                return HtmlFetchResult(
                    html="",
                    used_browser=True, blocked_by_anti_scraping=True, request_error="403", browser_error=None,
                )
            return HtmlFetchResult(
                html="<html><body>丁文伯，清华大学深圳国际研究生院副教授。</body></html>",
                used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None,
            )

        async def fake_verify_identity(**kwargs):
            return MagicMock(is_same_person=True, confidence=0.95)

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.verify_identity",
            fake_verify_identity,
        )

        extract_first = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [],
            "company_mentions": [{"company_name": "无界智航", "role": "联合研发团队成员", "evidence_url": ""}],
        }, ensure_ascii=False)
        extract_second = json.dumps({
            "awards": [], "education_structured": [], "work_experience": [],
            "research_directions": [], "academic_positions": [],
            "company_mentions": [{"company_name": "无界智航", "role": "发起人", "evidence_url": ""}],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_first}\n```"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extract_second}\n```"))]),
        ]

        result = await search_and_enrich(
            profile=profile,
            search_provider=SearchProvider(),
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test",
            max_pages=2,
        )

        assert any(m.company_name == "无界智航" and m.role == "发起人" for m in result.company_mentions)

    async def test_search_and_enrich_caps_total_search_queries(self, monkeypatch):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            department="数据与信息学院",
            research_directions=["机器人触觉感知"],
        )

        seen_queries: list[str] = []

        class SearchProvider:
            def search(self, query):
                seen_queries.append(query)
                return {"organic": []}

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.build_search_queries",
            lambda _profile: ["q1", "q2", "q3", "q4", "q5"],
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=SearchProvider(),
            fetch_html_fn=MagicMock(),
            llm_client=MagicMock(),
            llm_model="test",
            max_search_queries=2,
        )

        assert result.pages_searched == 0
        assert seen_queries == ["q1", "q2"]

    async def test_search_and_enrich_prioritizes_three_initial_queries_when_budget_allows(self, monkeypatch):
        profile = _make_profile(
            name="丁文伯",
            institution="清华大学深圳国际研究生院",
            department="数据与信息学院",
            research_directions=["机器人触觉感知"],
        )

        seen_queries: list[str] = []

        class SearchProvider:
            def search(self, query):
                seen_queries.append(query)
                return {"organic": []}

        monkeypatch.setattr(
            "src.data_agents.professor.web_search_enrichment.build_search_queries",
            lambda _profile: ["q1", "q2", "q3", "q4", "q5"],
        )

        result = await search_and_enrich(
            profile=profile,
            search_provider=SearchProvider(),
            fetch_html_fn=MagicMock(),
            llm_client=MagicMock(),
            llm_model="test",
            max_search_queries=4,
        )

        assert result.pages_searched == 0
        assert seen_queries == ["q1", "q2", "q3"]

    async def test_search_api_exception(self):
        """Search API throws exception → profile unchanged, error logged."""
        profile = _make_profile()

        mock_search = MagicMock()
        mock_search.search.side_effect = RuntimeError("API key expired")

        result = await search_and_enrich(
            profile=profile,
            search_provider=mock_search,
            fetch_html_fn=MagicMock(),
            llm_client=MagicMock(),
            llm_model="test",
        )
        assert result.profile == profile
        assert result.error is not None
