from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import pytest

from src.data_agents.canonical_v2 import (
    knowledge_read_isolated as isolated_read_module,
)
from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving_module
from src.data_agents.canonical_v2.knowledge_answer import TurnRequest
from src.data_agents.canonical_v2.knowledge_read import (
    CanonicalEntityHandle,
    EnumerationPlanningContext,
    EvidenceClaimBinding,
    EvidenceItem,
    EvidenceSet,
    FusedCandidate,
    InstitutionCatalog,
    LaneRequest,
    ProtectedSlot,
    QueryPlanningRequest,
    RerankRequest,
    StructuredConstraints,
    WebSearchPolicy,
    _lane_request,
    _materialize_requested_traversal,
    create_ephemeral_query_planner,
)
from src.data_agents.canonical_v2.knowledge_serving_isolated import (
    RecordedServingBundle,
    load_recorded_serving_inputs,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s12b-test"


class _Embedding:
    model_id = "recorded-embedding-v1"
    dimension = 32


def _bundle(tmp_path: Path) -> RecordedServingBundle:
    return RecordedServingBundle(
        schema_version="canonical-v2-serving-bundle-v1",
        bundle_id="serving-bundle:candidate-s12b-test",
        release_id=RELEASE_ID,
        database_name="miroflow_candidate_s12b_test",
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


def _write_bundle(tmp_path: Path) -> tuple[Path, RecordedServingBundle]:
    bundle = _bundle(tmp_path)
    path = tmp_path / "serving-bundle.json"
    path.write_text(
        json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path, bundle


def test_content_addressed_serving_bundle_is_secret_free_and_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    monkeypatch.setenv("BOCHA_API_KEY", "bocha-secret-must-stay-outside-bundle")
    monkeypatch.setenv("SERPER_API_KEY", "secret-must-stay-outside-bundle")

    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )

    assert "secret-must-stay-outside-bundle" not in path.read_text(encoding="utf-8")
    assert inputs.planning_policy.max_provider_calls == 2
    assert inputs.planning_policy.max_candidates == (
        bundle.max_candidates + bundle.max_web_results
    )
    assert inputs.universal_web_policy.max_provider_calls == 2
    request = QueryPlanningRequest(
        request_id="query-request:s12b-test",
        release_id=RELEASE_ID,
        original_query="丁文伯教授的研究方向是什么？",
        as_of=NOW,
    )
    proposal = inputs.proposal_provider(request)
    assert proposal.request_sha256 == request.content_sha256
    assert proposal.domains == ("professor",)
    assert "vector" in proposal.lanes
    assert proposal.professor_vector_view == "both"
    assert proposal.query_views[0].text == "丁文伯"
    assert proposal.max_candidates == bundle.max_candidates + bundle.max_web_results
    plan = create_ephemeral_query_planner(
        planning_policy=inputs.planning_policy,
        institution_catalog=InstitutionCatalog(
            catalog_id="institution-catalog:s12b-test",
            catalog_version="institution-catalog-v1",
            release_id=RELEASE_ID,
            entries=(),
        ),
        proposal_provider=inputs.proposal_provider,
    ).plan(request)
    assert plan.pure_topic_text == "丁文伯"
    assert all("丁文伯" in query.query_text for query in plan.lane_queries)

    snippet = json.dumps(
        {
            "name": "丁文伯",
            "institution": "清华大学深圳国际研究生院",
            "title": "副教授",
            "research_directions": [{"name": "机器人技术"}],
            "profile_summary": "研究信号处理、机器人技术和人机交互。",
        },
        ensure_ascii=False,
    )
    evidence = EvidenceItem(
        evidence_id="evidence:s12b:test",
        object_id="professor:s12b:ding-wenbo",
        domain="professor",
        lane="lexical",
        source_nature="local",
        source_locator="canonical-v2-isolated:test",
        snippet=snippet,
        score=1.0,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id="professor:s12b:ding-wenbo",
            predicate="canonical_projection",
            value="a" * 64,
            status="admitted",
        ),
    )
    noisy_evidence = EvidenceItem(
        evidence_id="evidence:s12b:noisy-vector",
        object_id="professor:s12b:unrelated",
        domain="professor",
        lane="vector",
        source_nature="local",
        source_locator="canonical-v2-isolated:noisy",
        snippet=json.dumps({"name": "无关教授"}, ensure_ascii=False),
        score=0.5,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id="professor:s12b:unrelated",
            predicate="semantic_recall",
            value="b" * 64,
            status="admitted",
        ),
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=request.original_query,
        protected_slots=(),
        items=(evidence, noisy_evidence),
        traces=(),
        limitations=(),
        entity_handles=(
            CanonicalEntityHandle(
                canonical_id=evidence.object_id,
                domain="professor",
                display_name="丁文伯",
                evidence_ids=(evidence.evidence_id,),
            ),
            CanonicalEntityHandle(
                canonical_id=noisy_evidence.object_id,
                domain="professor",
                display_name="无关教授",
                evidence_ids=(noisy_evidence.evidence_id,),
            ),
        ),
    )
    result = inputs.answer_factory().answer(
        TurnRequest(
            session_id="session:s12b-test",
            turn_id="turn:s12b-test",
            query=request.original_query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )
    assert "丁文伯" in result.answer_text
    assert "机器人技术" in result.answer_text
    assert "无关教授" not in result.answer_text
    assert result.context_receipt is not None
    assert result.context_receipt.displayed_result_set is not None
    assert result.context_receipt.displayed_result_set.handle_ids == (
        evidence.object_id,
    )
    assert result.citations[0].source_locator == "canonical-v2-isolated:test"


def test_normal_answer_uses_injected_llm_renderer_and_preserves_founder_role(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    rendered_claims: list[tuple[str, ...]] = []
    rendered_queries: list[str | None] = []

    def render(result: object) -> str:
        claims = tuple(claim.text for claim in result.claims)  # type: ignore[attr-defined]
        rendered_claims.append(claims)
        rendered_queries.append(getattr(result, "original_query", None))
        return "丁文伯参与创立了深圳无界智航科技有限公司。"

    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        prose_renderer=render,
        clock=lambda: NOW,
    )
    company_id = "company-c-wujie-zhihang"
    relationship = EvidenceItem(
        evidence_id="evidence:s12d:founder",
        object_id=company_id,
        domain="company",
        lane="relationship",
        source_nature="local",
        source_locator="canonical-v2-isolated:relationship",
        snippet=json.dumps(
            {
                "name": "深圳无界智航科技有限公司",
                "profile_summary": "聚焦具身智能全栈解决方案。",
                "_relationship": {
                    "relationship_type": "professor_company_role",
                    "roles": ["founder"],
                },
            },
            ensure_ascii=False,
        ),
        score=1.0,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id="canonical:professor:ding-wenbo",
            predicate="professor_company_role",
            value=f"canonical:company:{company_id}",
            status="accepted",
        ),
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query="他是否有参与哪些企业的创立",
        protected_slots=(),
        items=(relationship,),
        traces=(),
        limitations=(),
        entity_handles=(
            CanonicalEntityHandle(
                canonical_id=company_id,
                domain="company",
                display_name="深圳无界智航科技有限公司",
                evidence_ids=(relationship.evidence_id,),
            ),
        ),
    )

    result = inputs.answer_factory().answer(
        TurnRequest(
            session_id="session:s12d-founder",
            turn_id="turn:s12d-founder",
            query=evidence_set.original_query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )

    assert result.render_mode == "prose_renderer"
    assert result.answer_text == "丁文伯参与创立了深圳无界智航科技有限公司。"
    assert rendered_claims
    assert rendered_queries == ["他是否有参与哪些企业的创立"]
    assert "original_query" not in result.model_dump(mode="json")
    assert "参与创立" in rendered_claims[0][0]


def test_llm_prose_renderer_receives_grounded_public_claims_only() -> None:
    calls: list[dict[str, object]] = []

    class _Completions:
        def create(self, **kwargs: object) -> object:
            calls.append(kwargs)
            return SimpleNamespace(
                choices=(
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="丁文伯是深圳无界智航科技有限公司的创始人。"
                        )
                    ),
                )
            )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=_Completions()),
    )
    renderer = serving_module._OpenAIProseRenderer(
        client=client,
        model="recorded-chat-model",
        extra_body={"thinking": {"type": "disabled"}},
    )
    result = SimpleNamespace(
        original_query="他是否有参与哪些企业的创立？",
        claims=(
            SimpleNamespace(
                text="该教授参与创立了深圳无界智航科技有限公司，角色为创始人。",
                predicate="professor_company_role",
                status="accepted",
                source_natures=("local",),
                evidence_ids=("evidence:renderer:founder",),
            ),
            SimpleNamespace(
                text="Service Robot Arm 配备双机械手，可自主按下电梯按钮。",
                predicate="current_web_result",
                status="observed",
                source_natures=("current_web",),
                evidence_ids=("evidence:renderer:product-capability",),
            ),
        ),
        citations=(
            SimpleNamespace(
                evidence_id="evidence:renderer:product-capability",
                source_nature="current_web",
                source_locator="https://official.example/products/service-robot-arm",
            ),
        ),
        context_receipt=SimpleNamespace(
            active_anchor=SimpleNamespace(display_name="丁文伯", domain="professor"),
            displayed_result_set=SimpleNamespace(
                handles=(
                    SimpleNamespace(
                        display_name="深圳无界智航科技有限公司",
                        domain="company",
                    ),
                )
            ),
            traversed_path_ids=("professor_to_company",),
        ),
    )

    rendered = renderer(result)

    assert rendered == (
        "丁文伯参与创立了深圳无界智航科技有限公司。\n\n"
        "丁文伯是深圳无界智航科技有限公司的创始人。"
    )
    assert len(calls) == 1
    serialized = json.dumps(calls[0], ensure_ascii=False)
    assert "该教授参与创立" in serialized
    assert "丁文伯" in serialized
    assert "professor_to_company" in serialized
    assert "他是否有参与哪些企业的创立" in serialized
    assert "围绕用户问题" in serialized
    assert "不要逐字段复述" in serialized
    assert "canonical-v2-prose-v3" in serialized
    assert "具体产品与具体能力" in serialized
    assert "https://official.example/products/service-robot-arm" in serialized
    assert "evidence:" not in serialized
    assert "canonical-v2-isolated" not in serialized


@pytest.mark.parametrize(
    "query",
    (
        "介绍清华的丁文伯",
        "介绍深圳无界智航科技有限公司",
        "pFedGPA 这篇论文讲了什么",
        "专利 CN117873146A 的详细信息",
    ),
)
def test_llm_prose_renderer_keeps_each_public_domain_question(query: str) -> None:
    calls: list[dict[str, object]] = []

    class _Completions:
        def create(self, **kwargs: object) -> object:
            calls.append(kwargs)
            return SimpleNamespace(
                choices=(
                    SimpleNamespace(message=SimpleNamespace(content="已整理回答")),
                )
            )

    renderer = serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=_Completions()),
        ),
        model="recorded-chat-model",
        extra_body={"thinking": {"type": "disabled"}},
    )

    assert (
        renderer(
            SimpleNamespace(
                original_query=query,
                claims=(),
                context_receipt=None,
            )
        )
        == "已整理回答"
    )
    assert query in json.dumps(calls[0], ensure_ascii=False)


def test_environment_prose_renderer_bounds_the_default_provider_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_calls: list[dict[str, object]] = []
    result_timeouts: list[float] = []

    class _Completions:
        def create(self, **_: object) -> object:
            return SimpleNamespace(
                choices=(
                    SimpleNamespace(message=SimpleNamespace(content="已整理回答")),
                )
            )

    def openai_client(**kwargs: object) -> object:
        client_calls.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))

    class _ImmediateFuture:
        def __init__(self, function: Any, value: Any) -> None:
            self._function = function
            self._value = value

        def result(self, *, timeout: float) -> str:
            result_timeouts.append(timeout)
            return self._function(self._value)

    class _ImmediateExecutor:
        def submit(self, function: Any, value: Any) -> _ImmediateFuture:
            return _ImmediateFuture(function, value)

    monkeypatch.delenv("CHAT_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(
        serving_module,
        "resolve_professor_llm_settings",
        lambda _profile: {
            "local_llm_api_key": "test-key",
            "local_llm_model": "qwen3.6-35b-a3b-fp8",
            "local_llm_base_url": "https://llm.example/v1",
        },
    )
    monkeypatch.setattr(serving_module, "OpenAI", openai_client)
    monkeypatch.setattr(
        serving_module,
        "_PROSE_RENDER_EXECUTOR",
        _ImmediateExecutor(),
    )

    rendered = serving_module._EnvironmentProseRenderer()(
        SimpleNamespace(claims=(), context_receipt=None)
    )

    assert rendered == "已整理回答"
    assert result_timeouts == [12.0]
    assert client_calls == [
        {
            "base_url": "https://llm.example/v1",
            "api_key": "test-key",
            "timeout": 12.0,
            "max_retries": 0,
        }
    ]


def test_environment_prose_renderer_reuses_client_for_warm_and_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_calls: list[dict[str, object]] = []
    completion_calls: list[dict[str, object]] = []

    class _Completions:
        def create(self, **kwargs: object) -> object:
            completion_calls.append(kwargs)
            return SimpleNamespace(
                choices=(
                    SimpleNamespace(message=SimpleNamespace(content="已整理回答")),
                )
            )

    def openai_client(**kwargs: object) -> object:
        client_calls.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))

    class _ImmediateFuture:
        def __init__(self, function: Any, value: Any) -> None:
            self._function = function
            self._value = value

        def result(self, *, timeout: float) -> str:
            return self._function(self._value)

    class _ImmediateExecutor:
        def submit(self, function: Any, value: Any) -> _ImmediateFuture:
            return _ImmediateFuture(function, value)

    monkeypatch.setattr(
        serving_module,
        "resolve_professor_llm_settings",
        lambda _profile: {
            "local_llm_api_key": "test-key",
            "local_llm_model": "qwen3.6-35b-a3b-fp8",
            "local_llm_base_url": "https://llm.example/v1",
        },
    )
    monkeypatch.setattr(serving_module, "OpenAI", openai_client)
    monkeypatch.setattr(
        serving_module,
        "_PROSE_RENDER_EXECUTOR",
        _ImmediateExecutor(),
    )
    renderer = serving_module._EnvironmentProseRenderer()
    result = SimpleNamespace(claims=(), context_receipt=None)

    assert renderer(result) == "已整理回答"
    renderer.warm()
    assert renderer(result) == "已整理回答"

    assert len(client_calls) == 1
    assert [call["max_tokens"] for call in completion_calls] == [1200, 1, 1200]


def test_environment_prose_renderer_stays_out_of_answer_session_copy() -> None:
    renderer = serving_module._EnvironmentProseRenderer()
    answer = serving_module.create_ephemeral_knowledge_answer(
        prose_renderer=renderer,
    )

    forked = deepcopy(answer)

    assert forked is not answer
    assert forked._prose_renderer is renderer


def test_focused_missing_entity_prefers_current_web_over_vector_neighbors(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    query = "清华的王学谦的评价如何，他是否是属于大牛"
    vector = EvidenceItem(
        evidence_id="evidence:s12b:wrong-neighbor",
        object_id="professor:s12b:wang-xuefeng",
        domain="professor",
        lane="vector",
        source_nature="local",
        source_locator="canonical-v2-isolated:wrong-neighbor",
        snippet=json.dumps({"name": "王学锋"}, ensure_ascii=False),
        score=0.8,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id="professor:s12b:wang-xuefeng",
            predicate="semantic_recall",
            value="b" * 64,
            status="admitted",
        ),
    )
    web = EvidenceItem(
        evidence_id="evidence:s12b:current-web",
        object_id="web-object:s12b:wang-xueqian",
        domain="professor",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/wang-xueqian",
        snippet="王学谦：清华大学自动化系教师主页",
        score=1.0,
        source_authority="official",
        claim_binding=EvidenceClaimBinding(
            subject_id="web-object:s12b:wang-xueqian",
            predicate="current_web_result",
            value="c" * 64,
            status="observed",
        ),
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=(),
        items=(vector, web),
        traces=(),
        limitations=(),
        entity_handles=(
            CanonicalEntityHandle(
                canonical_id=vector.object_id,
                domain="professor",
                display_name="王学锋",
                evidence_ids=(vector.evidence_id,),
            ),
        ),
    )

    result = inputs.answer_factory().answer(
        TurnRequest(
            session_id="session:s12b-web-fallback",
            turn_id="turn:s12b-web-fallback",
            query=query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )

    assert "王学谦" in result.answer_text
    assert "王学锋" not in result.answer_text
    assert tuple(citation.source_nature for citation in result.citations) == (
        "current_web",
    )


def test_explicit_link_gap_keeps_current_web_url_with_exact_local_evidence(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    title = (
        "pFedGPA: Diffusion-based Generative Parameter Aggregation for "
        "Personalized Federated Learning"
    )
    query = f"{title} 这篇论文的链接是什么"
    local = EvidenceItem(
        evidence_id="evidence:s12b:pfedgpa-local-link-gap",
        object_id="paper:s12b:pfedgpa",
        domain="paper",
        lane="exact",
        source_nature="local",
        source_locator="canonical-v2-isolated:pfedgpa",
        snippet=json.dumps({"title": title}, ensure_ascii=False),
        score=1.0,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id="paper:s12b:pfedgpa",
            predicate="canonical_projection",
            value="a" * 64,
            status="admitted",
        ),
    )
    url = "https://arxiv.org/abs/2409.05701"
    web = EvidenceItem(
        evidence_id="evidence:s12b:pfedgpa-current-web-link",
        object_id="web-object:s12b:pfedgpa",
        domain="paper",
        lane="web",
        source_nature="current_web",
        source_locator=url,
        snippet=f"{title}：arXiv record",
        score=1.0,
        source_authority="official",
        claim_binding=EvidenceClaimBinding(
            subject_id="paper:s12b:pfedgpa",
            predicate="current_web_result",
            value="b" * 64,
            status="observed",
        ),
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=(),
        items=(local, web),
        traces=(),
        limitations=(),
        entity_handles=(
            CanonicalEntityHandle(
                canonical_id=local.object_id,
                domain="paper",
                display_name=title,
                evidence_ids=(local.evidence_id, web.evidence_id),
            ),
        ),
    )

    result = inputs.answer_factory().answer(
        TurnRequest(
            session_id="session:s12b-pfedgpa-link-gap",
            turn_id="turn:s12b-pfedgpa-link-gap",
            query=query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )

    assert url in result.answer_text
    assert tuple(citation.source_nature for citation in result.citations) == (
        "local",
        "current_web",
    )


@pytest.mark.parametrize(
    "query",
    (
        "上述企业的产品哪些可以使用机械手操作楼宇设备",
        "上述企业具备什么独特的末端执行能力",
        "上述企业当前公开了哪些新产品能力",
        "上述企业的创始人分别是谁",
        "上述企业的官方网站链接是什么",
    ),
)
def test_recall_first_answer_keeps_web_evidence_for_followup_families(
    tmp_path: Path,
    query: str,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    rendered_claims: list[tuple[object, ...]] = []

    def render(result: object) -> str:
        rendered_claims.append(tuple(result.claims))  # type: ignore[attr-defined]
        return "已根据本地与公开信息综合回答。"

    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        prose_renderer=render,
        clock=lambda: NOW,
    )
    local_items = tuple(
        EvidenceItem(
            evidence_id=f"evidence:recall-first:local:{index}",
            object_id=f"company:recall-first:{index}",
            domain="company",
            lane="lexical",
            source_nature="local",
            source_locator=f"canonical-v2-isolated:company:{index}",
            snippet=json.dumps(
                {
                    "name": f"候选企业{index}",
                    "profile_summary": "提供商用服务机器人。",
                },
                ensure_ascii=False,
            ),
            score=1.0 - (index * 0.01),
            source_authority="canonical_release",
            claim_binding=EvidenceClaimBinding(
                subject_id=f"company:recall-first:{index}",
                predicate="canonical_projection",
                value=f"{index:064x}",
                status="admitted",
            ),
        )
        for index in range(bundle.max_candidates)
    )
    web_item = EvidenceItem(
        evidence_id="evidence:recall-first:web:direct-product-capability",
        object_id="web-object:recall-first:product-capability",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://official.example/products/service-robot-arm",
        snippet=(
            "Service Robot Arm：该产品配备双机械手，可自主识别并按下电梯按钮。"
        ),
        score=1.0,
        source_authority="official",
        claim_binding=EvidenceClaimBinding(
            subject_id="company:recall-first:0",
            predicate="current_web_result",
            value="f" * 64,
            status="observed",
        ),
    )
    handles = tuple(
        CanonicalEntityHandle(
            canonical_id=item.object_id,
            domain="company",
            display_name=f"候选企业{index}",
            evidence_ids=(item.evidence_id,),
        )
        for index, item in enumerate(local_items)
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=(),
        items=(*local_items, web_item),
        traces=(),
        limitations=(),
        entity_handles=handles,
    )

    result = inputs.answer_factory().answer(
        TurnRequest(
            session_id="session:recall-first",
            turn_id="turn:recall-first",
            query=query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )

    assert result.render_mode == "prose_renderer"
    assert rendered_claims
    assert any(
        "双机械手" in claim.text and "按下电梯按钮" in claim.text
        for claim in rendered_claims[0]
    )
    assert {nature for claim in rendered_claims[0] for nature in claim.source_natures} == {
        "local",
        "current_web",
    }


def test_focused_title_accepts_only_the_exact_named_vector_handle(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    title = (
        "pFedGPA: Diffusion-based Generative Parameter Aggregation for "
        "Personalized Federated Learning"
    )
    query = f"{title} 这篇论文的详细信息"
    target = EvidenceItem(
        evidence_id="evidence:s12b:pfedgpa",
        object_id="paper:s12b:pfedgpa",
        domain="paper",
        lane="vector",
        source_nature="local",
        source_locator="canonical-v2-isolated:pfedgpa",
        snippet=json.dumps(
            {"title": title, "summary_text": "Diffusion-based aggregation."},
            ensure_ascii=False,
        ),
        score=0.9,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id="paper:s12b:pfedgpa",
            predicate="semantic_recall",
            value="b" * 64,
            status="admitted",
        ),
    )
    neighbor = EvidenceItem(
        evidence_id="evidence:s12b:gan",
        object_id="paper:s12b:gan",
        domain="paper",
        lane="vector",
        source_nature="local",
        source_locator="canonical-v2-isolated:gan",
        snippet=json.dumps(
            {"title": "Generative Adversarial Networks"},
            ensure_ascii=False,
        ),
        score=0.5,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id="paper:s12b:gan",
            predicate="semantic_recall",
            value="c" * 64,
            status="admitted",
        ),
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=(),
        items=(target, neighbor),
        traces=(),
        limitations=(),
        entity_handles=(
            CanonicalEntityHandle(
                canonical_id=target.object_id,
                domain="paper",
                display_name=title,
                evidence_ids=(target.evidence_id,),
            ),
            CanonicalEntityHandle(
                canonical_id=neighbor.object_id,
                domain="paper",
                display_name="Generative Adversarial Networks",
                evidence_ids=(neighbor.evidence_id,),
            ),
        ),
    )

    result = inputs.answer_factory().answer(
        TurnRequest(
            session_id="session:s12b-pfedgpa",
            turn_id="turn:s12b-pfedgpa",
            query=query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )

    assert title in result.answer_text
    assert "Generative Adversarial Networks" not in result.answer_text
    assert tuple(citation.source_locator for citation in result.citations) == (
        "canonical-v2-isolated:pfedgpa",
    )
    assert result.context_receipt is not None
    assert result.context_receipt.active_anchor is not None
    assert result.context_receipt.active_anchor.canonical_id == target.object_id


@pytest.mark.parametrize(
    ("query", "displayed_entity_id", "expected_path"),
    (
        (
            "他是否有参与哪些企业的创立",
            "professor-c-ding-wenbo",
            (
                "professor_company_role",
                "professor_to_company",
                "professor",
                "company",
            ),
        ),
        (
            "这家公司的创始教授是谁",
            "company-c-wujie-zhihang",
            (
                "professor_company_role",
                "company_to_professor",
                "company",
                "professor",
            ),
        ),
    ),
)
def test_serving_planner_uses_the_built_professor_company_relationship(
    tmp_path: Path,
    query: str,
    displayed_entity_id: str,
    expected_path: tuple[str, str, str, str],
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    request = QueryPlanningRequest(
        request_id=f"query-request:{displayed_entity_id}",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
        displayed_entity_ids=(displayed_entity_id,),
        enumeration_context=EnumerationPlanningContext(
            requested=True,
            scope=query,
            as_of=NOW,
            finite_universe=None,
        ),
    )

    proposal = inputs.proposal_provider(request)

    assert proposal.lanes == ("relationship", "web")
    assert len(proposal.relationship_paths) == 1
    relationship_path = proposal.relationship_paths[0]
    assert (
        relationship_path.relationship_type_id,
        relationship_path.direction,
        relationship_path.source_type,
        relationship_path.target_type,
    ) == expected_path
    plan = create_ephemeral_query_planner(
        planning_policy=inputs.planning_policy,
        institution_catalog=InstitutionCatalog(
            catalog_id="institution-catalog:s12b-test",
            catalog_version="institution-catalog-v1",
            release_id=RELEASE_ID,
            entries=(),
        ),
        proposal_provider=inputs.proposal_provider,
    ).plan(request)
    relationship_request = _lane_request(
        plan,
        "relationship",
        WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=5,
        ),
    )
    assert plan.enumeration_policy is not None
    assert relationship_request.relationship_enumeration_policy == (
        plan.enumeration_policy
    )
    traversal = _materialize_requested_traversal(plan)
    assert traversal is not None
    assert (
        traversal.path_id,
        traversal.source_domain,
        traversal.target_domain,
        traversal.relationship_type,
        traversal.direction,
    ) == (
        expected_path[1],
        expected_path[2],
        expected_path[3],
        "professor_company_role",
        "forward" if expected_path[1] == "professor_to_company" else "inverse",
    )


def test_serving_bundle_rejects_hash_or_candidate_crosswire(tmp_path: Path) -> None:
    path, bundle = _write_bundle(tmp_path)

    with pytest.raises(ValueError, match="hash"):
        load_recorded_serving_inputs(
            path=path,
            expected_content_sha256="f" * 64,
            expected_release_id=RELEASE_ID,
            expected_database="miroflow_candidate_s12b_test",
            expected_index_root=(tmp_path / "index").resolve(),
            expected_envelope_path=(tmp_path / "envelope.json").resolve(),
            embedding_adapter=_Embedding(),
        )

    with pytest.raises(ValueError, match="release"):
        load_recorded_serving_inputs(
            path=path,
            expected_content_sha256=bundle.content_sha256,
            expected_release_id="candidate:cross-wired",
            expected_database="miroflow_candidate_s12b_test",
            expected_index_root=(tmp_path / "index").resolve(),
            expected_envelope_path=(tmp_path / "envelope.json").resolve(),
            embedding_adapter=_Embedding(),
        )


@pytest.mark.parametrize(
    ("query", "expected_domains", "expected_search_text"),
    (
        ("介绍清华的丁文伯", ("professor",), "丁文伯"),
        ("中国有哪些成熟的酒店送餐机器人供应商", ("company",), None),
        ("深圳有哪些具身智能、灵巧手厂商", ("company",), None),
        ("我想找PCB打板， 有哪些推荐", ("company",), None),
        (
            "介绍一下深圳市华力创科学技术有限公司",
            ("company",),
            "深圳市华力创科学技术有限公司",
        ),
        (
            "华力创科学这家公司相关信息，这家公司的产量特点是什么，市场竞争力怎么样",
            ("company",),
            "华力创科学",
        ),
        (
            "爱博合创企业情况以及创始人信息还有市场对这家企业的评价如何",
            ("company",),
            "爱博合创",
        ),
        (
            "清华的王学谦的评价如何，他是否是属于大牛",
            ("professor",),
            "王学谦",
        ),
        ("我关注的是深圳智航无界科技", ("company",), "深圳智航无界科技"),
        (
            "我关注的是人工智能",
            ("professor", "company", "paper", "patent"),
            "人工智能",
        ),
        (
            "请介绍无界智航的相关信息",
            ("professor", "company", "paper", "patent"),
            "无界智航",
        ),
        ("pFedGPA 这篇论文讲了什么", ("paper",), None),
        ("专利 CN117873146A 的详细信息", ("patent",), "CN117873146A"),
    ),
)
def test_serving_planner_extracts_generic_customer_query_axes(
    tmp_path: Path,
    query: str,
    expected_domains: tuple[str, ...],
    expected_search_text: str | None,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    request = QueryPlanningRequest(
        request_id=f"query-request:{abs(hash(query))}",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
    )

    proposal = inputs.proposal_provider(request)

    assert proposal.domains == expected_domains
    if expected_search_text is not None:
        assert proposal.query_views[0].text == expected_search_text


def test_explicit_company_name_does_not_become_a_geography_filter(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )

    focused = inputs.proposal_provider(
        QueryPlanningRequest(
            request_id="query-request:focused-company-name",
            release_id=RELEASE_ID,
            original_query="我关注的是深圳智航无界科技",
            as_of=NOW,
        )
    )
    introduced = inputs.proposal_provider(
        QueryPlanningRequest(
            request_id="query-request:introduced-company-name",
            release_id=RELEASE_ID,
            original_query="介绍一下深圳市华力创科学技术有限公司",
            as_of=NOW,
        )
    )
    filtered = inputs.proposal_provider(
        QueryPlanningRequest(
            request_id="query-request:shenzhen-company-filter",
            release_id=RELEASE_ID,
            original_query="深圳有哪些具身智能厂商",
            as_of=NOW,
        )
    )

    assert focused.query_views[0].retained_protected_values == ()
    assert introduced.query_views[0].retained_protected_values == ()
    assert filtered.query_views[0].retained_protected_values == ("深圳",)


@pytest.mark.parametrize(
    ("query_name", "display_name", "expected"),
    (
        ("深圳智航无界科技", "深圳无界智航科技有限公司", True),
        ("深圳智航无界科技", "深圳智航无人机有限公司", False),
        ("深圳智航无界科技", "深圳市环球智航机场科技有限公司", False),
    ),
)
def test_company_name_block_transposition_is_a_bounded_lexical_match(
    query_name: str,
    display_name: str,
    expected: bool,
) -> None:
    assert (
        isolated_read_module._matches_transposed_company_name(
            query_name,
            frozenset({display_name}),
        )
        is expected
    )


def test_projection_claim_exposes_a_matched_exact_identifier() -> None:
    request = LaneRequest(
        lane="exact",
        release_id=RELEASE_ID,
        query_view="view:exact-patent",
        original_query="专利 CN117873146A 的详细信息是什么",
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(mode="disabled"),
        query_text="CN117873146A",
        domains=("patent",),
        protected_slots=(
            ProtectedSlot(
                kind="exact_identifier",
                value="CN117873146A",
                raw_text="CN117873146A",
            ),
        ),
        structured_constraints=StructuredConstraints(),
        max_candidates=8,
    )

    binding = isolated_read_module._projection_claim_binding(
        request=request,
        subject_id="patent-c-test",
        lookup_content_sha256="a" * 64,
        identifier_terms=frozenset({"patent-c-test", "cn117873146a"}),
        status="admitted",
    )

    assert (binding.subject_id, binding.predicate, binding.value) == (
        "patent-c-test",
        "exact_identifier",
        "CN117873146A",
    )


def test_serving_planner_routes_lawful_avoidance_request_to_static_safety(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    request = QueryPlanningRequest(
        request_id="query-request:safety-avoidance",
        release_id=RELEASE_ID,
        original_query="在外地旅游时，如何避开涉及黄赌毒的场所？",
        as_of=NOW,
    )

    proposal = inputs.proposal_provider(request)

    assert proposal.behavior_class == "F"
    assert proposal.interaction_mode == "safety_guidance"
    assert proposal.domains == ()
    assert proposal.lanes == ()
    assert proposal.web_mode == "disabled"


def test_dual_web_lane_reuses_request_transport_and_isolates_keepwarm_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    observed: dict[str, Any] = {}

    class _Provider:
        def __init__(self, **kwargs: object) -> None:
            observed["provider_constructions"] = (
                int(observed.get("provider_constructions", 0)) + 1
            )
            observed["kwargs"] = kwargs

        def search(self, query: str) -> dict[str, object]:
            observed["query"] = query
            return {
                "organic": [
                    {
                        "title": "深圳机器人产业资料",
                        "link": "https://example.test/robotics",
                        "snippet": "公开资料摘要",
                    }
                ]
            }

    class _EmptyBochaProvider:
        def __init__(self, **_: object) -> None:
            pass

        def search(self, query: str) -> dict[str, object]:
            return {"organic": []}

    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setattr(serving_module, "BochaSearchProvider", _EmptyBochaProvider)
    monkeypatch.setattr(serving_module, "WebSearchProvider", _Provider)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    request = QueryPlanningRequest(
        request_id="query-request:web-fallback",
        release_id=RELEASE_ID,
        original_query="清华的王学谦的评价如何，他是否是属于大牛",
        as_of=NOW,
    )
    plan = create_ephemeral_query_planner(
        planning_policy=inputs.planning_policy,
        institution_catalog=InstitutionCatalog(
            catalog_id="institution-catalog:s12b-test",
            catalog_version="institution-catalog-v1",
            release_id=RELEASE_ID,
            entries=(),
        ),
        proposal_provider=inputs.proposal_provider,
    ).plan(request)
    lane_request = _lane_request(plan, "web", inputs.universal_web_policy)

    result = inputs.web_search(lane_request)
    repeated_result = inputs.web_search(lane_request)

    assert len(result.candidates) == 1
    assert len(repeated_result.candidates) == 1
    assert observed["provider_constructions"] == 2
    assert observed["query"] == "王学谦"
    kwargs = observed["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs == {"timeout": pytest.approx(0.675)}


def test_dual_web_lane_deduplicates_url_and_retains_provider_provenance() -> None:
    calls: list[tuple[str, str]] = []

    class _Provider:
        def __init__(self, name: str, payload: dict[str, object]) -> None:
            self.name = name
            self.payload = payload

        def search(self, query: str) -> dict[str, object]:
            calls.append((self.name, query))
            return self.payload

    bocha = _Provider(
        "bocha",
        {
            "organic": [
                {
                    "title": "清华大学丁文伯主页",
                    "link": "https://www.sigs.tsinghua.edu.cn/dwb/",
                    "snippet": "教师主页",
                    "summary": "丁文伯，副教授、博士生导师。",
                }
            ]
        },
    )
    serper = _Provider(
        "serper",
        {
            "organic": [
                {
                    "title": "清华大学丁文伯主页",
                    "link": "https://www.sigs.tsinghua.edu.cn/dwb",
                    "snippet": "清华大学深圳国际研究生院教师信息。",
                },
                {
                    "title": "无界智航官网",
                    "link": "https://www.wujiezhihang.example/",
                    "snippet": "企业官方网站。",
                },
            ]
        },
    )
    adapter = serving_module._DualWebLaneAdapter(
        bocha=bocha,
        serper=serper,
        timeout_ms=1500,
        max_snapshot_bytes=16384,
        clock=lambda: NOW,
    )
    request = LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:dual-web",
        original_query="介绍丁文伯",
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=1500,
            max_results=5,
        ),
        query_text="丁文伯 [lane=web]",
        domains=("professor",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=5,
    )

    result = adapter(request)

    assert sorted(calls) == [("bocha", "丁文伯"), ("serper", "丁文伯")]
    assert len(result.candidates) == 2
    assert result.candidates[0].provider_version == "bocha-v1"
    assert result.candidates[1].provider_version == "serper-v1"
    snapshot = json.loads(result.web_snapshot_payloads[0].content)
    assert snapshot["summary"] == "丁文伯，副教授、博士生导师。"
    assert snapshot["primary_provider_version"] == "bocha-v1"
    assert snapshot["corroborating_provider_versions"] == [
        "bocha-v1",
        "serper-v1",
    ]


def test_dual_web_lane_reserves_capacity_for_each_provider() -> None:
    class _Provider:
        def __init__(self, prefix: str, count: int) -> None:
            self.prefix = prefix
            self.count = count

        def search(self, query: str) -> dict[str, object]:
            return {
                "organic": [
                    {
                        "title": f"{self.prefix} result {index}",
                        "link": f"https://{self.prefix}.example/{query}/{index}",
                        "snippet": f"{self.prefix} snippet {index}",
                    }
                    for index in range(self.count)
                ]
            }

    adapter = serving_module._DualWebLaneAdapter(
        bocha=_Provider("bocha", 8),
        serper=_Provider("serper", 3),
        timeout_ms=1500,
        max_snapshot_bytes=16384,
        clock=lambda: NOW,
    )
    result = adapter(
        LaneRequest(
            lane="web",
            release_id=RELEASE_ID,
            query_view="view:provider-balanced-web",
            original_query="酒店服务机器人供应商",
            behavior_class="A",
            interaction_mode="information_retrieval",
            web_policy=WebSearchPolicy(
                mode="universal",
                max_provider_calls=2,
                timeout_ms=1500,
                max_results=5,
            ),
            query_text="酒店服务机器人供应商 [lane=web]",
            domains=("company",),
            protected_slots=(),
            structured_constraints=StructuredConstraints(),
            max_candidates=5,
        )
    )

    provider_versions = tuple(
        candidate.provider_version for candidate in result.candidates
    )
    assert len(provider_versions) == 5
    assert "bocha-v1" in provider_versions
    assert "serper-v1" in provider_versions


def test_dual_web_lane_preserves_one_provider_when_the_other_fails() -> None:
    class _FailingProvider:
        def search(self, query: str) -> dict[str, object]:
            raise RuntimeError(f"unavailable for {query}")

    class _WorkingProvider:
        def search(self, query: str) -> dict[str, object]:
            return {
                "organic": [
                    {
                        "title": "官方资料",
                        "link": "https://example.test/official",
                        "snippet": query,
                    }
                ]
            }

    adapter = serving_module._DualWebLaneAdapter(
        bocha=_FailingProvider(),
        serper=_WorkingProvider(),
        timeout_ms=1500,
        max_snapshot_bytes=16384,
        clock=lambda: NOW,
    )
    request = LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:dual-web-degraded",
        original_query="深圳机器人企业",
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=1500,
            max_results=5,
        ),
        query_text="深圳机器人企业",
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=5,
    )

    result = adapter(request)

    assert len(result.candidates) == 1
    assert result.candidates[0].provider_version == "serper-v1"


def test_dual_web_lane_reports_unavailable_when_both_providers_fail() -> None:
    class _FailingProvider:
        def search(self, query: str) -> dict[str, object]:
            raise RuntimeError(f"unavailable for {query}")

    adapter = serving_module._DualWebLaneAdapter(
        bocha=_FailingProvider(),
        serper=_FailingProvider(),
        timeout_ms=1500,
        max_snapshot_bytes=16384,
        clock=lambda: NOW,
    )
    request = LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:dual-web-unavailable",
        original_query="深圳机器人企业",
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=1500,
            max_results=5,
        ),
        query_text="深圳机器人企业",
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=5,
    )

    with pytest.raises(ConnectionError, match="Bocha and Serper"):
        adapter(request)


def test_provider_keepwarm_cycle_runs_all_external_paths_concurrently() -> None:
    barrier = Barrier(4, timeout=1.0)
    calls: list[str] = []

    def operation(name: str) -> None:
        calls.append(name)
        barrier.wait()

    cycle = serving_module._provider_keepwarm_cycle(
        operations=tuple(
            lambda name=name: operation(name)
            for name in ("bocha", "serper", "embedding", "llm")
        )
    )

    cycle()

    assert sorted(calls) == ["bocha", "embedding", "llm", "serper"]


def test_contextual_web_query_binds_display_name_and_geography(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    observed: dict[str, str] = {}

    class _Provider:
        def __init__(self, **_: object) -> None:
            pass

        def search(self, query: str) -> dict[str, object]:
            observed["query"] = query
            return {
                "organic": [
                    {
                        "title": "深圳市普渡科技有限公司",
                        "link": "https://example.test/pudu",
                        "snippet": "普渡机器人成立于2016年，总部位于广东深圳。",
                    }
                ]
            }

    class _EmptyBochaProvider:
        def __init__(self, **_: object) -> None:
            pass

        def search(self, query: str) -> dict[str, object]:
            return {"organic": []}

    monkeypatch.setattr(serving_module, "BochaSearchProvider", _EmptyBochaProvider)
    monkeypatch.setattr(serving_module, "WebSearchProvider", _Provider)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    company_id = "company-c-pudu"
    company_name = "深圳市普渡科技有限公司"
    query = "上述企业里总部在深圳的企业有哪些"
    request = QueryPlanningRequest(
        request_id="query-request:contextual-web-geography",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
        displayed_entity_ids=(company_id,),
        displayed_entity_names=(company_name,),
        enumeration_context=EnumerationPlanningContext(
            requested=True,
            scope=query,
            as_of=NOW,
            finite_universe=None,
        ),
    )
    plan = create_ephemeral_query_planner(
        planning_policy=inputs.planning_policy,
        institution_catalog=InstitutionCatalog(
            catalog_id="institution-catalog:s12b-test",
            catalog_version="institution-catalog-v1",
            release_id=RELEASE_ID,
            entries=(),
        ),
        proposal_provider=inputs.proposal_provider,
    ).plan(request)
    lane_request = _lane_request(plan, "web", inputs.universal_web_policy)

    result = inputs.web_search(lane_request)

    assert company_name in observed["query"]
    assert "[lane=web]" not in observed["query"]
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.canonical_id == company_id
    assert candidate.identity_kind == "web_candidate"
    assert candidate.resolution_state == "resolved"
    assert candidate.evidence[0].claim_binding is not None
    assert candidate.evidence[0].claim_binding.predicate == "geography"
    assert candidate.evidence[0].claim_binding.value == "深圳"


def test_contextual_web_query_removes_referent_question_scaffolding(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    company_name = "深圳市普渡科技有限公司"
    proposal = inputs.proposal_provider(
        QueryPlanningRequest(
            request_id="query-request:contextual-capability-search-view",
            release_id=RELEASE_ID,
            original_query="上述企业的产品哪些支持自主刷卡和开门",
            as_of=NOW,
            displayed_entity_ids=("company-c-pudu",),
            displayed_entity_names=(company_name,),
        )
    )

    search_text = proposal.query_views[0].text
    assert search_text == f'"{company_name}" 自主刷卡和开门'
    assert "上述" not in search_text
    assert "哪些支持" not in search_text


def test_serving_reranker_keeps_web_gap_ahead_of_vector_neighbors(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    vector_evidence = EvidenceItem(
        evidence_id="evidence:s12b:vector-neighbor",
        object_id="professor:s12b:wang-xuefeng",
        domain="professor",
        lane="vector",
        source_nature="local",
        source_locator="canonical-v2-isolated:neighbor",
        snippet="王学锋",
        score=0.8,
    )
    web_evidence = EvidenceItem(
        evidence_id="evidence:s12b:web-gap",
        object_id="web-object:s12b:wang-xueqian",
        domain="professor",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/wang-xueqian",
        snippet="王学谦：清华大学教师主页",
        score=1.0,
    )

    def fused(token: str, item: EvidenceItem) -> FusedCandidate:
        return FusedCandidate(
            result_id=f"fused-result:{token}",
            canonical_id=(item.object_id if item.source_nature == "local" else None),
            display_name=("王学锋" if item.source_nature == "local" else "王学谦"),
            domain="professor",
            raw_candidate_ids=(f"raw-candidate:{token}",),
            evidence_ids=(item.evidence_id,),
            evidence=(item,),
            quality_flags=(),
            raw_score=item.score,
            identity_kind=(
                "canonical" if item.source_nature == "local" else "web_only"
            ),
            resolution_state=(
                "resolved" if item.source_nature == "local" else "unresolved"
            ),
            origin_lane=item.lane,
            origin_attempt=1,
            adapter_versions=("test",),
            provider_versions=(),
        )

    assert inputs.reranker is not None
    request = RerankRequest(
        release_id=RELEASE_ID,
        original_query="清华的王学谦的评价如何，他是否是属于大牛",
        eligible_candidates=(
            fused("vector", vector_evidence),
            fused("web", web_evidence),
        ),
    )
    result = inputs.reranker(request)

    assert result.ordered_result_ids[0] == "fused-result:web"


def test_serving_reranker_reserves_web_capacity_without_query_markers(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )

    def fused(*, token: str, source_nature: str, score: float) -> FusedCandidate:
        local = source_nature == "local"
        evidence = EvidenceItem(
            evidence_id=f"evidence:lane-balanced:{token}",
            object_id=f"object:lane-balanced:{token}",
            domain="company",
            lane=("lexical" if local else "web"),
            source_nature=source_nature,
            source_locator=(
                f"canonical-v2-isolated:{token}"
                if local
                else f"https://example.test/{token}"
            ),
            snippet=token,
            score=score,
        )
        return FusedCandidate(
            result_id=f"fused-result:{token}",
            canonical_id=(f"company:{token}" if local else None),
            display_name=token,
            domain="company",
            raw_candidate_ids=(f"raw-candidate:{token}",),
            evidence_ids=(evidence.evidence_id,),
            evidence=(evidence,),
            quality_flags=(),
            raw_score=score,
            identity_kind=("canonical" if local else "web_only"),
            resolution_state=("resolved" if local else "unresolved"),
            origin_lane=evidence.lane,
            origin_attempt=1,
            adapter_versions=("test",),
            provider_versions=(() if local else ("serper-v1",)),
        )

    local_candidates = tuple(
        fused(token=f"local-{index}", source_nature="local", score=1.0)
        for index in range(bundle.max_candidates)
    )
    web_candidates = tuple(
        fused(token=f"web-{index}", source_nature="current_web", score=0.9)
        for index in range(bundle.max_web_results)
    )
    assert inputs.reranker is not None
    result = inputs.reranker(
        RerankRequest(
            release_id=RELEASE_ID,
            original_query="上述企业的产品哪些可以使用机械手操作楼宇设备",
            eligible_candidates=(*local_candidates, *web_candidates),
        )
    )

    retained = result.ordered_result_ids[: bundle.max_candidates]
    assert any(result_id.startswith("fused-result:local-") for result_id in retained)
    assert any(result_id.startswith("fused-result:web-") for result_id in retained)
