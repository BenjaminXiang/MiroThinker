"""Hermetic contract tests for serving person-criteria sufficiency/supplemental.

The serving path answers person-criteria questions (毕业于X 的企业家/创始人是谁)
over a release whose local evidence names the companies but not the people.
These tests drive the real serving pipeline — deterministic planner, ephemeral
knowledge read, serving sufficiency decider, and serving supplemental search —
with fake dual-Web providers and fake local lanes, asserting that:

* thin local evidence with company candidates triggers bounded per-candidate
  probes whose person evidence reaches the final evidence set inside the
  supplemental budget;
* missing candidates, already-sufficient local evidence, exhausted budgets,
  and non-person-criteria queries all behave honestly.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving_module
from src.data_agents.canonical_v2.knowledge_read import (
    EvidenceClaimBinding,
    EvidenceItem,
    InstitutionCatalog,
    QueryPlanningRequest,
    RecallCandidate,
    RetrievalLaneResult,
    RetrievalPlan,
    SupplementalBudget,
    create_ephemeral_knowledge_read,
    create_ephemeral_query_planner,
)
from src.data_agents.canonical_v2.knowledge_serving_isolated import (
    RecordedServingBundle,
    RecordedServingInputs,
    load_recorded_serving_inputs,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s11-person-test"
PERSON_QUERY = "毕业于早稻田，且在深圳专注在机器人行业的企业家有谁"
PASINI = "帕西尼感知科技（深圳）有限公司"
MAIBU = "深圳市迈步机器人科技有限公司"


class _Embedding:
    model_id = "recorded-embedding-v1"
    dimension = 32


def _timeout_prose_renderer(_: Any) -> str:
    raise TimeoutError("test-owned prose renderer is unavailable")


class _DisabledQueryRewriter:
    """Keep serving tests hermetic: like the environment prose renderer, the
    environment LLM query rewriter must stay out of unit tests even when an
    API key is resolvable; disabled rewriting keeps the deterministic
    single-view plans these contracts assert."""

    producer_version = "test-disabled-query-rewriter-v1"

    def __call__(self, _query: str) -> tuple[str, ...]:
        return ()


@pytest.fixture(autouse=True)
def _disable_environment_query_rewriter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        serving_module,
        "_ServingQueryRewriter",
        _DisabledQueryRewriter,
    )


def _bundle(tmp_path: Path) -> RecordedServingBundle:
    return RecordedServingBundle(
        schema_version="canonical-v2-serving-bundle-v1",
        bundle_id=f"serving-bundle:{RELEASE_ID}",
        release_id=RELEASE_ID,
        database_name="miroflow_candidate_s11_person_test",
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
        web_timeout_ms=1500,
        web_snapshot_max_bytes=16384,
    )


class _FakeDualWebProviders:
    """Routes probe queries to person articles and everything else to news."""

    def __init__(self) -> None:
        self.bocha_queries: list[str] = []

    def _organic(
        self,
        *,
        title: str,
        link: str,
        snippet: str,
    ) -> dict[str, object]:
        return {
            "organic": [
                {
                    "title": title,
                    "link": link,
                    "snippet": snippet,
                }
            ]
        }

    def _search(self, query: str) -> dict[str, object]:
        self.bocha_queries.append(query)
        if "帕西尼" in query and ("早稻田" in query or "创始人" in query):
            return self._organic(
                title="帕西尼感知科技创始人许晋诚：早稻田大学博士团队创业",
                link="https://example.test/pasini-founder",
                snippet=(
                    f"{PASINI}创始人许晋诚，毕业于早稻田大学，"
                    "师从菅野重树教授，专注机器人触觉感知技术。"
                ),
            )
        if "迈步" in query and ("早稻田" in query or "创始人" in query):
            return self._organic(
                title="迈步机器人创始人陈功：早稻田大学毕业后回国创业",
                link="https://example.test/maibu-founder",
                snippet=(
                    f"{MAIBU}创始人兼CEO陈功，早稻田大学毕业后回国创业，"
                    "专注康复外骨骼机器人。"
                ),
            )
        return self._organic(
            title="深圳机器人产业动态",
            link="https://example.test/robotics-news",
            snippet="深圳机器人行业融资新闻汇总，多家企业布局。",
        )

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = self

        class _Bocha:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return backend._search(query)

        class _Serper:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return {"organic": []}

        monkeypatch.setattr(serving_module, "BochaSearchProvider", _Bocha)
        monkeypatch.setattr(serving_module, "WebSearchProvider", _Serper)


def _load_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    providers: _FakeDualWebProviders | _FakeRelationProviders,
    *,
    web_timeout_ms: int = 1500,
) -> RecordedServingInputs:
    base = _bundle(tmp_path)
    bundle = RecordedServingBundle.model_validate(
        {
            **base.model_dump(mode="json", exclude={"content_sha256"}),
            "web_timeout_ms": web_timeout_ms,
        }
    )
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
        expected_database="miroflow_candidate_s11_person_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )


def _local_company_item(
    token: str,
    name: str,
    summary: str,
    *,
    canonical_id: str | None = None,
    predicate: str = "geography",
    value: str = "深圳",
) -> EvidenceItem:
    object_id = canonical_id if canonical_id is not None else f"company:{token}"
    return EvidenceItem(
        evidence_id=f"evidence:local:{token}",
        object_id=object_id,
        domain="company",
        lane="lexical",
        source_nature="local",
        source_locator=f"canonical-v2-isolated:{token}",
        snippet=json.dumps(
            {"name": name, "profile_summary": summary},
            ensure_ascii=False,
        ),
        score=1.0,
        source_authority="canonical_release",
        observed_at=NOW,
        claim_binding=EvidenceClaimBinding(
            subject_id=object_id,
            predicate=predicate,
            value=value,
            status="admitted",
        ),
    )


def _local_company_candidate(
    token: str, name: str, item: EvidenceItem, *, canonical_id: str | None = None
) -> RecallCandidate:
    return RecallCandidate(
        raw_candidate_id=f"raw:lexical:{token}",
        display_name=name,
        domain="company",
        identity_kind="canonical",
        canonical_id=canonical_id if canonical_id is not None else f"company:{token}",
        resolution_state="resolved",
        query_view="view:original",
        lane="lexical",
        attempt=1,
        release_id=RELEASE_ID,
        adapter_version="test-lexical-v1",
        raw_score=1.0,
        evidence=(item,),
    )


def _plan(
    inputs: RecordedServingInputs,
    query: str,
    *,
    supplemental_budget: SupplementalBudget | None = None,
    displayed: tuple[tuple[str, ...], tuple[str, ...]] | None = None,
) -> Any:
    displayed_ids, displayed_names = displayed or ((), ())
    request = QueryPlanningRequest(
        request_id=f"query-request:{abs(hash(query))}",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
        displayed_entity_ids=displayed_ids,
        displayed_entity_names=displayed_names,
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
    payload["supplemental_budget"] = (
        supplemental_budget
        if supplemental_budget is not None
        else inputs.supplemental_budget
    ).model_dump(mode="json")
    payload["session_id"] = "session:s11-person-test"
    return RetrievalPlan.model_validate(payload)


def _read(
    inputs: RecordedServingInputs,
    *,
    local_candidates: tuple[RecallCandidate, ...],
    plan: Any,
) -> Any:
    read = create_ephemeral_knowledge_read(
        universal_web_policy=inputs.universal_web_policy,
        lane_adapters={
            "exact": lambda request: RetrievalLaneResult(),
            "structured": lambda request: RetrievalLaneResult(),
            "lexical": lambda request: RetrievalLaneResult(candidates=local_candidates),
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


def _thin_local_candidates() -> tuple[RecallCandidate, ...]:
    pasini_item = _local_company_item(
        "pasini",
        PASINI,
        "专注机器人触觉传感器与灵巧手。",
    )
    maibu_item = _local_company_item(
        "maibu",
        MAIBU,
        "专注康复外骨骼机器人。",
    )
    return (
        _local_company_candidate("pasini", PASINI, pasini_item),
        _local_company_candidate("maibu", MAIBU, maibu_item),
    )


def _probe_queries(providers: _FakeDualWebProviders) -> list[str]:
    return [
        query
        for query in providers.bocha_queries
        if "帕西尼" in query or "迈步" in query
    ]


def test_person_criteria_gap_triggers_bounded_per_candidate_probes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _FakeDualWebProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    plan = _plan(inputs, PERSON_QUERY)

    assert len(plan.material_parts) == 1
    part = plan.material_parts[0]
    assert part.subject_id.startswith("serving-person-criteria:")
    assert part.predicate == "geography"
    assert part.requested_value == "深圳"

    evidence_set = _read(
        inputs,
        local_candidates=_thin_local_candidates(),
        plan=plan,
    )

    probes = _probe_queries(providers)
    assert sorted(probes) == sorted(
        [
            f"{MAIBU} 早稻田",
            f"{PASINI} 早稻田",
        ]
    )
    supplemental_items = tuple(
        item for item in evidence_set.items if item.lane == "supplemental"
    )
    assert len(supplemental_items) == 1
    aggregate = supplemental_items[0]
    assert aggregate.domain == "company"
    assert aggregate.source_nature != "current_web"
    assert aggregate.source_authority == "web_search"
    assert aggregate.web_snapshot is not None
    assert aggregate.claim_binding is not None
    assert aggregate.claim_binding.subject_id == part.subject_id
    assert aggregate.claim_binding.predicate == part.predicate
    assert aggregate.claim_binding.value == part.requested_value
    assert "许晋诚" in aggregate.snippet
    assert "早稻田" in aggregate.snippet
    assert "陈功" in aggregate.snippet
    report = evidence_set.sufficiency_report
    assert report is not None
    assert report.complete is True
    decision = report.parts[0]
    assert decision.outcome == "supported"
    assert decision.evidence_ids == (aggregate.evidence_id,)
    receipt = evidence_set.supplemental_budget_receipt
    assert receipt is not None
    assert receipt.exhausted is False
    assert receipt.provider_calls <= inputs.supplemental_budget.max_provider_calls
    assert receipt.retry_count <= inputs.supplemental_budget.max_retries
    assert receipt.elapsed_ms <= inputs.supplemental_budget.max_wall_time_ms
    assert receipt.cost_units <= inputs.supplemental_budget.max_cost_units
    assert "evidence_gap" not in evidence_set.continuation_reasons
    assert all(
        limitation.code != "supplemental_budget_exhausted"
        for limitation in evidence_set.limitations
    )
    supplemental_traces = tuple(
        trace for trace in evidence_set.traces if trace.phase == "supplemental"
    )
    assert len(supplemental_traces) == 1
    assert supplemental_traces[0].status == "succeeded"


def test_no_company_candidates_means_no_probes_and_honest_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _FakeDualWebProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    plan = _plan(inputs, PERSON_QUERY)

    evidence_set = _read(inputs, local_candidates=(), plan=plan)

    assert _probe_queries(providers) == []
    assert all(item.lane != "supplemental" for item in evidence_set.items)
    report = evidence_set.sufficiency_report
    assert report is not None
    assert report.complete is False
    assert report.parts[0].outcome == "missing"
    assert "evidence_gap" in evidence_set.continuation_reasons
    receipt = evidence_set.supplemental_budget_receipt
    assert receipt is not None
    assert receipt.exhausted is False
    assert receipt.cost_units == 0.0
    supplemental_traces = tuple(
        trace for trace in evidence_set.traces if trace.phase == "supplemental"
    )
    assert len(supplemental_traces) == 1
    assert supplemental_traces[0].candidate_count == 0


def test_local_person_evidence_skips_probes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _FakeDualWebProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    plan = _plan(inputs, PERSON_QUERY)
    covering_item = _local_company_item(
        "pasini",
        PASINI,
        "创始人许晋诚，毕业于早稻田大学，专注机器人触觉感知技术。",
    )
    candidates = (_local_company_candidate("pasini", PASINI, covering_item),)

    evidence_set = _read(inputs, local_candidates=candidates, plan=plan)

    assert _probe_queries(providers) == []
    report = evidence_set.sufficiency_report
    assert report is not None
    assert report.complete is True
    assert report.parts[0].outcome == "supported"
    rebound = tuple(item for item in evidence_set.items if item.lane == "supplemental")
    assert len(rebound) == 1
    assert rebound[0].source_nature == "local"
    assert "许晋诚" in rebound[0].snippet
    assert report.parts[0].evidence_ids == (rebound[0].evidence_id,)
    receipt = evidence_set.supplemental_budget_receipt
    assert receipt is not None
    assert receipt.exhausted is False
    assert receipt.cost_units == 0.0
    assert "evidence_gap" not in evidence_set.continuation_reasons


def test_exhausted_budget_returns_partial_result_with_typed_limitation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _FakeDualWebProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    tight_budget = SupplementalBudget(
        max_wall_time_ms=1500,
        max_provider_calls=1,
        max_retries=0,
        max_cost_units=2.0,
    )
    plan = _plan(inputs, PERSON_QUERY, supplemental_budget=tight_budget)

    evidence_set = _read(
        inputs,
        local_candidates=_thin_local_candidates(),
        plan=plan,
    )

    probes = _probe_queries(providers)
    assert len(probes) == 2
    supplemental_items = tuple(
        item for item in evidence_set.items if item.lane == "supplemental"
    )
    assert len(supplemental_items) == 1
    assert "许晋诚" in supplemental_items[0].snippet
    receipt = evidence_set.supplemental_budget_receipt
    assert receipt is not None
    assert receipt.exhausted is True
    assert receipt.exhaustion_reason == "provider_calls"
    assert receipt.exhausted_axis == "provider_calls"
    assert receipt.provider_calls <= tight_budget.max_provider_calls
    assert receipt.elapsed_ms <= tight_budget.max_wall_time_ms
    assert receipt.cost_units <= tight_budget.max_cost_units
    limitations = tuple(
        limitation
        for limitation in evidence_set.limitations
        if limitation.code == "supplemental_budget_exhausted"
    )
    assert len(limitations) == 1
    assert limitations[0].material is True
    assert limitations[0].material_part_ids == (plan.material_parts[0].part_id,)
    assert limitations[0].reason == "provider_calls"
    assert "budget_exhausted" in evidence_set.continuation_reasons


def test_named_who_is_query_stays_off_the_supplemental_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare "X是谁" asks about a named subject, not people-by-criteria.

    Person-criteria probes exist to find PEOPLE BY CRITERIA (founder role or
    education constraint) across candidate companies. A bare who-is question
    carries no probe-able criteria, so the planner must not mint a
    person-criteria material part: otherwise the serving layer would fire
    per-company "创始人" probes and could append a spurious gap sentence to a
    plain profile answer.
    """
    providers = _FakeDualWebProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    for query in ("冯娟是谁", "王力是谁"):
        plan = _plan(inputs, query)

        assert plan.material_parts == ()

        evidence_set = _read(
            inputs,
            local_candidates=_thin_local_candidates(),
            plan=plan,
        )

        assert evidence_set.sufficiency_report is None
        assert evidence_set.supplemental_budget_receipt is None
        assert all(item.lane != "supplemental" for item in evidence_set.items)
        assert _probe_queries(providers) == []


def test_non_person_criteria_query_stays_off_the_supplemental_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plain profile question has no probe-able criteria at all."""
    providers = _FakeDualWebProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    query = "介绍清华的丁文伯"
    plan = _plan(inputs, query)

    assert plan.material_parts == ()

    evidence_set = _read(
        inputs,
        local_candidates=_thin_local_candidates(),
        plan=plan,
    )

    assert evidence_set.sufficiency_report is None
    assert evidence_set.supplemental_budget_receipt is None
    assert all(trace.phase != "supplemental" for trace in evidence_set.traces)
    assert all(item.lane != "supplemental" for item in evidence_set.items)
    assert _probe_queries(providers) == []


class _FakeRelationProviders:
    """Routes per-entity relation probes; generic contextual queries get news."""

    def __init__(self) -> None:
        self.bocha_queries: list[str] = []

    def _organic(
        self,
        *,
        title: str,
        link: str,
        snippet: str,
    ) -> dict[str, object]:
        return {
            "organic": [
                {
                    "title": title,
                    "link": link,
                    "snippet": snippet,
                }
            ]
        }

    def _news(self) -> dict[str, object]:
        return self._organic(
            title="深圳机器人产业动态",
            link="https://example.test/robotics-news",
            snippet="深圳机器人行业融资新闻汇总，多家企业布局。",
        )

    def _search(self, query: str) -> dict[str, object]:
        self.bocha_queries.append(query)
        if query.endswith(" 机械臂 按电梯"):
            return self._organic(
                title="普渡科技闪电匣配送机器人发布",
                link="https://example.test/pudu-flashbot-arm",
                snippet=(
                    "深圳市普渡科技有限公司闪电匣机器人可以自主机械臂按电梯，"
                    "覆盖酒店楼宇配送。"
                ),
            )
        if query.endswith(" 总部") and "普渡" in query:
            return self._organic(
                title="深圳市普渡科技有限公司官网",
                link="https://example.test/pudu-hq",
                snippet="普渡机器人成立于2016年，总部位于广东深圳，专注酒店配送机器人。",
            )
        if query.endswith(" 总部") and "迈步" in query:
            return self._organic(
                title="迈步机器人官网",
                link="https://example.test/maibu-hq",
                snippet="深圳市迈步机器人科技有限公司总部位于深圳，专注康复外骨骼机器人。",
            )
        if query.endswith(" 总部") and "奥达智声" in query:
            return self._organic(
                title="奥达智声官网",
                link="https://example.test/aoda-hq",
                snippet="深圳奥达智声科技有限公司总部位于上海，专注医疗手术机器人。",
            )
        return self._news()

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = self

        class _Bocha:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return backend._search(query)

        class _Serper:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return {"organic": []}

        monkeypatch.setattr(serving_module, "BochaSearchProvider", _Bocha)
        monkeypatch.setattr(serving_module, "WebSearchProvider", _Serper)


PUDU_ID = "company-c-pudu"
PUDU_NAME = "深圳市普渡科技有限公司"
MAIBU_ROBOT_ID = "company-c-maibu"
MAIBU_ROBOT_NAME = "深圳市迈步机器人科技有限公司"
AODA_ID = "company-c-aoda"
AODA_NAME = "深圳奥达智声科技有限公司"
HQ_QUERY = "上述企业里总部在深圳的企业有哪些"
CAPABILITY_QUERY = "上述企业的产品哪些能机械臂按电梯"


def _projection_local_candidate(
    token: str,
    canonical_id: str,
    name: str,
    summary: str,
) -> RecallCandidate:
    item = _local_company_item(
        token,
        name,
        summary,
        canonical_id=canonical_id,
        predicate="canonical_projection",
        value="a" * 64,
    )
    return _local_company_candidate(token, name, item, canonical_id=canonical_id)


def _relation_probe_queries(providers: _FakeRelationProviders) -> list[str]:
    return [
        query
        for query in providers.bocha_queries
        if query.endswith((" 总部", " 机械臂 按电梯"))
    ]


def test_hq_followup_with_unbound_web_triggers_per_company_probes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _FakeRelationProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    displayed_ids = (PUDU_ID, MAIBU_ROBOT_ID, AODA_ID)
    displayed_names = (PUDU_NAME, MAIBU_ROBOT_NAME, AODA_NAME)
    plan = _plan(
        inputs,
        HQ_QUERY,
        displayed=(displayed_ids, displayed_names),
    )

    parts = plan.material_parts
    assert len(parts) == 3
    assert {part.subject_id for part in parts} == set(displayed_ids)
    assert all(
        part.predicate == "geography" and part.requested_value == "深圳"
        for part in parts
    )

    local_candidates = (
        _projection_local_candidate("pudu", PUDU_ID, PUDU_NAME, "酒店配送机器人。"),
        _projection_local_candidate(
            "maibu", MAIBU_ROBOT_ID, MAIBU_ROBOT_NAME, "康复外骨骼机器人。"
        ),
        _projection_local_candidate("aoda", AODA_ID, AODA_NAME, "医疗手术机器人。"),
    )
    evidence_set = _read(inputs, local_candidates=local_candidates, plan=plan)

    probes = _relation_probe_queries(providers)
    assert sorted(probes) == sorted(
        [
            f"{PUDU_NAME} 总部",
            f"{MAIBU_ROBOT_NAME} 总部",
            f"{AODA_NAME} 总部",
        ]
    )
    supplemental_by_object = {
        item.object_id: item
        for item in evidence_set.items
        if item.lane == "supplemental"
    }
    assert set(supplemental_by_object) == {PUDU_ID, MAIBU_ROBOT_ID}
    for object_id, item in supplemental_by_object.items():
        assert item.domain == "company"
        assert item.source_nature != "current_web"
        assert item.source_authority == "web_search"
        assert item.web_snapshot is not None
        assert item.claim_binding is not None
        assert item.claim_binding.subject_id == object_id
        assert item.claim_binding.predicate == "geography"
        assert item.claim_binding.value == "深圳"
        assert "总部" in item.snippet
    report = evidence_set.sufficiency_report
    assert report is not None
    subject_by_part_id = {part.part_id: part.subject_id for part in parts}
    supported_subjects = {
        subject_by_part_id[part.part_id]
        for part in report.parts
        if part.outcome == "supported"
    }
    assert supported_subjects == {PUDU_ID, MAIBU_ROBOT_ID}
    aoda_part = next(part for part in parts if part.subject_id == AODA_ID)
    aoda_decision = next(
        part for part in report.parts if part.part_id == aoda_part.part_id
    )
    assert aoda_decision.outcome == "missing"
    receipt = evidence_set.supplemental_budget_receipt
    assert receipt is not None
    assert receipt.exhausted is False
    assert receipt.provider_calls <= inputs.supplemental_budget.max_provider_calls
    assert receipt.retry_count <= inputs.supplemental_budget.max_retries
    assert receipt.elapsed_ms <= inputs.supplemental_budget.max_wall_time_ms
    assert receipt.cost_units <= inputs.supplemental_budget.max_cost_units
    supplemental_traces = tuple(
        trace for trace in evidence_set.traces if trace.phase == "supplemental"
    )
    assert len(supplemental_traces) == 1
    assert supplemental_traces[0].status == "succeeded"


def test_capability_followup_triggers_targeted_capability_probes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _FakeRelationProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    plan = _plan(
        inputs,
        CAPABILITY_QUERY,
        displayed=((PUDU_ID,), (PUDU_NAME,)),
    )

    assert len(plan.material_parts) == 1
    part = plan.material_parts[0]
    assert part.subject_id == PUDU_ID
    assert part.predicate == "product_capability_evidence"
    assert part.requested_value == "机械臂 + 按电梯"

    local_candidates = (
        _projection_local_candidate("pudu", PUDU_ID, PUDU_NAME, "酒店配送机器人。"),
    )
    evidence_set = _read(inputs, local_candidates=local_candidates, plan=plan)

    probes = _relation_probe_queries(providers)
    assert probes == [f"{PUDU_NAME} 机械臂 按电梯"]
    supplemental_items = tuple(
        item for item in evidence_set.items if item.lane == "supplemental"
    )
    assert len(supplemental_items) == 1
    capability_item = supplemental_items[0]
    assert capability_item.object_id == PUDU_ID
    assert capability_item.claim_binding is not None
    assert capability_item.claim_binding.subject_id == PUDU_ID
    assert capability_item.claim_binding.predicate == "product_capability_evidence"
    assert capability_item.claim_binding.value == "机械臂 + 按电梯"
    assert "机械臂" in capability_item.snippet
    assert "按电梯" in capability_item.snippet
    report = evidence_set.sufficiency_report
    assert report is not None
    assert report.complete is True
    assert report.parts[0].outcome == "supported"
    assert report.parts[0].evidence_ids == (capability_item.evidence_id,)
    receipt = evidence_set.supplemental_budget_receipt
    assert receipt is not None
    assert receipt.exhausted is False
    assert receipt.cost_units <= inputs.supplemental_budget.max_cost_units


def test_relation_evidence_already_bound_skips_probes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = _FakeRelationProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    plan = _plan(
        inputs,
        HQ_QUERY,
        displayed=((PUDU_ID,), (PUDU_NAME,)),
    )
    covering_item = _local_company_item(
        "pudu",
        PUDU_NAME,
        "普渡机器人总部位于深圳，专注酒店配送机器人。",
        canonical_id=PUDU_ID,
    )
    candidates = (
        _local_company_candidate(
            "pudu", PUDU_NAME, covering_item, canonical_id=PUDU_ID
        ),
    )

    evidence_set = _read(inputs, local_candidates=candidates, plan=plan)

    assert _relation_probe_queries(providers) == []
    assert all(item.lane != "supplemental" for item in evidence_set.items)
    report = evidence_set.sufficiency_report
    assert report is not None
    assert report.complete is True
    assert report.parts[0].outcome == "supported"
    assert report.parts[0].evidence_ids == (covering_item.evidence_id,)
    assert evidence_set.supplemental_budget_receipt is None
    assert "evidence_gap" not in evidence_set.continuation_reasons


def test_capability_probes_cover_the_whole_displayed_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-company relation probes must not starve later displayed members.

    Live-derived: a six-company displayed set capped the probes at the first
    three companies, so 普渡's 机械臂按电梯 evidence was never fetched even
    though the provider had it. Parts and probes cover up to six displayed
    companies, still inside the supplemental budget.
    """
    providers = _FakeRelationProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    displayed_ids = (
        AODA_ID,
        MAIBU_ROBOT_ID,
        "company-c-jia",
        "company-c-yi",
        "company-c-bing",
        PUDU_ID,
    )
    displayed_names = (
        AODA_NAME,
        MAIBU_ROBOT_NAME,
        "深圳市甲机器人有限公司",
        "深圳市乙机器人有限公司",
        "深圳市丙机器人有限公司",
        PUDU_NAME,
    )
    plan = _plan(
        inputs,
        CAPABILITY_QUERY,
        displayed=(displayed_ids, displayed_names),
    )

    parts = plan.material_parts
    assert len(parts) == 6
    assert {part.subject_id for part in parts} == set(displayed_ids)

    local_candidates = tuple(
        _projection_local_candidate(f"member{index}", cid, name, "服务机器人。")
        for index, (cid, name) in enumerate(
            zip(displayed_ids, displayed_names, strict=True)
        )
    )
    evidence_set = _read(inputs, local_candidates=local_candidates, plan=plan)

    probes = _relation_probe_queries(providers)
    assert sorted(probes) == sorted(f"{name} 机械臂 按电梯" for name in displayed_names)
    supplemental_by_object = {
        item.object_id: item
        for item in evidence_set.items
        if item.lane == "supplemental"
    }
    assert set(supplemental_by_object) == {PUDU_ID}
    capability_item = supplemental_by_object[PUDU_ID]
    assert capability_item.claim_binding is not None
    assert capability_item.claim_binding.subject_id == PUDU_ID
    assert capability_item.claim_binding.predicate == "product_capability_evidence"
    report = evidence_set.sufficiency_report
    assert report is not None
    subject_by_part_id = {part.part_id: part.subject_id for part in parts}
    supported_subjects = {
        subject_by_part_id[part.part_id]
        for part in report.parts
        if part.outcome == "supported"
    }
    assert supported_subjects == {PUDU_ID}
    receipt = evidence_set.supplemental_budget_receipt
    assert receipt is not None
    assert receipt.exhausted is False
    assert receipt.cost_units <= inputs.supplemental_budget.max_cost_units


class _SlowSerperRelationProviders(_FakeRelationProviders):
    """Bocha answers instantly with news; Serper answers after 1.5s with the
    capability hit (live-derived: Serper needs ~2s from this network, Bocha
    cannot resolve per-company capability probes at all)."""

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = self

        class _Bocha:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return backend._news()

        class _Serper:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                time.sleep(1.5)
                return backend._search(query)

        monkeypatch.setattr(serving_module, "BochaSearchProvider", _Bocha)
        monkeypatch.setattr(serving_module, "WebSearchProvider", _Serper)


def test_capability_probe_waits_for_slow_serper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe providers must get enough wall time for a ~2s Serper round trip.

    Live-derived: the probe adapter's 1s per-provider deadline always cut
    Serper off, leaving only Bocha's unresolvable results, so per-company
    capability probes systematically returned empty even when the evidence
    was one Serper call away.
    """
    providers = _SlowSerperRelationProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers, web_timeout_ms=10_000)
    plan = _plan(
        inputs,
        CAPABILITY_QUERY,
        displayed=((PUDU_ID,), (PUDU_NAME,)),
    )

    local_candidates = (
        _projection_local_candidate("pudu", PUDU_ID, PUDU_NAME, "酒店配送机器人。"),
    )
    evidence_set = _read(inputs, local_candidates=local_candidates, plan=plan)

    supplemental_items = tuple(
        item for item in evidence_set.items if item.lane == "supplemental"
    )
    assert len(supplemental_items) == 1
    capability_item = supplemental_items[0]
    assert capability_item.object_id == PUDU_ID
    assert capability_item.claim_binding is not None
    assert capability_item.claim_binding.predicate == "product_capability_evidence"
    assert capability_item.claim_binding.value == "机械臂 + 按电梯"
    report = evidence_set.sufficiency_report
    assert report is not None
    assert report.complete is True
    assert report.parts[0].outcome == "supported"


class _FounderWordingProviders:
    """Live-derived probe pages: founding teams are described with 创立/创始团队
    wording, never with the literal 创始人 marker."""

    def __init__(self) -> None:
        self.bocha_queries: list[str] = []

    def _search(self, query: str) -> dict[str, object]:
        self.bocha_queries.append(query)
        if "迈步" in query and "早稻田" in query:
            return {
                "organic": [
                    {
                        "title": "迈步团队- 迈步机器人-Walk with MileBot",
                        "link": "https://example.test/maibu-team",
                        "snippet": (
                            "公司由海归博士技术团队创立，我们的核心成员毕业于新加坡国立、"
                            "日本早稻田、上海交大、华中科大、哈工大、曼切斯特等国内外知名高校。"
                        ),
                    }
                ]
            }
        if "帕西尼" in query and "早稻田" in query:
            return {
                "organic": [
                    {
                        "title": "PaXini 帕西尼- 官方网站",
                        "link": "https://example.test/pasini-about",
                        "snippet": (
                            "帕西尼创始团队源自世界首个人形机器人诞生地——日本早稻田大学"
                            "菅野实验室，是一家拥有前沿核心触觉技术及人形机器人的公司。"
                        ),
                    }
                ]
            }
        return {
            "organic": [
                {
                    "title": "深圳机器人产业动态",
                    "link": "https://example.test/robotics-news",
                    "snippet": "深圳机器人行业融资新闻汇总，多家企业布局。",
                }
            ]
        }

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = self

        class _Bocha:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return backend._search(query)

        class _Serper:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return {"organic": []}

        monkeypatch.setattr(serving_module, "BochaSearchProvider", _Bocha)
        monkeypatch.setattr(serving_module, "WebSearchProvider", _Serper)


def test_founder_probe_accepts_founding_team_wording(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Founding-team wording (创立/创始团队) counts as founder evidence.

    Live-derived: the two perfect probe pages （迈步 "由海归博士技术团队创立，
    核心成员毕业于…日本早稻田"; 帕西尼 "创始团队源自…早稻田大学菅野实验室")
    were both rejected because the acceptance list only knew 创始人/联合创始
    人/创办人, and the part stayed missing with a spurious gap sentence.
    """
    providers = _FounderWordingProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    plan = _plan(inputs, PERSON_QUERY)

    evidence_set = _read(
        inputs,
        local_candidates=_thin_local_candidates(),
        plan=plan,
    )

    supplemental_items = tuple(
        item for item in evidence_set.items if item.lane == "supplemental"
    )
    assert len(supplemental_items) == 1
    aggregate = supplemental_items[0]
    assert aggregate.claim_binding is not None
    assert aggregate.claim_binding.subject_id == plan.material_parts[0].subject_id
    assert "迈步" in aggregate.snippet
    assert "帕西尼" in aggregate.snippet
    report = evidence_set.sufficiency_report
    assert report is not None
    assert report.complete is True
    assert report.parts[0].outcome == "supported"


class _DiscoveryProviders:
    """Constraint-seeded discovery: the contextual first pass returns industry
    news, but the discovery query ("早稻田 深圳 创始人") returns pages that
    name the companies, one of them with direct founder evidence."""

    DISCOVERY_QUERY = "早稻田 深圳 机器人 创始人"

    def __init__(self) -> None:
        self.bocha_queries: list[str] = []

    def _search(self, query: str) -> dict[str, object]:
        self.bocha_queries.append(query)
        if query == self.DISCOVERY_QUERY:
            return {
                "organic": [
                    {
                        "title": "许晋诚：帕西尼创始人",
                        "link": "https://example.test/xu-jincheng",
                        "snippet": (
                            "许晋诚毕业于日本早稻田大学菅野机器人实验室。2021年6月，"
                            "许晋诚回国创立帕西尼感知科技（深圳）有限公司，并担任创始人"
                            "兼首席执行官，公司专注于机器人触觉感知技术。"
                        ),
                    },
                    {
                        "title": "迈步机器人融资动态",
                        "link": "https://example.test/maibu-funding",
                        "snippet": (
                            "深圳市迈步机器人科技有限公司完成新一轮融资，"
                            "专注康复外骨骼机器人。"
                        ),
                    },
                ]
            }
        if "迈步" in query and "早稻田" in query:
            return {
                "organic": [
                    {
                        "title": "迈步团队- 迈步机器人",
                        "link": "https://example.test/maibu-team",
                        "snippet": (
                            "公司由海归博士技术团队创立，核心成员陈功毕业于日本早稻田"
                            "大学，专注康复外骨骼机器人。"
                        ),
                    }
                ]
            }
        return {
            "organic": [
                {
                    "title": "深圳机器人产业动态",
                    "link": "https://example.test/robotics-news",
                    "snippet": "深圳机器人行业融资新闻汇总，多家企业布局。",
                }
            ]
        }

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = self

        class _Bocha:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return backend._search(query)

        class _Serper:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return {"organic": []}

        monkeypatch.setattr(serving_module, "BochaSearchProvider", _Bocha)
        monkeypatch.setattr(serving_module, "WebSearchProvider", _Serper)


def test_person_criteria_discovery_seeds_company_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A constraint-seeded discovery probe feeds companies the lanes missed.

    Live-derived: with no local candidates and a generic first-pass Web, the
    person-criteria probe list was built from noisy web-page text alone, the
    constraint-bearing companies were never probed, and the question failed
    with "未能确认". One discovery query ("早稻田 深圳 创始人") surfaces the
    companies; hits with direct founder evidence become findings immediately,
    the rest join the per-company verification probes.
    """
    providers = _DiscoveryProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    plan = _plan(inputs, PERSON_QUERY)

    evidence_set = _read(inputs, local_candidates=(), plan=plan)

    assert _DiscoveryProviders.DISCOVERY_QUERY in providers.bocha_queries
    assert any(
        query.endswith(" 早稻田") and "迈步" in query
        for query in providers.bocha_queries
    )
    supplemental_items = tuple(
        item for item in evidence_set.items if item.lane == "supplemental"
    )
    assert len(supplemental_items) == 1
    aggregate = supplemental_items[0]
    assert "帕西尼" in aggregate.snippet
    assert "迈步" in aggregate.snippet
    report = evidence_set.sufficiency_report
    assert report is not None
    assert report.complete is True
    assert report.parts[0].outcome == "supported"
    receipt = evidence_set.supplemental_budget_receipt
    assert receipt is not None
    assert receipt.cost_units <= inputs.supplemental_budget.max_cost_units


def test_enumeration_query_widens_the_candidate_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """List-style queries get a wider candidate window than the default 13.

    Live-derived: the vector lane ranked 上海开普勒 at 15 and 安赛步 at 24 for
    "中国有哪些成熟的酒店送餐机器人供应商", but the default 13-candidate
    window cut both, so required suppliers never reached the answer. An
    enumeration request now keeps 24 candidates.
    """
    providers = _FakeDualWebProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    from src.data_agents.canonical_v2.knowledge_read import (
        EnumerationPlanningContext,
    )

    context = EnumerationPlanningContext(
        requested=True,
        scope="中国有哪些成熟的酒店送餐机器人供应商",
        as_of=NOW,
        finite_universe=None,
    )
    request = QueryPlanningRequest(
        request_id="query-request:enumeration-window",
        release_id=RELEASE_ID,
        original_query="中国有哪些成熟的酒店送餐机器人供应商",
        as_of=NOW,
        displayed_entity_ids=(),
        displayed_entity_names=(),
        enumeration_context=context,
    )
    planner = create_ephemeral_query_planner(
        planning_policy=inputs.planning_policy,
        institution_catalog=InstitutionCatalog(
            catalog_id=f"institution-catalog:{RELEASE_ID}",
            catalog_version="institution-catalog-v1",
            release_id=RELEASE_ID,
            entries=(),
        ),
        proposal_provider=inputs.proposal_provider,
    )
    plan = planner.plan(request)

    assert plan.max_candidates >= 24

    plain_request = QueryPlanningRequest(
        request_id="query-request:plain-window",
        release_id=RELEASE_ID,
        original_query="介绍清华的丁文伯",
        as_of=NOW,
        displayed_entity_ids=(),
        displayed_entity_names=(),
    )
    plain_plan = planner.plan(plain_request)
    assert plain_plan.max_candidates < 24

    # The chat layer only attaches enumeration_context on follow-up turns
    # (displayed ids present), so the planner must also detect list-style
    # markers on its own for fresh list queries — the primary 查全 case.
    fresh_list_request = QueryPlanningRequest(
        request_id="query-request:fresh-list-window",
        release_id=RELEASE_ID,
        original_query="中国有哪些成熟的酒店送餐机器人供应商",
        as_of=NOW,
        displayed_entity_ids=(),
        displayed_entity_names=(),
    )
    fresh_list_plan = planner.plan(fresh_list_request)
    assert fresh_list_plan.max_candidates >= 24


KEPLER_ID = "company-c-kepler"
KEPLER_NAME = "上海开普勒机器人有限公司"
THEME_QUERY = "中国有哪些成熟的酒店送餐机器人供应商"


class _ThemeProbeProviders:
    """Contextual first pass returns industry news; per-candidate theme probes
    return the hotel-delivery page for 开普勒 only."""

    def __init__(self) -> None:
        self.bocha_queries: list[str] = []

    def _search(self, query: str) -> dict[str, object]:
        self.bocha_queries.append(query)
        if "开普勒" in query and "酒店送餐机器人" in query:
            return {
                "organic": [
                    {
                        "title": "开普勒探索者D1酒店配送机器人发布",
                        "link": "https://example.test/kepler-d1",
                        "snippet": (
                            "上海开普勒机器人有限公司推出探索者D1酒店配送机器人，"
                            "面向酒店客房送餐与楼宇配送场景。"
                        ),
                    }
                ]
            }
        return {
            "organic": [
                {
                    "title": "机器人行业动态",
                    "link": "https://example.test/robotics-news",
                    "snippet": "人形机器人行业新闻汇总。",
                }
            ]
        }

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = self

        class _Bocha:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return backend._search(query)

        class _Serper:
            def __init__(self, **_: object) -> None:
                pass

            def search(self, query: str) -> dict[str, object]:
                return {"organic": []}

        monkeypatch.setattr(serving_module, "BochaSearchProvider", _Bocha)
        monkeypatch.setattr(serving_module, "WebSearchProvider", _Serper)


def test_theme_probes_verify_uncovered_enumeration_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enumeration candidates whose profile lacks the theme get verified.

    Live-derived: 开普勒 ranks 15 for the hotel query but its profile says
    人形机器人 with no hotel terms, so the answer dropped it for lacking
    direct evidence. Theme-verification probes fetch the missing binding
    deterministically: candidates already covered by retained evidence are
    skipped, uncovered ones get one bounded per-candidate probe.
    """
    providers = _ThemeProbeProviders()
    inputs = _load_inputs(tmp_path, monkeypatch, providers)
    plan = _plan(inputs, THEME_QUERY)

    parts = plan.material_parts
    assert len(parts) == 1
    part = parts[0]
    assert part.predicate == "theme_relevance"
    assert part.requested_value == "酒店送餐机器人"

    kepler_item = _local_company_item(
        "kepler",
        KEPLER_NAME,
        "通用人形机器人研发与应用。",
        canonical_id=KEPLER_ID,
    )
    pudu_item = _local_company_item(
        "pudu",
        PUDU_NAME,
        "酒店配送机器人与服务机器人解决方案，覆盖酒店场景。",
        canonical_id=PUDU_ID,
    )
    local_candidates = (
        _local_company_candidate(
            "kepler", KEPLER_NAME, kepler_item, canonical_id=KEPLER_ID
        ),
        _local_company_candidate("pudu", PUDU_NAME, pudu_item, canonical_id=PUDU_ID),
    )
    evidence_set = _read(inputs, local_candidates=local_candidates, plan=plan)

    probe_queries = [
        query for query in providers.bocha_queries if "酒店送餐机器人" in query
    ]
    assert any("开普勒" in query for query in probe_queries)
    assert not any(
        "普渡" in query and "酒店送餐机器人" in query and "深圳市普渡" in query
        for query in probe_queries
    )
    kepler_supplemental = tuple(
        item
        for item in evidence_set.items
        if item.lane == "supplemental" and item.object_id == KEPLER_ID
    )
    assert len(kepler_supplemental) == 1
    bound = kepler_supplemental[0].claim_binding
    assert bound is not None
    assert bound.subject_id == KEPLER_ID
    assert bound.predicate == "theme_relevance"
    assert "酒店配送机器人" in kepler_supplemental[0].snippet
    report = evidence_set.sufficiency_report
    assert report is not None
    assert report.complete is True
    assert report.parts[0].outcome == "supported"


def test_probe_acceptance_falls_back_to_llm_when_rules_reject() -> None:
    """A paraphrase hit the rules miss gets rescued by the LLM judge.

    Identity (迈步机器人) and the founding marker (创立) both rule-match, but
    the literal constraint 早稻田 never appears in the text (the page uses the
    paraphrase 早大), so the deterministic matcher rejects; only the LLM judge
    can bind the paraphrased education back to the constraint.
    """
    from src.data_agents.canonical_v2 import llm_judgments as lj

    class _Judge:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def judge_batch(
            self, kind: str, question: str, items: Any, context: str = ""
        ) -> Any:
            self.calls.append({"kind": kind, "items": items})
            return (
                lj.ProbeAcceptJudgment(
                    item_id="hit-1",
                    accept=True,
                    entity_id="company-c-maibu",
                    predicate="person_criteria",
                    value="早稻田",
                ),
            )

    judge = _Judge()
    accepted = serving_module._accept_probe_hit(
        judge=judge,
        kind="person",
        question=PERSON_QUERY,
        entity_name=MAIBU_ROBOT_NAME,
        semantics={"constraint": "早稻田"},
        result=serving_module._NormalizedWebResult(
            title="迈步团队- 迈步机器人",
            url="https://example.test/maibu-team",
            snippet="公司由海归博士技术团队创立，核心成员毕业于日本早大。",
            summary="",
            primary_provider_version="bocha-v1",
            corroborating_provider_versions=("bocha-v1",),
        ),
    )
    assert accepted is True
    assert judge.calls and judge.calls[0]["kind"] == "probe_accept"
    rendered = judge.calls[0]["items"]["hit-1"]
    assert MAIBU_ROBOT_NAME in rendered
    assert "早稻田" in rendered
    assert "迈步团队" in rendered


def test_probe_acceptance_rule_hit_skips_llm() -> None:
    class _ExplodingJudge:
        def judge_batch(self, **kwargs: Any) -> Any:
            raise AssertionError("LLM must not be called on rule hits")

    assert (
        serving_module._accept_probe_hit(
            judge=_ExplodingJudge(),
            kind="person",
            question="q",
            entity_name=PASINI,
            semantics={"constraint": "早稻田"},
            result=serving_module._NormalizedWebResult(
                title="帕西尼创始人许晋诚",
                url="https://example.test/xu",
                snippet="帕西尼感知科技（深圳）有限公司创始人许晋诚，毕业于早稻田大学。",
                summary="",
                primary_provider_version="bocha-v1",
                corroborating_provider_versions=("bocha-v1",),
            ),
        )
        is True
    )


def test_probe_acceptance_llm_failure_falls_back_to_rule_result() -> None:
    """A failed judge keeps the rule result instead of admitting the miss.

    The real harness degrades to per-item fail-open defaults (accept=True)
    with ``last_outcome`` marked ``*_fail_open``; honoring those defaults
    would admit exactly the noise the rules rejected, so the rule result
    stands and only a successful ("ok") judgment can recover a rule miss.
    """
    from src.data_agents.canonical_v2 import llm_judgments as lj

    class _TimeoutJudge:
        last_outcome = "timeout_fail_open"

        def judge_batch(self, **kwargs: Any) -> Any:
            return (lj.ProbeAcceptJudgment(item_id="hit-1", accept=True),)

    assert (
        serving_module._accept_probe_hit(
            judge=_TimeoutJudge(),
            kind="person",
            question="q",
            entity_name=PASINI,
            semantics={"constraint": "早稻田"},
            result=serving_module._NormalizedWebResult(
                title="电梯配件黄页",
                url="https://example.test/junk",
                snippet="电梯按钮箱与配件。",
                summary="",
                primary_provider_version="bocha-v1",
                corroborating_provider_versions=("bocha-v1",),
            ),
        )
        is False
    )


def test_probe_acceptance_batches_rule_misses_into_one_judge_call() -> None:
    """Per probe job, every rule-miss result rides ONE batched judge call.

    Both results rule-miss (the first lacks any founder marker, the second
    paraphrases the constraint as 早大), so neither short-circuits; the LLM
    rejects hit-1 but accepts hit-2, so the second result wins, and exactly
    one judge_batch call carries both entries in result order.
    """
    from src.data_agents.canonical_v2 import llm_judgments as lj

    class _BatchJudge:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []
            self.last_outcome = "ok"

        def judge_batch(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            return tuple(
                lj.ProbeAcceptJudgment(item_id=item_id, accept=item_id == "hit-2")
                for item_id in kwargs["items"]
            )

    judge = _BatchJudge()
    first = serving_module._NormalizedWebResult(
        title="迈步团队- 迈步机器人",
        url="https://example.test/maibu-news",
        snippet="公司发布新一代康复外骨骼机器人。",
        summary="",
        primary_provider_version="bocha-v1",
        corroborating_provider_versions=("bocha-v1",),
    )
    second = serving_module._NormalizedWebResult(
        title="迈步团队- 迈步机器人",
        url="https://example.test/maibu-team",
        snippet="公司由海归博士技术团队创立，核心成员毕业于日本早大。",
        summary="",
        primary_provider_version="bocha-v1",
        corroborating_provider_versions=("bocha-v1",),
    )
    accepted = serving_module._select_probe_hit(
        judge=judge,
        kind="person",
        question=PERSON_QUERY,
        entity_name=MAIBU_ROBOT_NAME,
        semantics={"constraint": "早稻田"},
        results=(first, second),
    )
    assert accepted is second
    assert len(judge.calls) == 1
    assert judge.calls[0]["kind"] == "probe_accept"
    assert list(judge.calls[0]["items"]) == ["hit-1", "hit-2"]
