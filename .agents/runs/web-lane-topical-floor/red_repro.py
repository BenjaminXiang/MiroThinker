"""RED reproduction for the web-lane topical floor (T1 of the slice contract).

Runs the *current* serving code (the tree this file lives in) over the three
web results the live line 18188 admitted for the user query
「详细介绍一下 国先中心（深圳）」 (turn 3 of session bKkX9SSixSj6):

    turn-debug: .agents/runs/close-workbook-gaps/turn-debug/turn-debug-bKkX9SSixSj6-03.json
    query=详细介绍一下 国先中心（深圳）  lane_timings web=4.159s

Titles/URLs are verbatim from that turn's 「查看检索过程」 list. Snippets are
NOT recoverable from the turn debug dump (it stores evidence counts, not raw
provider text) and are reconstructed approximations, marked as such below.

Usage:  python red_repro.py            (needs the serving app on sys.path)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "miroflow-agent"))

from src.data_agents.canonical_v2 import knowledge_serving_isolated as K  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    LaneRequest,
    StructuredConstraints,
    WebSearchPolicy,
)
from src.data_agents.canonical_v2.turn_trace_context import (  # noqa: E402
    reset_turn_trace_reporter,
    set_turn_trace_reporter,
)

ANCHOR = "深圳国际先进技术应用推进中心"
QUERY = "详细介绍一下 国先中心（深圳）"

# title, url, provider versions, snippet source
CASES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "多彩深圳——减肥达人训练营深圳国贸营地简介",
        "https://www.sohu.com/a/redacted-diet-camp",
        ("bocha",),
        # reconstructed: a sohu listing page for a Shenzhen weight-loss camp;
        # the ad copy is city + camp + branch boilerplate, no 国先中心 token.
        "多彩深圳——减肥达人训练营深圳国贸营地简介：营地位于深圳市罗湖区国贸"
        "商圈，开设封闭式减肥训练、塑形课程与营养配餐，报名可享体验营名额，"
        "详情请咨询营地客服。",
    ),
    (
        "建重大平台强核心攻关优产业生态深圳新质生产力加速迸发",
        "https://www.sz.gov.cn/cn/xxgk/zfxxgj/zwdt/content/redacted",
        ("bocha", "serper"),
        # reconstructed: sz.gov.cn 政务动态 round-up of Shenzhen platform
        # projects; the paragraph below the snippet cut is where 国际先进 /
        # 技术应用 live (search-engine snippet shows the Round-up lede only).
        "深圳坚持把创新作为城市发展主导战略，加快建设重大科技基础设施与"
        "产业创新平台，推动新质生产力加速迸发。",
    ),
    (
        "百步先(深圳)信息技术有限公司",
        "https://www.11467.com/shenzhen/co/redacted.htm",
        ("bocha",),
        # reconstructed: a 11467 company-directory page whose registered-name
        # boilerplate shares the 先...中心 surface form with 国先中心.
        "百步先(深圳)信息技术有限公司主营软件开发与信息技术咨询，注册地址"
        "位于深圳市南山区，经营范围包括计算机系统集成、数据处理服务。",
    ),
)


class _Reporter:
    def __init__(self) -> None:
        self.gate_drops: list[tuple[str, int]] = []

    def record_gate_drop(self, gate_name: str, count: int) -> None:
        self.gate_drops.append((gate_name, count))

    def record_web_outcome(self, **kwargs: object) -> None:  # pragma: no cover
        pass

    def set_degradation(self, token: str) -> None:  # pragma: no cover
        pass

    def record_lane_counts(
        self, lane: str, *, in_: int, retained: int, filtered: int
    ) -> None:  # pragma: no cover
        pass


def _request(*, bound: tuple[str, ...], soft: str | None) -> LaneRequest:
    return LaneRequest(
        lane="web",
        release_id="candidate-v2-20260913-r1",
        query_view="view:web",
        original_query=QUERY,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=1500,
            max_results=8,
        ),
        query_text="详细介绍一下 国先中心（深圳） [lane=web]",
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=8,
        bound_entity_ids=tuple(
            f"company-c-{index}" for index in range(len(bound))
        ),
        bound_entity_names=bound,
        soft_context_subject=soft,
    )


def _results() -> tuple[K._NormalizedWebResult, ...]:
    return tuple(
        K._NormalizedWebResult(
            title=title,
            url=url,
            snippet=snippet,
            summary=snippet,
            primary_provider_version=providers[0],
            corroborating_provider_versions=providers,
        )
        for title, url, providers, snippet in CASES
    )


def describe(request: LaneRequest) -> None:
    results = _results()
    bound = request.bound_entity_names
    if request.soft_context_subject and request.soft_context_subject not in bound:
        bound = (*bound, request.soft_context_subject)
    print(f"  bound={bound} soft={request.soft_context_subject!r}")
    if not bound:
        print("  H1: no bound entity -> gate returns all results unfiltered")
        return
    qualifier = next(
        (
            q
            for name in bound
            if (q := K._anchor_location_qualifier(name, QUERY)) is not None
        ),
        None,
    )
    print(f"  anchor_qualifier={qualifier!r}")
    for result in results:
        tier = K._web_result_relevance_tier(
            result=result, bound_entity_names=bound, anchor_qualifier=qualifier
        )
        hits = K._web_result_hits_bound_entity(
            bound_entity_names=bound, title=result.title, snippet=result.snippet
        )
        corroborated = len(result.corroborating_provider_versions) >= 2
        print(
            f"  tier={tier} entity_hit={hits} corroborated={corroborated} "
            f"| {result.title}"
        )
    reporter = _Reporter()
    token = set_turn_trace_reporter(reporter)
    try:
        kept = K._apply_web_subject_consistency(results=results, request=request)
    finally:
        reset_turn_trace_reporter(token)
    print(f"  gate kept {len(kept)}/{len(results)}; gate_drops={reporter.gate_drops}")
    for result in kept:
        print(f"    KEPT  {result.title}")
    floored = K._apply_web_topical_floor(results=kept, request=request)
    core = K._web_query_core_tokens(QUERY)
    print(f"  core_tokens={core}")
    print(f"  floor kept {len(floored)}/{len(kept)}; gate_drops={reporter.gate_drops}")
    for result in floored:
        print(f"    KEPT  {result.title}")


def main() -> int:
    print("=" * 78)
    print(f"query: {QUERY}")
    print(f"anchor: {ANCHOR}")
    for bound, soft in (
        ((), None),
        ((ANCHOR,), None),
        ((ANCHOR,), ANCHOR),
        ((ANCHOR,), "国先中心"),
        ((), "国先中心"),
    ):
        print("-" * 78)
        print(f"CASE bound={bound} soft={soft!r}")
        describe(_request(bound=bound, soft=soft))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
