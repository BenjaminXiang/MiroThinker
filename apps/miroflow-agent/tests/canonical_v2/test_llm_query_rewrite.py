"""Hermetic contract tests for serving LLM query rewriting (recall widening).

Multi-intent and thematic/conceptual serving queries are rewritten by the
environment LLM into 1-3 short keyword-style search views. The deterministic
view stays first in the plan; the Web lane fans every view out through the
dual providers concurrently and merges all results by normalized URL. Any
rewrite failure (timeout, invalid JSON, empty list) falls back to the
deterministic view only. Identifier, single named-entity profile, and
safety-guidance queries never trigger rewriting.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import pytest

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving_module
from src.data_agents.canonical_v2.knowledge_read import (
    InstitutionCatalog,
    LaneRequest,
    QueryPlanningRequest,
    RetrievalLaneResult,
    RetrievalPlan,
    StructuredConstraints,
    WebSearchPolicy,
    create_ephemeral_knowledge_read,
    create_ephemeral_query_planner,
)
from src.data_agents.canonical_v2.knowledge_serving_isolated import (
    RecordedServingBundle,
    RecordedServingInputs,
    load_recorded_serving_inputs,
)

NOW = datetime(2026, 7, 31, 9, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s12d-rewrite-test"
MULTI_INTENT_QUERY = "爱博合创企业情况以及创始人信息还有市场对这家企业的评价如何"
THEMATIC_QUERY = "酒店送餐机器人有哪些主流品牌"
PROFILE_QUERY = "介绍清华的丁文伯"
PATENT_QUERY = "CN2024101234567.5有哪些同族专利"
GEO_QUERY = "深圳有哪些配送机器人企业推荐"
REWRITES = ("爱博合创 企业情况", "爱博合创 创始人", "爱博合创 市场评价")


class _Embedding:
    model_id = "recorded-embedding-v1"
    dimension = 32


def _timeout_prose_renderer(_: Any) -> str:
    raise TimeoutError("test-owned prose renderer is unavailable")


def _organic(title: str, link: str, snippet: str) -> dict[str, Any]:
    return {"title": title, "link": link, "snippet": snippet}


class _FakeQueryRewriter:
    """Deterministic test double for the environment LLM query rewriter."""

    producer_version = "fake-query-rewriter-v1"

    def __init__(
        self,
        queries: tuple[str, ...] = (),
        *,
        error: Exception | None = None,
    ) -> None:
        self._queries = queries
        self._error = error
        self.calls: list[str] = []

    def __call__(self, query: str) -> tuple[str, ...]:
        self.calls.append(query)
        if self._error is not None:
            raise self._error
        return self._queries


class _RoutingWebProviders:
    """Routes the first matching query marker to canned organic results."""

    def __init__(
        self,
        *,
        bocha_routes: tuple[tuple[str, tuple[dict[str, Any], ...]], ...] = (),
        serper_routes: tuple[tuple[str, tuple[dict[str, Any], ...]], ...] = (),
        bocha_barrier: Barrier | None = None,
    ) -> None:
        self.bocha_queries: list[str] = []
        self.serper_queries: list[str] = []
        self._bocha_routes = bocha_routes
        self._serper_routes = serper_routes
        self._bocha_barrier = bocha_barrier

    @staticmethod
    def _route(
        query: str,
        routes: tuple[tuple[str, tuple[dict[str, Any], ...]], ...],
    ) -> dict[str, Any]:
        for marker, results in routes:
            if marker in query:
                return {"organic": list(results)}
        return {"organic": []}

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = self

        class _Bocha:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, Any]:
                backend.bocha_queries.append(query)
                if backend._bocha_barrier is not None:
                    backend._bocha_barrier.wait(timeout=0.5)
                return backend._route(query, backend._bocha_routes)

        class _Serper:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, Any]:
                backend.serper_queries.append(query)
                return backend._route(query, backend._serper_routes)

        monkeypatch.setattr(serving_module, "BochaSearchProvider", _Bocha)
        monkeypatch.setattr(serving_module, "WebSearchProvider", _Serper)


def _bundle(tmp_path: Path, *, web_timeout_ms: int = 1500) -> RecordedServingBundle:
    return RecordedServingBundle(
        schema_version="canonical-v2-serving-bundle-v1",
        bundle_id=f"serving-bundle:{RELEASE_ID}",
        release_id=RELEASE_ID,
        database_name="miroflow_candidate_s12d_rewrite_test",
        database_target_kind="disposable",
        index_target_id=f"index:{RELEASE_ID}",
        index_root=(tmp_path / "index").resolve(),
        envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_model_id="recorded-embedding-v1",
        planner_model_id="canonical-v2-deterministic-planner-v1",
        answer_model_id="canonical-v2-deterministic-answer-v1",
        web_provider="bocha-serper-v1",
        bocha_api_key_env="BOCHA_API_KEY",
        serper_api_key_env="SERPER_API_KEY",
        max_candidates=12,
        max_web_results=5,
        web_timeout_ms=web_timeout_ms,
        web_snapshot_max_bytes=16384,
    )


def _load_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    providers: _RoutingWebProviders,
    *,
    query_rewriter: Any,
    web_timeout_ms: int = 1500,
) -> RecordedServingInputs:
    bundle = _bundle(tmp_path, web_timeout_ms=web_timeout_ms)
    path = tmp_path / "serving-bundle.json"
    path.write_text(
        json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    providers.install(monkeypatch)
    return load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12d_rewrite_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
        query_rewriter=query_rewriter,
    )


def _plan(inputs: RecordedServingInputs, query: str) -> RetrievalPlan:
    request = QueryPlanningRequest(
        request_id=f"query-request:{abs(hash(query))}",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
    )
    plan = create_ephemeral_query_planner(
        planning_policy=inputs.planning_policy,
        institution_catalog=InstitutionCatalog(
            catalog_id=f"institution-catalog:{RELEASE_ID}",
            catalog_version="institution-catalog-v1",
            release_id=RELEASE_ID,
            entries=(),
        ),
        proposal_provider=inputs.proposal_provider,
    ).plan(request)
    payload = plan.model_dump(mode="json", exclude={"content_sha256"})
    payload["supplemental_budget"] = inputs.supplemental_budget.model_dump(mode="json")
    payload["session_id"] = "session:s12d-rewrite-test"
    return RetrievalPlan.model_validate(payload)


def _read(inputs: RecordedServingInputs, plan: RetrievalPlan) -> Any:
    read = create_ephemeral_knowledge_read(
        universal_web_policy=inputs.universal_web_policy,
        lane_adapters={
            "exact": lambda request: RetrievalLaneResult(),
            "structured": lambda request: RetrievalLaneResult(),
            "lexical": lambda request: RetrievalLaneResult(),
            "vector": lambda request: RetrievalLaneResult(),
        },
        web_search=inputs.web_search,
        reranker=inputs.reranker,
        sufficiency_decider=inputs.sufficiency_decider,
        supplemental_search=inputs.supplemental_search,
        web_snapshot_policy=inputs.web_snapshot_policy,
        clock=lambda: NOW,
    )
    return read.execute(plan)


def _web_items(evidence_set: Any) -> list[Any]:
    return [item for item in evidence_set.items if item.lane == "web"]


def _lane_request(query: str) -> LaneRequest:
    return LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
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
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=12,
    )


def test_multi_intent_query_fans_out_all_views_concurrently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _RoutingWebProviders(
        bocha_barrier=Barrier(4),
        bocha_routes=(
            (
                "爱博合创 企业情况",
                (
                    _organic(
                        "爱博合创公司概况",
                        "https://example.test/aibo-profile",
                        "爱博合创专注血管介入手术机器人。",
                    ),
                ),
            ),
            (
                "爱博合创 创始人",
                (
                    _organic(
                        "爱博合创创始人专访",
                        "https://example.test/aibo-founder",
                        "爱博合创创始人介绍。",
                    ),
                ),
            ),
            (
                "爱博合创 市场评价",
                (
                    _organic(
                        "市场如何评价爱博合创",
                        "https://example.test/aibo-review",
                        "市场对爱博合创的评价汇总。",
                    ),
                ),
            ),
            (
                "爱博合创",
                (
                    _organic(
                        "爱博合创官网",
                        "https://example.test/aibo",
                        "爱博合创官方网站。",
                    ),
                ),
            ),
        ),
        serper_routes=(
            (
                "爱博合创",
                (
                    _organic(
                        "爱博合创媒体报道",
                        "https://example.test/aibo-news",
                        "媒体对爱博合创的报道。",
                    ),
                ),
            ),
        ),
    )
    rewriter = _FakeQueryRewriter(REWRITES)
    inputs = _load_inputs(
        tmp_path,
        monkeypatch,
        providers,
        query_rewriter=rewriter,
        web_timeout_ms=4000,
    )

    plan = _plan(inputs, MULTI_INTENT_QUERY)

    assert rewriter.calls == [MULTI_INTENT_QUERY]
    assert len(plan.query_views) == 4
    deterministic = plan.query_views[0]
    assert deterministic.producer_kind == "deterministic"
    assert deterministic.producer_version == "canonical-v2-deterministic-planner-v1"
    rewrite_views = plan.query_views[1:]
    assert [view.text for view in rewrite_views] == list(REWRITES)
    assert [view.producer_kind for view in rewrite_views] == ["llm_rewrite"] * 3
    assert [view.producer_version for view in rewrite_views] == [
        "fake-query-rewriter-v1"
    ] * 3
    assert len({view.view_id for view in plan.query_views}) == 4
    assert all(
        view.retained_protected_values == deterministic.retained_protected_values
        for view in rewrite_views
    )

    evidence_set = _read(inputs, plan)

    # All four views hit both providers; a serialized fan-out would trip the
    # barrier and starve every Bocha view, so the merged evidence also proves
    # concurrent execution.
    assert set(providers.bocha_queries[:4]) == {deterministic.text, *REWRITES}
    assert set(providers.serper_queries[:4]) == {deterministic.text, *REWRITES}
    web_items = _web_items(evidence_set)
    locators = [item.source_locator for item in web_items]
    assert len(locators) == len(set(locators))
    assert set(locators) == {
        "https://example.test/aibo",
        "https://example.test/aibo-profile",
        "https://example.test/aibo-founder",
        "https://example.test/aibo-review",
        "https://example.test/aibo-news",
    }
    assert all(item.claim_binding is not None for item in web_items)
    assert all(
        item.claim_binding is not None
        and item.claim_binding.status == "observed"
        and bool(item.claim_binding.predicate)
        for item in web_items
    )
    web_traces = [
        trace
        for trace in evidence_set.traces
        if trace.lane == "web" and trace.phase == "initial"
    ]
    assert len(web_traces) == 1
    assert web_traces[0].candidate_count == 5
    assert web_traces[0].status == "succeeded"


def test_thematic_query_synonym_expansion_merges_all_variants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variants = ("酒店配送机器人 品牌", "酒店送餐机器人 厂商", "酒店餐饮配送机器人")
    providers = _RoutingWebProviders(
        bocha_routes=(
            (
                "酒店配送机器人 品牌",
                (
                    _organic(
                        "酒店配送机器人品牌榜",
                        "https://example.test/hotel-robot-brands",
                        "酒店配送机器人主流品牌。",
                    ),
                ),
            ),
            (
                "酒店送餐机器人 厂商",
                (
                    _organic(
                        "酒店送餐机器人厂商名录",
                        "https://example.test/hotel-robot-vendors",
                        "酒店送餐机器人厂商汇总。",
                    ),
                ),
            ),
            (
                "酒店餐饮配送机器人",
                (
                    _organic(
                        "餐饮配送机器人方案",
                        "https://example.test/hotel-robot-solutions",
                        "酒店餐饮配送机器人解决方案。",
                    ),
                ),
            ),
            (
                "酒店送餐机器人",
                (
                    _organic(
                        "酒店送餐机器人综述",
                        "https://example.test/hotel-robot-overview",
                        "酒店送餐机器人行业综述。",
                    ),
                ),
            ),
        ),
    )
    rewriter = _FakeQueryRewriter(variants)
    inputs = _load_inputs(
        tmp_path,
        monkeypatch,
        providers,
        query_rewriter=rewriter,
    )

    plan = _plan(inputs, THEMATIC_QUERY)
    assert len(plan.query_views) == 4
    assert [view.text for view in plan.query_views[1:]] == list(variants)

    evidence_set = _read(inputs, plan)

    locators = {item.source_locator for item in _web_items(evidence_set)}
    assert locators == {
        "https://example.test/hotel-robot-brands",
        "https://example.test/hotel-robot-vendors",
        "https://example.test/hotel-robot-solutions",
        "https://example.test/hotel-robot-overview",
    }


def test_named_entity_profile_query_never_rewrites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _RoutingWebProviders(
        bocha_routes=(
            (
                "丁文伯",
                (
                    _organic(
                        "丁文伯教授简介",
                        "https://example.test/dingwenbo",
                        "丁文伯，清华大学教授。",
                    ),
                ),
            ),
        ),
    )
    rewriter = _FakeQueryRewriter(("丁文伯 论文", "丁文伯 研究方向"))
    inputs = _load_inputs(
        tmp_path,
        monkeypatch,
        providers,
        query_rewriter=rewriter,
    )

    plan = _plan(inputs, PROFILE_QUERY)

    assert rewriter.calls == []
    assert len(plan.query_views) == 1
    assert plan.query_views[0].producer_kind == "deterministic"

    evidence_set = _read(inputs, plan)

    deterministic_text = plan.query_views[0].text
    assert providers.bocha_queries == [deterministic_text]
    assert providers.serper_queries == [deterministic_text]
    assert [item.source_locator for item in _web_items(evidence_set)] == [
        "https://example.test/dingwenbo"
    ]


def test_patent_identifier_query_never_rewrites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _RoutingWebProviders()
    rewriter = _FakeQueryRewriter(("同族专利 检索",))
    inputs = _load_inputs(
        tmp_path,
        monkeypatch,
        providers,
        query_rewriter=rewriter,
    )

    plan = _plan(inputs, PATENT_QUERY)

    assert rewriter.calls == []
    assert len(plan.query_views) == 1
    assert plan.query_views[0].producer_kind == "deterministic"


def test_rewriter_timeout_falls_back_to_deterministic_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _RoutingWebProviders(
        bocha_routes=(
            (
                "酒店送餐机器人",
                (
                    _organic(
                        "酒店送餐机器人综述",
                        "https://example.test/hotel-robot-overview",
                        "酒店送餐机器人行业综述。",
                    ),
                ),
            ),
        ),
    )
    rewriter = _FakeQueryRewriter(error=TimeoutError("rewrite timed out"))
    inputs = _load_inputs(
        tmp_path,
        monkeypatch,
        providers,
        query_rewriter=rewriter,
    )

    plan = _plan(inputs, THEMATIC_QUERY)

    assert rewriter.calls == [THEMATIC_QUERY]
    assert len(plan.query_views) == 1

    evidence_set = _read(inputs, plan)

    deterministic_text = plan.query_views[0].text
    assert providers.bocha_queries == [deterministic_text]
    assert [item.source_locator for item in _web_items(evidence_set)] == [
        "https://example.test/hotel-robot-overview"
    ]


def test_rewriter_empty_output_falls_back_to_deterministic_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _RoutingWebProviders(
        bocha_routes=(
            (
                "酒店送餐机器人",
                (
                    _organic(
                        "酒店送餐机器人综述",
                        "https://example.test/hotel-robot-overview",
                        "酒店送餐机器人行业综述。",
                    ),
                ),
            ),
        ),
    )
    rewriter = _FakeQueryRewriter(())
    inputs = _load_inputs(
        tmp_path,
        monkeypatch,
        providers,
        query_rewriter=rewriter,
    )

    plan = _plan(inputs, THEMATIC_QUERY)

    assert len(plan.query_views) == 1
    evidence_set = _read(inputs, plan)
    assert providers.bocha_queries == [plan.query_views[0].text]
    assert len(_web_items(evidence_set)) == 1


def test_environment_rewriter_hard_timeout_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rewriter = serving_module._ServingQueryRewriter(timeout_seconds=0.2)

    def slow_completion(_query: str) -> str:
        time.sleep(1.5)
        return '{"queries": ["迟到"]}'

    monkeypatch.setattr(rewriter, "_chat_completion", slow_completion)
    started = time.monotonic()
    assert rewriter("酒店送餐机器人有哪些主流品牌") == ()
    assert time.monotonic() - started < 1.0


def test_environment_rewriter_invalid_json_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rewriter = serving_module._ServingQueryRewriter(timeout_seconds=0.2)
    monkeypatch.setattr(rewriter, "_chat_completion", lambda _query: "抱歉，无法改写")
    assert rewriter("酒店送餐机器人有哪些主流品牌") == ()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            '{"queries": ["酒店配送机器人", "送餐机器人品牌"]}',
            ("酒店配送机器人", "送餐机器人品牌"),
        ),
        ('```json\n{"queries": ["甲", "乙"]}\n```', ("甲", "乙")),
        ('说明文字 {"queries": ["核心查询"]} 其他', ("核心查询",)),
        ('{"queries": []}', ()),
        ('{"queries": "酒店机器人"}', ()),
        ("完全不是JSON", ()),
        ('{"results": ["错位字段"]}', ()),
        (
            '{"queries": ["", "  ", 7, "有效查询", "有效查询", "第二"]}',
            ("有效查询", "第二"),
        ),
        ('{"queries": ["q1", "q2", "q3", "q4"]}', ("q1", "q2", "q3")),
    ],
)
def test_parse_rewritten_queries(payload: str, expected: tuple[str, ...]) -> None:
    assert serving_module._parse_rewritten_queries(payload) == expected


@pytest.mark.parametrize(
    "query",
    [
        MULTI_INTENT_QUERY,
        "深圳有哪些做人形机器人的公司",
        "推荐几家深圳的服务机器人企业",
        "酒店送餐机器人的技术方案和竞争力如何",
        "固态电池的能量密度发展趋势",
        # Attribute questions carry an attribute dimension the deterministic
        # entity view does not search, so they reach the rewrite views even
        # with a named subject (matches test_rewrite_gate_fires_for_attribute_followups).
        "丁文伯教授的研究方向是什么？",
        "帕西尼感知科技（深圳）有限公司的专利以及论文情况",
    ],
)
def test_rewrite_trigger_fires(query: str) -> None:
    assert serving_module._should_rewrite_serving_query(query) is True


@pytest.mark.parametrize(
    "query",
    [
        PROFILE_QUERY,
        PATENT_QUERY,
        "arXiv:2401.12345这篇论文的贡献有哪些",
        "帕西尼感知科技（深圳）有限公司的详细信息",
        "如何防范黄赌毒场所的安全风险",
    ],
)
def test_rewrite_trigger_never_fires(query: str) -> None:
    assert serving_module._should_rewrite_serving_query(query) is False


def test_protected_geography_slot_is_retained_on_rewrite_views(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _RoutingWebProviders()
    rewriter = _FakeQueryRewriter(("配送机器人 企业", "送餐机器人 公司"))
    inputs = _load_inputs(
        tmp_path,
        monkeypatch,
        providers,
        query_rewriter=rewriter,
    )

    plan = _plan(inputs, GEO_QUERY)

    assert len(plan.query_views) == 3
    deterministic = plan.query_views[0]
    assert "深圳" in deterministic.text
    assert "深圳" in deterministic.retained_protected_values
    assert [view.text for view in plan.query_views[1:]] == [
        "配送机器人 企业 深圳",
        "送餐机器人 公司 深圳",
    ]
    assert all(
        view.retained_protected_values == deterministic.retained_protected_values
        for view in plan.query_views[1:]
    )


def test_cross_view_url_dedup_merges_corroborating_providers() -> None:
    def bocha_search(query: str) -> dict[str, Any]:
        if "配送机器人 品牌" in query:
            return {
                "organic": [
                    _organic(
                        "配送机器人品牌榜（备选标题）",
                        "https://example.test/robot-brands/",
                        "配送机器人品牌榜。",
                    )
                ]
            }
        return {
            "organic": [
                _organic(
                    "送餐机器人品牌榜",
                    "https://example.test/robot-brands",
                    "酒店送餐机器人品牌榜。",
                )
            ]
        }

    def serper_search(query: str) -> dict[str, Any]:
        if "酒店配送" in query:
            return {
                "organic": [
                    _organic(
                        "配送机器人品牌第三方榜",
                        "https://example.test/robot-brands",
                        "第三方品牌榜。",
                    )
                ]
            }
        return {"organic": []}

    adapter = serving_module._DualWebLaneAdapter(
        timeout_ms=10_000,
        max_snapshot_bytes=8_192,
        clock=lambda: NOW,
        bocha=SimpleNamespace(search=bocha_search),
        serper=SimpleNamespace(search=serper_search),
        extra_view_queries=lambda _original: ("酒店配送机器人 品牌",),
    )
    request = LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:test",
        original_query=THEMATIC_QUERY,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=10_000,
            max_results=5,
        ),
        query_text="酒店送餐机器人有哪些主流品牌",
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=12,
    )

    result = adapter(request)

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.provider_version == "bocha-v1"
    assert candidate.evidence[0].source_locator == "https://example.test/robot-brands"
    payload = json.loads(result.web_snapshot_payloads[0].content.decode("utf-8"))
    assert payload["title"] == "送餐机器人品牌榜"
    assert payload["corroborating_provider_versions"] == ["bocha-v1", "serper-v1"]


def test_bocha_garbage_keeps_good_serper_hits() -> None:
    bocha = SimpleNamespace(
        search=lambda _query: {
            "organic": [
                {"title": "", "link": "https://example.test/empty-title"},
                {"title": "无链接", "link": ""},
                {"title": "坏协议", "link": "ftp://example.test/x"},
                "junk",
                {"title": "相对路径", "link": "/local/path"},
            ]
        }
    )
    serper = SimpleNamespace(
        search=lambda _query: {
            "organic": [
                _organic(
                    "酒店机器人品牌一",
                    "https://example.test/brand-one",
                    "品牌一介绍。",
                ),
                _organic(
                    "酒店机器人品牌二",
                    "https://example.test/brand-two",
                    "品牌二介绍。",
                ),
            ]
        }
    )
    adapter = serving_module._DualWebLaneAdapter(
        timeout_ms=10_000,
        max_snapshot_bytes=8_192,
        clock=lambda: NOW,
        bocha=bocha,
        serper=serper,
    )
    request = LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:test",
        original_query=THEMATIC_QUERY,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=10_000,
            max_results=5,
        ),
        query_text="酒店送餐机器人有哪些主流品牌",
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=12,
    )

    result = adapter(request)

    assert [candidate.provider_version for candidate in result.candidates] == [
        "serper-v1",
        "serper-v1",
    ]
    assert [
        candidate.evidence[0].source_locator for candidate in result.candidates
    ] == [
        "https://example.test/brand-one",
        "https://example.test/brand-two",
    ]


def test_gap_check_triggers_one_bounded_followup_round() -> None:
    """A covered=False gap check fires at most two follow-up queries and merges
    their results by URL; a covered check stays a pure single pass."""
    from src.data_agents.canonical_v2 import llm_judgments as lj

    queries: list[str] = []

    def fake_search_provider(query: str) -> dict[str, Any]:
        queries.append(query)
        if query == "具身智能 遥操作 动捕 具体方式":
            return {
                "organic": [
                    _organic(
                        "具身智能遥操作与动捕数据采集综述",
                        "https://example.test/teleop",
                        "遥操作与动作捕捉是真实数据采集的两条主路。",
                    )
                ]
            }
        return {
            "organic": [
                _organic(
                    "行业新闻",
                    "https://example.test/news",
                    "机器人行业动态。",
                )
            ]
        }

    class _Judge:
        def judge_batch(
            self,
            kind: str,
            question: str,
            items: Any,
            context: str = "",
        ) -> Any:
            return (
                lj.GapCheckResult(
                    covered=False,
                    missing_aspects=("真实数据采集具体方式",),
                    followup_queries=(
                        "具身智能 遥操作 动捕 具体方式",
                        "具身智能 真机数据 采集",
                        "第三条不该发",
                    ),
                ),
            )

    adapter = serving_module._DualWebLaneAdapter(
        timeout_ms=10_000,
        max_snapshot_bytes=8_192,
        clock=lambda: NOW,
        bocha=SimpleNamespace(search=fake_search_provider),
        serper=SimpleNamespace(search=lambda query: {"organic": []}),
        page_fetcher=None,
        gap_judge=_Judge(),
    )
    result = adapter(_lane_request("在真实数据采集路线中，有哪些具体方式"))
    assert queries.count("具身智能 遥操作 动捕 具体方式") == 1
    assert queries.count("具身智能 真机数据 采集") == 1
    assert "第三条不该发" not in queries
    assert any(
        "遥操作" in candidate.evidence[0].snippet for candidate in result.candidates
    )
