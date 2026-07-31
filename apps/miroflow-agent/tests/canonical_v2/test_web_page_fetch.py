"""Hermetic tests for bounded page fetch and Web-lane enrichment."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from src.data_agents.canonical_v2 import (
    knowledge_serving_isolated as serving_module,
)
from src.data_agents.canonical_v2.knowledge_read import (
    LaneRequest,
    StructuredConstraints,
    WebSearchPolicy,
)
from src.data_agents.providers.page_fetch import (
    create_tiered_page_fetcher,
    extract_main_text,
    fetch_page_text,
)

NOW = datetime(2026, 7, 29, 8, 0, tzinfo=timezone.utc)


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"",
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}


class _FakeClient:
    def __init__(self, response: Any) -> None:
        self._response = response

    def get(self, url: str, timeout: float = 5.0) -> Any:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


_HTML_TEXT = """
<html><head><title>t</title><style>body{color:red}</style></head>
<body>
<nav>导航菜单 首页 产品 关于我们</nav>
<script>var tracker = 1;</script>
<article>
<h1>王学谦：空间机器人智能控制专家</h1>
<p>王学谦是清华大学深圳国际研究生院教授、博士生导师，主要研究方向为空间机器人、
在轨服务与智能控制，主持多项国家级科研项目，发表了多篇IROS与IEEE Transactions论文，
曾获省部级科技奖励。他的团队长期从事空间机器人在轨装配与维护关键技术研究。</p>
</article>
<footer>版权所有 2026 联系我们 网站地图 备案号</footer>
</body></html>
"""
_HTML = _HTML_TEXT.encode("utf-8")


def test_extract_main_text_drops_boilerplate_and_keeps_main() -> None:
    text = extract_main_text(_HTML)
    assert text is not None
    assert "王学谦" in text
    assert "在轨服务" in text
    assert "导航菜单" not in text
    assert "版权所有" not in text
    assert "tracker" not in text


def test_extract_main_text_caps_length() -> None:
    text = extract_main_text(_HTML, max_chars=60)
    assert text is not None
    assert len(text) <= 60


def test_extract_main_text_rejects_thin_pages() -> None:
    assert extract_main_text("<html><body><p>短</p></body></html>") is None


def test_fetch_page_text_success_and_failures() -> None:
    ok = fetch_page_text(
        "https://example.com/prof",
        client=_FakeClient(_FakeResponse(content=_HTML)),
    )
    assert ok is not None and "王学谦" in ok

    assert (
        fetch_page_text(
            "https://example.com/missing",
            client=_FakeClient(_FakeResponse(status_code=404)),
        )
        is None
    )
    assert (
        fetch_page_text(
            "https://example.com/doc.pdf",
            client=_FakeClient(
                _FakeResponse(content=b"%PDF-1.7", content_type="application/pdf")
            ),
        )
        is None
    )
    assert (
        fetch_page_text(
            "https://example.com",
            client=_FakeClient(ConnectionError("down")),
        )
        is None
    )
    assert fetch_page_text("ftp://example.com") is None


def test_thin_direct_result_escalates_to_headless() -> None:
    """JS-shell/thin direct pages escalate to the headless tier; rich direct
    pages never start the browser."""
    calls: list[str] = []

    class _FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def goto(self, url: str, timeout: int, wait_until: str) -> None:
            calls.append(url)

        def eval_on_selector(self, selector: str, script: str) -> str:
            return self._text

    class _FakeBrowser:
        def new_page(self) -> Any:
            return _FakePage("开普勒探索者D1酒店配送机器人正式发布。" * 30)

    fetcher = create_tiered_page_fetcher(
        browser_factory=lambda: _FakeBrowser(),
        direct_fetcher=lambda url: "<html><body><script>var x=1;</script></body></html>",
    )
    text = fetcher("https://example.test/js-shell")
    assert calls == ["https://example.test/js-shell"]
    assert "开普勒探索者D1酒店配送机器人" in (text or "")

    calls.clear()
    rich = "<html><body><p>" + "酒店送餐机器人主流品牌评测。" * 60 + "</p></body></html>"
    rich_fetcher = create_tiered_page_fetcher(
        browser_factory=lambda: (_ for _ in ()).throw(AssertionError("browser must not start")),
        direct_fetcher=lambda url: rich,
    )
    assert rich_fetcher("https://example.test/static") is not None
    assert calls == []


def test_headless_failure_keeps_the_snippet() -> None:
    class _HangBrowser:
        def new_page(self) -> Any:
            raise ConnectionError("browser crashed")

    fetcher = create_tiered_page_fetcher(
        browser_factory=lambda: _HangBrowser(),
        direct_fetcher=lambda url: None,
    )
    assert fetcher("https://example.test/dead") is None


def _lane_request(query: str) -> LaneRequest:
    return LaneRequest(
        lane="web",
        release_id="release-test",
        query_view="view:test",
        original_query=query,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=10_000,
            max_results=5,
        ),
        query_text=query,
        domains=("professor",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=5,
    )


def _fake_bocha(results: list[dict[str, str]]) -> Any:
    return SimpleNamespace(search=lambda query: {"organic": results})


def _empty_serper() -> Any:
    return SimpleNamespace(search=lambda query: {"organic": []})


def _adapter(
    *,
    bocha_results: list[dict[str, str]],
    page_fetcher: Any,
) -> Any:
    return serving_module._DualWebLaneAdapter(
        timeout_ms=10_000,
        max_snapshot_bytes=8_192,
        clock=lambda: NOW,
        bocha=_fake_bocha(bocha_results),
        serper=_empty_serper(),
        page_fetcher=page_fetcher,
    )


_BOCHA_RESULTS = [
    {
        "title": "王学谦教授 - 清华大学",
        "link": "https://www.tsinghua.edu.cn/prof/wxq",
        "snippet": "王学谦，教授、博士生导师。",
        "summary": "",
    },
    {
        "title": "空间机器人团队",
        "link": "https://www.sigs.tsinghua.edu.cn/wxq-team",
        "snippet": "空间机器人研究团队简介。",
        "summary": "",
    },
    {
        "title": "机器人新闻",
        "link": "https://news.example.com/robot-daily",
        "snippet": "机器人行业动态一则。",
        "summary": "",
    },
]


def test_web_lane_enriches_top_results_with_fetched_page_text() -> None:
    fetched = {
        "https://www.tsinghua.edu.cn/prof/wxq": "王学谦是清华大学深圳国际研究生院教授，研究方向为空间机器人与智能控制，发表多篇IROS论文。",
        "https://www.sigs.tsinghua.edu.cn/wxq-team": "团队长期从事空间机器人在轨服务关键技术研究。",
    }
    adapter = _adapter(
        bocha_results=_BOCHA_RESULTS,
        page_fetcher=lambda url: fetched.get(url),
    )

    result = adapter(_lane_request("清华的王学谦"))

    snippets = [
        candidate.evidence[0].snippet for candidate in result.candidates
    ]
    assert any("研究方向为空间机器人与智能控制" in text for text in snippets[:2])
    assert any("在轨服务关键技术" in text for text in snippets[:2])
    assert snippets[2].startswith("机器人新闻")
    providers = {
        candidate.evidence[0].web_snapshot is not None
        for candidate in result.candidates
    }
    assert providers == {True}


def test_web_lane_fetch_failure_keeps_original_snippet() -> None:
    def explode(url: str) -> None:
        raise ConnectionError("page unreachable")

    adapter = _adapter(bocha_results=_BOCHA_RESULTS, page_fetcher=explode)
    result = adapter(_lane_request("清华的王学谦"))

    first = result.candidates[0].evidence[0]
    assert first.snippet.startswith("王学谦教授 - 清华大学")


def test_web_lane_without_page_fetcher_keeps_original_snippet() -> None:
    adapter = _adapter(bocha_results=_BOCHA_RESULTS, page_fetcher=None)
    result = adapter(_lane_request("清华的王学谦"))

    first = result.candidates[0].evidence[0]
    assert first.snippet.startswith("王学谦教授 - 清华大学")


def test_enumeration_lane_fetches_deeper_pages_for_recall() -> None:
    """List-style queries fetch the top-5 pages; others keep top-2.

    Live-derived: DB profiles for 开普勒/九号 lack hotel-delivery terms, so
    their hotel relevance can only bind from fetched listicle bodies
    ("行业主流品牌评测" pages mention them below the snippet cut). Two fetches
    never reached those mentions; five do.
    """
    results = [
        {
            "title": f"酒店机器人榜单第{i}名",
            "link": f"https://listicle.example.com/rank-{i}",
            "snippet": f"酒店送餐机器人主流品牌评测节选{i}。",
            "summary": "",
        }
        for i in range(1, 7)
    ]
    fetched_urls: list[str] = []
    adapter = _adapter(
        bocha_results=results,
        page_fetcher=lambda url: fetched_urls.append(url) or "榜单正文：九号机器人、开普勒均有酒店配送机型。",
    )

    adapter(_lane_request("中国有哪些成熟的酒店送餐机器人供应商"))
    assert len(fetched_urls) == 5

    fetched_urls.clear()
    adapter(_lane_request("介绍清华的丁文伯"))
    assert len(fetched_urls) == 2
