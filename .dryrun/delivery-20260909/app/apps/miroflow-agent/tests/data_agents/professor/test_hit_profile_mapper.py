from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import src.data_agents.professor.hit_playwright_profile as hit_profile
from src.data_agents.professor.hit_playwright_profile import (
    HIT_PROFILE_SOURCE,
    extract_hit_profile_fields,
    is_hit_profile_url,
)
from src.data_agents.professor.homepage_crawler import crawl_homepage
from src.data_agents.professor.models import EnrichedProfessorProfile


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "hit"
RUN_ID = "11111111-1111-1111-1111-111111111111"
EXPECTED_BIO_RESEARCH_TOPICS = {
    "人工智能",
    "网络空间安全",
    "机器人",
    "大模型",
    "具身智能",
    "医疗大健康",
}
UI_CHROME_DENYLIST = {
    "更新日期",
    "人气",
    "主页地址",
    "复制地址",
    "二维码",
    "更换皮肤",
    "版式",
    "编辑",
    "提交",
    "校内单位",
    "学科",
    "更多",
    "手机",
    "回到顶部",
    "http",
    "None",
    "空",
}


def _make_profile(**kwargs) -> EnrichedProfessorProfile:
    defaults = dict(
        name="何道敬",
        institution="哈尔滨工业大学（深圳）",
        department=None,
        title=None,
        homepage="https://faculty.hitsz.edu.cn/hedaojing",
        profile_url="https://faculty.hitsz.edu.cn/hedaojing",
        roster_source="https://cs.hitsz.edu.cn/szll1.htm",
        extraction_status="structured",
        research_directions=[],
    )
    defaults.update(kwargs)
    return EnrichedProfessorProfile(**defaults)


def test_hit_profile_mapper_extracts_rendered_profile_fields() -> None:
    html = (FIXTURE_DIR / "hedaojing_rendered.html").read_text(encoding="utf-8")

    extraction = extract_hit_profile_fields(
        html,
        source_url="https://homepage.hit.edu.cn/hedaojing",
        professor_id="PROF-HIT-HEDAOJING",
        run_id=RUN_ID,
    )

    assert extraction.canonical_name == "何道敬"
    assert extraction.department == "信息学部/计算机科学与技术学院（深圳）"
    assert extraction.contact_email == "hedaojinghit@163.com"
    assert EXPECTED_BIO_RESEARCH_TOPICS <= set(extraction.research_directions)
    assert not (UI_CHROME_DENYLIST & set(extraction.research_directions))
    assert extraction.academic_positions == []
    assert extraction.profile_summary is not None
    assert "人工智能" in extraction.profile_summary
    assert extraction.education
    assert ("浙江大学", "博士") in [
        (item.school, item.degree) for item in extraction.education
    ]
    assert extraction.work_experience
    assert ("哈尔滨工业大学（深圳）", "副院长") in [
        (item.organization, item.role) for item in extraction.work_experience
    ]
    assert ("哈尔滨工业大学（深圳）", "教授") in [
        (item.organization, item.role) for item in extraction.work_experience
    ]

    fact_types = {fact.fact_type for fact in extraction.facts}
    assert {
        "research_topic",
        "education",
        "work_experience",
        "contact",
    } <= fact_types
    assert all(fact.source == HIT_PROFILE_SOURCE for fact in extraction.facts)
    assert all(str(fact.run_id) == RUN_ID for fact in extraction.facts)
    assert all(fact.professor_id == "PROF-HIT-HEDAOJING" for fact in extraction.facts)
    assert not any(fact.fact_type == "paper" for fact in extraction.facts)


def test_hit_profile_mapper_omits_absent_sections_without_fabrication() -> None:
    extraction = extract_hit_profile_fields(
        """
        <html><body>
          <h1>何道敬</h1>
          <div class="teacher_Tab teacher_Tab_zh">研究方向</div>
          <div class="part_box"><p>人工智能、网络空间安全</p></div>
        </body></html>
        """,
        source_url="https://homepage.hit.edu.cn/hedaojing",
        professor_id="PROF-HIT-HEDAOJING",
        run_id=RUN_ID,
    )

    assert extraction.research_directions == ["人工智能", "网络空间安全"]
    assert extraction.education == []
    assert extraction.work_experience == []
    assert extraction.academic_positions == []
    assert extraction.contact_email is None
    assert {fact.fact_type for fact in extraction.facts} == {"research_topic"}


def test_hit_profile_url_detection_is_host_scoped() -> None:
    assert is_hit_profile_url("https://homepage.hit.edu.cn/hedaojing")
    assert is_hit_profile_url("https://faculty.hitsz.edu.cn/hedaojing")
    assert not is_hit_profile_url("https://www.sigs.tsinghua.edu.cn/a/main.htm")


@pytest.mark.asyncio
async def test_crawl_homepage_routes_hit_hosts_to_playwright_profile_mapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered_html = (FIXTURE_DIR / "hedaojing_rendered.html").read_text(
        encoding="utf-8"
    )
    rendered_urls: list[str] = []

    async def fake_render(url: str, *, timeout: float = 20.0) -> str:
        del timeout
        rendered_urls.append(url)
        return rendered_html

    monkeypatch.setattr(hit_profile, "render_hit_profile_html_async", fake_render)

    def mock_fetch(url: str, timeout: float = 20.0):
        from src.data_agents.professor.discovery import HtmlFetchResult

        del url, timeout
        return HtmlFetchResult(
            html="""
            <html><body>
              <h1>何道敬</h1>
              <p>邮箱：hedaojing@hit.edu.cn</p>
            </body></html>
            """,
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

    result = await crawl_homepage(
        profile=_make_profile(),
        fetch_html_fn=mock_fetch,
        llm_client=mock_llm,
        llm_model="test-model",
        run_id=RUN_ID,
    )

    assert result.success
    assert rendered_urls == ["https://faculty.hitsz.edu.cn/hedaojing"]
    assert result.profile.title is None
    assert result.profile.department == "信息学部/计算机科学与技术学院（深圳）"
    assert EXPECTED_BIO_RESEARCH_TOPICS <= set(result.profile.research_directions)
    assert not (UI_CHROME_DENYLIST & set(result.profile.research_directions))
    assert result.profile.education_structured
    assert result.profile.work_experience
    assert result.profile.email == "hedaojinghit@163.com"
    assert result.profile.profile_summary
    assert result.profile.official_top_papers == []


def test_research_direction_deny_rejects_publication_list_fragments() -> None:
    from src.data_agents.professor.hit_playwright_profile import (
        _is_denied_research_direction,
    )

    # Citation / publication-list fragments that previously leaked in for verbose
    # professors (e.g. wangfei's 581 garbage research_topic facts). The deny filter
    # catches numeric citations, punctuation, and non-terms. (Author/journal names
    # like "Fei Wang" are term-like and are prevented upstream by dropping the
    # unreliable inline-labeled research fallback, not by this filter.)
    garbage = [
        '"', "(", ")", "*", "[", "]", "）",
        "114: 103462", "10. 宋鹏", "141904 (2016)", "138-145",
        "150(16)", "10.1038/abc123",
        "更新日期", "人气", "二维码",
    ]
    for value in garbage:
        assert _is_denied_research_direction(value), value

    # Real research directions must survive.
    for value in ["人工智能", "网络空间安全", "机器人", "大模型", "machine learning", "deep learning"]:
        assert not _is_denied_research_direction(value), value
