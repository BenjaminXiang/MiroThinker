"""Web-lane topical floor: reported case, exemptions, fail-open, kill switch.

Slice contract: `.agents/runs/web-lane-topical-floor/verification-contract.md`.
The reported case is the live 18188 turn
`turn-debug-bKkX9SSixSj6-03.json` (query `详细介绍一下 国先中心（深圳）`); its three
web items are verbatim in title/url, reconstructed in snippet (the turn debug
dump stores evidence counts, not raw provider text).

RED note: these tests were written before the implementation; R1/R2/R3
(`test_*_drops_*`, `test_floor_applies_to_refinement_results`) failed with the
module-level attribute missing / results unfiltered.
"""

from __future__ import annotations

from time import perf_counter

import pytest

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving
from src.data_agents.canonical_v2 import turn_trace_context
from src.data_agents.canonical_v2.knowledge_read import (
    LaneRequest,
    StructuredConstraints,
    WebSearchPolicy,
)

RELEASE_ID = "candidate-v2-20260913-r1"
ANCHOR = "深圳国际先进技术应用推进中心"
REPORTED_QUERY = "详细介绍一下 国先中心（深圳）"

# Reported turn items: (title, url, corroborating providers, snippet).
# Snippets are reconstructed (marked in red-case.md): the diet-camp page is a
# Shenzhen weight-loss camp listing, the sz.gov.cn page a platform round-up,
# the 11467 page a company directory entry.
_DIET_CAMP = (
    "多彩深圳——减肥达人训练营深圳国贸营地简介",
    "https://www.sohu.com/a/redacted-diet-camp",
    ("bocha",),
    "多彩深圳——减肥达人训练营深圳国贸营地简介：营地位于深圳市罗湖区国贸商圈，"
    "开设封闭式减肥训练、塑形课程与营养配餐，报名可享体验营名额。",
)
_PLATFORM_ROUNDUP = (
    "建重大平台强核心攻关优产业生态深圳新质生产力加速迸发",
    "https://www.sz.gov.cn/cn/xxgk/zfxxgj/zwdt/content/redacted",
    ("bocha", "serper"),
    "深圳坚持把创新作为城市发展主导战略，加快建设重大科技基础设施与产业创新平台，"
    "推动新质生产力加速迸发。",
)
_DIRECTORY_PAGE = (
    "百步先(深圳)信息技术有限公司",
    "https://www.11467.com/shenzhen/co/redacted.htm",
    ("bocha",),
    "百步先(深圳)信息技术有限公司主营软件开发与信息技术咨询，注册地址位于深圳市"
    "南山区，经营范围包括计算机系统集成、数据处理服务。",
)


def _result(
    fixture: tuple[str, str, tuple[str, ...], str],
) -> serving._NormalizedWebResult:
    title, url, providers, snippet = fixture
    return serving._NormalizedWebResult(
        title=title,
        url=url,
        snippet=snippet,
        summary=snippet,
        primary_provider_version=providers[0],
        corroborating_provider_versions=providers,
    )


def _request(
    *,
    original_query: str = REPORTED_QUERY,
    bound: tuple[str, ...] = (ANCHOR,),
    soft: str | None = None,
) -> LaneRequest:
    return LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:web",
        original_query=original_query,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=1500,
            max_results=8,
        ),
        query_text=f"{original_query} [lane=web]",
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=8,
        bound_entity_ids=tuple(f"company-c-{i}" for i in range(len(bound))),
        bound_entity_names=bound,
        soft_context_subject=soft,
    )


def _floor(
    results: tuple[serving._NormalizedWebResult, ...],
    request: LaneRequest,
) -> tuple[serving._NormalizedWebResult, ...]:
    return serving._apply_web_topical_floor(results=results, request=request)


class _Reporter:
    def __init__(self) -> None:
        self.gate_drops: list[tuple[str, int]] = []

    def record_gate_drop(self, gate_name: str, count: int) -> None:
        self.gate_drops.append((gate_name, count))

    def record_web_outcome(self, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("floor must not report web outcomes")

    def set_degradation(self, token: str) -> None:  # pragma: no cover
        raise AssertionError("floor must not set degradation")

    def record_lane_counts(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("floor must not record lane counts")


def _titles(results: tuple[serving._NormalizedWebResult, ...]) -> list[str]:
    return [result.title for result in results]


# --- core-token extraction ------------------------------------------------


def test_core_tokens_exclude_location_and_frame_words() -> None:
    assert serving._web_query_core_tokens(REPORTED_QUERY) == (
        "国先",
        "先中",
        "中心",
    )


def test_core_tokens_fail_open_without_topic() -> None:
    assert serving._web_query_core_tokens("介绍一下") == ()
    assert serving._web_query_core_tokens("请问深圳有哪些") == ()


# --- RED case -------------------------------------------------------------


def test_reported_case_drops_diet_camp_page() -> None:
    """R1: the reported sohu page shares no core token with the query.

    Composed exactly as the lane runs it — subject gate first (which backfills
    the two tier-5 pages to reach its floor), then the topical floor. The
    sz.gov.cn round-up is the gate's top-ranked result and is what the
    non-empty-lane guard retains; the two junk pages go.
    """
    results = (
        _result(_DIET_CAMP),
        _result(_PLATFORM_ROUNDUP),
        _result(_DIRECTORY_PAGE),
    )
    request = _request()
    gated = serving._apply_web_subject_consistency(results=results, request=request)
    assert len(gated) == 3, "gate backfills both T5 pages (H2) — the RED fact"
    kept = _titles(_floor(gated, request))
    assert kept == [_PLATFORM_ROUNDUP[0]]
    assert "多彩深圳——减肥达人训练营深圳国贸营地简介" not in kept
    assert "百步先(深圳)信息技术有限公司" not in kept


def test_location_only_overlap_is_not_enough() -> None:
    """R2: 深圳 alone (the query's location qualifier) never admits a result."""
    topical = _result(
        (
            "国先中心正式揭牌",
            "https://www.sz.gov.cn/redacted/gxzx",
            ("bocha",),
            "国先中心在深圳揭牌。",
        )
    )
    kept = _titles(_floor((topical, _result(_DIET_CAMP)), _request()))
    assert kept == [topical.title]


def test_floor_applies_to_refinement_results() -> None:
    """R3: refinement-round results pass the floor before the merge."""
    topical = _result(
        (
            "机器人企业榜单",
            "https://www.example.com/list",
            ("bocha",),
            "榜单收录深圳机器人企业。",
        )
    )
    refined = (topical, _result(_DIET_CAMP))
    kept = _floor(refined, _request(original_query="深圳有哪些做机器人的公司"))
    assert _titles(kept) == [topical.title]


def test_empty_floor_keeps_top_ranked_result() -> None:
    """The lane must never empty: WebLane raises 'unavailable' on no results."""
    results = (_result(_DIET_CAMP), _result(_DIRECTORY_PAGE))
    kept = _floor(results, _request())
    assert _titles(kept) == [_DIET_CAMP[0]]


# --- exemptions -----------------------------------------------------------


def test_bound_entity_page_survives_without_core_token() -> None:
    """G1: registry page naming the anchor verbatim (0 core-token overlap)."""
    page = _result(
        (
            "深圳国际先进技术应用推进中心（深圳）第一届理事会第二次会议召开",
            "http://www.sz.gov.cn/redacted/gxzx",
            ("bocha",),
            "会议审议通过中心年度工作计划，部署共性技术平台建设任务。",
        )
    )
    kept = _floor((page,), _request())
    assert _titles(kept) == [page.title]


def test_pinyin_brand_domain_survives_without_literal_overlap() -> None:
    """G2: identity domain exemption — brand domain, zero character overlap.

    The domain is built to the existing rule (pinyin of the compact alias +
    an allowed suffix): 深圳市智谱科技有限公司 -> 智谱 -> zhipu + ai. This is
    the narrow case the subject gate already trusts, and the floor must not
    undo it.
    """
    page = _result(
        (
            "Home — zhipuai",
            "https://www.zhipuai.com/en/",
            ("serper",),
            "We build large language models and agent platforms.",
        )
    )
    request = _request(
        original_query="深圳市智谱科技有限公司 简介",
        bound=("深圳市智谱科技有限公司",),
    )
    assert _titles(_floor((page,), request)) == [page.title]


def test_soft_context_subject_identity_is_exempt() -> None:
    page = _result(
        (
            "深圳国际先进技术应用推进中心正式揭牌",
            "http://www.sz.gov.cn/redacted",
            ("bocha",),
            "该中心由深圳市人民政府与国家发展改革委共同推动设立。",
        )
    )
    request = _request(bound=(), soft=ANCHOR)
    assert _titles(_floor((page,), request)) == [page.title]


def test_enumeration_regression_sample_kept() -> None:
    """G3: 深圳有哪些做机器人的公司 keeps 人形机器人企业盘点."""
    page = _result(
        (
            "人形机器人企业盘点：谁在量产",
            "https://www.example.com/list",
            ("bocha",),
            "盘点国内外人形机器人整机厂商的量产进度与融资情况。",
        )
    )
    request = _request(original_query="深圳有哪些做机器人的公司", bound=())
    assert _titles(_floor((page,), request)) == [page.title]


# --- fail-open / kill switch ---------------------------------------------


def test_fail_open_without_core_tokens() -> None:
    """G4: a query with no topical token never drops anything."""
    results = (_result(_DIET_CAMP), _result(_DIRECTORY_PAGE))
    assert _floor(results, _request(original_query="介绍一下")) == results


def test_fail_open_with_empty_text() -> None:
    page = _result(("标题", "https://example.com/x", ("bocha",), ""))
    empty = serving._NormalizedWebResult(
        title="",
        url="https://example.com/y",
        snippet="",
        summary="",
        primary_provider_version="bocha",
        corroborating_provider_versions=("bocha",),
    )
    kept = _floor((page, empty), _request())
    assert kept == (empty,)


def test_kill_switch_restores_old_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    """G5: CANONICAL_V2_WEB_TOPICAL_FLOOR=0 is a byte-identical no-op."""
    results = (_result(_DIET_CAMP), _result(_PLATFORM_ROUNDUP), _result(_DIRECTORY_PAGE))
    monkeypatch.setenv("CANONICAL_V2_WEB_TOPICAL_FLOOR", "0")
    assert _floor(results, _request()) == results
    monkeypatch.setenv("CANONICAL_V2_WEB_TOPICAL_FLOOR", "false")
    assert _floor(results, _request()) == results


def test_floor_is_deterministic() -> None:
    """G6: same input, same output (twice)."""
    results = (_result(_DIET_CAMP), _result(_PLATFORM_ROUNDUP), _result(_DIRECTORY_PAGE))
    request = _request()
    assert _floor(results, request) == _floor(results, request)


# --- observability / cost -------------------------------------------------


def test_gate_drop_is_recorded_only_when_something_drops() -> None:
    """G7: trace counts the discarded pages under the floor's own gate name."""
    topical = _result(
        (
            "国先中心在深圳揭牌",
            "http://www.sz.gov.cn/redacted/gxzx",
            ("bocha",),
            "国先中心由市人民政府与国家发展改革委共同推动设立。",
        )
    )
    reporter = _Reporter()
    token = turn_trace_context.set_turn_trace_reporter(reporter)
    try:
        _floor((topical, _result(_DIET_CAMP), _result(_DIRECTORY_PAGE)), _request())
        assert reporter.gate_drops == [("web_topical_floor", 2)]
        reporter.gate_drops.clear()
        assert _titles(_floor((topical,), _request())) == [topical.title]
        assert reporter.gate_drops == []
    finally:
        turn_trace_context.reset_turn_trace_reporter(token)


def test_floor_costs_under_five_ms_for_sixty_four_results() -> None:
    """G8: P5 budget — no model, no network, ≤5 ms for 64 results."""
    results = tuple(
        _result(
            (
                f"{_DIRECTORY_PAGE[0]}（{index}）",
                f"https://www.11467.com/shenzhen/co/{index}.htm",
                ("bocha",),
                _DIRECTORY_PAGE[3],
            )
        )
        for index in range(64)
    )
    request = _request()
    starts = perf_counter()
    for _ in range(20):
        _floor(results, request)
    elapsed_ms = (perf_counter() - starts) * 1000 / 20
    assert elapsed_ms <= 5.0, f"floor took {elapsed_ms:.3f} ms for 64 results"
