"""Phase 5 — deep enumeration fetch + one refinement round (RED-first).

Adapter-level fakes: providers return org-shaped results; the fetcher
returns listicle bodies whose org lists start beyond the old 1200-char cut.
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from typing import Any

serving = import_module(
    "src.data_agents.canonical_v2.knowledge_serving_isolated"
)
trace_context = import_module(
    "src.data_agents.canonical_v2.turn_trace_context"
)

ENUM_QUERY = "深圳有哪些做具身智能的公司"


class _OrgResultsProvider:
    """Returns the same org-shaped organic list for any query; counts calls."""

    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[str] = []
        self._results = results if results is not None else [
            {"title": f"公司{i}科技有限公司", "link": f"https://example.com/org/{i}",
             "snippet": "智能制造"} for i in range(3)
        ]

    def search(self, query: str) -> dict[str, Any]:
        self.calls.append(query)
        return {"organic": list(self._results)}


class _RichProvider(_OrgResultsProvider):
    def __init__(self) -> None:
        super().__init__([
            {"title": f"公司{i}科技有限公司", "link": f"https://example.com/org/{i}",
             "snippet": "智能制造"} for i in range(8)
        ])


class _RecordingReporter:
    def __init__(self) -> None:
        self.web_outcomes: list[dict[str, Any]] = []

    def record_gate_drop(self, *_: Any, **__: Any) -> None: ...

    def record_web_outcome(self, **kwargs: Any) -> None:
        self.web_outcomes.append(kwargs)

    def set_degradation(self, *_: Any) -> None: ...

    def record_lane_counts(self, *_: Any, **__: Any) -> None: ...


def _long_listicle_body() -> str:
    head = "行业背景介绍。" * 220  # ~1540 chars: entries live in the 1200-2400 zone
    orgs = "".join(f"\n{i}. 榜单企业{chr(0x4e00 + i)}科技有限公司：专注具身智能。" for i in range(1, 9))
    return head + orgs


class _ListicleFetcher:
    def __init__(self) -> None:
        self.fetched: list[str] = []

    def __call__(self, url: str) -> str | None:
        self.fetched.append(url)
        return _long_listicle_body()


def _adapter(*, bocha: Any, serper: Any, fetcher: Any = None) -> Any:
    return serving._DualWebLaneAdapter(
        timeout_ms=8000,
        max_snapshot_bytes=1024,
        clock=lambda: datetime.now(UTC),
        bocha=bocha,
        serper=serper,
        page_fetcher=fetcher,
    )


def _request(query: str) -> Any:
    read_module = import_module(
        "src.data_agents.canonical_v2.knowledge_read"
    )
    return read_module.LaneRequest(
        lane="web",
        release_id="test-release",
        query_view=query,
        original_query=query,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=read_module.WebSearchPolicy(mode="universal"),
        query_text=query,
        domains=("company",),
        protected_slots=(),
        structured_constraints=read_module.StructuredConstraints(),
        max_candidates=16,
    )


def test_enumeration_snippet_keeps_list_beyond_1200_chars() -> None:
    fetcher = _ListicleFetcher()
    adapter = _adapter(
        bocha=_OrgResultsProvider([
            {"title": "榜单页", "link": "https://example.com/listicle",
             "snippet": "深圳具身智能企业榜单"},
        ]),
        serper=_OrgResultsProvider([]),
        fetcher=fetcher,
    )
    results = adapter._enrich_with_page_text(
        (
            serving._NormalizedWebResult(
                title="榜单页", url="https://example.com/listicle",
                snippet="深圳具身智能企业榜单", summary="",
                primary_provider_version="bocha-v1",
                corroborating_provider_versions=("bocha-v1",),
            ),
        ),
        depth=8,
    )
    # 榜单条目起点在 ~840 字符之后——旧 1200 截断会保留，但更长列表会被切；
    # 断言至少 6 个榜单条目存活（2400 窗口）。
    survived = sum(
        1 for i in range(1, 9) if f"榜单企业{chr(0x4e00 + i)}" in results[0].snippet
    )
    assert survived >= 6, f"only {survived} list entries survived the snippet window"


def test_thin_round1_triggers_refined_round2() -> None:
    bocha = _OrgResultsProvider()  # 3 org-looking results (thin)
    serper = _OrgResultsProvider([])
    adapter = _adapter(bocha=bocha, serper=serper)
    request = _request(ENUM_QUERY)
    reporter = _RecordingReporter()
    token = trace_context.set_turn_trace_reporter(reporter)
    try:
        adapter(request)
    finally:
        trace_context.reset_turn_trace_reporter(token)
    # RED today: no refinement round exists; round-2 views never searched.
    assert any(
        ("榜单" in o["view"]) or ("名单" in o["view"]) or ("盘点" in o["view"])
        for o in reporter.web_outcomes
    ), "refinement views were never searched"


def test_rich_round1_skips_refinement() -> None:
    bocha = _RichProvider()  # 8 org-looking results
    serper = _OrgResultsProvider([])
    adapter = _adapter(bocha=bocha, serper=serper)
    request = _request(ENUM_QUERY)
    reporter = _RecordingReporter()
    token = trace_context.set_turn_trace_reporter(reporter)
    try:
        adapter(request)
    finally:
        trace_context.reset_turn_trace_reporter(token)
    assert not any(
        "榜单" in o["view"] or "名单" in o["view"] or "盘点" in o["view"]
        for o in reporter.web_outcomes
    ), "refinement fired despite rich round-1"


class TestDualSourceWeighting:
    """Phase 7.1: corroborated (dual-channel) results outrank single-channel."""

    def test_corroborated_first(self) -> None:
        adapter = _adapter(
            bocha=_OrgResultsProvider([
                {"title": "单通道A", "link": "https://a.com", "snippet": ""},
                {"title": "双通道B", "link": "https://b.com", "snippet": ""},
            ]),
            serper=_OrgResultsProvider([
                {"title": "双通道B", "link": "https://b.com", "snippet": ""},
                {"title": "单通道C", "link": "https://c.com", "snippet": ""},
            ]),
        )
        results = adapter._merged_results("测试查询")
        titles = [r.title for r in results]
        assert titles[0] == "双通道B"  # corroborated first
        assert set(titles[1:]) == {"单通道A", "单通道C"}
