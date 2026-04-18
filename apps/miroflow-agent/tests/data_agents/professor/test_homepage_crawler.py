# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for homepage recursive crawler."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.data_agents.professor.homepage_crawler import (
    HomepageCrawlResult,
    HomepageExtractOutput,
    _extract_official_link_targets,
    _extract_official_publication_signals,
    _parse_extraction_output,
    _FetchedPage,
    _sanitize_page_content,
    crawl_homepage,
    extract_same_domain_links,
    filter_relevant_links,
)
from src.data_agents.professor.models import EnrichedProfessorProfile, EducationEntry, WorkEntry


def _make_profile(**kwargs) -> EnrichedProfessorProfile:
    defaults = dict(
        name="李志",
        institution="南方科技大学",
        department=None,
        title=None,
        homepage="https://faculty.sustech.edu.cn/lizhi/",
        profile_url="https://www.sustech.edu.cn/zh/lizhi",
        roster_source="https://www.sustech.edu.cn/zh/letter/",
        extraction_status="structured",
        research_directions=[],
    )
    defaults.update(kwargs)
    return EnrichedProfessorProfile(**defaults)


class TestExtractSameDomainLinks:
    """Test link extraction from HTML."""

    def test_extracts_links_from_same_domain(self):
        html = """
        <html><body>
        <a href="/lizhi/publications.html">Publications</a>
        <a href="/lizhi/cv.html">CV</a>
        <a href="https://external.com/other">External</a>
        </body></html>
        """
        links = extract_same_domain_links(html, "https://faculty.sustech.edu.cn/lizhi/")
        # Should include same-domain links, not external
        assert "https://faculty.sustech.edu.cn/lizhi/publications.html" in links
        assert "https://faculty.sustech.edu.cn/lizhi/cv.html" in links
        assert "https://external.com/other" not in links

    def test_deduplicates_links(self):
        html = """
        <html><body>
        <a href="/page.html">Link 1</a>
        <a href="/page.html">Link 2</a>
        </body></html>
        """
        links = extract_same_domain_links(html, "https://example.com/")
        page_links = [l for l in links if l.endswith("page.html")]
        assert len(page_links) == 1

    def test_excludes_self_link(self):
        html = '<a href="/lizhi/">Home</a>'
        links = extract_same_domain_links(html, "https://faculty.sustech.edu.cn/lizhi/")
        assert "https://faculty.sustech.edu.cn/lizhi/" not in links


class TestFilterRelevantLinks:
    """Test filtering links by relevance keywords."""

    def test_keeps_relevant_links(self):
        links = [
            "https://faculty.sustech.edu.cn/lizhi/publications.html",
            "https://faculty.sustech.edu.cn/lizhi/research.html",
            "https://faculty.sustech.edu.cn/lizhi/contact.html",
        ]
        relevant = filter_relevant_links(links)
        assert "https://faculty.sustech.edu.cn/lizhi/publications.html" in relevant
        assert "https://faculty.sustech.edu.cn/lizhi/research.html" in relevant

    def test_keeps_chinese_keyword_links(self):
        links = [
            "https://faculty.sustech.edu.cn/lizhi/论文.html",
            "https://faculty.sustech.edu.cn/lizhi/获奖.html",
        ]
        relevant = filter_relevant_links(links)
        assert len(relevant) == 2

    def test_limits_to_max_links(self):
        links = [f"https://example.com/paper{i}.html" for i in range(20)]
        relevant = filter_relevant_links(links, max_links=5)
        assert len(relevant) <= 5


def test_parse_extraction_output_drops_invalid_partial_entries():
    output = _parse_extraction_output(
        json.dumps({
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
            "awards": [],
            "academic_positions": [],
        }, ensure_ascii=False)
    )

    assert [item.school for item in output.education_structured] == ["MIT", "Stanford"]
    assert [item.organization for item in output.work_experience] == ["微软亚洲研究院", "Google"]


def test_parse_extraction_output_salvages_first_json_object_from_mixed_output():
    output = _parse_extraction_output(
        """
        thought: inspect the page first
        ```json
        {
          "title": "讲席教授",
          "department": "医学院",
          "research_directions": ["医学影像"],
          "education_structured": [],
          "work_experience": [],
          "awards": [],
          "academic_positions": []
        }
        ```
        trailing note
        {"ignored": true}
        """
    )

    assert output.title == "讲席教授"
    assert output.department == "医学院"
    assert output.research_directions == ["医学影像"]


def test_sanitize_page_content_strips_html_noise():
    html = """
    <html>
      <head>
        <style>.hero { color: red; }</style>
        <script>console.log('debug')</script>
      </head>
      <body>
        <!-- hidden -->
        <h1>吴亚北</h1>
        <div>二维材料研究</div>
      </body>
    </html>
    """

    cleaned = _sanitize_page_content(html)

    assert "吴亚北" in cleaned
    assert "二维材料研究" in cleaned
    assert "<h1>" not in cleaned
    assert "console.log" not in cleaned
    assert ".hero" not in cleaned


def test_extract_official_publication_signals_includes_inline_homepage_titles():
    pages = [
        _FetchedPage(
            url="https://faculty.sustech.edu.cn/wuyb/",
            html="""
            <html><body>
            <h1>吴亚北</h1>
            <p>累计发表研究论文 86 篇。</p>
            <ul>
              <li>Twisted bilayer graphene and emergent phases</li>
              <li>Correlated states in moire superlattices</li>
            </ul>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert signals.paper_count == 86
    assert [paper.title for paper in signals.top_papers] == [
        "Twisted bilayer graphene and emergent phases",
        "Correlated states in moire superlattices",
    ]
    assert signals.evidence_urls == ["https://faculty.sustech.edu.cn/wuyb/"]




def test_extract_official_publication_signals_ignores_resume_lines_on_homepage():
    pages = [
        _FetchedPage(
            url="http://www.sigs.tsinghua.edu.cn/dwb/main.htm",
            html="""
            <html><body>
            <h1>丁文伯</h1>
            <p>Research Area：Signal Processing, Robotics, Human-machine interface, Machine Learning</p>
            <p>2011 - 2016, Ph.D. in Electronic Engineering, Tsinghua University, China</p>
            <p>2007 - 2011, B. Eng. in Electronic Engineering, Tsinghua University, China</p>
            <p>2022 - Present, Associate Professor, Institute of Data and Information, Tsinghua Shenzhen International Graduate School, China</p>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert signals.top_papers == []




def test_extract_official_publication_signals_requires_publication_context_for_homepage_titles():
    pages = [
        _FetchedPage(
            url="http://www.sigs.tsinghua.edu.cn/dwb/main.htm",
            html="""
            <html><body>
            <h1>丁文伯</h1>
            <p>Associate Editor, Diginal Signal Processing: A Review Journal</p>
            <p>Co-Chair, Ubicomp/ISWC’21 CPD Workshop</p>
            <p>Workshop Co-Chair, IEEE SmartGridComm 2019</p>
            <p>Reviewer for over 40 journals and conferences</p>
            <p>Advanced Signal Processing: Methods and Practice (Spring, since 2020)</p>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert signals.top_papers == []


def test_extract_official_publication_signals_keeps_homepage_titles_with_publication_heading():
    pages = [
        _FetchedPage(
            url="https://faculty.sustech.edu.cn/wuyb/",
            html="""
            <html><body>
            <h1>吴亚北</h1>
            <h2>Selected Publications</h2>
            <ul>
              <li>Twisted bilayer graphene and emergent phases</li>
              <li>Correlated states in moire superlattices</li>
            </ul>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert [paper.title for paper in signals.top_papers] == [
        "Twisted bilayer graphene and emergent phases",
        "Correlated states in moire superlattices",
    ]


def test_extract_official_publication_signals_excludes_reviewer_lines_with_publication_heading():
    pages = [
        _FetchedPage(
            url="https://www.sustech.edu.cn/zh/faculties/riwu.html",
            html="""
            <html><body>
            <h1>吴日</h1>
            <h2>代表论文</h2>
            <ul>
              <li>Angew. Chem、Adv. Sci.、Anal. Chem.、J. Phys. Chem. Lett.等期刊审稿人</li>
              <li>Ri Wu#, Despoina Svingou#, Jonas B. Metternich, Renato Zenobi*. Transition Metal Ion FRET-Based Probe to Study Cu(II)-Mediated Amyloid-beta Ligand Binding.</li>
            </ul>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert [paper.title for paper in signals.top_papers] == [
        "Ri Wu#, Despoina Svingou#, Jonas B. Metternich, Renato Zenobi*. Transition Metal Ion FRET-Based Probe to Study Cu(II)-Mediated Amyloid-beta Ligand Binding"
    ]


def test_extract_official_publication_signals_ignores_institute_level_publication_count_pages():
    pages = [
        _FetchedPage(
            url="http://www.sigs.tsinghua.edu.cn/dwb/main.htm",
            html="<html><body><h1>丁文伯</h1></body></html>",
            publication_candidate=False,
        ),
        _FetchedPage(
            url="http://www.sigs.tsinghua.edu.cn/7652/list.htm",
            html="""
            <html><body>
            <strong>科研论文</strong>
            <p>截至至2025年5月，我院共发表SCI论文12322篇、EI论文18868篇，近2021-2025年，我院科研人员作为一作或通讯作者发表的高水平论文持续增长。</p>
            </body></html>
            """,
            publication_candidate=True,
        ),
    ]

    signals = _extract_official_publication_signals(pages)

    assert signals.paper_count is None
    assert signals.evidence_urls == []


def test_extract_official_publication_signals_excludes_footer_copyright_lines():
    pages = [
        _FetchedPage(
            url="https://jianwei.cuhk.edu.cn/teaching.html",
            html="""
            <html><body>
            <h1>Teaching</h1>
            <div>Copyright © 2026 Jianwei Huang. All Rights Reserved. Designed by SmartWebby.com</div>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert signals.top_papers == []


def test_extract_official_publication_signals_keeps_legitimate_title_with_copyright_word():
    pages = [
        _FetchedPage(
            url="https://law.example.edu/faculty/profile",
            html="""
            <html><body>
            <h2>Selected Publications</h2>
            <ul>
              <li>Copyright Law and Digital Innovation in China</li>
            </ul>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert [paper.title for paper in signals.top_papers] == [
        "Copyright Law and Digital Innovation in China"
    ]


def test_extract_official_link_targets_ignores_external_academic_links_on_publication_pages():
    pages = [
        _FetchedPage(
            url="https://faculty.sustech.edu.cn/wuyb/",
            html="""
            <html><body>
            <a href="https://orcid.org/0000-0001-2345-6789">ORCID</a>
            <a href="https://faculty.sustech.edu.cn/wuyb/cv.pdf">CV</a>
            </body></html>
            """,
            publication_candidate=False,
        ),
        _FetchedPage(
            url="https://faculty.sustech.edu.cn/wuyb/publications",
            html="""
            <html><body>
            <a href="https://orcid.org/9999-9999-9999-9999">Coauthor ORCID</a>
            <a href="https://scholar.google.com/citations?user=coauthor">Coauthor Scholar</a>
            </body></html>
            """,
            publication_candidate=True,
        ),
    ]

    scholarly_profile_urls, cv_urls = _extract_official_link_targets(pages)

    assert scholarly_profile_urls == ["https://orcid.org/0000-0001-2345-6789"]
    assert cv_urls == ["https://faculty.sustech.edu.cn/wuyb/cv.pdf"]


@pytest.mark.asyncio
class TestCrawlHomepage:
    """Test the full crawl_homepage function."""

    async def test_happy_path_extracts_from_homepage_and_subpages(self):
        """Homepage with sub-links: extracts education + awards from sub-pages."""
        main_html = """
        <html><body>
        <h1>李志教授</h1>
        <a href="/lizhi/publications.html">Publications</a>
        <a href="/lizhi/cv.html">CV</a>
        </body></html>
        """
        sub_html = "<html><body>2015-2019 PhD MIT Computer Science</body></html>"

        llm_response = json.dumps({
            "name_en": "Zhi Li",
            "title": "教授",
            "department": "计算机科学与工程系",
            "research_directions": ["机器学习", "计算机视觉"],
            "education_structured": [
                {"school": "MIT", "degree": "PhD", "field": "Computer Science", "start_year": 2015, "end_year": 2019}
            ],
            "work_experience": [],
            "awards": ["国家优秀青年基金"],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(html=main_html if "lizhi/" == url.split("/")[-1] + "/" or url.endswith("lizhi/") else sub_html, used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None)

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile()
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en == "Zhi Li"
        assert result.profile.title == "教授"
        assert result.profile.department == "计算机科学与工程系"
        assert "机器学习" in result.profile.research_directions
        assert len(result.profile.education_structured) == 1
        assert result.profile.education_structured[0].school == "MIT"
        assert "国家优秀青年基金" in result.profile.awards

    async def test_recovers_structured_research_directions_when_llm_omits_them(self):
        main_html = """
        <html><body>
        <h1>靳玉乐</h1>
        <table>
          <tr>
            <th>研究领域</th>
            <td>课程思政、 高等教育治理</td>
          </tr>
          <tr>
            <th>职称</th>
            <td>教授</td>
          </tr>
        </table>
        </body></html>
        """

        llm_response = json.dumps({
            "title": "教授",
            "department": "教育学部",
            "research_directions": [],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="靳玉乐",
            institution="深圳大学",
            department="教育学部",
            homepage="https://faculty.szu.edu.cn/jinyule/",
            profile_url="https://faculty.szu.edu.cn/jinyule/",
        )

        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.research_directions == ["课程思政", "高等教育治理"]

    async def test_collects_official_publication_signals_from_anchor_text_and_subpage(self):
        main_html = """
        <html><body>
        <h1>陈伟津</h1>
        <a href="/teacher/162/publications">科研成果</a>
        <a href="/teacher/162/cv">简历</a>
        <p>累计发表研究论文 86 篇。</p>
        </body></html>
        """
        publication_html = """
        <html><body>
        <ul>
          <li>Microstructure-mediated phase transition mechanics in ferroic materials</li>
          <li>Elastic coupling in metal-insulator transition functional ceramics</li>
        </ul>
        </body></html>
        """
        cv_html = "<html><body>中山大学 材料学院</body></html>"

        llm_response = json.dumps({
            "title": "教授",
            "department": "材料学院",
            "research_directions": ["功能材料"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            payload = main_html
            if url.endswith("/publications"):
                payload = publication_html
            elif url.endswith("/cv"):
                payload = cv_html
            return HtmlFetchResult(
                html=payload,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="陈伟津",
            institution="中山大学（深圳）",
            department="材料学院",
            homepage="http://materials.sysu.edu.cn/teacher/162",
            profile_url="http://materials.sysu.edu.cn/teacher/162",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.publication_evidence_urls == [
            "http://materials.sysu.edu.cn/teacher/162",
            "http://materials.sysu.edu.cn/teacher/162/publications",
        ]
        assert result.profile.official_paper_count == 86
        assert [paper.title for paper in result.profile.official_top_papers] == [
            "Microstructure-mediated phase transition mechanics in ferroic materials",
            "Elastic coupling in metal-insulator transition functional ceramics",
        ]

    async def test_recurses_from_official_profile_to_llm_selected_personal_homepage_and_publication_page(self):
        pages = {
            "https://sai.cuhk.edu.cn/teacher/104": """
            <html><body>
            <h1>NAKAMURA, Satoshi</h1>
            <a href="https://satoshi.example.com/">个人主页</a>
            <a href="https://orcid.org/0000-0001-7223-1754">ORCID</a>
            </body></html>
            """,
            "https://satoshi.example.com/": """
            <html><body>
            <h1>Satoshi Nakamura</h1>
            <a href="/publications.html">Publications</a>
            </body></html>
            """,
            "https://satoshi.example.com/publications.html": """
            <html><body>
            <p>累计发表研究论文 86 篇。</p>
            <ul>
              <li>Transllama: LLM-based simultaneous translation system</li>
              <li>LLaST: Improved End-to-end Speech Translation System Leveraged by Large Language Models</li>
            </ul>
            </body></html>
            """,
        }

        link_plan_response = json.dumps({
            "links": [
                {
                    "url": "https://satoshi.example.com/",
                    "category": "personal_homepage",
                    "priority": 1,
                    "should_follow": True,
                    "reason": "官方页明确给出个人主页",
                }
            ]
        }, ensure_ascii=False)
        extraction_response = json.dumps({
            "title": "校长讲座教授",
            "department": "人工智能学院",
            "research_directions": ["语音与自然语言处理"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        }, ensure_ascii=False)

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=pages[url],
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="```json\n" + link_plan_response + "\n```"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content="```json\n" + extraction_response + "\n```"))]),
        ]

        profile = _make_profile(
            name="NAKAMURA, Satoshi",
            institution="香港中文大学（深圳）",
            department="人工智能学院",
            homepage="https://sai.cuhk.edu.cn/teacher/104",
            profile_url="https://sai.cuhk.edu.cn/teacher/104",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.pages_fetched == 3
        assert result.profile.scholarly_profile_urls == [
            "https://orcid.org/0000-0001-7223-1754"
        ]
        assert result.profile.publication_evidence_urls == [
            "https://satoshi.example.com/publications.html"
        ]
        assert result.profile.official_paper_count == 86
        assert [paper.title for paper in result.profile.official_top_papers] == [
            "Transllama: LLM-based simultaneous translation system",
            "LLaST: Improved End-to-end Speech Translation System Leveraged by Large Language Models",
        ]

    async def test_only_follows_llm_selected_anchored_targets_from_official_page(self):
        pages = {
            "https://official.example.edu/faculty/alice": """
                <html><body>
                <h1>Alice Zhang</h1>
                <a href="https://alice.example.com">个人主页</a>
                <a href="/research/platform.html">科研平台</a>
                </body></html>
            """,
            "https://alice.example.com": """
                <html><body>
                <h1>Alice Zhang</h1>
                <p>研究方向：智能感知</p>
                <a href="/publications.html">Publications</a>
                </body></html>
            """,
            "https://alice.example.com/publications.html": """
                <html><body>
                <p>发表论文86篇</p>
                <ul>
                  <li>Learning Systems for Intelligent Sensing at Scale</li>
                </ul>
                </body></html>
            """,
            "https://official.example.edu/research/platform.html": """
                <html><body>
                <h1>科研平台</h1>
                <p>这不是教师个人主页。</p>
                </body></html>
            """,
        }

        link_plan_response = json.dumps({
            "links": [
                {
                    "url": "https://alice.example.com",
                    "category": "personal_homepage",
                    "priority": 1,
                    "should_follow": True,
                    "reason": "官方详情页明确给出个人主页。",
                },
                {
                    "url": "https://official.example.edu/research/platform.html",
                    "category": "ignore",
                    "priority": 5,
                    "should_follow": False,
                    "reason": "学院科研平台，不是教师本人页面。",
                },
            ]
        }, ensure_ascii=False)
        extraction_response = json.dumps({
            "title": "教授",
            "department": "人工智能学院",
            "research_directions": ["智能感知"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        }, ensure_ascii=False)

        fetched_urls: list[str] = []

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            fetched_urls.append(url)
            return HtmlFetchResult(
                html=pages[url],
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{link_plan_response}\n```"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extraction_response}\n```"))]),
        ]

        profile = _make_profile(
            name="Alice Zhang",
            institution="测试大学",
            department="人工智能学院",
            homepage="https://official.example.edu/faculty/alice",
            profile_url="https://official.example.edu/faculty/alice",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert fetched_urls == [
            "https://official.example.edu/faculty/alice",
            "https://alice.example.com",
            "https://alice.example.com/publications.html",
        ]
        assert "https://official.example.edu/research/platform.html" not in result.profile.evidence_urls
        assert "https://alice.example.com" in result.profile.evidence_urls
        assert result.profile.publication_evidence_urls == [
            "https://alice.example.com/publications.html"
        ]
        assert result.profile.official_paper_count == 86

    async def test_planning_failure_does_not_fallback_to_external_personal_homepage(self):
        pages = {
            "https://official.example.edu/faculty/alice": """
                <html><body>
                <h1>Alice Zhang</h1>
                <a href="https://alice.example.com">个人主页</a>
                </body></html>
            """,
            "https://alice.example.com": """
                <html><body>
                <h1>Alice Zhang</h1>
                <p>这个外部主页不应该在规划失败时被自动跟进。</p>
                </body></html>
            """,
        }
        extraction_response = json.dumps({
            "title": "教授",
            "department": "人工智能学院",
            "research_directions": ["智能感知"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        }, ensure_ascii=False)

        fetched_urls: list[str] = []

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            fetched_urls.append(url)
            return HtmlFetchResult(
                html=pages[url],
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content='not valid json'))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extraction_response}\n```"))]),
        ]

        profile = _make_profile(
            name="Alice Zhang",
            institution="测试大学",
            department="人工智能学院",
            homepage="https://official.example.edu/faculty/alice",
            profile_url="https://official.example.edu/faculty/alice",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert fetched_urls == ["https://official.example.edu/faculty/alice"]
        assert "https://alice.example.com" not in result.profile.evidence_urls

    async def test_link_planner_receives_official_cv_and_academic_profile_candidates(self):
        main_html = """
        <html><body>
        <h1>李海文</h1>
        <a href="https://dblp.org/pid/12/3456.html">DBLP</a>
        <a href="/files/lihw_cv.pdf">Curriculum Vitae</a>
        </body></html>
        """
        link_plan_response = json.dumps({
            "links": [
                {
                    "url": "https://dblp.org/pid/12/3456.html",
                    "category": "academic_profile",
                    "priority": 1,
                    "should_follow": True,
                    "reason": "官方页给出的学术档案。",
                },
                {
                    "url": "https://ae.sysu.edu.cn/files/lihw_cv.pdf",
                    "category": "cv",
                    "priority": 2,
                    "should_follow": True,
                    "reason": "官方页给出的教师简历。",
                },
            ]
        }, ensure_ascii=False)
        extraction_response = json.dumps({
            "title": "教授",
            "department": "先进能源学院",
            "research_directions": ["能源材料"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        }, ensure_ascii=False)

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{link_plan_response}\n```"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extraction_response}\n```"))]),
        ]

        profile = _make_profile(
            name="李海文",
            institution="中山大学（深圳）",
            department="先进能源学院",
            homepage="https://ae.sysu.edu.cn/teacher/lihw",
            profile_url="https://ae.sysu.edu.cn/teacher/lihw",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        planner_prompt = mock_llm.chat.completions.create.call_args_list[0].kwargs["messages"][1]["content"]
        assert "https://dblp.org/pid/12/3456.html" in planner_prompt
        assert "https://ae.sysu.edu.cn/files/lihw_cv.pdf" in planner_prompt
        assert result.profile.scholarly_profile_urls == [
            "https://dblp.org/pid/12/3456.html"
        ]
        assert result.profile.cv_urls == [
            "https://ae.sysu.edu.cn/files/lihw_cv.pdf"
        ]
        assert result.pages_fetched == 1

    async def test_collects_official_orcid_and_cv_links_from_profile_page(self):
        main_html = """
        <html><body>
        <h1>李海文</h1>
        <a href="https://orcid.org/0000-0001-7223-1754">ORCID</a>
        <a href="/files/cv.pdf">CV</a>
        </body></html>
        """

        llm_response = json.dumps({
            "title": "教授",
            "department": "先进能源学院",
            "research_directions": ["能源材料"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="李海文",
            institution="中山大学（深圳）",
            department="先进能源学院",
            homepage="https://ae.sysu.edu.cn/teacher/lihw",
            profile_url="https://ae.sysu.edu.cn/teacher/lihw",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.scholarly_profile_urls == [
            "https://orcid.org/0000-0001-7223-1754"
        ]
        assert result.profile.cv_urls == [
            "https://ae.sysu.edu.cn/files/cv.pdf"
        ]

    async def test_extracts_main_page_paper_count_and_narrative_research_direction(self):
        main_html = """
        <html><body>
        <h1>李慧云</h1>
        <p>李慧云，英国剑桥大学计算机系博士，现为深理工算力院副院长。</p>
        <p>长期从事高性能集成电路芯片设计与系统应用。发表了100余篇学术论文，包括高被引文章与优秀学术论文。</p>
        <p>承担国家863计划课题、国家自然科学基金等在内的科研项目数十项。</p>
        </body></html>
        """

        llm_response = json.dumps({
            "title": "副院长",
            "department": "算力微电子学院",
            "research_directions": [],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="李慧云",
            institution="深圳理工大学",
            department="算力微电子学院",
            homepage="https://cme.suat-sz.edu.cn/info/1012/1294.htm",
            profile_url="https://cme.suat-sz.edu.cn/info/1012/1294.htm",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.official_paper_count == 100
        assert result.profile.publication_evidence_urls == [
            "https://cme.suat-sz.edu.cn/info/1012/1294.htm"
        ]
        assert result.profile.research_directions == [
            "高性能集成电路芯片设计与系统应用"
        ]

    async def test_prefers_specific_profile_url_over_generic_homepage_root(self):
        homepage_html = """
        <html><body>
        <h1>深圳理工大学</h1>
        <p>构建跨学科、高水平的科研与人才汇聚平台。</p>
        </body></html>
        """
        profile_html = """
        <html><body>
        <h1>李慧云</h1>
        <p>长期从事高性能集成电路芯片设计与系统应用。发表了100余篇学术论文。</p>
        </body></html>
        """

        llm_response = json.dumps({
            "title": "副院长",
            "department": "算力微电子学院",
            "research_directions": [],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        fetched_urls: list[str] = []

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            fetched_urls.append(url)
            payload = profile_html if url.endswith("/1294.htm") else homepage_html
            return HtmlFetchResult(
                html=payload,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="李慧云",
            institution="深圳理工大学",
            department="算力微电子学院",
            homepage="https://www.suat-sz.edu.cn/",
            profile_url="https://cme.suat-sz.edu.cn/info/1012/1294.htm",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert fetched_urls[0] == "https://cme.suat-sz.edu.cn/info/1012/1294.htm"
        assert result.profile.official_paper_count == 100
        assert result.profile.research_directions == [
            "高性能集成电路芯片设计与系统应用"
        ]

    async def test_prefers_official_profile_url_over_external_research_profile(self):
        external_html = """
        <html><body>
        <h1>ResearchGate</h1>
        <p>External profile shell</p>
        </body></html>
        """
        profile_html = """
        <html><body>
        <h1>包童</h1>
        <p>长期从事生态系统生态学与全球变化生态学研究。发表了56篇学术论文。</p>
        </body></html>
        """

        llm_response = json.dumps({
            "title": "副教授",
            "department": "生态学院",
            "research_directions": [],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        fetched_urls: list[str] = []

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            fetched_urls.append(url)
            payload = profile_html if "eco.sysu.edu.cn" in url else external_html
            return HtmlFetchResult(
                html=payload,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="包童",
            institution="中山大学（深圳）",
            department="生态学院",
            homepage="https://www.researchgate.net/profile/Tong_Bao",
            profile_url="http://eco.sysu.edu.cn/teacher/BaoTong",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert fetched_urls[0] == "http://eco.sysu.edu.cn/teacher/BaoTong"
        assert result.profile.official_paper_count == 56
        assert result.profile.research_directions == [
            "生态系统生态学与全球变化生态学"
        ]

    async def test_prefers_official_profile_url_when_homepage_is_broken_personal_site(self):
        official_profile_html = """
        <html><body>
        <h1>吴日</h1>
        <div>助理教授</div>
        <p>主要从事以生物大分子结构解析为导向的质谱仪器研制与方法学研究。</p>
        <p>近五年，以第一/通讯作者发表20多篇论文，包括J. Am. Chem. Soc.（4）、Nat. Commun.、Anal. Chem.（2）。</p>
        </body></html>
        """

        llm_response = json.dumps({
            "title": "助理教授",
            "department": "先进光源科学中心",
            "research_directions": ["生物大分子结构解析", "质谱仪器研制与方法学研究"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        fetched_urls: list[str] = []

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            fetched_urls.append(url)
            payload = official_profile_html if 'sustech.edu.cn/zh/faculties/riwu.html' in url else ''
            return HtmlFetchResult(
                html=payload,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )


        profile = _make_profile(
            name="吴日",
            institution="南方科技大学",
            department=None,
            homepage="https://faculty.sustech.edu.cn/wuri",
            profile_url="https://www.sustech.edu.cn/zh/faculties/riwu.html",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert fetched_urls[0] == "https://www.sustech.edu.cn/zh/faculties/riwu.html"
        assert result.profile.official_paper_count == 20
        assert "生物大分子结构解析" in result.profile.research_directions
        assert any(
            "质谱仪器研制与方法学研究" in direction
            for direction in result.profile.research_directions
        )

    async def test_filters_llm_selected_sitewide_publication_pages(self):
        homepage_url = "https://www.sustech.edu.cn/zh/faculties/zhouyao.html"
        pages = {
            homepage_url: """
            <html><body>
            <h1>周垚</h1>
            <div>研究助理教授</div>
            <a href="/zh/scientific-achievements.html">科研成果</a>
            <a href="/zh/colleges/index.html">院系总览</a>
            </body></html>
            """,
            "https://www.sustech.edu.cn/zh/scientific-achievements.html": """
            <html><body>
            <h1>科研成果</h1>
            <p>学校累计发表论文 7913 篇。</p>
            <ul><li>Model checking</li></ul>
            </body></html>
            """,
            "https://www.sustech.edu.cn/zh/colleges/index.html": """
            <html><body>
            <h1>院系总览</h1>
            <ul><li>Raul Mario Ures De La Madrid</li></ul>
            </body></html>
            """,
        }

        link_plan_response = json.dumps({
            "links": [
                {
                    "url": "https://www.sustech.edu.cn/zh/scientific-achievements.html",
                    "category": "publication_page",
                    "priority": 1,
                    "should_follow": True,
                    "reason": "科研成果页",
                },
                {
                    "url": "https://www.sustech.edu.cn/zh/colleges/index.html",
                    "category": "publication_page",
                    "priority": 2,
                    "should_follow": True,
                    "reason": "院系列表页",
                },
            ]
        }, ensure_ascii=False)
        extraction_response = json.dumps({
            "title": "研究助理教授",
            "research_directions": ["学生发展"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        }, ensure_ascii=False)

        fetched_urls: list[str] = []

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            fetched_urls.append(url)
            return HtmlFetchResult(
                html=pages[url],
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{link_plan_response}\n```"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extraction_response}\n```"))]),
        ]

        profile = _make_profile(
            name="周垚",
            institution="南方科技大学",
            title="研究助理教授",
            homepage=homepage_url,
            profile_url=homepage_url,
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert fetched_urls == [homepage_url]
        assert result.profile.publication_evidence_urls == []
        assert result.profile.official_paper_count is None
        assert result.profile.official_top_papers == []

    async def test_ignores_low_affinity_sitewide_research_page_counts(self):
        main_html = """
        <html><body>
        <h1>尤政院士</h1>
        <a href="/7652/list.htm">科研成果</a>
        </body></html>
        """
        sitewide_html = """
        <html><body>
        <p>学校累计发表论文 12322 篇。</p>
        </body></html>
        """

        llm_response = json.dumps({
            "research_directions": [],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            payload = main_html if url.endswith("/main.htm") else sitewide_html
            return HtmlFetchResult(
                html=payload,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="尤政院士",
            institution="清华大学深圳国际研究生院",
            homepage="http://www.sigs.tsinghua.edu.cn/yzys/main.htm",
            profile_url="http://www.sigs.tsinghua.edu.cn/yzys/main.htm",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.official_paper_count is None
        assert result.profile.publication_evidence_urls == []

    async def test_falls_back_to_html_english_name_when_llm_omits_name_en(self):
        main_html = """
        <html><body>
        <h1>吴亚北</h1>
        <div class="name-en">Yabei Wu</div>
        </body></html>
        """

        llm_response = json.dumps({
            "title": "教授",
            "department": "物理系",
            "research_directions": ["二维材料"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="吴亚北",
            homepage="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
            profile_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en == "Yabei Wu"

    async def test_reader_metadata_does_not_pollute_name_en_fallback(self):
        main_html = """
        李海洲 | 人工智能学院
        URL Source: https://sai.cuhk.edu.cn/teacher/102
        Published Time: Thu, 02 Apr 2026 08:09:45 GMT
        Markdown Content:
        华南理工大学博士
        人工智能学院院长
        """

        llm_response = json.dumps({
            "research_directions": ["语音识别"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="李海洲",
            institution="香港中文大学（深圳）",
            department="人工智能学院",
            homepage="https://sai.cuhk.edu.cn/teacher/102",
            profile_url="https://sai.cuhk.edu.cn/teacher/102",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en != "All Rights Reserved"

    async def test_name_en_fallback_prefers_repeated_candidate_over_single_coauthors(self):
        main_html = """
        李海洲 | 人工智能学院
        URL Source: https://sai.cuhk.edu.cn/teacher/102
        Published Time: Thu, 02 Apr 2026 08:09:45 GMT
        Markdown Content:
        1. Chenglin Xu, Wei Rao, Eng Siong Chng and Haizhou Li, SpEx: Multi-Scale Time Domain Speaker Extraction Network.
        2. Tomi Kinnunen, Haizhou Li, An overview of text-independent speaker recognition.
        3. Haizhou Li, Bin Ma and Chin-Hui Lee, A Vector Space Modeling Approach to Spoken Language Identification.
        """

        llm_response = json.dumps({
            "research_directions": ["语音识别"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="李海洲",
            institution="香港中文大学（深圳）",
            department="人工智能学院",
            homepage="https://sai.cuhk.edu.cn/teacher/102",
            profile_url="https://sai.cuhk.edu.cn/teacher/102",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en == "Haizhou Li"

    async def test_name_en_fallback_does_not_pick_arbitrary_single_mention_coauthor(self):
        main_html = """
        李海洲 | 人工智能学院
        URL Source: https://sai.cuhk.edu.cn/teacher/102
        Published Time: Thu, 02 Apr 2026 08:09:45 GMT
        Markdown Content:
        1. Chenglin Xu, Wei Rao, Eng Siong Chng, SpEx: Multi-Scale Time Domain Speaker Extraction Network.
        2. Tomi Kinnunen, Kai Yu, An overview of text-independent speaker recognition.
        """

        llm_response = json.dumps({
            "research_directions": ["语音识别"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="李海洲",
            institution="香港中文大学（深圳）",
            department="人工智能学院",
            homepage="https://sai.cuhk.edu.cn/teacher/102",
            profile_url="https://sai.cuhk.edu.cn/teacher/102",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en != "All Rights Reserved"

    async def test_invalid_llm_name_en_institution_phrase_is_dropped(self):
        main_html = """
        黄建华 | 人工智能学院
        曾任Journal of American Statistical Association编委。
        """

        llm_response = json.dumps({
            "name_en": "American Statistical Association",
            "research_directions": ["统计学习"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="黄建华",
            institution="香港中文大学（深圳）",
            department="人工智能学院",
            homepage="https://sai.cuhk.edu.cn/teacher/108",
            profile_url="https://sai.cuhk.edu.cn/teacher/108",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en != "All Rights Reserved"

    async def test_invalid_llm_name_en_subject_phrase_is_dropped(self):
        main_html = """
        黄建华 | 人工智能学院
        Research interests include Applied Statistics and Gaussian processes.
        """

        llm_response = json.dumps({
            "name_en": "Applied Statistics",
            "research_directions": ["统计学习"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="黄建华",
            institution="香港中文大学（深圳）",
            department="人工智能学院",
            homepage="https://sai.cuhk.edu.cn/teacher/108",
            profile_url="https://sai.cuhk.edu.cn/teacher/108",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en != "All Rights Reserved"

    async def test_name_en_fallback_drops_ui_phrase(self):
        main_html = """
        潘毅 | 计算机科学与人工智能学院
        <a href="/teacher/1">View More</a>
        <a href="/teacher/2">View More</a>
        """

        llm_response = json.dumps({
            "research_directions": ["人工智能"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="潘毅",
            institution="深圳理工大学",
            department="计算机科学与人工智能学院",
            homepage="https://csce.suat-sz.edu.cn/teacher/1",
            profile_url="https://csce.suat-sz.edu.cn/teacher/1",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en is None

    async def test_invalid_llm_name_en_falls_back_to_html_candidate_before_url_slug(self):
        main_html = """
        郭烈锦 | 先进能源学院
        Guo Liejin
        Research interests in hydrogen energy and multiphase flow.
        Guo Liejin
        """

        llm_response = json.dumps({
            "name_en": "Gongchang Road",
            "research_directions": ["氢能"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="郭烈锦",
            institution="中山大学（深圳）",
            department="先进能源学院",
            homepage="https://ae.sysu.edu.cn/teacher/GuoLiejin",
            profile_url="https://ae.sysu.edu.cn/teacher/GuoLiejin",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en == "Guo Liejin"

    async def test_invalid_llm_name_en_institution_banner_is_dropped(self):
        main_html = """
        潘毅 | 计算机科学与人工智能学院
        Bio-X International Institute
        """

        llm_response = json.dumps({
            "name_en": "Bio-X International Institute",
            "research_directions": ["人工智能"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="潘毅",
            institution="深圳理工大学",
            department="计算机科学与人工智能学院",
            homepage="https://csce.suat-sz.edu.cn/teacher/1",
            profile_url="https://csce.suat-sz.edu.cn/teacher/1",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en is None

    async def test_invalid_llm_name_en_title_phrase_is_dropped(self):
        main_html = """
        杜鹤民 | 创意设计学院
        Mediated Social Touch
        """

        llm_response = json.dumps({
            "name_en": "Mediated Social Touch",
            "research_directions": ["交互设计"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="杜鹤民",
            institution="深圳技术大学",
            department="创意设计学院",
            homepage="https://design.sztu.edu.cn/teacher/1",
            profile_url="https://design.sztu.edu.cn/teacher/1",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en is None

    async def test_invalid_llm_name_en_design_school_is_dropped(self):
        main_html = """
        杜鹤民 | 创意设计学院
        Central Saint Martins
        """

        llm_response = json.dumps({
            "name_en": "Central Saint Martins",
            "research_directions": ["工业设计"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="杜鹤民",
            institution="深圳技术大学",
            department="创意设计学院",
            homepage="https://design.sztu.edu.cn/teacher/1",
            profile_url="https://design.sztu.edu.cn/teacher/1",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en is None

    async def test_invalid_llm_name_en_art_school_suffix_is_dropped(self):
        main_html = """
        杜鹤民 | 创意设计学院
        Arts London
        """

        llm_response = json.dumps({
            "name_en": "Arts London",
            "research_directions": ["时尚设计"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="杜鹤民",
            institution="深圳技术大学",
            department="创意设计学院",
            homepage="https://design.sztu.edu.cn/teacher/1",
            profile_url="https://design.sztu.edu.cn/teacher/1",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en is None

    async def test_conflicting_llm_name_en_falls_back_to_url_candidate(self):
        main_html = """
        <html><body>
        <h1>周垚</h1>
        <p>华中科技大学管理学博士、经济学学士，研究方向包括学生发展与高等教育院校影响力。</p>
        </body></html>
        """

        llm_response = json.dumps({
            "name_en": "Joseph Sifakis",
            "title": "研究助理教授",
            "research_directions": ["学生发展"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        homepage_url = "https://www.sustech.edu.cn/zh/faculties/zhouyao.html"
        profile = _make_profile(
            name="周垚",
            institution="南方科技大学",
            homepage=homepage_url,
            profile_url=homepage_url,
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en in {"Yao Zhou", "Zhou Yao"}
        assert result.profile.name_en != "Joseph Sifakis"

    async def test_prefers_url_slug_over_unrelated_english_phrase_and_focuses_anchor_bio(self):
        main_html = """
        <html><body>
        <nav>本科招生 人才招聘 科研平台 Educational Development</nav>
        <div class="introduce">
          <div class="message-left fl">
            <span class="font fl">周垚</span>
            <span>研究助理教授</span>
            <span>zhouy2021@sustech.edu.cn</span>
          </div>
          <div class="message-right fr">
            <p>1993年生，云南大理人，华中科技大学管理学博士、经济学学士。主要研究领域包括学生发展、高等教育院校影响力、教师发展等。在 International Journal of Educational Development 发表论文多篇。</p>
          </div>
        </div>
        </body></html>
        """

        llm_response = json.dumps({
            "title": "研究助理教授",
            "research_directions": ["学生发展", "高等教育院校影响力", "教师发展"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        homepage_url = "https://www.sustech.edu.cn/zh/faculties/zhouyao.html"
        profile = _make_profile(
            name="周垚",
            institution="南方科技大学",
            homepage=homepage_url,
            profile_url=homepage_url,
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en in {"Yao Zhou", "Zhou Yao"}
        assert result.profile.official_anchor_profile is not None
        assert "本科招生" not in result.profile.official_anchor_profile.bio_text
        assert "人才招聘" not in result.profile.official_anchor_profile.bio_text


    async def test_invalid_llm_name_en_footer_phrase_is_dropped(self):
        main_html = """
        周垚 | 南方科技大学
        All Rights Reserved
        """

        llm_response = json.dumps({
            "name_en": "All Rights Reserved",
            "research_directions": ["凝聚态物理"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="周垚",
            institution="南方科技大学",
            department=None,
            homepage="https://www.sustech.edu.cn/zh/zhouyao",
            profile_url="https://www.sustech.edu.cn/zh/zhouyao",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en != "All Rights Reserved"

    async def test_invalid_llm_name_en_journal_phrase_is_dropped(self):
        main_html = """
        吴远鹏 | 北京大学深圳研究生院
        Selected publication in Nano Lett.
        """

        llm_response = json.dumps({
            "name_en": "Nano Lett",
            "research_directions": ["纳米材料"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="吴远鹏",
            institution="北京大学深圳研究生院",
            department=None,
            homepage="https://www.pkusz.edu.cn/teacher/1",
            profile_url="https://www.pkusz.edu.cn/teacher/1",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en is None

    async def test_invalid_llm_name_en_abbreviated_journal_phrase_is_dropped(self):
        main_html = """
        吴远鹏 | 北京大学深圳研究生院
        Selected publication in Light Sci.
        """

        llm_response = json.dumps({
            "name_en": "Light Sci",
            "research_directions": ["光电子"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="吴远鹏",
            institution="北京大学深圳研究生院",
            department=None,
            homepage="https://www.pkusz.edu.cn/teacher/1",
            profile_url="https://www.pkusz.edu.cn/teacher/1",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en is None

    async def test_invalid_llm_name_en_journal_title_is_dropped(self):
        main_html = """
        黄建华 | 人工智能学院
        曾任 Statistica Sinica 编委。
        """

        llm_response = json.dumps({
            "name_en": "Statistica Sinica",
            "research_directions": ["统计学"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="黄建华",
            institution="香港中文大学（深圳）",
            department="人工智能学院",
            homepage="https://sai.cuhk.edu.cn/teacher/108",
            profile_url="https://sai.cuhk.edu.cn/teacher/108",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.name_en is None

    async def test_reader_metadata_polluted_title_is_dropped(self):
        main_html = """
        李海洲 | 人工智能学院
        URL Source: https://sai.cuhk.edu.cn/teacher/102
        Published Time: Thu, 02 Apr 2026 08:09:45 GMT
        Markdown Content:
        华南理工大学博士
        人工智能学院院长
        """

        llm_response = json.dumps({
            "title": (
                "李海洲 | 人工智能学院 URL Source: https://sai.cuhk.edu.cn/teacher/102 "
                "Published Time: Thu, 02 Apr 2026 08:09:45 GMT Markdown Content: ..."
            ),
            "research_directions": ["语音识别"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="李海洲",
            institution="香港中文大学（深圳）",
            department="人工智能学院",
            homepage="https://sai.cuhk.edu.cn/teacher/102",
            profile_url="https://sai.cuhk.edu.cn/teacher/102",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.title is None

    async def test_title_trailing_phone_is_stripped(self):
        main_html = """
        陈少川 | 北京大学深圳研究生院
        助理教授 电话：0755-26037691
        """

        llm_response = json.dumps({
            "title": "助理教授 电话：0755-26037691",
            "research_directions": ["材料科学"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(
                html=main_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(
            name="陈少川",
            institution="北京大学深圳研究生院",
            homepage="https://www.pkusz.edu.cn/teacher/1",
            profile_url="https://www.pkusz.edu.cn/teacher/1",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.title == "助理教授"

    async def test_no_homepage_or_profile_url_returns_unchanged(self):
        """Professor without homepage and without profile_url → returns original profile unchanged."""
        profile = _make_profile(homepage=None, profile_url="")
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=MagicMock(),
            llm_client=MagicMock(),
            llm_model="test-model",
        )
        assert not result.success
        assert result.profile == profile
        assert result.pages_fetched == 0

    async def test_homepage_404_returns_unchanged(self):
        """Homepage URL returns 404 → returns original profile unchanged."""
        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(html=None, used_browser=False, blocked_by_anti_scraping=False, request_error="404", browser_error=None)

        profile = _make_profile()
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=MagicMock(),
            llm_model="test-model",
        )
        assert not result.success
        assert result.profile == profile

    async def test_llm_invalid_json_returns_unchanged(self):
        """LLM returns invalid JSON → returns original profile, logs warning."""
        main_html = "<html><body>Faculty page content</body></html>"

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(html=main_html, used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None)

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="not valid json at all"))]
        )

        profile = _make_profile()
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )
        assert not result.success
        assert result.profile == profile

    async def test_does_not_overwrite_existing_fields(self):
        """Existing non-empty fields should not be overwritten by homepage data."""
        main_html = "<html><body>Faculty page</body></html>"

        llm_response = json.dumps({
            "title": "副教授",  # Should NOT overwrite existing
            "department": "物理系",  # Should NOT overwrite existing
            "research_directions": ["量子计算"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(html=main_html, used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None)

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile(title="教授", department="计算机系")
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.title == "教授"  # Kept original
        assert result.profile.department == "计算机系"  # Kept original

    async def test_cleans_extracted_research_directions(self):
        """Extracted research directions should be cleaned via direction_cleaner."""
        main_html = "<html><body>Faculty page</body></html>"

        llm_response = json.dumps({
            "research_directions": ["机器学习 主讲课程：深度学习", "计算机视觉、图像处理"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        })

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult
            return HtmlFetchResult(html=main_html, used_browser=False, blocked_by_anti_scraping=False, request_error=None, browser_error=None)

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
        )

        profile = _make_profile()
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        # "主讲课程" should be truncated, compound split should work
        assert "机器学习" in result.profile.research_directions
        assert "计算机视觉" in result.profile.research_directions
        assert "图像处理" in result.profile.research_directions
