# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for homepage recursive crawler."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.discovery import _should_refresh_cached_html
from src.data_agents.professor.homepage_crawler import (
    _extract_official_link_targets,
    _extract_official_publication_signals,
    _extract_follow_candidate_link_infos,
    _extract_sigs_tab_homepage_output,
    _parse_extraction_output,
    _FetchedPage,
    _sanitize_page_content,
    crawl_homepage,
    extract_same_domain_links,
    filter_relevant_links,
)
from src.data_agents.professor.models import EnrichedProfessorProfile


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


_SIGS_AHMED_TAB_HTML = """
<html><body>
  <div class="teacher_right">
    <h1 class="news_title">Ahmed Elazab</h1>
    <div class="carrer">
      <span class="f5">助理教授</span><span class="dh">，</span><span class="f37">博士生导师</span>
    </div>
    <p class="news_text"><span>邮箱：</span><span class="email">ahmedelazab@sz.tsinghua.edu.cn</span></p>
    <div class="sudy-tab">
      <ul class="tab-menu">
        <li><span>个人简历</span></li>
        <li><span>教学</span></li>
        <li><span>研究领域</span></li>
        <li><span>研究成果</span></li>
        <li><span>奖励荣誉</span></li>
      </ul>
      <ul class="tab-list">
        <li>
          <div class="post" id="jyjl">
            <h3 class="tit"><span class="title">教育经历</span></h3>
            <div class="con"><p>09/2012-01/2017, University of Chinese Academy of Sciences, Pattern Recognition &amp; Intelligent Systems, PhD</p></div>
          </div>
          <div class="post" id="gzjl">
            <h3 class="tit"><span class="title">工作经历</span></h3>
            <div class="con"><p>08/2017 -04/2020, Postdoctoral Fellow, Shenzhen University</p><p>11/2025 – now Assistant Professor, Tsinghua SIGS</p></div>
          </div>
          <div class="post" id="xsjz">
            <h3 class="tit"><span class="title">学术兼职</span></h3>
            <div class="con"><p>1. PeerJ Computer Science, PeerJ Publisher, Academic Editor (June 2020 till now)</p></div>
          </div>
        </li>
        <li></li>
        <li>
          <div class="post" id="yjly">
            <h3 class="tit"><span class="title">研究领域</span></h3>
            <div class="con"><p>My research focuses on developing trustworthy artificial intelligence for medical image analysis, with a special emphasis on brain disease diagnosis and prognosis. I integrate advanced machine and deep learning techniques with multi-modal neuroimaging data fusion to build robust computer-aided detection and diagnosis systems. A core aspect of my work involves applying pattern recognition and neural informatics to uncover disease-specific biomarkers, while simultaneously prioritizing explainable AI to ensure clinical interpretability and trust.</p></div>
          </div>
        </li>
        <li>
          <div class="post" id="dbxlw">
            <h3 class="tit"><span class="title">代表性论文</span></h3>
            <div class="con"><p>1- A. Elazab, C. Wang. Improved Alzheimer's disease diagnosis using multimodal sparse similarity feature selection and auxiliary data, Biomedical Signal Processing and Control, 2026.</p></div>
          </div>
        </li>
        <li>
          <div class="post" id="jxry">
            <h3 class="tit"><span class="title">荣誉奖项</span></h3>
            <div class="con"><p>1. Best paper award of the 2023 International Workshop on Computational Mathematics Modeling in Cancer Analysis, MICCAI (co-author).</p></div>
          </div>
        </li>
      </ul>
    </div>
  </div>
</body></html>
"""


def test_extract_follow_candidate_link_infos_supports_markdown_personal_homepage_links():
    markdown = """
    Title: BRESAR, Miha | 香港中文大学（深圳）数据科学学院
    URL Source: https://sds.cuhk.edu.cn/teacher/2238
    Markdown Content:
    ## BRESAR, Miha 助理教授
    [个人网站](https://sites.google.com/view/mihabresar)
    [学院新闻](https://sds.cuhk.edu.cn/news)
    """

    links = _extract_follow_candidate_link_infos(
        markdown,
        "https://sds.cuhk.edu.cn/teacher/2238",
    )

    assert [(link.url, link.text) for link in links] == [
        ("https://sites.google.com/view/mihabresar", "个人网站")
    ]


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
        page_links = [link for link in links if link.endswith("page.html")]
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


@pytest.mark.asyncio
async def test_crawl_homepage_extracts_sigs_tab_sections_without_llm_facts():
    llm_response = json.dumps(
        {
            "research_directions": [],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        }
    )

    def mock_fetch(url: str, timeout: float = 20.0):
        from src.data_agents.professor.discovery import HtmlFetchResult

        return HtmlFetchResult(
            html=_SIGS_AHMED_TAB_HTML,
            used_browser=False,
            blocked_by_anti_scraping=False,
            request_error=None,
            browser_error=None,
        )

    mock_llm = MagicMock()
    mock_llm.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=f"```json\n{llm_response}\n```"))]
    )

    result = await crawl_homepage(
        profile=_make_profile(
            name="Ahmed Elazab",
            institution="清华大学深圳国际研究生院",
            homepage="https://www.sigs.tsinghua.edu.cn/Ahmed%20Elazab/main.psp",
            profile_url="https://www.sigs.tsinghua.edu.cn/Ahmed%20Elazab/main.psp",
            roster_source="https://www.sigs.tsinghua.edu.cn/teacherHome/teacherList.do",
        ),
        fetch_html_fn=mock_fetch,
        llm_client=mock_llm,
        llm_model="test-model",
    )

    assert result.success
    assert "trustworthy artificial intelligence" in result.profile.research_directions
    assert "medical image analysis" in result.profile.research_directions
    assert result.profile.education_structured[0].school == (
        "University of Chinese Academy of Sciences"
    )
    assert result.profile.education_structured[0].degree == "PhD"
    assert result.profile.work_experience[0].organization == "Shenzhen University"
    assert result.profile.work_experience[0].role == "Postdoctoral Fellow"
    assert any(
        "PeerJ Computer Science" in item for item in result.profile.academic_positions
    )
    assert any("Best paper award" in item for item in result.profile.awards)
    assert result.profile.official_top_papers


@pytest.mark.asyncio
async def test_crawl_homepage_follows_github_pages_personal_site_into_publication_page():
    official_url = "https://school.example.edu/faculty/alice"
    personal_url = "https://alice-research.github.io/"
    publications_url = "https://alice-research.github.io/publications/"
    html_by_url = {
        official_url: f"""
        <html><body>
          <h1>Alice Zhang</h1>
          <p>研究方向：Robotics</p>
          <a href="{personal_url}">GitHub Pages</a>
        </body></html>
        """,
        personal_url: f"""
        <html><body>
          <h1>Alice Zhang Lab</h1>
          <p>Research interests: federated robotics and adaptive sensing.</p>
          <a href="{publications_url}">Publications</a>
        </body></html>
        """,
        publications_url: """
        <html><body>
          <h2>Selected Publications</h2>
          <ul>
            <li>Communication Efficient Federated Robotics with Adaptive Quantization. IEEE Robotics and Automation Letters, 2024.</li>
          </ul>
        </body></html>
        """,
    }
    fetched_urls: list[str] = []

    def mock_fetch(url: str, timeout: float = 20.0):
        from src.data_agents.professor.discovery import HtmlFetchResult

        del timeout
        fetched_urls.append(url)
        return HtmlFetchResult(
            html=html_by_url.get(url, ""),
            used_browser=False,
            blocked_by_anti_scraping=False,
            request_error=None,
            browser_error=None,
        )

    profile = _make_profile(
        name="Alice Zhang",
        institution="Example University",
        department="School of Engineering",
        homepage=None,
        profile_url=official_url,
        roster_source="https://school.example.edu/faculty",
    )
    follow_response = json.dumps({"links": []})
    extract_response = json.dumps(
        {
            "research_directions": ["federated robotics", "adaptive sensing"],
            "education_structured": [],
            "work_experience": [],
            "awards": [],
            "academic_positions": [],
        }
    )
    mock_llm = MagicMock()
    mock_llm.chat.completions.create.side_effect = [
        MagicMock(
            choices=[
                MagicMock(message=MagicMock(content=f"```json\n{follow_response}\n```"))
            ]
        ),
        MagicMock(
            choices=[
                MagicMock(message=MagicMock(content=f"```json\n{extract_response}\n```"))
            ]
        ),
    ]

    result = await crawl_homepage(
        profile=profile,
        fetch_html_fn=mock_fetch,
        llm_client=mock_llm,
        llm_model="test-model",
    )

    assert result.success
    assert personal_url in fetched_urls
    assert publications_url in fetched_urls
    assert result.pages_fetched == 3
    assert "federated robotics" in result.profile.research_directions
    assert "adaptive sensing" in result.profile.research_directions
    assert "Robotics" in result.profile.research_directions
    assert [paper.title for paper in result.profile.official_top_papers] == [
        "Communication Efficient Federated Robotics with Adaptive Quantization"
    ]
    assert result.profile.publication_evidence_urls == [publications_url]
    assert result.profile.field_provenance[
        f"source_page_role:{personal_url}"
    ] == "personal_homepage"
    assert result.profile.field_provenance[
        f"source_page_role:{publications_url}"
    ] == "personal_homepage"


def test_extract_sigs_tab_homepage_output_parses_chinese_date_fact_lines():
    html = """
    <html><body><div class="teacher_right"><div class="sudy-tab">
      <ul class="tab-menu"><li><span>个人简历</span></li></ul>
      <ul class="tab-list"><li>
        <div class="post"><h3 class="tit"><span class="title">教育经历</span></h3>
          <div class="con">
            <p>2015 年 7 月 -2020 年 6 月 清华大学 土木工程 博士</p>
            <p>2011 年 7 月 -2015 年 6 月 清华大学 土木工程 学士</p>
          </div>
        </div>
        <div class="post"><h3 class="tit"><span class="title">工作经历</span></h3>
          <div class="con">
            <p>2025年6月-至今 清华大学深圳国际研究生院 助理教授</p>
            <p>2020 年 7 月 - 2025 年 5 月 香港大学 博士后</p>
          </div>
        </div>
      </li></ul>
    </div></div></body></html>
    """

    output = _extract_sigs_tab_homepage_output(
        html, "https://www.sigs.tsinghua.edu.cn/gyt2/main.htm"
    )

    assert output.education_structured[0].school == "清华大学"
    assert output.education_structured[0].field == "土木工程"
    assert output.education_structured[0].degree == "博士"
    assert output.education_structured[0].start_year == 2015
    assert output.education_structured[0].end_year == 2020
    assert output.work_experience[0].organization == "清华大学深圳国际研究生院"
    assert output.work_experience[0].role == "助理教授"
    assert output.work_experience[0].start_year == 2025
    assert output.work_experience[0].end_year is None


def test_extract_sigs_tab_homepage_output_splits_compound_sigs_fact_lines():
    html = """
    <html><body><div class="teacher_right"><div class="sudy-tab">
      <ul class="tab-menu"><li><span>个人简历</span></li></ul>
      <ul class="tab-list"><li>
        <div class="post"><h3 class="tit"><span class="title">教育经历</span></h3>
          <div class="con">
            <p>2010 年 1 月 -2013 年 8 月， 美国新墨西哥州立大学 电气工程 博士； 2007 年 8 月- 2009 年 12 月， 哈尔滨工业大学 控制科学与工程 硕士； 2003 年 8 月- 2007 年 7 月， 哈尔滨工业大学 控制科学与工程 学士；</p>
          </div>
        </div>
        <div class="post"><h3 class="tit"><span class="title">工作经历</span></h3>
          <div class="con">
            <p>2020 年 7 月 至今，清华大学深圳国际研究生院，清华伯克利深圳学院，信息学科，副教授</p>
            <p>2018 年 - 至今，清华大学，教授</p>
          </div>
        </div>
      </li></ul>
    </div></div></body></html>
    """

    output = _extract_sigs_tab_homepage_output(
        html, "https://www.sigs.tsinghua.edu.cn/xyl/main.htm"
    )

    assert [(item.school, item.field, item.degree) for item in output.education_structured] == [
        ("美国新墨西哥州立大学", "电气工程", "博士"),
        ("哈尔滨工业大学", "控制科学与工程", "硕士"),
        ("哈尔滨工业大学", "控制科学与工程", "学士"),
    ]
    assert output.work_experience[0].organization == "清华大学深圳国际研究生院"
    assert output.work_experience[0].role == "副教授"
    assert output.work_experience[0].start_year == 2020
    assert output.work_experience[0].end_year is None
    assert output.work_experience[1].organization == "清华大学"
    assert output.work_experience[1].role == "教授"
    assert output.work_experience[1].start_year == 2018
    assert output.work_experience[1].end_year is None


def test_extract_sigs_tab_homepage_output_parses_degree_first_fact_lines():
    html = """
    <html><body><div class="teacher_right"><div class="sudy-tab">
      <ul class="tab-menu"><li><span>个人简历</span></li></ul>
      <ul class="tab-list"><li>
        <div class="post"><h3 class="tit"><span class="title">教育经历</span></h3>
          <div class="con">
            <p>2005 年 08 月 -2009 年 12 月，博士，美国北卡罗来纳州立大学电气工程专业</p>
            <p>2002 年 09 月 -2005 年 07 月，硕士，清华大学信息与通信工程专业</p>
          </div>
        </div>
        <div class="post"><h3 class="tit"><span class="title">工作经历</span></h3>
          <div class="con">
            <p>2019 年 09 月至今，副教授，清华大学深圳国际研究生院</p>
            <p>2015 年 9 月 - 2018 年 8 月 ，电气与计算机工程系，美国卡内基梅隆大学，兼职教员</p>
          </div>
        </div>
      </li></ul>
    </div></div></body></html>
    """

    output = _extract_sigs_tab_homepage_output(
        html, "https://www.sigs.tsinghua.edu.cn/dyh/main.htm"
    )

    assert output.education_structured[0].school == "美国北卡罗来纳州立大学"
    assert output.education_structured[0].field == "电气工程专业"
    assert output.education_structured[0].degree == "博士"
    assert output.education_structured[1].school == "清华大学"
    assert output.education_structured[1].field == "信息与通信工程专业"
    assert output.work_experience[0].organization == "清华大学深圳国际研究生院"
    assert output.work_experience[0].role == "副教授"
    assert output.work_experience[1].organization == "美国卡内基梅隆大学"
    assert output.work_experience[1].role == "兼职教员"


def test_extract_sigs_tab_homepage_output_parses_tilde_and_adjacent_date_ranges():
    html = """
    <html><body><div class="teacher_right"><div class="sudy-tab">
      <ul class="tab-menu"><li><span>个人简历</span></li></ul>
      <ul class="tab-list"><li>
        <div class="post"><h3 class="tit"><span class="title">教育经历</span></h3>
          <div class="con">
            <p>2003年09月～2008年07月，清华大学，光学工程专业，工学博士，导师：金国藩</p>
            <p>2018年09月–2023年06月，荷兰莱顿大学，产业生态学专业，博士 2015年09月–2018年06月，重庆大学，管理科学与工程专业，硕士</p>
          </div>
        </div>
        <div class="post"><h3 class="tit"><span class="title">工作经历</span></h3>
          <div class="con">
            <p>2019年08月～今，清华大学深圳国际研究生院，先进制造学部，副研究员</p>
            <p>2026年02月–至今，清华大学 深圳国际研究生院 ，助理教授 2023年04月–2026年02月，国际应用系统分析研究所，研究员</p>
          </div>
        </div>
      </li></ul>
    </div></div></body></html>
    """

    output = _extract_sigs_tab_homepage_output(
        html, "https://www.sigs.tsinghua.edu.cn/nk/main.htm"
    )

    assert [(item.school, item.field, item.degree) for item in output.education_structured] == [
        ("清华大学", "光学工程专业", "工学博士"),
        ("荷兰莱顿大学", "产业生态学专业", "博士"),
        ("重庆大学", "管理科学与工程专业", "硕士"),
    ]
    assert [(item.organization, item.role) for item in output.work_experience] == [
        ("清华大学深圳国际研究生院", "副研究员"),
        ("清华大学 深圳国际研究生院", "助理教授"),
        ("国际应用系统分析研究所", "研究员"),
    ]


def test_extract_official_publication_signals_sigs_author_prefix_yields_title():
    pages = [
        _FetchedPage(
            url="https://www.sigs.tsinghua.edu.cn/Ahmed%20Elazab/main.psp",
            html="""
            <html><body>
            <div class="post">
              <h3 class="tit"><span class="title">代表性论文</span></h3>
              <div class="con">
                <p>1- M. Abdelaziz, T. Wang, W. Anwaar, A. Elazab *, Robust attention transfer neural networks for diagnosis of Alzheimer's disease from structural magnetic resonance images, Engineering Applications of Artificial Intelligence, 164, 113260, 2026.</p>
                <p>All publications: https://sites.google.com/view/mihabresar</p>
              </div>
            </div>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert [paper.title for paper in signals.top_papers] == [
        "Robust attention transfer neural networks for diagnosis of Alzheimer's disease from structural magnetic resonance images"
    ]


def test_extract_official_publication_signals_sigs_author_period_lines_yield_titles():
    pages = [
        _FetchedPage(
            url="https://www.sigs.tsinghua.edu.cn/zy2/main.htm",
            html="""
            <html><body>
            <div class="post">
              <h3 class="tit"><span class="title">代表性论文</span></h3>
              <div class="con">
                <p>[1 ] Yuhang Zhang, Xu Han, Tianxi Wei, Xiaoyong Zhao, Yi Zhang* . (2023) Techno-environmental-economical performance of allocating multiple energy storage resources for multi-scale and multi-type urban forms towards low carbon district. Sustainable Cities and Society, 2023, 104974.</p>
                <p>[2] Zhaoming Wang, Li Zhang, Jingzhou Li, Guodan Wei, Yuhan Dong, and H.Y. Fu. Fluorescent concentrator based MISO-NOMA for visible light communications. Optics Letters, 2022, 47(4): 902-905.</p>
              </div>
            </div>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert [paper.title for paper in signals.top_papers[:2]] == [
        "Techno-environmental-economical performance of allocating multiple energy storage resources for multi-scale and multi-type urban forms towards low carbon district",
        "Fluorescent concentrator based MISO-NOMA for visible light communications",
    ]


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


def test_extract_official_publication_signals_prefers_structured_publication_section():
    pages = [
        _FetchedPage(
            url="http://www.sigs.tsinghua.edu.cn/wlm/main.htm",
            html="""
            <html><body>
            <h1>王黎明</h1>
            <div class="post">
              <div class="tt"><h3><span class="title">学术兼职</span></h3></div>
              <div class="con">
                <p>IEEE Dielectrics and Electrical Insulation Society 'Discharges in Air at UHV'技术委员会主席</p>
                <p>CIGRE SC D1 Materials and Emerging Test Techniques中国专家委员会委员</p>
              </div>
            </div>
            <div class="post">
              <div class="tt"><h3><span class="title">代表性论文</span></h3></div>
              <div class="con">
                <p>目前已发表学术论文500余篇。</p>
                <p><span>[1] Zimin Luo, </span><strong>Liming Wang</strong><span>, Bin Cao, Yuhao Liu, Xiaobang Tong, Libao Liu, Xiaoqing Wu, Xukai Zhu. Synergistic enhancement of heat resistance and mechanical performance of epoxy resin by introducing entanglement effect. Composites Part A: Applied Science and Manufacturing, 2026, 203, 109581.</span></p>
                <p><span>[2] Huijie Li, Yafeng Chao, Te Li, Fanghui Yin, Hongwei Mei, </span><strong>Liming Wang</strong><span>, Masoud Farzaneh. Aging Mechanism of Composite Insulated Cross-Arm Under Multi-Factor Coupling Effect, in IEEE Transactions on Dielectrics and Electrical Insulation, doi: 10.1109/TDEI.2025.3634477.</span></p>
              </div>
            </div>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert signals.paper_count == 500
    assert [paper.title for paper in signals.top_papers] == [
        "Synergistic enhancement of heat resistance and mechanical performance of epoxy resin by introducing entanglement effect",
        "Aging Mechanism of Composite Insulated Cross-Arm Under Multi-Factor Coupling Effect",
    ]


def test_extract_official_publication_signals_bounds_fallback_to_publication_section():
    pages = [
        _FetchedPage(
            url="http://www.sigs.tsinghua.edu.cn/wlm/main.htm",
            html="""
            <html><body>
            <h3>学术兼职</h3>
            <p>IEEE Dielectrics and Electrical Insulation Society 'Discharges in Air at UHV'技术委员会主席</p>
            <p>CIGRE SC D1 Materials and Emerging Test Techniques中国专家委员会委员</p>
            <h3>代表性论文</h3>
            <p>目前已发表学术论文500余篇，其中SCI收录140余篇。</p>
            <h3>代表性著作</h3>
            </body></html>
            """,
            publication_candidate=False,
        )
    ]

    signals = _extract_official_publication_signals(pages)

    assert signals.paper_count == 500
    assert signals.top_papers == []


def test_should_refresh_stale_sigs_cached_profile_without_publication_items():
    html = """
    <html><body>
    <h3>代表性论文</h3>
    <p>目前已发表学术论文500余篇，其中SCI收录140余篇。</p>
    <h3>代表性著作</h3>
    </body></html>
    """

    assert _should_refresh_cached_html("http://www.sigs.tsinghua.edu.cn/wlm/main.htm", html)


def test_should_refresh_suat_roster_cache_with_visualsitebuilder_profile_ids():
    html = """
    <html><body>
      <ul class="list2">
        <li class="item">
          <a href="../info/1012/1395.htm" title="李慧敏">李慧敏 教研助理教授</a>
        </li>
      </ul>
      <script>
        _showDynClickBatch(['dynclicks_u10_1395'],[1395],"wbnews",1978015886)
      </script>
    </body></html>
    """

    assert _should_refresh_cached_html("https://cme.suat-sz.edu.cn/szdw/dsjs.htm", html)


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
        "Transition Metal Ion FRET-Based Probe to Study Cu(II)-Mediated Amyloid-beta Ligand Binding"
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

    async def test_hit_homepage_fetches_dynamic_teacher_body(self):
        main_html = """
        <html><body>
        <h1>张钦宇</h1>
        <div class="teacher-body" data-tid="cc01a95e2af64116a28ba2c3e5ba36bc"></div>
        </body></html>
        """
        dynamic_body = json.dumps(
            """
            <html><body>
            <h3>研究方向</h3>
            <p>宽带移动通信、卫星通信与无线网络</p>
            <h3>代表性论文</h3>
            <ul>
              <li>Confidence Based Asynchronous Integrated Communication and Localization Networks Using IR-UWB Signals</li>
            </ul>
            </body></html>
            """,
            ensure_ascii=False,
        )

        calls: list[dict[str, object]] = []

        def mock_fetch(
            url: str,
            timeout: float = 20.0,
            *,
            method: str = "GET",
            data: dict[str, str] | None = None,
            headers: dict[str, str] | None = None,
        ):
            from src.data_agents.professor.discovery import HtmlFetchResult

            calls.append({
                "url": url,
                "method": method,
                "data": data,
                "headers": headers,
            })
            html = (
                dynamic_body
                if (
                    "TeacherHome/teacherBody.do" in url
                    and method == "POST"
                    and data == {"id": "cc01a95e2af64116a28ba2c3e5ba36bc"}
                )
                else main_html
            )
            return HtmlFetchResult(
                html=html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        llm_response = json.dumps(
            {
                "research_directions": [],
                "education_structured": [],
                "work_experience": [],
                "awards": [],
                "academic_positions": [],
            },
            ensure_ascii=False,
        )
        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=llm_response))]
        )

        profile = _make_profile(
            name="张钦宇",
            institution="哈尔滨工业大学（深圳）",
            homepage="http://homepage.hit.edu.cn/zhangqinyu?lang=zh",
            profile_url="http://homepage.hit.edu.cn/zhangqinyu?lang=zh",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        body_calls = [
            call for call in calls if "TeacherHome/teacherBody.do" in str(call["url"])
        ]
        assert body_calls == [
            {
                "url": "https://homepage.hit.edu.cn/TeacherHome/teacherBody.do",
                "method": "POST",
                "data": {"id": "cc01a95e2af64116a28ba2c3e5ba36bc"},
                "headers": {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
                },
            }
        ]
        assert result.profile.research_directions == ["宽带移动通信", "卫星通信与无线网络"]
        assert [
            paper.title for paper in result.profile.official_top_papers
        ] == [
            "Confidence Based Asynchronous Integrated Communication and Localization Networks Using IR-UWB Signals"
        ]
        assert result.profile.profile_raw_text is not None
        assert "研究方向" in result.profile.profile_raw_text
        assert "宽带移动通信、卫星通信与无线网络" in result.profile.profile_raw_text
        assert "代表性论文" in result.profile.profile_raw_text
        assert "Confidence Based Asynchronous Integrated Communication" in (
            result.profile.profile_raw_text
        )

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
        assert result.profile.profile_raw_text is not None
        assert "陈伟津" in result.profile.profile_raw_text
        assert "累计发表研究论文 86 篇" in result.profile.profile_raw_text
        assert "Microstructure-mediated phase transition mechanics" not in (
            result.profile.profile_raw_text
        )
        assert "Elastic coupling in metal-insulator transition" not in (
            result.profile.profile_raw_text
        )

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
        assert result.profile.field_provenance[
            "source_page_role:https://satoshi.example.com/"
        ] == "personal_homepage"
        assert result.profile.field_provenance[
            "source_page_role:https://satoshi.example.com/publications.html"
        ] == "personal_homepage"
        assert result.profile.official_paper_count == 86
        assert [paper.title for paper in result.profile.official_top_papers] == [
            "Transllama: LLM-based simultaneous translation system",
            "LLaST: Improved End-to-end Speech Translation System Leveraged by Large Language Models",
        ]
        assert result.profile.profile_raw_text is not None
        assert "Satoshi Nakamura" in result.profile.profile_raw_text
        assert "Transllama: LLM-based simultaneous translation system" not in (
            result.profile.profile_raw_text
        )
        assert "https://satoshi.example.com/publications.html" not in (
            result.profile.profile_raw_text
        )

    async def test_recurses_to_personal_homepage_with_inline_publications(self):
        pages = {
            "https://sai.cuhk.edu.cn/teacher/105": """
            <html><body>
            <h1>LI, Mei</h1>
            <a href="https://meili.example.com/">个人主页</a>
            </body></html>
            """,
            "https://meili.example.com/": """
            <html><body>
            <h1>Mei Li</h1>
            <h2>Selected Publications</h2>
            <ul>
              <li>Adaptive Systems for Trustworthy Federated Learning</li>
              <li>Efficient Quantization for Collaborative Edge Intelligence</li>
            </ul>
            </body></html>
            """,
        }

        link_plan_response = json.dumps({
            "links": [
                {
                    "url": "https://meili.example.com/",
                    "category": "personal_homepage",
                    "priority": 1,
                    "should_follow": True,
                    "reason": "官方页明确给出个人主页",
                }
            ]
        }, ensure_ascii=False)
        extraction_response = json.dumps({
            "title": "助理教授",
            "department": "人工智能学院",
            "research_directions": ["联邦学习"],
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
            name="LI, Mei",
            institution="香港中文大学（深圳）",
            department="人工智能学院",
            homepage="https://sai.cuhk.edu.cn/teacher/105",
            profile_url="https://sai.cuhk.edu.cn/teacher/105",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.pages_fetched == 2
        assert result.profile.publication_evidence_urls == [
            "https://meili.example.com/"
        ]
        assert result.profile.field_provenance[
            "source_page_role:https://meili.example.com/"
        ] == "personal_homepage"
        assert [paper.title for paper in result.profile.official_top_papers] == [
            "Adaptive Systems for Trustworthy Federated Learning",
            "Efficient Quantization for Collaborative Edge Intelligence",
        ]

    async def test_recurses_same_root_profile_subpages_from_personal_homepage(self):
        pages = {
            "https://sai.cuhk.edu.cn/teacher/106": """
            <html><body>
            <h1>CHEN, Ada</h1>
            <a href="https://ada.example.com/">Personal Homepage</a>
            </body></html>
            """,
            "https://ada.example.com/": """
            <html><body>
            <h1>Ada Chen</h1>
            <nav>
              <a href="/research">Research</a>
              <a href="/projects">Projects</a>
              <a href="/publications">Publications</a>
              <a href="/news">News</a>
              <a href="https://elsewhere.example.com/research">External Research</a>
            </nav>
            </body></html>
            """,
            "https://ada.example.com/research": """
            <html><body>
            <h2>Research</h2>
            <p>My group studies privacy-preserving robotics for eldercare.</p>
            </body></html>
            """,
            "https://ada.example.com/projects": """
            <html><body>
            <h2>Projects</h2>
            <p>The CareBot project deploys assistive robots in hospitals.</p>
            </body></html>
            """,
            "https://ada.example.com/publications": """
            <html><body>
            <h2>Selected Publications</h2>
            <ul>
              <li>Privacy Preserving Robot Learning for Assistive Care</li>
            </ul>
            </body></html>
            """,
            "https://ada.example.com/news": """
            <html><body><p>Sitewide news should not be followed.</p></body></html>
            """,
            "https://elsewhere.example.com/research": """
            <html><body><p>Cross-site research should not be followed.</p></body></html>
            """,
        }

        link_plan_response = json.dumps({
            "links": [
                {
                    "url": "https://ada.example.com/",
                    "category": "personal_homepage",
                    "priority": 1,
                    "should_follow": True,
                    "reason": "官方页明确给出个人主页",
                }
            ]
        }, ensure_ascii=False)
        extraction_response = json.dumps({
            "title": "助理教授",
            "department": "人工智能学院",
            "research_directions": ["机器人学习"],
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
            MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=f"```json\n{link_plan_response}\n```"
                        )
                    )
                ]
            ),
            MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=f"```json\n{extraction_response}\n```"
                        )
                    )
                ]
            ),
        ]

        result = await crawl_homepage(
            profile=_make_profile(
                name="CHEN, Ada",
                institution="香港中文大学（深圳）",
                department="人工智能学院",
                homepage="https://sai.cuhk.edu.cn/teacher/106",
                profile_url="https://sai.cuhk.edu.cn/teacher/106",
            ),
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        extraction_prompt = mock_llm.chat.completions.create.call_args_list[1].kwargs[
            "messages"
        ][1]["content"]

        assert result.success
        assert fetched_urls[:2] == [
            "https://sai.cuhk.edu.cn/teacher/106",
            "https://ada.example.com/",
        ]
        assert set(fetched_urls[2:]) == {
            "https://ada.example.com/research",
            "https://ada.example.com/projects",
            "https://ada.example.com/publications",
        }
        assert "https://ada.example.com/news" not in fetched_urls
        assert "https://elsewhere.example.com/research" not in fetched_urls
        assert "privacy-preserving robotics for eldercare" in extraction_prompt
        assert "CareBot project deploys assistive robots" in extraction_prompt
        assert "Privacy Preserving Robot Learning" in extraction_prompt
        assert result.profile.profile_raw_text is not None
        assert "privacy-preserving robotics for eldercare" in (
            result.profile.profile_raw_text
        )
        assert "CareBot project deploys assistive robots" in (
            result.profile.profile_raw_text
        )
        assert "Privacy Preserving Robot Learning" not in (
            result.profile.profile_raw_text
        )
        assert result.profile.publication_evidence_urls == [
            "https://ada.example.com/publications"
        ]
        assert [paper.title for paper in result.profile.official_top_papers] == [
            "Privacy Preserving Robot Learning for Assistive Care"
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

    async def test_planning_failure_falls_back_to_explicit_external_personal_homepage(self):
        pages = {
            "https://official.example.edu/faculty/alice": """
                <html><body>
                <h1>Alice Zhang</h1>
                <a href="https://alice.example.com">个人网站</a>
                <a href="https://random.example.net/news">更多链接</a>
                </body></html>
            """,
            "https://alice.example.com": """
                <html><body>
                <h1>Alice Zhang</h1>
                <p>这个外部主页由教师本人维护，包含 richer research details。</p>
                </body></html>
            """,
            "https://random.example.net/news": """
                <html><body><p>Unrelated external news.</p></body></html>
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
        assert fetched_urls == [
            "https://official.example.edu/faculty/alice",
            "https://alice.example.com",
        ]
        assert "https://alice.example.com" in result.profile.evidence_urls
        assert "https://random.example.net/news" not in result.profile.evidence_urls
        assert (
            result.profile.field_provenance[
                "source_page_role:https://alice.example.com"
            ]
            == "personal_homepage"
        )

    async def test_planning_failure_falls_back_to_institutional_personal_homepage(self):
        pages = {
            "https://www.sustech.edu.cn/zh/faculties/alice.html": """
                <html><body>
                <h1>Alice Zhang</h1>
                <a href="https://faculty.sustech.edu.cn/alice/">个人主页</a>
                </body></html>
            """,
            "https://faculty.sustech.edu.cn/alice/": """
                <html><body>
                <h1>Alice Zhang Lab</h1>
                <p>Research interests include trustworthy machine learning.</p>
                </body></html>
            """,
        }
        extraction_response = json.dumps({
            "title": "助理教授",
            "department": "人工智能学院",
            "research_directions": ["可信机器学习"],
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
            MagicMock(choices=[MagicMock(message=MagicMock(content="not valid json"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extraction_response}\n```"))]),
        ]

        profile = _make_profile(
            name="Alice Zhang",
            institution="南方科技大学",
            department="人工智能学院",
            homepage="https://www.sustech.edu.cn/zh/faculties/alice.html",
            profile_url="https://www.sustech.edu.cn/zh/faculties/alice.html",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert fetched_urls == [
            "https://www.sustech.edu.cn/zh/faculties/alice.html",
            "https://faculty.sustech.edu.cn/alice/",
        ]
        assert "https://faculty.sustech.edu.cn/alice/" in result.profile.evidence_urls
        assert result.profile.field_provenance[
            "source_page_role:https://faculty.sustech.edu.cn/alice/"
        ] == "personal_homepage"

    async def test_szu_planning_failure_follows_personal_homepage_not_school_homepage(self):
        pages = {
            "https://math.szu.edu.cn/info/1012/1001.htm": """
                <html><body>
                <h1>张三</h1>
                <a href="https://www.szu.edu.cn/">学校主页</a>
                <a href="https://math.szu.edu.cn/">学院主页</a>
                <a href="https://faculty.szu.edu.cn/zhangsan/">个人主页</a>
                </body></html>
            """,
            "https://faculty.szu.edu.cn/zhangsan/": """
                <html><body>
                <h1>张三课题组</h1>
                <p>研究方向：组合优化。</p>
                </body></html>
            """,
        }
        extraction_response = json.dumps({
            "title": "教授",
            "department": "数学科学学院",
            "research_directions": ["组合优化"],
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
            MagicMock(choices=[MagicMock(message=MagicMock(content="not valid json"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=f"```json\n{extraction_response}\n```"))]),
        ]

        profile = _make_profile(
            name="张三",
            institution="深圳大学",
            department="数学科学学院",
            homepage="https://math.szu.edu.cn/info/1012/1001.htm",
            profile_url="https://math.szu.edu.cn/info/1012/1001.htm",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert fetched_urls == [
            "https://math.szu.edu.cn/info/1012/1001.htm",
            "https://faculty.szu.edu.cn/zhangsan/",
        ]
        assert "https://www.szu.edu.cn/" not in result.profile.evidence_urls
        assert "https://math.szu.edu.cn/" not in result.profile.evidence_urls
        assert result.profile.field_provenance[
            "source_page_role:https://faculty.szu.edu.cn/zhangsan/"
        ] == "personal_homepage"

    async def test_suat_planner_filters_school_homepage_and_recruitment_links(self):
        pages = {
            "https://msee.suat-sz.edu.cn/info/1010/1093.htm": """
                <html><body>
                <h1>成会明</h1>
                <a href="https://suat-sz.edu.cn/">学校主页</a>
                <a href="https://msee.suat-sz.edu.cn/zpxx/ktzzp.htm">课题组招聘</a>
                <p>研究方向：先进储能材料。</p>
                </body></html>
            """,
            "https://suat-sz.edu.cn/": """
                <html><body><h1>深圳理工大学</h1></body></html>
            """,
            "https://msee.suat-sz.edu.cn/zpxx/ktzzp.htm": """
                <html><body><h1>课题组招聘</h1></body></html>
            """,
        }
        follow_response = json.dumps(
            {
                "links": [
                    {
                        "url": "https://suat-sz.edu.cn/",
                        "category": "personal_homepage",
                        "should_follow": True,
                        "priority": 1,
                    },
                    {
                        "url": "https://msee.suat-sz.edu.cn/zpxx/ktzzp.htm",
                        "category": "lab_or_group",
                        "should_follow": True,
                        "priority": 2,
                    },
                ]
            },
            ensure_ascii=False,
        )
        extraction_response = json.dumps(
            {
                "title": "院士",
                "department": "材料科学与能源工程学院",
                "research_directions": ["先进储能材料"],
                "education_structured": [],
                "work_experience": [],
                "awards": [],
                "academic_positions": [],
            },
            ensure_ascii=False,
        )

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
            MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=f"```json\n{follow_response}\n```"))
                ]
            ),
            MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=f"```json\n{extraction_response}\n```"))
                ]
            ),
        ]

        profile = _make_profile(
            name="成会明",
            institution="深圳理工大学",
            department="材料科学与能源工程学院",
            homepage="https://msee.suat-sz.edu.cn/info/1010/1093.htm",
            profile_url="https://msee.suat-sz.edu.cn/info/1010/1093.htm",
        )
        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert fetched_urls == ["https://msee.suat-sz.edu.cn/info/1010/1093.htm"]
        assert "https://suat-sz.edu.cn/" not in result.profile.evidence_urls
        assert "https://msee.suat-sz.edu.cn/zpxx/ktzzp.htm" not in result.profile.evidence_urls

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

    async def test_crawl_homepage_collects_yjsjy_secondary_academic_urls(self):
        source_url = (
            "https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/12345?yxsh=28"
        )
        faculty_url = "https://faculty.uestc.edu.cn/huangye/zh_CN/index.htm"
        main_html = f"""
        <html><body>
          <div id="mcontent"><div class="news_list"><table class="box">
            <tr><td>姓名</td><td><span id="Labeldsxm">黄野</span></td></tr>
            <tr><td>职称</td><td><span id="Labelzc">教授</span></td></tr>
            <tr><td>Google Scholar</td><td><a href="https://scholar.google.com/citations?user=abc123">Scholar</a></td></tr>
            <tr><td>DBLP</td><td><a href="https://dblp.org/pid/12/3456.html">DBLP profile</a></td></tr>
            <tr><td>教师主页</td><td><a href="{faculty_url}">学院教师主页</a></td></tr>
            <tr><td>个人简介</td><td>更多成果见 https://staff.uestc.edu.cn/huangye 。代表性成果 DOI: https://doi.org/10.1145/1234567.7654321</td></tr>
          </table></div></div>
        </body></html>
        """
        link_plan_response = json.dumps({"links": []}, ensure_ascii=False)
        extraction_response = json.dumps(
            {
                "title": "教授",
                "department": "计算机技术",
                "research_directions": ["网络空间安全"],
                "education_structured": [],
                "work_experience": [],
                "awards": [],
                "academic_positions": [],
            },
            ensure_ascii=False,
        )

        def mock_fetch(url: str, timeout: float = 20.0):
            from src.data_agents.professor.discovery import HtmlFetchResult

            html = (
                "<html><body><h1>黄野</h1><p>Faculty profile</p></body></html>"
                if url == faculty_url
                else main_html
            )
            return HtmlFetchResult(
                html=html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

        mock_llm = MagicMock()
        mock_llm.chat.completions.create.side_effect = [
            MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=f"```json\n{link_plan_response}\n```"
                        )
                    )
                ]
            ),
            MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=f"```json\n{extraction_response}\n```"
                        )
                    )
                ]
            ),
        ]

        result = await crawl_homepage(
            profile=_make_profile(
                name="黄野",
                institution="电子科技大学（深圳）高等研究院",
                department="计算机技术",
                homepage=source_url,
                profile_url=source_url,
            ),
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.scholarly_profile_urls == [
            "https://scholar.google.com/citations?user=abc123",
            "https://dblp.org/pid/12/3456.html",
            faculty_url,
            "https://staff.uestc.edu.cn/huangye",
            "https://doi.org/10.1145/1234567.7654321",
        ]
        assert result.profile.publication_evidence_urls == []

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

    async def test_sztu_fragment_profile_raw_text_is_scoped_before_merging(self):
        main_html = """
        <html><body>
        <div class="teacher-details">
          <div class="team-item" id="prof-duhemin">
            <h3>杜鹤民</h3>
            <p>教授</p>
            <p>代表性论文：Designing Mediated Social Touch for Mobile Communication:
            From Hand Gestures to Touch Signals. International Journal of
            Human-Computer Studies, 2026.</p>
          </div>
          <div class="team-item" id="prof-liumo">
            <h3>刘墨</h3>
            <p>助理教授</p>
            <p>研究方向：交互设计、智能产品设计。</p>
          </div>
        </div>
        </body></html>
        """

        llm_response = json.dumps({
            "title": "助理教授",
            "department": "创意设计学院",
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
            name="刘墨",
            institution="深圳技术大学",
            department="创意设计学院",
            homepage=(
                "https://design.sztu.edu.cn/xygk/szdw/jytd.htm"
                "#prof-%E5%88%98%E5%A2%A8"
            ),
            profile_url=(
                "https://design.sztu.edu.cn/xygk/szdw/jytd.htm"
                "#prof-%E5%88%98%E5%A2%A8"
            ),
        )

        result = await crawl_homepage(
            profile=profile,
            fetch_html_fn=mock_fetch,
            llm_client=mock_llm,
            llm_model="test-model",
        )

        assert result.success
        assert result.profile.profile_raw_text is not None
        assert "刘墨" in result.profile.profile_raw_text
        assert "杜鹤民" not in result.profile.profile_raw_text
        assert "International Journal of Human-Computer Studies" not in (
            result.profile.profile_raw_text
        )

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
