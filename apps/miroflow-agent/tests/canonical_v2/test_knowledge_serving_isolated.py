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
from src.data_agents.canonical_v2.knowledge_answer import (
    ProseSynthesisResult,
    TurnRequest,
)
from src.data_agents.canonical_v2.knowledge_build_isolated import (
    _PROFESSOR_MISSING_FIELD_FALLBACK,
)
from src.data_agents.canonical_v2.knowledge_read import (
    CanonicalEntityHandle,
    EnumerationPlanningContext,
    EvidenceClaimBinding,
    EvidenceItem,
    EvidenceSet,
    FusedCandidate,
    InstitutionCatalog,
    LaneRequest,
    LocalSourceRelationshipTrace,
    MaterialQuestionPart,
    ProtectedSlot,
    QueryPlanningRequest,
    RerankRequest,
    StructuredConstraints,
    SufficiencyDecisionRequest,
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


def _timeout_prose_renderer(_: Any) -> str:
    """Keep serving tests hermetic: the deterministic grounded path is the
    contract under test; the live environment renderer must stay out of unit
    tests even when an API key is resolvable."""
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


def _source_relationship_trace(
    *,
    displayed_entity_id: str,
    candidate_canonical_id: str,
    candidate_display_name: str,
) -> LocalSourceRelationshipTrace:
    """Minimal legal source-bound relationship trace bound to one displayed anchor."""
    sha = "a" * 64
    return LocalSourceRelationshipTrace(
        target_id="index-target:s12b-test",
        target_marker_sha256=sha,
        manifest_sha256=sha,
        index_result_content_sha256=sha,
        publication_verification_evidence_ids=("evidence:publication:1",),
        release_id=RELEASE_ID,
        lane_request_content_sha256=sha,
        relationship_enumeration_policy_sha256=sha,
        displayed_entity_ids=(displayed_entity_id,),
        displayed_entity_id=displayed_entity_id,
        protected_slot_id="slot:displayed-entity-set",
        protected_slot_content_sha256=sha,
        query_as_of=NOW,
        query_relationship_type_id="company_has_patent",
        query_direction="company_to_patent",
        query_source_type="company",
        query_target_type="patent",
        relationship_request_sha256=sha,
        relationship_result_sha256=sha,
        relationship_snapshot_as_of=NOW,
        canonical_relationship_id="canonical-relationship:1",
        current_relationship_content_sha256=sha,
        relationship_type_id="patent_has_applicant",
        relationship_type_version="canonical-v2-relationship-v1",
        physical_direction="inverse",
        physical_source_id=candidate_canonical_id,
        physical_source_type="patent",
        physical_target_id=displayed_entity_id,
        physical_target_type="company",
        relationship_role_bindings=(("applicant", f"canonical:company:{displayed_entity_id}"),),
        selected_evidence_refs=("evidence:relationship:1",),
        projection_candidate_id="projection-candidate:1",
        projection_candidate_content_sha256=sha,
        assertion_kind="typed_relationship_assertion",
        assertion_id="assertion:1",
        assertion_content_sha256=sha,
        source_record_id="source-record:1",
        relationship_decision_id="relationship-decision:1",
        relationship_decision_content_sha256=sha,
        candidate_outcome_content_sha256=sha,
        candidate_canonical_id=candidate_canonical_id,
        candidate_domain="patent",
        candidate_display_name=candidate_display_name,
        candidate_projection_content_sha256=sha,
        candidate_origin_public_evidence_ids=("evidence:publication:1",),
        claim_subject_id=f"canonical:company:{displayed_entity_id}",
        claim_predicate="patent_has_applicant",
        claim_value=f"canonical:patent:{candidate_canonical_id}",
        snippet_sha256=sha,
    )


def test_soft_context_subject_prefixes_the_deterministic_search_view(
    tmp_path: Path,
) -> None:
    provider = serving_module._proposal_provider(bundle=_bundle(tmp_path))
    request = QueryPlanningRequest(
        request_id="query-request:soft-context-prefix",
        release_id=RELEASE_ID,
        original_query="有没有更详细的信息",
        as_of=NOW,
        soft_context_subject="优必选",
    )

    proposal = provider(request)

    deterministic = proposal.query_views[0]
    assert deterministic.producer_kind == "deterministic"
    assert deterministic.text.startswith("优必选 ")
    assert "有没有更详细" in deterministic.text
    assert "优必选" in deterministic.retained_protected_values


def test_soft_context_subject_is_appended_back_to_rewrite_views(
    tmp_path: Path,
) -> None:
    provider = serving_module._proposal_provider(
        bundle=_bundle(tmp_path),
        query_rewriter=lambda _query: ("UBTECH robotics company profile",),
    )
    request = QueryPlanningRequest(
        request_id="query-request:soft-context-rewrite",
        release_id=RELEASE_ID,
        original_query="有没有更详细的信息",
        as_of=NOW,
        soft_context_subject="优必选",
    )

    proposal = provider(request)

    rewrite = next(
        view for view in proposal.query_views if view.producer_kind == "llm_rewrite"
    )
    assert "UBTECH robotics company profile" in rewrite.text
    assert "优必选" in rewrite.text


def test_soft_context_subject_already_in_search_text_is_not_doubled(
    tmp_path: Path,
) -> None:
    provider = serving_module._proposal_provider(bundle=_bundle(tmp_path))
    request = QueryPlanningRequest(
        request_id="query-request:soft-context-dedup",
        release_id=RELEASE_ID,
        original_query="优必选",
        as_of=NOW,
        soft_context_subject="优必选",
    )

    proposal = provider(request)

    assert proposal.query_views[0].text == "优必选"


def test_content_addressed_serving_bundle_is_secret_free_and_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    monkeypatch.setenv("BOCHA_API_KEY", "bocha-secret-must-stay-outside-bundle")
    monkeypatch.setenv("SERPER_API_KEY", "secret-must-stay-outside-bundle")

    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
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
    assert inputs.planning_policy.max_candidates == max(
        bundle.max_candidates + bundle.max_web_results,
        serving_module._ENUMERATION_CANDIDATE_WINDOW,
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
    # Prose synthesis is timeout-degraded here, so the server-owned grounded
    # fallback must preserve the selected professor while excluding neighbors.
    assert result.render_mode == "deterministic_fallback"
    assert "丁文伯" in result.answer_text
    assert "机器人技术" in result.answer_text
    assert "无关教授" not in result.answer_text
    assert result.context_receipt is not None
    assert result.context_receipt.displayed_result_set is not None
    assert result.context_receipt.displayed_result_set.handle_ids == (
        evidence.object_id,
    )
    assert result.citations[0].source_locator == "canonical-v2-isolated:test"


def test_enumeration_proposal_widens_the_web_result_window(
    tmp_path: Path,
) -> None:
    """List-style questions must not truncate web candidates at the ordinary
    window: supplier mentions like 九号 sit at ranks 9-16 of the merged
    brand-list views, so the enumeration web window has to be wider than the
    default result cap."""
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
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
        request_id="query-request:enumeration-window",
        release_id=RELEASE_ID,
        original_query="中国有哪些成熟的酒店送餐机器人供应商",
        as_of=NOW,
    )
    proposal = inputs.proposal_provider(request)
    assert proposal.max_candidates >= serving_module._ENUMERATION_CANDIDATE_WINDOW
    assert proposal.max_web_results >= 16

    ordinary = inputs.proposal_provider(
        QueryPlanningRequest(
            request_id="query-request:ordinary-window",
            release_id=RELEASE_ID,
            original_query="丁文伯教授的研究方向是什么？",
            as_of=NOW,
        )
    )
    assert ordinary.max_web_results == bundle.max_web_results


def test_enumeration_discovery_views_merge_before_other_rewrite_views() -> None:
    """Enumeration turns must surface brand-list views first: supplier
    mentions like 九号 sit at ranks 9-16 of those views and are buried below
    the candidate cut when the plain view merges first."""
    extras = (
        "国内成熟酒店配送机器人品牌",
        "酒店服务机器人头部企业名单",
        "中国酒店送餐机器人供应商",
    )
    ordered = serving_module._enumeration_ordered_view_queries(
        original_query="中国有哪些成熟的酒店送餐机器人供应商",
        extras=extras,
    )
    assert ordered == (
        "国内成熟酒店配送机器人品牌",
        "酒店服务机器人头部企业名单",
        "中国酒店送餐机器人供应商",
    )

    ordinary = serving_module._enumeration_ordered_view_queries(
        original_query="丁文伯教授的研究方向是什么？",
        extras=extras,
    )
    assert ordinary == extras


def test_discovery_front_merge_promotes_brand_listicle_mentions() -> None:
    """Brand-listicle views must have their head promoted above the
    literal-view tail: supplier mentions like 九号 at ranks 9-16 of a brand
    view stay inside the enumeration candidate window instead of being
    buried below it (plain view first, then discovery head, then the tails).
    """
    resolved = serving_module._discovery_front_merge

    def item(rank: int, name: str) -> serving_module._NormalizedWebResult:
        return serving_module._NormalizedWebResult(
            title=f"{name}",
            url=f"https://example.test/{name}-{rank}",
            snippet=f"{name} 相关信息",
            summary="",
            primary_provider_version="bocha-v1",
            corroborating_provider_versions=(),
        )

    literal = tuple(item(rank, f"企业{rank}") for rank in range(1, 23))
    brand = tuple(item(rank + 30, f"品牌{rank}") for rank in range(1, 17))
    merged = resolved([literal, brand], discovery_view_indexes=(1,))
    urls = tuple(entry.url for entry in merged)
    # Literal-view head keeps the top slot.
    assert urls[0] == "https://example.test/企业1-1"
    # Brand mentions at ranks 9-14 land inside the 24-wide enumeration
    # window (head 10 + discovery front 14).
    assert urls.index("https://example.test/品牌10-40") < 24
    assert urls.index("https://example.test/品牌14-44") < 24
    # The widened enumeration window (48) still covers the brand-view tail.
    assert urls.index("https://example.test/品牌15-45") < 48
    assert urls.index("https://example.test/品牌16-46") < 48
    assert len(urls) == 38  # no dedupe loss in this fixture

    untouched = resolved([literal, brand], discovery_view_indexes=())
    assert tuple(entry.url for entry in untouched)[0] == "https://example.test/企业1-1"
    assert tuple(entry.url for entry in untouched)[1] == "https://example.test/企业2-2"


def test_is_brand_discovery_view_classifies_listicle_queries() -> None:
    assert serving_module._is_brand_discovery_view("国内成熟酒店配送机器人品牌")
    assert serving_module._is_brand_discovery_view("酒店服务机器人头部企业名单")
    assert not serving_module._is_brand_discovery_view("中国酒店送餐机器人供应商")


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


_PROSE_SELECTION_MARKER = "<|canonical_v2_selection_v1|>"
_PROSE_ANSWER_MARKER = "<|canonical_v2_answer_v1|>"


def _prose_wire(
    answer: str,
    *,
    claim_indexes: tuple[int, ...] = (),
    entity_indexes: tuple[int, ...] = (),
    header: str | None = None,
) -> str:
    selection = header or json.dumps(
        {
            "selected_claim_indexes": claim_indexes,
            "selected_entity_indexes": entity_indexes,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        f"{_PROSE_SELECTION_MARKER}\n{selection}\n"
        f"{_PROSE_ANSWER_MARKER}\n{answer}"
    )


class _RecordedProseCompletions:
    def __init__(
        self,
        content: str,
        *,
        chunk_width: int = 1,
        finish_reason: str | None = None,
    ) -> None:
        self.content = content
        self.chunk_width = chunk_width
        self.finish_reason = finish_reason
        self.calls: list[dict[str, object]] = []
        self.provider_finished = False

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if not kwargs.get("stream"):
            return SimpleNamespace(
                choices=(
                    SimpleNamespace(
                        message=SimpleNamespace(content=self.content),
                        finish_reason=self.finish_reason,
                    ),
                )
            )

        def completion() -> object:
            for index in range(0, len(self.content), self.chunk_width):
                yield SimpleNamespace(
                    choices=(
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=self.content[index : index + self.chunk_width]
                            ),
                            finish_reason=None,
                        ),
                    )
                )
            yield SimpleNamespace(
                choices=(
                    SimpleNamespace(
                        delta=SimpleNamespace(content=None),
                        finish_reason=self.finish_reason,
                    ),
                )
            )
            self.provider_finished = True

        return completion()


def _prose_renderer(
    completions: _RecordedProseCompletions,
    *,
    page_fetcher: Any = None,
) -> Any:
    return serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=completions),
        ),
        model="recorded-chat-model",
        extra_body={"thinking": {"type": "disabled"}},
        page_fetcher=page_fetcher,
    )


def _prose_result() -> tuple[Any, Any, Any]:
    claim = SimpleNamespace(
        claim_id="claim:stream",
        text="深圳科创助手提供服务。",
        subject_id="company:stream",
        subject_handle_ids=("company:stream",),
        predicate="preferred_name",
        status="accepted",
        source_natures=("local",),
        evidence_ids=("evidence:stream",),
    )
    handle = SimpleNamespace(
        canonical_id="company:stream",
        display_name="深圳科创助手",
        domain="company",
        evidence_ids=("evidence:stream",),
    )
    result = SimpleNamespace(
        original_query="介绍深圳科创",
        claims=(claim,),
        citations=(),
        context_receipt=SimpleNamespace(
            active_anchor=None,
            displayed_result_set=SimpleNamespace(handles=(handle,)),
            traversed_path_ids=(),
        ),
    )
    return result, claim, handle


@pytest.mark.parametrize("finish_reason", ("length", "content_filter"))
@pytest.mark.parametrize("mode", ("sync", "stream"))
def test_openai_prose_renderer_rejects_explicit_truncated_finish_reason(
    finish_reason: str,
    mode: str,
) -> None:
    wire = _prose_wire(
        "结构完整回答",
        claim_indexes=(1,),
        entity_indexes=(1,),
    )
    completions = _RecordedProseCompletions(
        wire,
        chunk_width=len(wire),
        finish_reason=finish_reason,
    )
    renderer = _prose_renderer(completions)
    result, _, _ = _prose_result()
    published: list[str] = []

    with pytest.raises(
        ValueError,
        match=rf"finish_reason={finish_reason}",
    ):
        if mode == "stream":
            renderer.stream(result, on_chunk=published.append)
        else:
            renderer(result)

    assert len(completions.calls) == 1


def test_openai_prose_renderer_framed_wire_streams_answer_and_preserves_selection() -> (
    None
):
    expected = '你好\n世界，他说"你好"。\t路径\\完成 {原样}'
    wire = "\n" + _prose_wire(
        f" {expected} \n",
        claim_indexes=(1,),
        entity_indexes=(1,),
    )
    result, claim, handle = _prose_result()

    for chunk_width in (1, 7, 29):
        completions = _RecordedProseCompletions(
            wire,
            chunk_width=chunk_width,
            finish_reason="stop",
        )
        renderer = _prose_renderer(completions)
        received: list[str] = []
        observed_before_final: list[bool] = []
        sync_rendered = renderer(result)

        def receive(text: str) -> None:
            observed_before_final.append(not completions.provider_finished)
            received.append(text)

        streamed = renderer.stream(result, on_chunk=receive)

        assert isinstance(sync_rendered, ProseSynthesisResult)
        assert isinstance(streamed, ProseSynthesisResult)
        assert streamed == sync_rendered
        assert streamed.answer_text == expected
        assert streamed.selected_claim_ids == (claim.claim_id,)
        assert streamed.selected_handle_ids == (handle.canonical_id,)
        assert "".join(received) == expected
        assert observed_before_final and all(observed_before_final)
        assert completions.provider_finished is True
        assert _PROSE_SELECTION_MARKER not in "".join(received)
        assert _PROSE_ANSWER_MARKER not in "".join(received)
        assert len(completions.calls) == 2
        assert completions.calls[0].get("stream") is None
        assert completions.calls[1]["stream"] is True


@pytest.mark.parametrize(
    "leading_whitespace_length",
    (64, 65, 10_000),
    ids=("boundary", "past-boundary", "long"),
)
def test_openai_prose_renderer_accepts_framed_wire_after_leading_whitespace(
    leading_whitespace_length: int,
) -> None:
    wire = " " * leading_whitespace_length + _prose_wire(
        "安全回答",
        claim_indexes=(1,),
        entity_indexes=(1,),
    )
    completions = _RecordedProseCompletions(wire, chunk_width=1)
    renderer = _prose_renderer(completions)
    result, claim, handle = _prose_result()
    published: list[str] = []

    sync_rendered = renderer(result)
    streamed = renderer.stream(result, on_chunk=published.append)

    expected = ProseSynthesisResult(
        answer_text="安全回答",
        selected_claim_ids=(claim.claim_id,),
        selected_handle_ids=(handle.canonical_id,),
    )
    assert sync_rendered == expected
    assert streamed == expected
    assert "".join(published) == "安全回答"
    assert len(completions.calls) == 2


@pytest.mark.parametrize(
    "content",
    ("<", _PROSE_SELECTION_MARKER[:-1]),
    ids=("less-than", "marker-strict-prefix"),
)
def test_openai_prose_renderer_treats_selection_marker_strict_prefix_at_eof_as_plain(
    content: str,
) -> None:
    completions = _RecordedProseCompletions(content, chunk_width=1)
    renderer = _prose_renderer(completions)
    result, _, _ = _prose_result()
    published: list[str] = []

    sync_rendered = renderer(result)
    streamed = renderer.stream(result, on_chunk=published.append)

    assert sync_rendered == content
    assert streamed == content
    assert "".join(published) == content
    assert len(completions.calls) == 2


@pytest.mark.parametrize(
    "marker",
    (_PROSE_SELECTION_MARKER, _PROSE_ANSWER_MARKER),
    ids=("selection-marker", "answer-marker"),
)
@pytest.mark.parametrize(
    ("position", "prefix", "suffix"),
    (
        # start omitted: marker-led response is protocol framing, not echo
        ("middle", "公开前文", "公开后文"),
        ("end", "公开前文", ""),
    ),
)
@pytest.mark.parametrize("wire_mode", ("plain", "framed"))
def test_openai_prose_renderer_strips_private_marker_in_answer_before_publish(
    marker: str,
    position: str,
    prefix: str,
    suffix: str,
    wire_mode: str,
) -> None:
    del position
    # Contract change (fix-prose-marker-strip): one echoed protocol marker
    # must cost its own removal, not the whole synthesized answer — the
    # all-or-nothing raise degraded full answers to raw-candidate dumps.
    answer = f"{prefix}{marker}{suffix}"
    content = _prose_wire(answer) if wire_mode == "framed" else answer
    completions = _RecordedProseCompletions(content, chunk_width=1)
    renderer = _prose_renderer(completions)
    result, _, _ = _prose_result()
    published: list[str] = []

    synced = renderer(result)
    renderer.stream(result, on_chunk=published.append)

    synced_text = (
        synced if isinstance(synced, str) else synced.answer_text
    )
    assert synced_text == f"{prefix}{suffix}"
    assert "".join(published) == f"{prefix}{suffix}"
    assert _PROSE_SELECTION_MARKER not in "".join(published)
    assert _PROSE_ANSWER_MARKER not in "".join(published)
    assert len(completions.calls) == 2


@pytest.mark.parametrize(
    ("content", "expected", "expect_all_before_final"),
    (
        (" \n纯文本降级回答 \t", "纯文本降级回答", True),
        ("{纯文本降级回答", "{纯文本降级回答", True),
        (
            "普通<文本 <<|canonical_v2_answer_vX|> 尾部<|canonical_v2_ans",
            "普通<文本 <<|canonical_v2_answer_vX|> 尾部<|canonical_v2_ans",
            False,
        ),
    ),
)
def test_openai_prose_renderer_plain_fallback_streams_progressively(
    content: str,
    expected: str,
    *,
    expect_all_before_final: bool,
) -> None:
    completions = _RecordedProseCompletions(content, chunk_width=1)
    renderer = _prose_renderer(completions)
    result = SimpleNamespace(
        original_query="q",
        claims=(),
        citations=(),
        context_receipt=None,
    )
    received: list[str] = []
    observed_before_final: list[bool] = []

    sync_rendered = renderer(result)

    def receive(text: str) -> None:
        observed_before_final.append(not completions.provider_finished)
        received.append(text)

    streamed = renderer.stream(result, on_chunk=receive)

    assert sync_rendered == expected
    assert streamed == expected
    assert "".join(received) == expected
    assert observed_before_final and any(observed_before_final)
    assert all(observed_before_final) is expect_all_before_final
    assert len(completions.calls) == 2


@pytest.mark.parametrize(
    (
        "model_answer",
        "expected",
        "expected_founder_phrase_count",
        "expect_progress_before_final",
    ),
    (
        (
            "丁文伯是深圳无界智航科技有限公司的创始人。",
            "丁文伯参与创立了深圳无界智航科技有限公司。\n\n"
            "丁文伯是深圳无界智航科技有限公司的创始人。",
            1,
            True,
        ),
        (
            "Ding Wenbo is a founder of Boundaryless Robotics. "
            "Public records confirm the relationship.",
            "丁文伯参与创立了深圳无界智航科技有限公司。\n\n"
            "Ding Wenbo is a founder of Boundaryless Robotics. "
            "Public records confirm the relationship.",
            1,
            True,
        ),
        (
            "丁文伯参与创立了深圳无界智航科技有限公司。\n\n公开信息可确认该关系。",
            "丁文伯参与创立了深圳无界智航科技有限公司。\n\n公开信息可确认该关系。",
            1,
            True,
        ),
        (
            "公开信息显示，丁文伯参与创立了深圳无界智航科技有限公司。",
            "丁文伯参与创立了深圳无界智航科技有限公司。\n\n"
            "公开信息显示，丁文伯参与创立了深圳无界智航科技有限公司。",
            2,
            True,
        ),
        (
            "丁文伯是深圳无界智航科技有限公司的创始人",
            "丁文伯参与创立了深圳无界智航科技有限公司。\n\n"
            "丁文伯是深圳无界智航科技有限公司的创始人",
            1,
            True,
        ),
        (
            "先给出公开结论。丁文伯参与创立了深圳无界智航科技有限公司。",
            "丁文伯参与创立了深圳无界智航科技有限公司。\n\n"
            "先给出公开结论。",
            1,
            True,
        ),
        (
            "丁文伯是该公司的创始人",
            "丁文伯参与创立了深圳无界智航科技有限公司。\n\n"
            "丁文伯是该公司的创始人",
            1,
            True,
        ),
        (
            "先给出公开结论。引用原文：“"
            "丁文伯参与创立了深圳无界智航科技有限公司。"
            "”以上为完整表述。",
            "丁文伯参与创立了深圳无界智航科技有限公司。\n\n"
            "先给出公开结论。引用原文：“"
            "丁文伯参与创立了深圳无界智航科技有限公司。"
            "”以上为完整表述。",
            2,
            True,
        ),
        (
            "先给出公开结论。\n"
            "1. 丁文伯参与创立了深圳无界智航科技有限公司。",
            "丁文伯参与创立了深圳无界智航科技有限公司。\n\n"
            "先给出公开结论。\n"
            "1. 丁文伯参与创立了深圳无界智航科技有限公司。",
            2,
            True,
        ),
    ),
)
def test_openai_prose_renderer_stream_publishes_founder_prefix_safely(
    model_answer: str,
    expected: str,
    expected_founder_phrase_count: int,
    *,
    expect_progress_before_final: bool,
) -> None:
    wire = _prose_wire(
        model_answer,
        claim_indexes=(1,),
        entity_indexes=(1, 2),
    )
    completions = _RecordedProseCompletions(wire, chunk_width=5)
    renderer = _prose_renderer(completions)
    received: list[str] = []
    observed_before_final: list[bool] = []
    claim = SimpleNamespace(
        claim_id="claim:founder",
        text="丁文伯参与创立了深圳无界智航科技有限公司，角色为创始人。",
        subject_id="professor:ding-wenbo",
        subject_handle_ids=("professor:ding-wenbo", "company:boundaryless"),
        predicate="professor_company_role",
        status="accepted",
        source_natures=("local",),
        evidence_ids=("evidence:founder",),
    )
    professor = SimpleNamespace(
        canonical_id="professor:ding-wenbo",
        display_name="丁文伯",
        domain="professor",
        evidence_ids=("evidence:founder",),
    )
    company = SimpleNamespace(
        canonical_id="company:boundaryless",
        display_name="深圳无界智航科技有限公司",
        domain="company",
        evidence_ids=("evidence:founder",),
    )
    result = SimpleNamespace(
        original_query="他是否有参与哪些企业的创立？",
        claims=(claim,),
        citations=(),
        context_receipt=SimpleNamespace(
            active_anchor=professor,
            displayed_result_set=SimpleNamespace(handles=(company,)),
            traversed_path_ids=(),
        ),
    )
    sync_rendered = renderer(result)

    def receive(text: str) -> None:
        observed_before_final.append(not completions.provider_finished)
        received.append(text)

    streamed = renderer.stream(result, on_chunk=receive)

    assert isinstance(sync_rendered, ProseSynthesisResult)
    assert isinstance(streamed, ProseSynthesisResult)
    assert streamed == sync_rendered
    assert streamed.answer_text == expected
    assert (
        streamed.answer_text.count("参与创立")
        == expected_founder_phrase_count
    )
    assert "".join(received) == expected
    assert observed_before_final
    assert all(observed_before_final) is expect_progress_before_final
    assert streamed.selected_claim_ids == (claim.claim_id,)
    assert streamed.selected_handle_ids == (
        company.canonical_id,
        professor.canonical_id,
    )
    assert len(completions.calls) == 2


def test_prose_text_normalizer_finish_flushes_aborted_founder_duplicate_candidate(
) -> None:
    founder_prefix = "丁文伯参与创立了深圳无界智航科技有限公司。"
    model_answer = "先给出公开结论。丁文"
    expected_before_finish = f"{founder_prefix}\n\n先给出公开结论。"
    expected = f"{expected_before_finish}丁文"
    received: list[str] = []
    normalizer = serving_module._ProseTextNormalizer(
        founder_prefix=founder_prefix,
        on_chunk=received.append,
    )

    normalizer.feed(model_answer)

    assert "".join(received) == expected_before_finish
    assert normalizer.finish() == expected
    assert "".join(received) == expected


@pytest.mark.parametrize(
    "wire",
    (
        _prose_wire("不得公开", header='{"selected_claim_indexes":[]}'),
        _prose_wire(
            "不得公开",
            header=(
                '{"selected_claim_indexes":[],"selected_entity_indexes":[],'
                '"extra":[]}'
            ),
        ),
        _prose_wire(
            "不得公开",
            header=(
                '{"selected_claim_indexes":"1","selected_entity_indexes":[]}'
            ),
        ),
        _prose_wire(
            "不得公开",
            header=(
                '{"selected_claim_indexes":[true],"selected_entity_indexes":[]}'
            ),
        ),
        _prose_wire(
            "不得公开",
            header=(
                '{"selected_claim_indexes":[1,1],"selected_entity_indexes":[]}'
            ),
        ),
        _prose_wire(
            "不得公开",
            header=(
                '{"selected_claim_indexes":[],"selected_claim_indexes":[],'
                '"selected_entity_indexes":[]}'
            ),
        ),
        _prose_wire(
            "不得公开",
            header=(
                '{"selected_claim_indexes":[],"\\u0073elected_claim_indexes":[],'
                '"selected_entity_indexes":[]}'
            ),
        ),
        _prose_wire("不得公开", header=" " * 4097),
        f'{_PROSE_SELECTION_MARKER}\n{{"selected_claim_indexes":[]',
    ),
    ids=(
        "missing-key",
        "extra-key",
        "wrong-type",
        "bool-index",
        "duplicate-index",
        "duplicate-key",
        "escaped-duplicate-key",
        "oversized",
        "unclosed",
    ),
)
def test_openai_prose_renderer_rejects_invalid_selection_header_before_publish(
    wire: str,
) -> None:
    completions = _RecordedProseCompletions(wire, chunk_width=3)
    renderer = _prose_renderer(completions)
    result, _, _ = _prose_result()
    published: list[str] = []

    with pytest.raises(ValueError):
        renderer(result)
    with pytest.raises(ValueError):
        renderer.stream(result, on_chunk=published.append)

    assert published == []
    assert len(completions.calls) == 2


@pytest.mark.parametrize(
    "content",
    (
        '{"answer_text":"legacy","selected_claim_indexes":[],'
        '"selected_entity_indexes":[]}',
        '```json\n{"answer_text":"legacy","selected_claim_indexes":[],'
        '"selected_entity_indexes":[]}\n```',
        (
            " " * 65
            + '{"answer_text":"legacy","selected_claim_indexes":[],'
            '"selected_entity_indexes":[]}'
        ),
        (
            " " * 65
            + '```json\n{"answer_text":"legacy","selected_claim_indexes":[],'
            '"selected_entity_indexes":[]}\n```'
        ),
    ),
    ids=(
        "json-object",
        "json-fence",
        "json-object-after-whitespace",
        "json-fence-after-whitespace",
    ),
)
def test_openai_prose_renderer_rejects_legacy_json_before_publish(
    content: str,
) -> None:
    completions = _RecordedProseCompletions(content, chunk_width=1)
    renderer = _prose_renderer(completions)
    result, _, _ = _prose_result()
    published: list[str] = []

    with pytest.raises(ValueError, match="legacy JSON"):
        renderer(result)
    with pytest.raises(ValueError, match="legacy JSON"):
        renderer.stream(result, on_chunk=published.append)

    assert published == []
    assert len(completions.calls) == 2


def test_openai_prose_renderer_rejects_real_unpaired_surrogate() -> None:
    wire = _prose_wire("\ud83d")
    completions = _RecordedProseCompletions(wire, chunk_width=4)
    renderer = _prose_renderer(completions)
    result, _, _ = _prose_result()
    published: list[str] = []

    with pytest.raises(ValueError, match="surrogate"):
        renderer(result)
    with pytest.raises(ValueError, match="surrogate"):
        renderer.stream(result, on_chunk=published.append)

    assert published == []
    assert len(completions.calls) == 2


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
                subject_id="professor:ding-wenbo",
                subject_handle_ids=(
                    "professor:ding-wenbo",
                    "company:boundaryless",
                ),
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
            active_anchor=SimpleNamespace(
                display_name="丁文伯",
                domain="professor",
                canonical_id="professor:ding-wenbo",
                evidence_ids=("evidence:renderer:founder",),
            ),
            displayed_result_set=SimpleNamespace(
                handles=(
                    SimpleNamespace(
                        display_name="深圳无界智航科技有限公司",
                        domain="company",
                        canonical_id="company:boundaryless",
                        evidence_ids=("evidence:renderer:founder",),
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
    assert "回答用户" in serialized
    assert "不要逐字段复述" in serialized
    assert "canonical-v2-prose-v16" in serialized
    assert _PROSE_SELECTION_MARKER in serialized
    assert _PROSE_ANSWER_MARKER in serialized
    assert "未经JSON编码的纯文本" in serialized
    assert "旧版JSON答案外壳" in serialized
    assert "逐字一致" in serialized
    assert "语义覆盖而非逐字匹配" in serialized
    assert "不要逐一列名" in serialized
    # Enumeration contract (2026-08-18 ruling): budgeted representative
    # list replaces the 求全 directive.
    assert "条目预算" in serialized
    assert "代表性清单" in serialized
    assert "另有X、Y暂未能确认" not in serialized
    assert "材料显示" in serialized
    assert "直接绑定具体产品与具体功能" in serialized
    assert "专利或公司技术不是产品名称" in serialized
    assert "不能从公司名称、分支机构或服务地点推断总部" in serialized
    assert "https://official.example/products/service-robot-arm" in serialized
    assert "evidence:" not in serialized
    assert "canonical-v2-isolated" not in serialized


def test_llm_prose_renderer_rejects_out_of_range_selection_indexes() -> None:
    class _Completions:
        def create(self, **_: object) -> object:
            return SimpleNamespace(
                choices=(
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=_prose_wire(
                                "无效选择",
                                claim_indexes=(2,),
                                entity_indexes=(1,),
                            )
                        )
                    ),
                )
            )

    renderer = serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=_Completions()),
        ),
        model="recorded-chat-model",
        extra_body={"thinking": {"type": "disabled"}},
    )
    result = SimpleNamespace(
        original_query="上述企业里总部在深圳的有哪些",
        claims=(
            SimpleNamespace(
                claim_id="claim:one",
                text="普渡机器人总部位于深圳。",
                subject_id="company-c-pudu",
                subject_handle_ids=("company-c-pudu",),
                predicate="headquarters_city",
                status="observed",
                source_natures=("current_web",),
                evidence_ids=("evidence:pudu",),
            ),
        ),
        citations=(),
        context_receipt=SimpleNamespace(
            active_anchor=None,
            displayed_result_set=SimpleNamespace(
                handles=(
                    SimpleNamespace(
                        canonical_id="company-c-pudu",
                        display_name="深圳市普渡科技有限公司",
                        domain="company",
                        evidence_ids=("evidence:pudu",),
                    ),
                )
            ),
            traversed_path_ids=(),
        ),
    )

    with pytest.raises(ValueError, match="selected_claim_indexes"):
        renderer(result)


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


_ANCHOR_NAME = "国际先进技术应用推进中心（深圳）"
_OFF_ANSWER = "华南先进技术应用研究院是一家位于广州的科研机构，主要开展应用基础研究。"
_ON_ANSWER = "国际先进技术应用推进中心（深圳）是位于深圳的共性技术服务平台。"
_HEFEI_ANSWER = "国际先进技术应用推进中心（合肥）采用事业单位企业化运作模式。"


class _SequentialProseCompletions:
    """Sync-only completions stub replaying one scripted content per call."""

    def __init__(self, *contents: str) -> None:
        self._contents = contents
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        content = self._contents[min(len(self.calls), len(self._contents)) - 1]
        return SimpleNamespace(
            choices=(
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason="stop",
                ),
            )
        )


class _StreamThenSyncProseCompletions:
    """Stream-first completions stub for the renderer's stream path.

    ``stream=True`` calls replay one scripted wire as content chunks;
    non-stream calls replay scripted sync contents in order (or raise
    ``sync_error``). Per-mode call counters let tests pin the stream
    contract: one streaming call, plus at most one non-stream correction.
    """

    def __init__(
        self,
        stream_content: str,
        *sync_contents: str,
        chunk_width: int = 7,
        sync_error: Exception | None = None,
    ) -> None:
        self._stream_content = stream_content
        self._sync_contents = sync_contents
        self._chunk_width = chunk_width
        self._sync_error = sync_error
        self.stream_create_calls = 0
        self.sync_create_calls = 0
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            self.stream_create_calls += 1
            content = self._stream_content
            width = self._chunk_width

            def completion() -> object:
                for index in range(0, len(content), width):
                    yield SimpleNamespace(
                        choices=(
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content=content[index : index + width]
                                ),
                                finish_reason=None,
                            ),
                        )
                    )
                yield SimpleNamespace(
                    choices=(
                        SimpleNamespace(
                            delta=SimpleNamespace(content=None),
                            finish_reason="stop",
                        ),
                    )
                )

            return completion()
        self.sync_create_calls += 1
        if self._sync_error is not None:
            raise self._sync_error
        content = self._sync_contents[
            min(self.sync_create_calls, len(self._sync_contents)) - 1
        ]
        return SimpleNamespace(
            choices=(
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason="stop",
                ),
            )
        )


def _anchored_prose_result(
    *,
    anchor_id: str = "company:anchor-serving",
    anchor_name: str = _ANCHOR_NAME,
    response_mode: str = "answer",
    soft_context_subject: str | None = None,
    citations: tuple[Any, ...] = (),
) -> Any:
    claim = SimpleNamespace(
        claim_id="claim:anchor-serving",
        text=f"{anchor_name}是位于深圳的共性技术服务平台。",
        subject_id=anchor_id,
        subject_handle_ids=(anchor_id,),
        predicate="profile_summary",
        status="accepted",
        source_natures=("local",),
        evidence_ids=("evidence:anchor-serving",),
    )
    anchor_key = (
        {"handle_id": anchor_id}
        if anchor_id.startswith("web-handle:")
        else {"canonical_id": anchor_id}
    )
    anchor = SimpleNamespace(
        display_name=anchor_name,
        domain="company",
        evidence_ids=("evidence:anchor-serving",),
        **anchor_key,
    )
    return SimpleNamespace(
        original_query=f"介绍{anchor_name}",
        response_mode=response_mode,
        claims=(claim,),
        citations=citations,
        context_receipt=SimpleNamespace(
            active_anchor=anchor,
            displayed_result_set=None,
            traversed_path_ids=(),
            soft_context_subject=soft_context_subject,
        ),
    )


def test_openai_prose_renderer_retries_once_when_answer_leaves_the_anchor() -> None:
    result = _anchored_prose_result()
    completions = _SequentialProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
        _prose_wire(_ON_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(completions)

    rendered = renderer(result)

    assert isinstance(rendered, ProseSynthesisResult)
    # The non-stream path publishes nothing, so its corrected result is never
    # marked as superseding a streamed draft.
    assert rendered.supersedes_streamed_draft is False
    assert rendered.answer_text == _ON_ANSWER
    assert rendered.selected_claim_ids == ("claim:anchor-serving",)
    assert rendered.selected_handle_ids == ("company:anchor-serving",)
    assert len(completions.calls) == 2
    first_messages = completions.calls[0]["messages"]
    retry_messages = completions.calls[1]["messages"]
    assert isinstance(first_messages, list)
    assert len(first_messages) == 2
    assert len(retry_messages) == 3
    correction = retry_messages[-1]
    assert correction["role"] == "user"
    assert _ANCHOR_NAME in correction["content"]
    assert "不得反问" in correction["content"]
    assert retry_messages[:2] == first_messages


def test_openai_prose_renderer_raises_off_anchor_when_retry_still_misses() -> None:
    result = _anchored_prose_result()
    completions = _SequentialProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(completions)

    with pytest.raises(ValueError, match="answer off-anchor"):
        renderer(result)

    assert len(completions.calls) == 2


def test_openai_prose_renderer_corrects_against_soft_subject_over_lookalike() -> None:
    # The vector lane can mis-anchor a web-only session onto a look-alike
    # canonical entity; an answer naming that wrong anchor must NOT pass the
    # correction check while a soft context subject exists.
    result = _anchored_prose_result(
        anchor_id="company:lookalike-anchor",
        anchor_name="华南先进技术应用研究院",
        soft_context_subject=_ANCHOR_NAME,
    )
    completions = _SequentialProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
        _prose_wire(_ON_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(completions)

    rendered = renderer(result)

    assert isinstance(rendered, ProseSynthesisResult)
    assert rendered.answer_text == _ON_ANSWER
    assert len(completions.calls) == 2
    correction = completions.calls[1]["messages"][-1]
    assert isinstance(correction, dict)
    assert _ANCHOR_NAME in correction["content"]


def test_mentions_anchor_with_qualifier_requires_branch_cooccurrence() -> None:
    assert serving_module._answer_mentions_anchor(
        "国际先进技术应用推进中心（深圳）依托粤港澳大湾区数字经济研究院建设。",
        "国际先进技术应用推进中心（深圳）",
        location_qualifier="深圳",
    )
    # Org mentioned, branch never pinned -> treated as off-anchor.
    assert not serving_module._answer_mentions_anchor(
        "国际先进技术应用推进中心（合肥）采用事业单位企业化运作模式。",
        "国际先进技术应用推进中心（深圳）",
        location_qualifier="深圳",
    )
    # No qualifier -> org-level mention passes (phase-1 behavior).
    assert serving_module._answer_mentions_anchor(
        "国际先进技术应用推进中心（合肥）采用事业单位企业化运作模式。",
        "国际先进技术应用推进中心",
    )


def test_mentions_anchor_qualified_rejects_lookalike_organized_answer() -> None:
    answer = (
        "中国科学院深圳先进技术研究院（简称“深圳先进院”）是深圳市人民政府与中国科学院共建的新型研发机构。"
        "深圳先进院在人才团队方面拥有李成睿、周磊等教授。"
        "该院的合作机构包括国际先进技术应用推进中心等。"
    )
    assert not serving_module._answer_mentions_anchor(
        answer, "国际先进技术应用推进中心（深圳）", location_qualifier="深圳",
    )


def test_mentions_anchor_qualified_accepts_lead_with_stem() -> None:
    assert serving_module._answer_mentions_anchor(
        "国际先进技术应用推进中心（深圳）依托粤港澳大湾区数字经济研究院建设。",
        "国际先进技术应用推进中心（深圳）", location_qualifier="深圳",
    )


def test_mentions_anchor_qualified_accepts_framing_opener_with_repeated_stem() -> None:
    answer = (
        "从公开信息看，这家机构的分量不低。"
        "国际先进技术应用推进中心（深圳）近日揭牌，国际先进技术应用推进中心由国家发改委指导。"
    )
    assert serving_module._answer_mentions_anchor(
        answer, "国际先进技术应用推进中心（深圳）", location_qualifier="深圳",
    )


def test_mentions_anchor_unqualified_path_unchanged() -> None:
    # Phase 3 semantics (G1 T3 form): a single mid-answer name-drop inside a
    # differently-framed answer is the drift signature — it must trigger the
    # correction retry, so it no longer counts as anchored. Leading or
    # recurring mentions still count (see test_answer_anchor_lead.py).
    assert not serving_module._answer_mentions_anchor(
        "从公开信息看，这家机构的分量不低。国际先进技术应用推进中心（合肥）采用理事会模式。",
        "国际先进技术应用推进中心",
    )


def test_correction_message_mentions_branch_when_qualified() -> None:
    msg = serving_module._anchor_correction_message(
        "国际先进技术应用推进中心（深圳）", location_qualifier="深圳",
    )
    assert "深圳" in msg and "不得反问" in msg and "明确归属" in msg


def test_openai_prose_renderer_pins_qualified_anchor_to_its_branch() -> None:
    # The first answer names the org but only its 合肥 branch; with the 深圳
    # qualifier pinned that still counts as off-anchor, so the corrective
    # retry must fire and its message must name the branch.
    result = _anchored_prose_result()
    completions = _SequentialProseCompletions(
        _prose_wire(_HEFEI_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
        _prose_wire(_ON_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(completions)

    rendered = renderer(result)

    assert isinstance(rendered, ProseSynthesisResult)
    assert rendered.answer_text == _ON_ANSWER
    assert len(completions.calls) == 2
    correction = completions.calls[1]["messages"][-1]
    assert isinstance(correction, dict)
    assert "深圳" in correction["content"]


@pytest.mark.parametrize(
    ("anchor_id", "response_mode"),
    (
        ("company:anchor-serving", "clarification_only"),
        ("web-handle:anchor-serving", "answer"),
    ),
    ids=("clarification-only", "web-handle-anchor"),
)
def test_openai_prose_renderer_anchor_check_skips_non_answer_or_web_anchor(
    anchor_id: str,
    response_mode: str,
) -> None:
    result = _anchored_prose_result(
        anchor_id=anchor_id,
        response_mode=response_mode,
    )
    completions = _SequentialProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(completions)

    rendered = renderer(result)

    assert isinstance(rendered, ProseSynthesisResult)
    assert rendered.answer_text == _OFF_ANSWER
    assert len(completions.calls) == 1


def test_openai_prose_renderer_anchor_check_skips_without_active_anchor() -> None:
    result, _, _ = _prose_result()
    completions = _SequentialProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(completions)

    rendered = renderer(result)

    assert isinstance(rendered, ProseSynthesisResult)
    assert rendered.answer_text == _OFF_ANSWER
    assert len(completions.calls) == 1


def test_stream_correction_replaces_final_answer_on_drift() -> None:
    """Off-anchor drift on the stream path is corrected in the FINAL answer.

    Published chunks are irrevocable, so one bounded non-stream retry replaces
    the returned result while the streamed draft stays published; the SSE
    answer event then differs from the draft and the frontend re-renders.

    Replaces the phase-1 pin ``stream never retries off-anchor``: the contract
    is now "single STREAM call; off-anchor adds one bounded non-stream
    correction call"."""
    result = _anchored_prose_result()
    completions = _StreamThenSyncProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
        _prose_wire(_ON_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(completions)
    published: list[str] = []

    rendered = renderer.stream(result, on_chunk=published.append)

    assert isinstance(rendered, ProseSynthesisResult)
    # Correction success marks the result: it supersedes the already-published
    # drifted draft, so the knowledge_answer stream guard exempts the mismatch.
    assert rendered.supersedes_streamed_draft is True
    assert "国际先进技术应用推进中心（深圳）" in (
        serving_module._rendered_prose_answer_text(rendered)
    )
    assert rendered.answer_text == _ON_ANSWER
    # Already-published chunks keep the drifted draft.
    assert "".join(published) == _OFF_ANSWER
    assert completions.stream_create_calls == 1
    assert completions.sync_create_calls == 1  # one corrective retry


def test_stream_correction_failure_returns_original_streamed_answer() -> None:
    """Fail-open: when the corrective retry also misses the anchor, the
    original streamed result stands — no exception, no second retry."""
    result = _anchored_prose_result()
    completions = _StreamThenSyncProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(completions)
    published: list[str] = []

    rendered = renderer.stream(result, on_chunk=published.append)

    assert isinstance(rendered, ProseSynthesisResult)
    # Fail-open keeps the streamed result: never marked as superseding.
    assert rendered.supersedes_streamed_draft is False
    assert "华南先进技术应用研究院" in (
        serving_module._rendered_prose_answer_text(rendered)
    )
    assert rendered.answer_text == _OFF_ANSWER
    assert completions.stream_create_calls == 1
    assert completions.sync_create_calls == 1  # bounded: no further retry


def test_stream_correction_provider_error_keeps_streamed_answer() -> None:
    """Fail-open on provider failure mid-correction: the exception is
    swallowed and the original streamed result is returned."""
    result = _anchored_prose_result()
    completions = _StreamThenSyncProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
        sync_error=RuntimeError("provider boom"),
    )
    renderer = _prose_renderer(completions)
    published: list[str] = []

    rendered = renderer.stream(result, on_chunk=published.append)

    assert isinstance(rendered, ProseSynthesisResult)
    assert rendered.supersedes_streamed_draft is False
    assert rendered.answer_text == _OFF_ANSWER
    assert completions.stream_create_calls == 1
    assert completions.sync_create_calls == 1


def test_stream_on_anchor_single_call() -> None:
    """An on-anchor stream needs no correction: exactly one provider call."""
    result = _anchored_prose_result()
    completions = _StreamThenSyncProseCompletions(
        _prose_wire(_ON_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(completions)
    published: list[str] = []

    rendered = renderer.stream(result, on_chunk=published.append)

    assert isinstance(rendered, ProseSynthesisResult)
    assert rendered.supersedes_streamed_draft is False
    assert rendered.answer_text == _ON_ANSWER
    assert completions.stream_create_calls == 1
    assert completions.sync_create_calls == 0


_REFERENCE_PAGE_TEXT = (
    "国际先进技术应用推进中心（深圳）是依托粤港澳大湾区数字经济研究院建设的机构。" * 40
)
_REFERENCE_URL = "https://www.guojixianjin.cn/about"


def _web_citation(
    *,
    locator: str,
    title: str | None = None,
    snippet: str | None = None,
    source_nature: str = "current_web",
) -> Any:
    citation = SimpleNamespace(
        evidence_id="evidence:reference-material",
        source_nature=source_nature,
        source_locator=locator,
    )
    if title is not None:
        citation.title = title
    if snippet is not None:
        citation.snippet = snippet
    return citation


def test_reference_material_fetched_from_domain_matched_url() -> None:
    fetched: list[str] = []

    def fetcher(url: str) -> str:
        fetched.append(url)
        return _REFERENCE_PAGE_TEXT

    renderer = _prose_renderer(
        _SequentialProseCompletions("unused"), page_fetcher=fetcher,
    )
    result = SimpleNamespace(
        citations=(
            _web_citation(locator="https://example.com/unrelated"),
            _web_citation(locator=_REFERENCE_URL),
        ),
    )

    material = renderer._fetch_anchor_reference_material(
        result=result, anchor_name=_ANCHOR_NAME,
    )

    assert material is not None
    # 1520 fetched chars are truncated to the 1200-char injection budget.
    assert len(material) == 1200
    assert "国际先进技术应用推进中心" in material
    assert fetched == [_REFERENCE_URL]


def test_reference_material_selected_by_title_when_domain_misses() -> None:
    fetched: list[str] = []

    def fetcher(url: str) -> str:
        fetched.append(url)
        return _REFERENCE_PAGE_TEXT

    renderer = _prose_renderer(
        _SequentialProseCompletions("unused"), page_fetcher=fetcher,
    )
    result = SimpleNamespace(
        citations=(
            _web_citation(
                locator="https://example.com/profile",
                title="国际先进技术应用推进中心（深圳）：机构简介",
            ),
        ),
    )

    material = renderer._fetch_anchor_reference_material(
        result=result, anchor_name=_ANCHOR_NAME,
    )

    assert material is not None
    assert fetched == ["https://example.com/profile"]


def test_reference_material_selected_by_snippet_head_when_title_absent() -> None:
    fetched: list[str] = []

    def fetcher(url: str) -> str:
        fetched.append(url)
        return _REFERENCE_PAGE_TEXT

    renderer = _prose_renderer(
        _SequentialProseCompletions("unused"), page_fetcher=fetcher,
    )
    result = SimpleNamespace(
        citations=(
            _web_citation(
                locator="https://example.com/profile",
                snippet="国际先进技术应用推进中心（深圳）：依托数字经济研究院建设",
            ),
        ),
    )

    material = renderer._fetch_anchor_reference_material(
        result=result, anchor_name=_ANCHOR_NAME,
    )

    assert material is not None
    assert fetched == ["https://example.com/profile"]


def test_reference_material_skips_non_current_web_citations() -> None:
    fetched: list[str] = []

    def fetcher(url: str) -> str:
        fetched.append(url)
        return _REFERENCE_PAGE_TEXT

    renderer = _prose_renderer(
        _SequentialProseCompletions("unused"), page_fetcher=fetcher,
    )
    result = SimpleNamespace(
        citations=(
            _web_citation(locator=_REFERENCE_URL, source_nature="local"),
        ),
    )

    material = renderer._fetch_anchor_reference_material(
        result=result, anchor_name=_ANCHOR_NAME,
    )

    assert material is None
    assert fetched == []


def test_reference_material_returns_none_without_fetcher() -> None:
    renderer = _prose_renderer(_SequentialProseCompletions("unused"))
    result = SimpleNamespace(citations=(_web_citation(locator=_REFERENCE_URL),))

    assert (
        renderer._fetch_anchor_reference_material(
            result=result, anchor_name=_ANCHOR_NAME,
        )
        is None
    )


def test_reference_material_returns_none_without_candidate() -> None:
    fetched: list[str] = []

    def fetcher(url: str) -> str:
        fetched.append(url)
        return _REFERENCE_PAGE_TEXT

    renderer = _prose_renderer(
        _SequentialProseCompletions("unused"), page_fetcher=fetcher,
    )
    result = SimpleNamespace(
        citations=(_web_citation(locator="https://example.com/unrelated"),),
    )

    material = renderer._fetch_anchor_reference_material(
        result=result, anchor_name=_ANCHOR_NAME,
    )

    assert material is None
    assert fetched == []


def test_reference_material_rejected_by_anti_echo_guard() -> None:
    def fetcher(url: str) -> str:
        return "中国科学院深圳先进技术研究院简介……" * 50

    renderer = _prose_renderer(
        _SequentialProseCompletions("unused"), page_fetcher=fetcher,
    )
    result = SimpleNamespace(citations=(_web_citation(locator=_REFERENCE_URL),))

    assert (
        renderer._fetch_anchor_reference_material(
            result=result, anchor_name=_ANCHOR_NAME,
        )
        is None
    )


def test_reference_material_fail_open_on_fetch_error() -> None:
    def fetcher(url: str) -> str:
        raise RuntimeError("boom")

    renderer = _prose_renderer(
        _SequentialProseCompletions("unused"), page_fetcher=fetcher,
    )
    result = SimpleNamespace(citations=(_web_citation(locator=_REFERENCE_URL),))

    assert (
        renderer._fetch_anchor_reference_material(
            result=result, anchor_name=_ANCHOR_NAME,
        )
        is None
    )


def test_correction_message_carries_reference_material() -> None:
    result = _anchored_prose_result(
        citations=(_web_citation(locator=_REFERENCE_URL),),
    )
    completions = _SequentialProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
        _prose_wire(_ON_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(
        completions, page_fetcher=lambda url: _REFERENCE_PAGE_TEXT,
    )

    rendered = renderer(result)

    assert isinstance(rendered, ProseSynthesisResult)
    assert rendered.answer_text == _ON_ANSWER
    assert len(completions.calls) == 2
    correction = completions.calls[1]["messages"][-1]
    assert isinstance(correction, dict)
    assert "补充材料" in correction["content"]
    assert "粤港澳大湾区数字经济研究院" in correction["content"]


def test_stream_correction_carries_reference_material() -> None:
    result = _anchored_prose_result(
        citations=(_web_citation(locator=_REFERENCE_URL),),
    )
    completions = _StreamThenSyncProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
        _prose_wire(_ON_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(
        completions, page_fetcher=lambda url: _REFERENCE_PAGE_TEXT,
    )
    published: list[str] = []

    rendered = renderer.stream(result, on_chunk=published.append)

    assert isinstance(rendered, ProseSynthesisResult)
    assert rendered.answer_text == _ON_ANSWER
    assert completions.stream_create_calls == 1
    assert completions.sync_create_calls == 1
    correction = completions.calls[-1]["messages"][-1]
    assert isinstance(correction, dict)
    assert "补充材料" in correction["content"]
    assert "粤港澳大湾区数字经济研究院" in correction["content"]


def test_stream_correction_fetch_error_stays_fail_open() -> None:
    # A failing reference fetch must not escape the stream correction: the
    # retry still runs, just without injected material.
    def fetcher(url: str) -> str:
        raise RuntimeError("boom")

    result = _anchored_prose_result(
        citations=(_web_citation(locator=_REFERENCE_URL),),
    )
    completions = _StreamThenSyncProseCompletions(
        _prose_wire(_OFF_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
        _prose_wire(_ON_ANSWER, claim_indexes=(1,), entity_indexes=(1,)),
    )
    renderer = _prose_renderer(completions, page_fetcher=fetcher)
    published: list[str] = []

    rendered = renderer.stream(result, on_chunk=published.append)

    assert isinstance(rendered, ProseSynthesisResult)
    assert rendered.answer_text == _ON_ANSWER
    assert completions.stream_create_calls == 1
    assert completions.sync_create_calls == 1
    correction = completions.calls[-1]["messages"][-1]
    assert isinstance(correction, dict)
    assert "补充材料" not in correction["content"]


def test_environment_prose_renderer_bounds_the_default_provider_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_calls: list[dict[str, object]] = []
    resolver_calls: list[tuple[str, dict[str, object]]] = []
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
    def resolve_settings(profile: str, **kwargs: object) -> dict[str, str]:
        resolver_calls.append((profile, kwargs))
        return {
            "local_llm_api_key": "test-key",
            "local_llm_model": "qwen3.6-35b-a3b-fp8",
            "local_llm_base_url": "https://llm.example/v1",
        }

    monkeypatch.setattr(
        serving_module,
        "resolve_professor_llm_settings",
        resolve_settings,
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
    assert resolver_calls == [
        ("gemma4", {"apply_endpoint_env_overrides": False})
    ]
    assert result_timeouts == [30.0]
    assert client_calls == [
        {
            "base_url": "https://llm.example/v1",
            "api_key": "test-key",
            "timeout": 30.0,
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
        lambda _profile, **_: {
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
    assert [call["max_tokens"] for call in completion_calls] == [6000, 1, 6000]


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
        prose_renderer=_timeout_prose_renderer,
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

    # Timeout degradation keeps the relevant current-web claim and excludes
    # the similarly named vector neighbor from the public answer.  The
    # fallback text no longer embeds the source locator for non-link
    # questions (that raw-dump shape was the T15 defect); traceability is
    # preserved through the structured citation instead.
    assert result.render_mode == "deterministic_fallback"
    assert "王学谦" in result.answer_text
    assert "https://example.test/wang-xueqian" not in result.answer_text
    assert "王学锋" not in result.answer_text
    assert tuple(citation.source_nature for citation in result.citations) == (
        "current_web",
    )
    assert result.citations[0].source_locator == "https://example.test/wang-xueqian"


def test_explicit_link_gap_keeps_current_web_url_with_exact_local_evidence(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
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

    # Timeout degradation keeps both the exact local title and its verified
    # current-web link in the server-owned grounded answer.
    assert result.render_mode == "deterministic_fallback"
    assert title in result.answer_text
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
        prose_renderer=_timeout_prose_renderer,
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

    # Timeout degradation preserves the exact paper and its summary while
    # excluding the unrelated vector neighbor from the public answer.
    assert result.render_mode == "deterministic_fallback"
    assert title in result.answer_text
    assert "Diffusion-based aggregation" in result.answer_text
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
        prose_renderer=_timeout_prose_renderer,
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


@pytest.mark.parametrize(
    "query",
    (
        "他有哪些代表性研究成果",
        "他的论文有哪些",
        "她还有哪些科研成果",
        "他的代表作是什么",
    ),
)
def test_serving_planner_traverses_professor_papers_for_research_followups(
    tmp_path: Path,
    query: str,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
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
        request_id="query-request:professor-research-output-follow-up",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
        displayed_entity_ids=("professor-c-ding-wenbo",),
        displayed_entity_names=("丁文伯",),
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
    ) == (
        "professor_authored_paper",
        "professor_to_paper",
        "professor",
        "paper",
    )


def test_serving_planner_does_not_traverse_for_plain_profile_followups(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
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
        request_id="query-request:professor-profile-follow-up",
        release_id=RELEASE_ID,
        original_query="他的研究方向是什么",
        as_of=NOW,
        displayed_entity_ids=("professor-c-ding-wenbo",),
        displayed_entity_names=("丁文伯",),
    )

    proposal = inputs.proposal_provider(request)

    assert proposal.relationship_paths == ()
    assert "relationship" not in proposal.lanes


@pytest.mark.parametrize(
    ("query", "displayed_entity_id", "expected_path"),
    (
        ("这论文的链接是什么", "paper-c-pfedgpa", None),
        (
            "这论文的作者是谁",
            "paper-c-pfedgpa",
            (
                "professor_authored_paper",
                "paper_to_professor",
                "paper",
                "professor",
            ),
        ),
        (
            "它的申请公司是哪个",
            "patent-p-cn117873146a",
            (
                "company_has_patent",
                "patent_to_company",
                "patent",
                "company",
            ),
        ),
        (
            "它的专利有哪些",
            "company-c-ubtech",
            (
                "company_has_patent",
                "company_to_patent",
                "company",
                "patent",
            ),
        ),
        (
            "上述公司的专利有哪些",
            "company-c-ubtech",
            (
                "company_has_patent",
                "company_to_patent",
                "company",
                "patent",
            ),
        ),
        (
            "深圳市普渡科技有限公司有哪些专利",
            "company-c-pudu",
            (
                "company_has_patent",
                "company_to_patent",
                "company",
                "patent",
            ),
        ),
        ("其他公司的专利有哪些", "company-c-ubtech", None),
        ("他有哪些专利", "professor-c-ding-wenbo", None),
        ("这篇论文有哪些专利引用", "paper-c-pfedgpa", None),
    ),
)
def test_serving_planner_binds_traversal_to_the_anchor_domain(
    tmp_path: Path,
    query: str,
    displayed_entity_id: str,
    expected_path: tuple[str, str, str, str] | None,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
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
        request_id=f"query-request:domain-bound:{displayed_entity_id}",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
        displayed_entity_ids=(displayed_entity_id,),
    )

    proposal = inputs.proposal_provider(request)

    if expected_path is None:
        assert proposal.relationship_paths == ()
        assert "relationship" not in proposal.lanes
        return
    assert proposal.lanes == ("relationship", "web")
    assert len(proposal.relationship_paths) == 1
    relationship_path = proposal.relationship_paths[0]
    assert (
        relationship_path.relationship_type_id,
        relationship_path.direction,
        relationship_path.source_type,
        relationship_path.target_type,
    ) == expected_path


def test_serving_bundle_rejects_hash_or_candidate_crosswire(tmp_path: Path) -> None:
    path, bundle = _write_bundle(tmp_path)

    with pytest.raises(ValueError, match="hash"):
        load_recorded_serving_inputs(
            prose_renderer=_timeout_prose_renderer,
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
            prose_renderer=_timeout_prose_renderer,
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
        prose_renderer=_timeout_prose_renderer,
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
        prose_renderer=_timeout_prose_renderer,
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
        prose_renderer=_timeout_prose_renderer,
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
        prose_renderer=_timeout_prose_renderer,
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
    # Web-lane resilience contract (add-turn-trace-observability 1.3): the
    # lane transport is constructed once and reused across requests, and
    # keepwarm now routes through the SAME lane transport (gated by the
    # quota watermark + breaker) — warming a separate transport burned quota
    # on connections the serving lane never used.
    assert observed["provider_constructions"] == 1
    assert observed["query"] == "王学谦"
    kwargs = observed["kwargs"]
    assert isinstance(kwargs, dict)
    # Per-provider attempt budgets (fix-web-lane-timeout-and-utf8-truncation):
    # the observed transport is Serper, whose floor is 4.0 s — the old shared
    # 0.675 s sat below Serper's measured 1.7–2.8 s latency and starved it.
    assert kwargs == {"timeout": 4.0}


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


@pytest.mark.parametrize(
    ("original_query", "official_snippet", "expected_predicate"),
    (
        (
            "上述企业里总部在深圳的企业有哪些",
            "普渡机器人的全球總部位于深圳。",
            "headquarters_city",
        ),
        (
            "酒店电梯需要送餐机器人能够使用机械臂自主按电梯，上述企业的产品有哪些可以实现",
            "FlashBot Arm通过机械臂和灵巧手自主按电梯。",
            "product_capability_evidence",
        ),
    ),
)
def test_dual_web_lane_prioritizes_relation_evidence_before_candidate_cap(
    original_query: str,
    official_snippet: str,
    expected_predicate: str,
) -> None:
    class _Provider:
        def __init__(self, prefix: str, count: int, *, official_at: int | None) -> None:
            self._prefix = prefix
            self._count = count
            self._official_at = official_at

        def search(self, query: str) -> dict[str, object]:
            # Controller amendment (three-tier gate): the phase-2 gate classifies
            # loose-alias-only evidence as T4 and backfills to FLOOR=3 when no
            # T0/T1 exists, so this fixture's old all-distinct URLs collapsed to
            # 3 survivors and cut the official evidence before prioritization.
            # Industry items now share provider-independent URLs, so overlapping
            # ranks corroborate (T0) and six results survive the gate; the
            # official title carries the full-name form 普渡科技 (T2), keeping
            # the official page behind five survivors pre-prioritization so the
            # candidate cap would still cut it without relation prioritization.
            return {
                "organic": [
                    {
                        "title": (
                            "普渡科技官方资料"
                            if index == self._official_at
                            else f"普渡行业资讯 {self._prefix}-{index}"
                        ),
                        "link": (
                            "https://www.pudurobotics.com/official-evidence"
                            if index == self._official_at
                            else f"https://pudu-news.example/{index}"
                        ),
                        "snippet": (
                            official_snippet
                            if index == self._official_at
                            else "普渡科技提供酒店服务机器人。"
                        ),
                    }
                    for index in range(self._count)
                ]
            }

    adapter = serving_module._DualWebLaneAdapter(
        bocha=_Provider("bocha", 5, official_at=None),
        serper=_Provider("serper", 5, official_at=4),
        timeout_ms=1500,
        max_snapshot_bytes=16384,
        clock=lambda: NOW,
    )
    result = adapter(
        LaneRequest(
            lane="web",
            release_id=RELEASE_ID,
            query_view="view:relation-evidence-priority",
            original_query=original_query,
            behavior_class="A",
            interaction_mode="information_retrieval",
            web_policy=WebSearchPolicy(
                mode="universal",
                max_provider_calls=2,
                timeout_ms=1500,
                max_results=5,
            ),
            query_text="深圳市普渡科技有限公司 机器人 [lane=web]",
            domains=("company",),
            protected_slots=(),
            structured_constraints=StructuredConstraints(),
            max_candidates=5,
            bound_entity_ids=("company-c-pudu",),
            bound_entity_names=("深圳市普渡科技有限公司",),
        )
    )

    first_evidence = result.candidates[0].evidence[0]
    assert len(result.candidates) == 5
    assert first_evidence.source_locator == (
        "https://www.pudurobotics.com/official-evidence"
    )
    assert first_evidence.claim_binding is not None
    assert first_evidence.claim_binding.predicate == expected_predicate


def test_dual_web_lane_diversifies_legal_company_name_query() -> None:
    observed: dict[str, str] = {}

    class _Provider:
        def __init__(self, name: str) -> None:
            self._name = name

        def search(self, query: str) -> dict[str, object]:
            observed[self._name] = query
            return {"organic": []}

    adapter = serving_module._DualWebLaneAdapter(
        bocha=_Provider("bocha"),
        serper=_Provider("serper"),
        timeout_ms=1500,
        max_snapshot_bytes=16384,
        clock=lambda: NOW,
    )
    query = "深圳市普渡科技有限公司 产品 酒店机器人 机械臂 自主按电梯"

    adapter._merged_results(query)

    assert observed["bocha"] == query
    assert observed["serper"] == "普渡 产品 酒店机器人 机械臂 自主按电梯"

    displayed_set_query = (
        '("云迹科技股份有限公司" OR "深圳市普渡科技有限公司") '
        "产品 酒店机器人 机械臂 自主按电梯"
    )
    adapter._merged_results(displayed_set_query)

    assert observed["bocha"] == displayed_set_query
    assert observed["serper"] == "(云迹 OR 普渡) 产品 酒店机器人 机械臂 自主按电梯"


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


def test_dual_web_lane_orders_corroborated_results_before_single_channel() -> None:
    class _Provider:
        def search(self, query: str) -> dict[str, object]:
            return {"organic": []}

    adapter = serving_module._DualWebLaneAdapter(
        bocha=_Provider(),
        serper=_Provider(),
        timeout_ms=1500,
        max_snapshot_bytes=16384,
        clock=lambda: NOW,
    )

    ordered = adapter._normalize_and_order_results(
        provider_results={
            "bocha-v1": [
                {
                    "title": "bocha 独有结果",
                    "link": "https://bocha-only.example/1",
                    "snippet": "仅 bocha 命中。",
                },
                {
                    "title": "双通道印证结果",
                    "link": "https://shared.example/page/",
                    "snippet": "bocha 侧摘要。",
                },
            ],
            "serper-v1": [
                {
                    "title": "serper 独有结果",
                    "link": "https://serper-only.example/1",
                    "snippet": "仅 serper 命中。",
                },
                {
                    "title": "双通道印证结果",
                    "link": "https://shared.example/page",
                    "snippet": "serper 侧摘要。",
                },
            ],
        }
    )

    assert tuple(item.title for item in ordered) == (
        "双通道印证结果",
        "bocha 独有结果",
        "serper 独有结果",
    )
    assert ordered[0].corroborating_provider_versions == ("bocha-v1", "serper-v1")


def _subject_consistency_request(**overrides: object) -> LaneRequest:
    values: dict[str, object] = {
        "lane": "web",
        "release_id": RELEASE_ID,
        "query_view": "view:subject-consistency",
        "original_query": "介绍深圳理工大学",
        "behavior_class": "A",
        "interaction_mode": "information_retrieval",
        "web_policy": WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=1500,
            max_results=5,
        ),
        "query_text": "深圳理工大学 [lane=web]",
        "domains": ("company",),
        "protected_slots": (),
        "structured_constraints": StructuredConstraints(),
        "max_candidates": 5,
        "bound_entity_ids": ("company-c-sut",),
        "bound_entity_names": ("深圳理工大学",),
    }
    values.update(overrides)
    return LaneRequest(**values)  # type: ignore[arg-type]


def _subject_consistency_adapter(
    bocha_payload: dict[str, object],
    serper_payload: dict[str, object],
) -> Any:
    class _Provider:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def search(self, query: str) -> dict[str, object]:
            return self._payload

    return serving_module._DualWebLaneAdapter(
        bocha=_Provider(bocha_payload),
        serper=_Provider(serper_payload),
        timeout_ms=1500,
        max_snapshot_bytes=16384,
        clock=lambda: NOW,
    )


def _sut_hit(title: str, url: str) -> dict[str, object]:
    return {
        "title": title,
        "link": url,
        "snippet": "深圳理工大学位于广东深圳的公办研究型大学。",
    }


def _siat_miss(title: str, url: str) -> dict[str, object]:
    return {
        "title": title,
        "link": url,
        "snippet": "中国科学院深圳先进技术研究院的最新动态。",
    }


def test_dual_web_lane_drops_off_subject_results_once_floor_is_met() -> None:
    shared_url = "https://off-topic.example/shared"
    adapter = _subject_consistency_adapter(
        {
            "organic": [
                _siat_miss("中国科学院深圳先进技术研究院", "https://siat.example/a"),
                _siat_miss("先进技术研究院招生", shared_url),
            ]
        },
        {
            "organic": [
                _sut_hit("深圳理工大学官网", "https://sut.example/1"),
                _sut_hit("深圳理工大学招生网", "https://sut.example/2"),
                _siat_miss("先进技术研究院招生", shared_url),
            ]
        },
    )

    result = adapter(_subject_consistency_request())

    locators = tuple(
        candidate.evidence[0].source_locator for candidate in result.candidates
    )
    assert len(locators) == 3
    assert "https://siat.example/a" not in locators
    # The off-subject URL both providers returned stays: dual-channel
    # corroboration counts as a keep signal even without a subject hit.
    assert shared_url in locators
    assert set(locators) == {
        shared_url,
        "https://sut.example/1",
        "https://sut.example/2",
    }


def test_dual_web_lane_backfills_off_subject_results_to_reach_floor() -> None:
    adapter = _subject_consistency_adapter(
        {
            "organic": [
                _siat_miss("中国科学院深圳先进技术研究院", "https://siat.example/1"),
                _siat_miss("先进技术研究院招生", "https://siat.example/2"),
                _siat_miss("先进技术研究院招聘", "https://siat.example/3"),
            ]
        },
        {"organic": [_sut_hit("深圳理工大学官网", "https://sut.example/1")]},
    )

    result = adapter(_subject_consistency_request())

    locators = tuple(
        candidate.evidence[0].source_locator for candidate in result.candidates
    )
    # kept (1 subject hit) < FLOOR (3): demoted results backfill in their
    # original order instead of leaving the lane empty.
    assert locators == (
        "https://sut.example/1",
        "https://siat.example/1",
        "https://siat.example/2",
    )


def test_dual_web_lane_without_bound_entities_keeps_round_robin_order() -> None:
    adapter = _subject_consistency_adapter(
        {
            "organic": [
                _sut_hit("结果 A", "https://a.example/1"),
                _sut_hit("结果 B", "https://b.example/1"),
            ]
        },
        {
            "organic": [
                _sut_hit("结果 C", "https://c.example/1"),
                _sut_hit("结果 D", "https://d.example/1"),
            ]
        },
    )

    result = adapter(
        _subject_consistency_request(bound_entity_ids=(), bound_entity_names=())
    )

    assert tuple(
        candidate.evidence[0].source_locator for candidate in result.candidates
    ) == (
        "https://a.example/1",
        "https://c.example/1",
        "https://b.example/1",
        "https://d.example/1",
    )


def test_web_bound_entity_match_ignores_shared_fragment_substrings() -> None:
    bound = ("国际先进技术应用推进中心（深圳）",)

    assert not serving_module._web_result_hits_bound_entity(
        bound_entity_names=bound,
        title="中国科学院深圳先进技术研究院",
        snippet="中国科学院深圳先进技术研究院在先进技术领域取得进展。",
    )
    assert serving_module._web_result_hits_bound_entity(
        bound_entity_names=bound,
        title="国际先进技术应用推进中心（深圳）",
        snippet="国际先进技术应用推进中心（深圳）最新动态。",
    )


_ANCHOR = "国际先进技术应用推进中心（深圳）"


def _result(
    title: str,
    snippet: str = "",
    url: str = "https://example.com/a",
    providers: tuple[str, ...] = ("bocha",),
) -> serving_module._NormalizedWebResult:
    return serving_module._NormalizedWebResult(
        title=title,
        url=url,
        snippet=snippet,
        summary="",
        primary_provider_version=providers[0],
        corroborating_provider_versions=providers,
    )


def test_tier_t1_branch_qualified_hit() -> None:
    r = _result("国际先进技术应用推进中心（深圳）揭牌", "河套深港科技创新合作区")
    assert (
        serving_module._web_result_relevance_tier(
            result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳"
        )
        == 1
    )


def test_tier_t2_same_org_unqualified() -> None:
    r = _result("国际先进技术应用推进中心是由国家发展改革委指导的综合性技术应用机构")
    assert (
        serving_module._web_result_relevance_tier(
            result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳"
        )
        == 2
    )


def test_tier_t3_other_branch_content() -> None:
    # Controller amendment: the brief's verbatim fixture used the 国先中心
    # abbreviation, which matches no identity form; the full stem is required
    # for the T3 branch to fire.
    r = _result("国际先进技术应用推进中心（合肥）执行主任程羽强调推动机器人真实应用")
    assert (
        serving_module._web_result_relevance_tier(
            result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳"
        )
        == 3
    )


def test_tier_t4_loose_alias_only() -> None:
    # 南开国际先进研究院 shares the compact alias 国际先进 but not the org stem.
    r = _result("南开国际先进研究院（深圳福田）在实验室参观交流中")
    assert (
        serving_module._web_result_relevance_tier(
            result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳"
        )
        == 4
    )


def test_tier_t0_corroborated_trumps_everything() -> None:
    r = _result("完全无关的标题", providers=("bocha", "serper"))
    assert (
        serving_module._web_result_relevance_tier(
            result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳"
        )
        == 0
    )


def test_tier_t5_no_match() -> None:
    # Controller amendment: the brief's verbatim title was
    # 两台国际先进水平手术的背后, but 国际先进水平 contains the compact alias
    # 国际先进, which classifies T4 by design; a T5 fixture must avoid it.
    r = _result("两台腹腔镜手术的背后", "华西口腔医院")
    assert (
        serving_module._web_result_relevance_tier(
            result=r, bound_entity_names=(_ANCHOR,), anchor_qualifier="深圳"
        )
        == 5
    )


def test_company_truncation_stays_full_name_form() -> None:
    forms = serving_module._web_identity_full_name_forms("深圳市普渡科技有限公司")
    assert any("普渡科技" in f for f in forms)
    assert (
        serving_module._web_result_relevance_tier(
            result=_result("普渡科技完成Pre-D轮融资"),
            bound_entity_names=("深圳市普渡科技有限公司",),
            anchor_qualifier=None,
        )
        == 2
    )


def test_anchor_location_qualifier_from_parens_and_query() -> None:
    assert serving_module._anchor_location_qualifier(_ANCHOR, "介绍一下") == "深圳"
    assert (
        serving_module._anchor_location_qualifier(
            "国际先进技术应用推进中心", "国际先进技术应用推进中心在深圳的布局"
        )
        == "深圳"
    )
    assert (
        serving_module._anchor_location_qualifier("国际先进技术应用推进中心", "介绍一下")
        is None
    )


def test_anchor_location_qualifier_ignores_city_inside_legal_name_stem() -> None:
    """A city that is part of the legal name stem itself (深圳市普渡科技
    有限公司) must not qualify the anchor: the lexicon scan runs on the query
    residual outside the stem, not on the full query. Legitimate co-occurrence
    outside the stem still qualifies."""
    assert (
        serving_module._anchor_location_qualifier(
            "深圳市普渡科技有限公司", "介绍一下深圳市普渡科技有限公司"
        )
        is None
    )
    assert (
        serving_module._anchor_location_qualifier(
            "深圳市普渡科技有限公司", "深圳市普渡科技有限公司在北京的布局"
        )
        == "北京"
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ("国际先进技术应用推进中心在深圳和广州的布局", "深圳"),
        ("国际先进技术应用推进中心在广州和深圳的布局", "广州"),
    ),
)
def test_anchor_location_qualifier_returns_earliest_residual_location(
    query: str,
    expected: str,
) -> None:
    """Multiple co-occurring locations resolve deterministically to the
    earliest one in the query residual — frozenset iteration order is a hash
    randomization artifact and must not decide the qualifier."""
    assert (
        serving_module._anchor_location_qualifier("国际先进技术应用推进中心", query)
        == expected
    )


def test_anchor_location_lexicon_members_stay_normalized() -> None:
    """Every lexicon member is invariant under _normalized_web_identity, so
    the verbatim member returned by the scan needs no normalize-at-return."""
    assert serving_module._ANCHOR_LOCATION_LEXICON
    assert all(
        serving_module._normalized_web_identity(location) == location
        for location in serving_module._ANCHOR_LOCATION_LEXICON
    )


def test_evidence_branch_qualifiers_excludes_anchor_and_non_locations() -> None:
    texts = (
        "国际先进技术应用推进中心（合肥）成立理事会",
        "国先中心（深圳）揭牌",
        "国际先进技术应用推进中心（大湾区）中心在广州南沙设立",
    )
    assert serving_module._evidence_branch_qualifiers(
        org_stem=serving_module._org_name_stem(_ANCHOR),
        texts=texts,
        anchor_qualifier="深圳",
    ) == ("合肥", "大湾区")


def _branch_evidence_result(
    *,
    query: str = "介绍一下国际先进技术应用推进中心",
    soft_context_subject: str | None = None,
    anchor_name: str = "国际先进技术应用推进中心",
    claim_texts: tuple[str, ...] = (
        "国际先进技术应用推进中心（合肥）成立理事会，聚焦长三角成果转化。",
        "国际先进技术应用推进中心（大湾区）中心在广州南沙设立。",
    ),
) -> Any:
    claims = tuple(
        SimpleNamespace(
            claim_id=f"claim:branch:{index}",
            text=text,
            subject_id="company:branch-anchor",
            subject_handle_ids=("company:branch-anchor",),
            predicate="current_web_result",
            status="accepted",
            source_natures=("current_web",),
            evidence_ids=(),
        )
        for index, text in enumerate(claim_texts, start=1)
    )
    return SimpleNamespace(
        original_query=query,
        response_mode="answer",
        claims=claims,
        citations=(),
        context_receipt=SimpleNamespace(
            active_anchor=SimpleNamespace(
                display_name=anchor_name,
                domain="company",
                canonical_id="company:branch-anchor",
                evidence_ids=(),
            ),
            displayed_result_set=None,
            traversed_path_ids=(),
            soft_context_subject=soft_context_subject,
        ),
    )


def test_multi_branch_guidance_injected_with_detected_branches() -> None:
    result = _branch_evidence_result(
        soft_context_subject="国际先进技术应用推进中心",
    )

    block = serving_module._multi_branch_context_for_result(result)

    assert block is not None
    assert "合肥" in block and "大湾区" in block
    assert "不得拒答" in block or "不得反问" in block
    assert "引导" in block or "注明" in block or "城市" in block


def test_multi_branch_guidance_absent_without_branch_evidence() -> None:
    result = _branch_evidence_result(
        claim_texts=("国际先进技术应用推进中心是国家级共性技术服务平台。",),
    )

    assert serving_module._multi_branch_context_for_result(result) is None


def test_multi_branch_guidance_absent_when_user_named_a_city() -> None:
    # The query pins 深圳, so qualifier pinning owns this turn; no guidance.
    result = _branch_evidence_result(
        query="介绍一下国际先进技术应用推进中心在深圳的布局",
    )

    assert serving_module._multi_branch_context_for_result(result) is None


def test_multi_branch_guidance_chat_request_appends_block_and_bumps_version() -> None:
    result = _branch_evidence_result()
    renderer = serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(chat=SimpleNamespace(completions=None)),
        model="recorded-chat-model",
        extra_body={"thinking": {"type": "disabled"}},
    )

    messages, *_ = renderer._chat_request(result)

    system = messages[0]["content"]
    assert "情境说明" in system
    assert "合肥" in system and "大湾区" in system
    assert '"prompt_version": "canonical-v2-prose-v16"' in messages[-1]["content"]


def _gate(
    results: list[serving_module._NormalizedWebResult],
    *,
    bound: tuple[str, ...] = (_ANCHOR,),
    soft: str | None = None,
) -> tuple[serving_module._NormalizedWebResult, ...]:
    request = _subject_consistency_request(
        bound_entity_names=bound,
        soft_context_subject=soft,
    )
    return serving_module._apply_web_subject_consistency(
        results=tuple(results),
        request=request,
    )


def test_gate_drops_loose_alias_and_miss_when_kept_meets_floor() -> None:
    results = [
        _result("国际先进技术应用推进中心（深圳）揭牌"),  # T1
        _result(
            "河套深圳园区打造深港科技创新聚集地", providers=("bocha", "serper")
        ),  # T0
        _result("国际先进技术应用推进中心（合肥）理事会扩容"),  # T3
        _result("南开国际先进研究院（深圳福田）在实验室参观交流中"),  # T4
        # Controller amendment: the brief labeled this T5, but 国际先进水平
        # contains the compact alias 国际先进, so it classifies T4 by design
        # (same amendment as test_tier_t5_no_match); T4/T5 both drop here.
        _result("两台国际先进水平手术的背后"),  # T4
        _result("国际先进技术应用推进中心是由国家发展改革委指导的机构"),  # T2
        # Controller amendment: the brief's verbatim fixture yielded only two
        # kept (T0∪T1) results — below the floor this test's name asserts —
        # so backfill would drop the T3 fixture its assertions require; one
        # additional T1 result makes kept meet FLOOR as intended.
        _result("国际先进技术应用推进中心（深圳）召开第一届理事会会议"),  # T1
    ]
    out = _gate(results)
    titles = [r.title for r in out]
    assert "南开国际先进研究院（深圳福田）在实验室参观交流中" not in titles  # T4 dropped
    assert "两台国际先进水平手术的背后" not in titles  # T4 dropped
    assert titles.index("国际先进技术应用推进中心（合肥）理事会扩容") > titles.index(
        "国际先进技术应用推进中心是由国家发展改革委指导的机构"
    )  # T2 before T3
    assert set(titles[:2]) == {
        "国际先进技术应用推进中心（深圳）揭牌",
        "河套深圳园区打造深港科技创新聚集地",
    }  # T0∪T1 first


def test_gate_backfills_in_tier_order_below_floor() -> None:
    results = [
        _result("国际先进技术应用推进中心（深圳）揭牌"),  # T1 only, kept=1
        _result("国际先进技术应用推进中心（合肥）理事会扩容"),  # T3
        _result("国际先进技术应用推进中心由发改委指导"),  # T2
        _result("南开国际先进研究院（深圳福田）"),  # T4
        _result("完全无关"),  # T5
    ]
    out = [r.title for r in _gate(results)]
    assert out == [
        "国际先进技术应用推进中心（深圳）揭牌",
        "国际先进技术应用推进中心由发改委指导",
        "国际先进技术应用推进中心（合肥）理事会扩容",
    ]  # backfilled to FLOOR=3 in T2→T3 order; T4/T5 dropped


def test_gate_soft_subject_still_binds_and_qualifier_comes_from_soft_name() -> None:
    # Web-only path: no canonical bound names, soft subject carries （深圳）.
    results = [
        _result("南开国际先进研究院（深圳福田）"),  # T4 for the soft anchor
        _result(
            "国际先进技术应用推进中心（深圳）依托粤港澳大湾区数字经济研究院建设"
        ),  # T1
        _result("国际先进技术应用推进中心（合肥）"),  # T3
        _result("河套揭牌新闻", providers=("bocha", "serper")),  # T0
    ]
    out = [r.title for r in _gate(results, bound=(), soft=_ANCHOR)]
    assert "南开国际先进研究院（深圳福田）" not in out
    assert len(out) == 3


def test_gate_without_bound_names_is_passthrough() -> None:
    results = [_result("a"), _result("b", providers=("bocha", "serper"))]
    assert list(_gate(results, bound=(), soft=None)) == results


def test_dual_web_lane_subject_consistency_binds_soft_context_subject() -> None:
    adapter = _subject_consistency_adapter(
        {
            "organic": [
                _siat_miss("中国科学院深圳先进技术研究院", "https://siat.example/a"),
                _siat_miss("先进技术研究院招生", "https://siat.example/b"),
            ]
        },
        {
            "organic": [
                _sut_hit("深圳理工大学官网", "https://sut.example/1"),
                _sut_hit("深圳理工大学招生网", "https://sut.example/2"),
                _sut_hit("深圳理工大学新闻网", "https://sut.example/3"),
            ]
        },
    )

    result = adapter(
        _subject_consistency_request(
            bound_entity_ids=(),
            bound_entity_names=(),
            soft_context_subject="深圳理工大学",
        )
    )

    locators = tuple(
        candidate.evidence[0].source_locator for candidate in result.candidates
    )
    assert len(locators) == 3
    assert set(locators) == {
        "https://sut.example/1",
        "https://sut.example/2",
        "https://sut.example/3",
    }
    # The soft subject never enters _matched_bound_entity: no candidate may be
    # anchored onto a canonical entity it merely resembles.
    assert all(candidate.canonical_id is None for candidate in result.candidates)
    assert all(
        candidate.identity_kind == "web_only" for candidate in result.candidates
    )


def test_soft_context_subject_reaches_the_web_lane_request(tmp_path: Path) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
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
    ).plan(
        QueryPlanningRequest(
            request_id="query-request:soft-context-lane-request",
            release_id=RELEASE_ID,
            original_query="有没有更详细的信息",
            as_of=NOW,
            soft_context_subject="优必选",
        )
    )

    lane_request = _lane_request(plan, "web", inputs.universal_web_policy)

    assert lane_request.soft_context_subject == "优必选"
    # The soft subject rides its own field: bound names/ids stay aligned to
    # displayed canonical entities (empty here), so _matched_bound_entity can
    # never anchor the soft subject onto a look-alike canonical entity.
    assert lane_request.bound_entity_names == ()
    assert lane_request.bound_entity_ids == ()


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


def test_contextual_web_query_binds_display_name_and_headquarters_relation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    observed: dict[str, list[str]] = {"queries": []}

    class _Provider:
        def __init__(self, **_: object) -> None:
            pass

        def search(self, query: str) -> dict[str, object]:
            observed["queries"].append(query)
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
        prose_renderer=_timeout_prose_renderer,
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

    # The displayed company is an org-level anchor (its name is not in the
    # follow-up query), so the web lane also fires the two authority-seeking
    # views (spec §2c) after the deterministic view query; view calls run
    # concurrently, so order is not asserted.
    assert set(observed["queries"]) == {
        "普渡 总部 深圳",
        "普渡 百度百科",
        "普渡 官网",
    }
    assert all("[lane=web]" not in query for query in observed["queries"])
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.canonical_id == company_id
    assert candidate.identity_kind == "web_candidate"
    assert candidate.resolution_state == "resolved"
    assert candidate.evidence[0].claim_binding is not None
    assert candidate.evidence[0].claim_binding.predicate == "headquarters_city"
    assert candidate.evidence[0].claim_binding.value == "深圳"


@pytest.mark.parametrize(
    ("query", "expected_predicate", "expected_values", "expected_logic"),
    (
        ("上述企业里总部在深圳的有哪些", "headquarters_city", ("深圳",), "all"),
        ("上述企业注册地址在深圳的有哪些", "registered_address", ("深圳",), "all"),
        ("上述企业在深圳设有办公室的有哪些", "office_city", ("深圳",), "all"),
        (
            "上述企业的产品哪些支持自主刷卡和开门",
            "product_capability",
            ("刷门禁", "开门"),
            "all",
        ),
        (
            "上述企业的产品哪些支持刷卡或开门",
            "product_capability",
            ("刷门禁", "开门"),
            "any",
        ),
    ),
)
def test_question_frame_preserves_relation_and_constraint_logic(
    query: str,
    expected_predicate: str,
    expected_values: tuple[str, ...],
    expected_logic: str,
) -> None:
    frame = serving_module._question_frame(query)

    assert frame.predicate == expected_predicate
    assert frame.requested_values == expected_values
    assert frame.logic == expected_logic


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ("上述企业里总部在深圳的有哪些", "总部 深圳"),
        ("上述企业注册地址在深圳的有哪些", "注册地址 深圳"),
        ("上述企业在深圳设有办公室的有哪些", "办公室 深圳"),
        ("上述企业在深圳有分公司的有哪些", "分公司 深圳"),
        (
            "上述企业的产品哪些支持自主刷卡和开门",
            "机器人 自主刷门禁 开门",
        ),
        (
            "酒店电梯需要送餐机器人使用机械臂自主按电梯，上述企业的产品有哪些可以实现",
            "机器人 机械臂 自主按电梯",
        ),
        ("他有哪些代表性研究成果", "代表性研究成果"),
        ("他的公司简介", "公司简介"),
    ),
)
def test_contextual_web_search_view_uses_relation_terms_not_conversation_scaffolding(
    query: str,
    expected: str,
) -> None:
    assert serving_module._contextual_web_search_view(query) == expected


@pytest.mark.parametrize(
    ("snippet", "expected_predicate", "expected_value"),
    (
        ("普渡机器人的全球总部位于广东深圳。", "headquarters_city", "深圳"),
        (
            "1. 全球總部. 深圳. 3. 研發中心. 深圳、成都、香港.",
            "headquarters_city",
            "深圳",
        ),
        (
            "云迹科技总部位于北京，并在深圳设有分公司。",
            "headquarters_city",
            "北京",
        ),
        (
            "云迹科技在深圳为酒店提供机器人服务。",
            "current_web_result",
            None,
        ),
        (
            "深圳市普渡科技有限公司发布了新一代配送机器人。",
            "current_web_result",
            None,
        ),
    ),
)
def test_headquarters_evidence_requires_an_explicit_headquarters_statement(
    snippet: str,
    expected_predicate: str,
    expected_value: str | None,
) -> None:
    frame = serving_module._question_frame("上述企业里总部在深圳的有哪些")

    predicate, value = serving_module._web_claim_semantics(
        frame=frame,
        title="企业官方信息",
        snippet=snippet,
        fallback_value="snapshot-hash",
    )

    assert predicate == expected_predicate
    assert value == (expected_value or "snapshot-hash")


def test_product_capability_evidence_normalizes_official_traditional_chinese() -> None:
    frame = serving_module._question_frame(
        "上述企业的产品哪些支持自主刷卡和开门"
    )

    predicate, value = serving_module._web_claim_semantics(
        frame=frame,
        title="產品 - 普渡",
        snippet="輕鬆按電梯按鈕、刷門禁卡並用雙手開門，無需改造場地。",
        fallback_value="snapshot-hash",
    )

    assert predicate == "product_capability_evidence"
    assert value == "刷门禁 + 开门"


def test_final_llm_selection_commits_only_answer_entities(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    forwarded: list[str] = []
    observed_before_final: list[bool] = []
    provider_finished = False
    deltas = (
        f"{_PROSE_SELECTION_MARKER}\n"
        '{"selected_claim_indexes":[1,2],"selected_entity_indexes":[1]}\n'
        f"{_PROSE_ANSWER_MARKER}\n总部",
        "在深圳的只有深圳市普渡科技有限公司。",
    )

    class _Completions:
        def create(self, **kwargs: object) -> object:
            calls.append(kwargs)

            def completion() -> object:
                nonlocal provider_finished
                for index, delta in enumerate(deltas):
                    yield SimpleNamespace(
                        choices=(SimpleNamespace(delta=SimpleNamespace(content=delta)),)
                    )
                    if index == 0:
                        assert "".join(forwarded) == "总部"
                        assert provider_finished is False
                provider_finished = True

            return completion()

    path, bundle = _write_bundle(tmp_path)
    renderer = serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(chat=SimpleNamespace(completions=_Completions())),
        model="recorded-chat-model",
        extra_body={"thinking": {"type": "disabled"}},
    )
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        prose_renderer=renderer,
        clock=lambda: NOW,
    )
    pudu = EvidenceItem(
        evidence_id="evidence:headquarters:pudu",
        object_id="company-c-pudu",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://www.pudurobotics.com/about",
        snippet="普渡机器人总部位于深圳。",
        score=1.0,
        source_authority="official",
        observed_at=NOW,
        claim_binding=EvidenceClaimBinding(
            subject_id="company-c-pudu",
            predicate="headquarters_city",
            value="深圳",
            status="observed",
        ),
    )
    yunji = EvidenceItem(
        evidence_id="evidence:headquarters:yunji",
        object_id="company-c-yunji",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://www.yunjichina.com.cn/about.html",
        snippet="云迹科技总部位于北京。",
        score=0.9,
        source_authority="official",
        observed_at=NOW,
        claim_binding=EvidenceClaimBinding(
            subject_id="company-c-yunji",
            predicate="headquarters_city",
            value="北京",
            status="observed",
        ),
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query="上述企业里总部在深圳的企业有哪些",
        protected_slots=(ProtectedSlot(kind="geography", value="深圳"),),
        items=(pudu, yunji),
        traces=(),
        limitations=(),
        entity_handles=(
            CanonicalEntityHandle(
                canonical_id=pudu.object_id,
                domain="company",
                display_name="深圳市普渡科技有限公司",
                evidence_ids=(pudu.evidence_id,),
            ),
            CanonicalEntityHandle(
                canonical_id=yunji.object_id,
                domain="company",
                display_name="云迹科技股份有限公司",
                evidence_ids=(yunji.evidence_id,),
            ),
        ),
    )

    def receive(text: str) -> None:
        observed_before_final.append(not provider_finished)
        forwarded.append(text)

    answer = inputs.answer_factory()
    answer.prose_progress = receive
    result = answer.answer(
        TurnRequest(
            session_id="session:headquarters-selection",
            turn_id="turn:headquarters-selection",
            query=evidence_set.original_query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )

    assert len(calls) == 1
    assert calls[0]["stream"] is True
    assert provider_finished is True
    assert observed_before_final and all(observed_before_final)
    assert "".join(forwarded) == "总部在深圳的只有深圳市普渡科技有限公司。"
    assert result.answer_text == "总部在深圳的只有深圳市普渡科技有限公司。"
    assert result.context_receipt is not None
    assert result.context_receipt.displayed_result_set is not None
    assert result.context_receipt.displayed_result_set.handle_ids == (pudu.object_id,)
    messages = calls[0]["messages"]
    assert isinstance(messages, list)
    user_payload = json.loads(messages[1]["content"])
    assert user_payload["displayed_entities"][0]["entity_index"] == 1
    assert user_payload["supported_claims"][0]["claim_index"] == 1
    serialized_payload = json.dumps(user_payload, ensure_ascii=False)
    assert "company-c-pudu" not in serialized_payload
    assert "evidence:headquarters" not in serialized_payload


def test_multi_entity_prose_commit_narrows_the_set_but_keeps_the_anchor(
    tmp_path: Path,
) -> None:
    responses = iter(
        (
            _prose_wire(
                "丁文伯是清华大学深圳国际研究生院副教授。",
                claim_indexes=(1,),
                entity_indexes=(1,),
            ),
            _prose_wire(
                "他的代表性成果包括 pFedGPA 与摩擦电智能手套两篇论文。",
                claim_indexes=(1, 2),
                entity_indexes=(1, 2),
            ),
            # The pronoun-only follow-up answer never names the anchor, so the
            # renderer's bounded correction retry re-asks once and this
            # anchor-named rewrite becomes the published answer.
            _prose_wire(
                "丁文伯的代表性成果包括 pFedGPA 与摩擦电智能手套两篇论文。",
                claim_indexes=(1, 2),
                entity_indexes=(1, 2),
            ),
        )
    )

    class _Completions:
        def create(self, **_: object) -> object:
            return SimpleNamespace(
                choices=(
                    SimpleNamespace(
                        message=SimpleNamespace(content=next(responses))
                    ),
                )
            )

    path, bundle = _write_bundle(tmp_path)
    renderer = serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(chat=SimpleNamespace(completions=_Completions())),
        model="recorded-chat-model",
        extra_body={"thinking": {"type": "disabled"}},
    )
    inputs = load_recorded_serving_inputs(
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        prose_renderer=renderer,
        clock=lambda: NOW,
    )

    def item(evidence_id: str, object_id: str, domain: str, snippet: str) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=evidence_id,
            object_id=object_id,
            domain=domain,
            lane="exact",
            source_nature="local",
            source_locator=f"canonical-v2-isolated:{object_id}",
            snippet=snippet,
            score=1.0,
            source_authority="canonical_release",
            observed_at=NOW,
            claim_binding=EvidenceClaimBinding(
                subject_id=object_id,
                predicate="canonical_projection",
                value=snippet,
                status="supported",
            ),
        )

    def handle(object_id: str, domain: str, name: str, evidence_id: str) -> Any:
        return CanonicalEntityHandle(
            canonical_id=object_id,
            domain=domain,
            display_name=name,
            evidence_ids=(evidence_id,),
        )

    professor_item = item(
        "evidence:professor:ding",
        "professor-c-ding",
        "professor",
        "丁文伯是清华大学深圳国际研究生院副教授。",
    )
    paper_one = item(
        "evidence:paper:pfedgpa",
        "paper-c-pfedgpa",
        "paper",
        "pFedGPA: Diffusion-based Generative Parameter Aggregation.",
    )
    paper_two = item(
        "evidence:paper:glove",
        "paper-c-glove",
        "paper",
        "Triboelectric bending sensor based smart glove.",
    )

    answer = inputs.answer_factory()
    first = answer.answer(
        TurnRequest(
            session_id="session:multi-entity-anchor",
            turn_id="turn:multi-entity-anchor:1",
            query="介绍清华的丁文伯",
            release_id=RELEASE_ID,
            evidence_set=EvidenceSet(
                release_id=RELEASE_ID,
                original_query="介绍清华的丁文伯",
                protected_slots=(),
                items=(professor_item,),
                traces=(),
                limitations=(),
                entity_handles=(
                    handle(
                        professor_item.object_id,
                        "professor",
                        "丁文伯",
                        professor_item.evidence_id,
                    ),
                ),
            ),
        )
    )
    assert first.context_receipt is not None
    assert first.context_receipt.active_anchor is not None
    assert first.context_receipt.active_anchor.canonical_id == "professor-c-ding"

    second = answer.answer(
        TurnRequest(
            session_id="session:multi-entity-anchor",
            turn_id="turn:multi-entity-anchor:2",
            query="他有哪些代表性研究成果",
            release_id=RELEASE_ID,
            evidence_set=EvidenceSet(
                release_id=RELEASE_ID,
                original_query="他有哪些代表性研究成果",
                protected_slots=(),
                items=(paper_one, paper_two),
                traces=(),
                limitations=(),
                entity_handles=(
                    handle(paper_one.object_id, "paper", "pFedGPA", paper_one.evidence_id),
                    handle(paper_two.object_id, "paper", "Smart glove", paper_two.evidence_id),
                ),
            ),
        )
    )

    assert second.context_receipt is not None
    assert second.answer_text == (
        "丁文伯的代表性成果包括 pFedGPA 与摩擦电智能手套两篇论文。"
    )
    assert second.context_receipt.displayed_result_set is not None
    assert second.context_receipt.displayed_result_set.handle_ids == (
        paper_one.object_id,
        paper_two.object_id,
    )
    assert second.context_receipt.active_anchor is not None
    assert second.context_receipt.active_anchor.canonical_id == "professor-c-ding"


def test_contextual_web_query_removes_referent_question_scaffolding(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
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
    assert search_text == f"{company_name} 机器人 自主刷门禁 开门"
    assert "上述" not in search_text
    assert "哪些支持" not in search_text
    assert '"' not in search_text

    capability_search = serving_module._contextual_web_search_view(
        "酒店电梯需要送餐机器人能够使用机械臂自主按电梯，上述企业的产品有哪些可以实现"
    )
    assert capability_search == "机器人 机械臂 自主按电梯"


def test_anchor_bound_pronoun_follow_up_keeps_the_professor_in_search_views(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    proposal = inputs.proposal_provider(
        QueryPlanningRequest(
            request_id="query-request:anchor-bound-professor-follow-up",
            release_id=RELEASE_ID,
            original_query="他有哪些代表性研究成果",
            as_of=NOW,
            displayed_entity_ids=("professor-p-dingwenbo",),
            displayed_entity_names=("丁文伯",),
        )
    )

    search_text = proposal.query_views[0].text
    assert search_text.startswith("丁文伯 ")
    assert "他" not in search_text
    assert "代表性研究成果" in search_text
    assert proposal.query_views[0].bound_entity_ids == ("professor-p-dingwenbo",)


def test_web_identity_matches_city_prefixed_legal_name_to_brand_snippet() -> None:
    request = SimpleNamespace(
        bound_entity_ids=("company-c-yunji", "company-c-pudu"),
        bound_entity_names=("云迹科技股份有限公司", "深圳市普渡科技有限公司"),
    )

    matched = serving_module._matched_bound_entity(
        request=request,
        title="自主按电梯送物，机器人开始干真活",
        snippet=(
            "普渡科技推出类人形具身智能服务机器人闪电匣Arm，"
            "通过机械臂和灵巧手自主按电梯。"
        ),
    )

    assert matched == ("company-c-pudu", "深圳市普渡科技有限公司")


@pytest.mark.parametrize(
    ("title", "snippet", "locator", "expected"),
    (
        (
            "全形态具身智能产品矩阵震撼首秀",
            "闪电匣Arm通过机械臂和灵巧手自主按电梯。",
            "https://www.pudutech.com/news/pudu-wrc-2025-embodied",
            ("company-c-pudu", "深圳市普渡科技有限公司"),
        ),
        (
            "產品 - 普渡",
            "刷門禁卡並用雙手開門。",
            "https://www.pudurobotics.com/zh-HK/products/flashbot-arm",
            ("company-c-pudu", "深圳市普渡科技有限公司"),
        ),
        (
            "全形态具身智能产品矩阵",
            "机械臂自主按电梯。",
            "https://www.pudufake.com/product",
            None,
        ),
        (
            "ROBOTIS GAEMI 酒店配送机器人",
            "使用机械臂按电梯。",
            "https://www.robotis.com/product",
            None,
        ),
    ),
)
def test_web_identity_uses_distinct_brand_text_or_official_style_domain(
    title: str,
    snippet: str,
    locator: str,
    expected: tuple[str, str] | None,
) -> None:
    request = SimpleNamespace(
        bound_entity_ids=("company-c-pudu",),
        bound_entity_names=("深圳市普渡科技有限公司",),
    )

    matched = serving_module._matched_bound_entity(
        request=request,
        title=title,
        snippet=snippet,
        locator=locator,
    )

    assert matched == expected


def test_serving_reranker_keeps_web_gap_ahead_of_vector_neighbors(
    tmp_path: Path,
) -> None:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
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
        prose_renderer=_timeout_prose_renderer,
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


def test_serving_reranker_keeps_enumeration_vector_canonical_in_window(
    tmp_path: Path,
) -> None:
    """List questions must not let Web gap candidates crowd out vector canonicals.

    Regression for the hotel-delivery-robot follow-up bug: the reranker filed
    every vector-lane candidate under ``other`` (they are neither strong local
    nor current-Web), so when the Web lane filled the whole window the vector
    canonicals never became handles, the displayed set stayed empty, and the
    next turn ("上述企业里总部在深圳的企业有哪些") could not resolve the
    collection reference.
    """
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )

    def fused(*, token: str, lane: str, score: float) -> FusedCandidate:
        local = lane == "vector"
        evidence = EvidenceItem(
            evidence_id=f"evidence:enumeration:{token}",
            object_id=f"object:enumeration:{token}",
            domain="company",
            lane=lane,
            source_nature=("local" if local else "current_web"),
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

    vector_candidates = tuple(
        fused(token=f"vector-{index}", lane="vector", score=1.0)
        for index in range(bundle.max_candidates)
    )
    web_candidates = tuple(
        fused(token=f"web-{index}", lane="web", score=0.9)
        for index in range(bundle.max_web_results)
    )
    assert inputs.reranker is not None
    result = inputs.reranker(
        RerankRequest(
            release_id=RELEASE_ID,
            original_query="中国有哪些成熟的酒店送餐机器人供应商",
            eligible_candidates=(*vector_candidates, *web_candidates),
        )
    )

    retained = result.ordered_result_ids[: bundle.max_candidates]
    # The vector canonicals must survive inside the window so they become
    # handles and anchor the next turn's collection reference.
    assert any(
        result_id.startswith("fused-result:vector-") for result_id in retained
    )
    # The Web lane keeps a bounded presence for recall as well.
    assert any(result_id.startswith("fused-result:web-") for result_id in retained)


def _stub_professor(identity_id: str, display_name: str) -> Any:
    return SimpleNamespace(
        canonical_identity_id=identity_id,
        name=display_name,
        canonical_name_zh=display_name,
        aliases=(),
    )


def _stub_company(
    identity_id: str,
    name: str,
    normalized_name: str,
    aliases: tuple[str, ...] = (),
) -> Any:
    return SimpleNamespace(
        canonical_identity_id=identity_id,
        name=name,
        normalized_name=normalized_name,
        aliases=aliases,
    )


def _release_bound_planner_with_named_resolution(
    tmp_path: Path,
    professors: tuple[Any, ...],
    companies: tuple[Any, ...] = (),
) -> Any:
    path, bundle = _write_bundle(tmp_path)
    inputs = load_recorded_serving_inputs(
        prose_renderer=_timeout_prose_renderer,
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    catalog = InstitutionCatalog(
        catalog_id="institution-catalog:s12b-test",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(),
    )
    delegate = create_ephemeral_query_planner(
        planning_policy=inputs.planning_policy,
        institution_catalog=catalog,
        proposal_provider=inputs.proposal_provider,
    )
    binding = isolated_read_module.PlanningReleaseBinding(
        release_id=RELEASE_ID,
        publication_state="active",
        published_release_sha256="0" * 64,
        publication_verification_evidence_ids=("evidence:release-binding",),
        manifest_sha256="0" * 64,
        index_projection_request_sha256="0" * 64,
        index_projection_result_sha256="0" * 64,
        candidate_projection_result_sha256="0" * 64,
        internal_reference_projection_result_sha256="0" * 64,
        institution_catalog_sha256=catalog.content_sha256,
        planning_policy_sha256="0" * 64,
    )
    return isolated_read_module._ReleaseBoundQueryPlanner(
        release_id=RELEASE_ID,
        release_binding=binding,
        delegate=delegate,
        named_professor_projections=professors,
        named_company_projections=companies,
    )


def test_named_professor_research_query_reaches_the_traversal_lane(
    tmp_path: Path,
) -> None:
    planner = _release_bound_planner_with_named_resolution(
        tmp_path,
        (
            _stub_professor("professor-c-ding-wenbo", "丁文伯"),
            _stub_professor("professor-c-zeng-long", "曾龙"),
        ),
    )

    plan = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:named-research-source",
            release_id=RELEASE_ID,
            original_query="丁文伯的代表性论文有哪些",
            as_of=NOW,
        )
    )

    assert plan.structured_constraints.displayed_entity_ids == (
        "professor-c-ding-wenbo",
    )
    assert plan.lanes == ("relationship", "web")
    assert len(plan.relationship_paths) == 1
    relationship_path = plan.relationship_paths[0]
    assert (
        relationship_path.relationship_type_id,
        relationship_path.direction,
        relationship_path.source_type,
        relationship_path.target_type,
    ) == (
        "professor_authored_paper",
        "professor_to_paper",
        "professor",
        "paper",
    )
    assert any(
        slot.kind == "displayed_entity_set"
        and slot.entity_ids == ("professor-c-ding-wenbo",)
        for slot in plan.protected_slots
    )


def test_named_resolution_falls_back_when_ambiguous_or_absent(
    tmp_path: Path,
) -> None:
    planner = _release_bound_planner_with_named_resolution(
        tmp_path,
        (
            _stub_professor("professor-c-wang-a", "王学谦"),
            _stub_professor("professor-c-wang-b", "王学谦"),
            _stub_professor("professor-c-ding-wenbo", "丁文伯"),
        ),
    )

    ambiguous = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:named-ambiguous",
            release_id=RELEASE_ID,
            original_query="王学谦的代表性论文有哪些",
            as_of=NOW,
        )
    )
    assert ambiguous.structured_constraints.displayed_entity_ids == ()
    assert ambiguous.relationship_paths == ()

    absent = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:named-absent",
            release_id=RELEASE_ID,
            original_query="李雷的代表性论文有哪些",
            as_of=NOW,
        )
    )
    assert absent.structured_constraints.displayed_entity_ids == ()
    assert absent.relationship_paths == ()

    unrelated = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:not-research",
            release_id=RELEASE_ID,
            original_query="丁文伯是清华大学深圳国际研究生院的副教授吗",
            as_of=NOW,
        )
    )
    assert unrelated.structured_constraints.displayed_entity_ids == ()


def test_named_company_patent_query_reaches_the_traversal_lane(
    tmp_path: Path,
) -> None:
    planner = _release_bound_planner_with_named_resolution(
        tmp_path,
        (),
        companies=(
            _stub_company(
                "company-c-pudu",
                "深圳市普渡科技有限公司",
                "普渡科技",
            ),
            _stub_company(
                "company-c-ubtech",
                "深圳市优必选科技股份有限公司",
                "优必选",
            ),
        ),
    )

    plan = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:named-company-patent",
            release_id=RELEASE_ID,
            original_query="深圳市普渡科技有限公司有哪些专利",
            as_of=NOW,
        )
    )

    assert plan.structured_constraints.displayed_entity_ids == ("company-c-pudu",)
    assert plan.lanes == ("relationship", "web")
    assert len(plan.relationship_paths) == 1
    relationship_path = plan.relationship_paths[0]
    assert (
        relationship_path.relationship_type_id,
        relationship_path.direction,
        relationship_path.source_type,
        relationship_path.target_type,
    ) == (
        "company_has_patent",
        "company_to_patent",
        "company",
        "patent",
    )
    assert any(
        slot.kind == "displayed_entity_set"
        and slot.entity_ids == ("company-c-pudu",)
        for slot in plan.protected_slots
    )


@pytest.mark.parametrize(
    "query",
    (
        "普渡科技的专利有哪些",
        "普渡科技有哪些专利",
    ),
)
def test_named_company_patent_query_binds_short_names(
    tmp_path: Path,
    query: str,
) -> None:
    planner = _release_bound_planner_with_named_resolution(
        tmp_path,
        (),
        companies=(
            _stub_company(
                "company-c-pudu",
                "深圳市普渡科技有限公司",
                "普渡科技",
            ),
            _stub_company(
                "company-c-ubtech",
                "深圳市优必选科技股份有限公司",
                "优必选",
            ),
        ),
    )

    plan = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:named-company-short",
            release_id=RELEASE_ID,
            original_query=query,
            as_of=NOW,
        )
    )

    assert plan.structured_constraints.displayed_entity_ids == ("company-c-pudu",)
    assert len(plan.relationship_paths) == 1
    assert plan.relationship_paths[0].direction == "company_to_patent"


def test_named_company_patent_query_stays_unbound_when_ambiguous_or_irrelevant(
    tmp_path: Path,
) -> None:
    planner = _release_bound_planner_with_named_resolution(
        tmp_path,
        (),
        companies=(
            _stub_company(
                "company-c-pudu-a",
                "深圳市普渡科技有限公司",
                "普渡科技",
            ),
            _stub_company(
                "company-c-pudu-b",
                "普渡科技（北京）有限公司",
                "普渡科技",
            ),
        ),
    )

    ambiguous = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:named-company-ambiguous",
            release_id=RELEASE_ID,
            original_query="普渡科技有哪些专利",
            as_of=NOW,
        )
    )
    assert ambiguous.structured_constraints.displayed_entity_ids == ()
    assert ambiguous.relationship_paths == ()

    profile = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:named-company-profile",
            release_id=RELEASE_ID,
            original_query="深圳市普渡科技有限公司怎么样",
            as_of=NOW,
        )
    )
    assert profile.structured_constraints.displayed_entity_ids == ()
    assert profile.relationship_paths == ()


def test_named_company_patent_query_requires_single_ownership_source(
    tmp_path: Path,
) -> None:
    """A named-company patent query only binds the traversal when it names
    exactly one company and the hit carries possessive/listing intent."""
    planner = _release_bound_planner_with_named_resolution(
        tmp_path,
        (),
        companies=(
            _stub_company(
                "company-c-pudu",
                "深圳市普渡科技有限公司",
                "普渡科技",
            ),
            _stub_company(
                "company-c-ubtech",
                "深圳市优必选科技股份有限公司",
                "优必选",
            ),
        ),
    )

    double = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:named-company-double",
            release_id=RELEASE_ID,
            original_query="深圳市普渡科技有限公司和优必选有哪些专利",
            as_of=NOW,
        )
    )
    assert double.structured_constraints.displayed_entity_ids == ()
    assert double.relationship_paths == ()

    competitor = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:named-company-competitor",
            release_id=RELEASE_ID,
            original_query="深圳市普渡科技有限公司的竞争对手有哪些专利",
            as_of=NOW,
        )
    )
    assert competitor.structured_constraints.displayed_entity_ids == (
        "company-c-pudu",
    )
    assert competitor.relationship_paths == ()

    owned = planner.plan(
        QueryPlanningRequest(
            request_id="query-request:named-company-owned",
            release_id=RELEASE_ID,
            original_query="深圳市普渡科技有限公司有哪些专利",
            as_of=NOW,
        )
    )
    assert owned.structured_constraints.displayed_entity_ids == ("company-c-pudu",)
    assert len(owned.relationship_paths) == 1
    assert owned.relationship_paths[0].direction == "company_to_patent"


def test_focused_named_traversal_keeps_relationship_claims_eligible() -> None:
    """A named-entity traversal turn has a focused search view and no
    exact-lane hits; the selector must still admit release-bound relationship
    claims instead of degrading to web-only eligibility."""
    query = "深圳市普渡科技有限公司有哪些专利"
    company_id = "company-c-pudu"
    patent_items = tuple(
        EvidenceItem(
            evidence_id=f"evidence:patent:{index}",
            object_id=f"patent-c-{index}",
            domain="patent",
            lane="relationship",
            source_nature="local",
            source_locator=f"canonical-v2-isolated:patent:{index}",
            snippet=json.dumps(
                {
                    "title": f"专利标题{index}",
                    "patent_number": f"CN10000000{index}U",
                    "applicants": [{"name": "深圳市普渡科技有限公司"}],
                    "_relationship": {
                        "relationship_type": "patent_has_applicant",
                        "roles": ["applicant"],
                        "source_id": f"patent-c-{index}",
                        "target_id": company_id,
                    },
                },
                ensure_ascii=False,
            ),
            score=1.0,
            source_authority="canonical_release",
            local_projection_trace=_source_relationship_trace(
                displayed_entity_id=company_id,
                candidate_canonical_id=f"patent-c-{index}",
                candidate_display_name=f"专利标题{index}",
            ),
            claim_binding=EvidenceClaimBinding(
                subject_id=f"canonical:company:{company_id}",
                predicate="patent_has_applicant",
                value=f"canonical:patent:patent-c-{index}",
                status="accepted",
            ),
        )
        for index in range(2)
    )
    web_item = EvidenceItem(
        evidence_id="evidence:web:1",
        object_id="web:1",
        domain="patent",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.com/news",
        snippet="深圳市普渡科技取得一项名为示例方法的专利：金融界消息……",
        score=0.9,
        source_authority="public_web",
        claim_binding=EvidenceClaimBinding(
            subject_id=f"canonical:company:{company_id}",
            predicate="patent_has_applicant",
            value="web:patent:example",
            status="accepted",
        ),
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=(
            ProtectedSlot(
                kind="displayed_entity_set",
                value="displayed_entity_set",
                raw_text="",
                entity_ids=(company_id,),
            ),
        ),
        items=(*patent_items, web_item),
        traces=(),
        limitations=(),
        entity_handles=tuple(
            CanonicalEntityHandle(
                canonical_id=item.object_id,
                domain="patent",
                display_name=f"专利标题{index}",
                evidence_ids=(item.evidence_id,),
            )
            for index, item in enumerate(patent_items)
        ),
    )
    selector = serving_module._answer_selector(
        bundle=SimpleNamespace(
            max_candidates=12,
            max_web_results=8,
            answer_model_id="canonical-v2-deterministic-answer-v1",
        )
    )

    proposal = selector(
        TurnRequest(
            session_id="session:focused-traversal",
            turn_id="turn:focused-traversal",
            query=query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )

    patent_claims = [
        claim for claim in proposal.claims if claim.predicate == "patent_has_applicant"
    ]
    assert len(patent_claims) == 3
    assert any("专利标题0" in claim.text for claim in patent_claims)
    assert any("专利标题1" in claim.text for claim in patent_claims)


def test_theme_probes_include_web_extracted_company_names_ordered_by_partial_match() -> None:
    """Theme probes must include web-extracted company names (深南 in a PCB
    top-100 ranking), ordered by theme partial-match so unrelated names
    cannot consume the probe ceiling; locally covered candidates stay out."""
    pcb_part = serving_module._theme_material_part("我想找PCB打板， 有哪些推荐")
    assert pcb_part is not None
    assert pcb_part.requested_value == "PCB打板"
    theme_part = MaterialQuestionPart(
        part_id="serving-theme:test",
        text="我想找PCB打板， 有哪些推荐",
        subject_id="serving-theme:test",
        predicate="theme_relevance",
        requested_value="PCB打板",
        material=True,
        answer_scoped=False,
    )
    local_uncovered = EvidenceItem(
        evidence_id="evidence:local:jiali",
        object_id="company-c-jiali",
        domain="company",
        lane="vector",
        source_nature="local",
        source_locator="canonical-v2-isolated:jiali",
        snippet=json.dumps(
            {"name": "深圳嘉立创科技集团股份有限公司"},
            ensure_ascii=False,
        ),
        score=0.8,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id="company-c-jiali",
            predicate="semantic_recall",
            value="v" * 64,
            status="admitted",
        ),
    )
    local_covered = EvidenceItem(
        evidence_id="evidence:local:huqiu",
        object_id="company-c-huqiu",
        domain="company",
        lane="vector",
        source_nature="local",
        source_locator="canonical-v2-isolated:huqiu",
        snippet=json.dumps(
            {"name": "华秋电子", "profile_summary": "PCB打板一站式服务"},
            ensure_ascii=False,
        ),
        score=0.8,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id="company-c-huqiu",
            predicate="semantic_recall",
            value="v" * 64,
            status="admitted",
        ),
    )
    web_ranking = EvidenceItem(
        evidence_id="evidence:web:ranking",
        object_id="web-object:ranking",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/pcb-top100",
        snippet="2023中国PCB百强企业名单：深南电路股份有限公司排名前列",
        score=0.9,
        source_authority="web_search",
        claim_binding=EvidenceClaimBinding(
            subject_id="web-object:ranking",
            predicate="current_web_result",
            value="v" * 64,
            status="observed",
        ),
    )
    store = serving_module._SupplementalContextStore()
    decider = serving_module._serving_sufficiency_decider(context_store=store)
    decider(
        SufficiencyDecisionRequest(
            plan_id="plan:theme-probe-test",
            release_id=RELEASE_ID,
            original_query="我想找PCB打板， 有哪些推荐",
            material_parts=(theme_part,),
            evidence=(local_uncovered, local_covered, web_ranking),
        )
    )
    context = store.pop("plan:theme-probe-test")
    assert context is not None
    probes = context.theme_probes
    names = tuple(probe.entity_name for probe in probes)
    assert "深南电路股份有限公司" in names
    assert "深圳嘉立创科技集团股份有限公司" in names
    assert "华秋电子" not in names  # locally covered: no probe needed
    assert names.index("深南电路股份有限公司") < names.index(
        "深圳嘉立创科技集团股份有限公司"
    )


def test_enumeration_selector_web_claim_limit_follows_widened_window() -> None:
    """Enumeration turns widen the selector web-claim limit to the candidate
    window: discovery-view tails (九号 at merged rank 36-43) must reach the
    prose model, while non-enumeration stays at the bundle web cap."""
    query = "中国有哪些成熟的酒店送餐机器人供应商"

    def web_item(index: int, name: str) -> EvidenceItem:
        evidence_id = f"evidence:web:{index}"
        return EvidenceItem(
            evidence_id=evidence_id,
            object_id=f"web-object:{index}",
            domain="company",
            lane="web",
            source_nature="current_web",
            source_locator=f"https://example.test/{index}",
            snippet=f"{name}：酒店送餐机器人相关公开信息",
            score=1.0 - index * 0.01,
            source_authority="web_search",
            claim_binding=EvidenceClaimBinding(
                subject_id=f"web-object:{index}",
                predicate="current_web_result",
                value="v" * 64,
                status="observed",
            ),
        )

    items = tuple(
        web_item(index, f"企业{index}" if index != 18 else "九号机器人")
        for index in range(1, 21)
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=(),
        items=items,
        traces=(),
        limitations=(),
        entity_handles=tuple(
            CanonicalEntityHandle(
                canonical_id=f"web-object:{index}",
                domain="company",
                display_name=f"企业{index}" if index != 18 else "九号机器人",
                evidence_ids=(f"evidence:web:{index}",),
            )
            for index in range(1, 21)
        ),
    )
    selector = serving_module._answer_selector(
        bundle=SimpleNamespace(
            max_candidates=8,
            max_web_results=8,
            answer_model_id="canonical-v2-deterministic-answer-v1",
        )
    )
    proposal = selector(
        TurnRequest(
            session_id="session:enum-claims",
            turn_id="turn:enum-claims",
            query=query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )
    assert any("九号机器人" in claim.text for claim in proposal.claims)

    ordinary = selector(
        TurnRequest(
            session_id="session:ordinary-claims",
            turn_id="turn:ordinary-claims",
            query="丁文伯教授的研究方向是什么？",
            release_id=RELEASE_ID,
            evidence_set=EvidenceSet(
                release_id=RELEASE_ID,
                original_query="丁文伯教授的研究方向是什么？",
                protected_slots=(),
                items=items,
                traces=(),
                limitations=(),
                entity_handles=tuple(
                    CanonicalEntityHandle(
                        canonical_id=f"web-object:{index}",
                        domain="company",
                        display_name=f"企业{index}" if index != 18 else "九号机器人",
                        evidence_ids=(f"evidence:web:{index}",),
                    )
                    for index in range(1, 21)
                ),
            ),
        )
    )
    assert not any("九号机器人" in claim.text for claim in ordinary.claims)


def test_focused_named_traversal_drops_relationship_items_unbound_to_displayed_anchor() -> None:
    """A focused named-entity traversal turn must admit only relationship claims
    whose local_projection_trace proves the item is bound to the turn's
    displayed anchor; untraceable and cross-anchor relationship candidates must
    never answer (cross-pool bleed), while current-web items stay eligible."""
    query = "深圳市普渡科技有限公司有哪些专利"
    company_id = "company-c-pudu"
    other_company_id = "company-c-ubtech"

    def patent_item(
        evidence_id: str,
        object_id: str,
        *,
        trace: LocalSourceRelationshipTrace | None,
    ) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=evidence_id,
            object_id=object_id,
            domain="patent",
            lane="relationship",
            source_nature="local",
            source_locator=f"canonical-v2-isolated:{object_id}",
            snippet=json.dumps(
                {
                    "title": f"专利{evidence_id}",
                    "patent_number": f"CN10000000{object_id}U",
                    "applicants": [{"name": "深圳市普渡科技有限公司"}],
                    "_relationship": {
                        "relationship_type": "patent_has_applicant",
                        "roles": ["applicant"],
                        "source_id": object_id,
                        "target_id": company_id,
                    },
                },
                ensure_ascii=False,
            ),
            score=1.0,
            source_authority="canonical_release",
            local_projection_trace=trace,
            claim_binding=EvidenceClaimBinding(
                subject_id=f"canonical:company:{company_id}",
                predicate="patent_has_applicant",
                value=f"canonical:patent:{object_id}",
                status="accepted",
            ),
        )

    bound_item = patent_item(
        "evidence:patent:bound",
        "patent-c-bound",
        trace=_source_relationship_trace(
            displayed_entity_id=company_id,
            candidate_canonical_id="patent-c-bound",
            candidate_display_name="专利bound",
        ),
    )
    untraceable_item = patent_item(
        "evidence:patent:untraceable",
        "patent-c-untraceable",
        trace=None,
    )
    wrong_anchor_item = patent_item(
        "evidence:patent:wrong-anchor",
        "patent-c-wrong-anchor",
        trace=_source_relationship_trace(
            displayed_entity_id=other_company_id,
            candidate_canonical_id="patent-c-wrong-anchor",
            candidate_display_name="专利wrong-anchor",
        ),
    )
    web_item = EvidenceItem(
        evidence_id="evidence:web:1",
        object_id="web:1",
        domain="patent",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.com/news",
        snippet="深圳市普渡科技取得一项名为示例方法的专利：金融界消息……",
        score=0.9,
        source_authority="public_web",
        claim_binding=EvidenceClaimBinding(
            subject_id=f"canonical:company:{company_id}",
            predicate="patent_has_applicant",
            value="web:patent:example",
            status="accepted",
        ),
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=(
            ProtectedSlot(
                kind="displayed_entity_set",
                value="displayed_entity_set",
                raw_text="",
                entity_ids=(company_id,),
            ),
        ),
        items=(bound_item, untraceable_item, wrong_anchor_item, web_item),
        traces=(),
        limitations=(),
        entity_handles=tuple(
            CanonicalEntityHandle(
                canonical_id=item.object_id,
                domain="patent",
                display_name=item.object_id,
                evidence_ids=(item.evidence_id,),
            )
            for item in (bound_item, untraceable_item, wrong_anchor_item, web_item)
        ),
    )
    selector = serving_module._answer_selector(
        bundle=SimpleNamespace(
            max_candidates=12,
            max_web_results=8,
            answer_model_id="canonical-v2-deterministic-answer-v1",
        )
    )

    proposal = selector(
        TurnRequest(
            session_id="session:focused-traversal",
            turn_id="turn:focused-traversal",
            query=query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )

    claim_evidence_ids = {
        evidence_id
        for claim in proposal.claims
        for evidence_id in claim.evidence_ids
    }
    assert "evidence:patent:bound" in claim_evidence_ids
    assert "evidence:web:1" in claim_evidence_ids
    assert "evidence:patent:untraceable" not in claim_evidence_ids
    assert "evidence:patent:wrong-anchor" not in claim_evidence_ids


def test_displayed_set_follow_up_binds_claims_after_prose_scope_narrowing(
    tmp_path: Path,
) -> None:
    """Hotel-robot regression: after the prose commit narrows the displayed set,
    a set-scope follow-up whose current turn selects no new handles must still
    bind claims to the session's displayed universe, never degrade."""
    path, bundle = _write_bundle(tmp_path)

    def _select_all_prose(result: Any) -> Any:
        return ProseSynthesisResult(
            answer_text="总部在深圳的是深圳市普渡科技有限公司。",
            selected_claim_ids=tuple(claim.claim_id for claim in result.claims),
            selected_handle_ids=(),
        )

    renderer = _select_all_prose
    inputs = load_recorded_serving_inputs(
        prose_renderer=renderer,
        path=path,
        expected_content_sha256=bundle.content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )

    def local_item(eid: str, oid: str, name: str) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=eid,
            object_id=oid,
            domain="company",
            lane="exact",
            source_nature="local",
            source_locator=f"canonical-v2-isolated:{oid}",
            snippet=json.dumps({"name": name}, ensure_ascii=False),
            score=1.0,
            source_authority="canonical_release",
            observed_at=NOW,
            claim_binding=EvidenceClaimBinding(
                subject_id=oid,
                predicate="canonical_projection",
                value="a" * 64,
                status="admitted",
            ),
        )

    def web_hq(eid: str, oid: str, city: str, locator: str) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=eid,
            object_id=oid,
            domain="company",
            lane="web",
            source_nature="current_web",
            source_locator=locator,
            snippet=f"总部{city}",
            score=1.0,
            source_authority="official",
            observed_at=NOW,
            claim_binding=EvidenceClaimBinding(
                subject_id=oid,
                predicate="headquarters_city",
                value=city,
                status="observed",
            ),
        )

    yunji = local_item("ev:yunji", "company-c-yunji", "云迹科技股份有限公司")
    pudu = local_item("ev:pudu", "company-c-pudu", "深圳市普渡科技有限公司")
    answer = inputs.answer_factory()
    first = answer.answer(
        TurnRequest(
            session_id="session:hotel-regression",
            turn_id="turn:hotel-regression:1",
            query="中国有哪些成熟的酒店送餐机器人供应商",
            release_id=RELEASE_ID,
            evidence_set=EvidenceSet(
                release_id=RELEASE_ID,
                original_query="中国有哪些成熟的酒店送餐机器人供应商",
                protected_slots=(),
                items=(yunji, pudu),
                traces=(),
                limitations=(),
                entity_handles=(
                    CanonicalEntityHandle(
                        canonical_id=yunji.object_id,
                        domain="company",
                        display_name="云迹科技股份有限公司",
                        evidence_ids=(yunji.evidence_id,),
                    ),
                    CanonicalEntityHandle(
                        canonical_id=pudu.object_id,
                        domain="company",
                        display_name="深圳市普渡科技有限公司",
                        evidence_ids=(pudu.evidence_id,),
                    ),
                ),
            ),
        )
    )
    assert first.context_receipt is not None
    assert first.context_receipt.displayed_result_set is not None

    hq_pudu = web_hq(
        "ev:hq:pudu", pudu.object_id, "深圳", "https://www.pudurobotics.com/about"
    )
    hq_yunji = web_hq(
        "ev:hq:yunji", yunji.object_id, "北京", "https://www.yunjichina.com.cn/a"
    )
    second = answer.answer(
        TurnRequest(
            session_id="session:hotel-regression",
            turn_id="turn:hotel-regression:2",
            query="上述企业里总部在深圳的企业有哪些",
            release_id=RELEASE_ID,
            evidence_set=EvidenceSet(
                release_id=RELEASE_ID,
                original_query="上述企业里总部在深圳的企业有哪些",
                protected_slots=(),
                items=(hq_pudu, hq_yunji),
                traces=(),
                limitations=(),
                entity_handles=(),
            ),
        )
    )

    assert second.answer_text != (
        "关于该主体的公开信息目前较为有限，暂未能确认您问的具体内容。"
    )
    assert any(
        claim.predicate == "headquarters_city"
        and claim.subject_id == pudu.object_id
        and claim.value == "深圳"
        for claim in second.claims
    )


def test_serving_semantic_text_omits_missing_field_placeholder() -> None:
    def item(payload: dict[str, Any]) -> EvidenceItem:
        return EvidenceItem(
            evidence_id="evidence:s12b:placeholder",
            object_id="professor:s12b:placeholder",
            domain="professor",
            lane="lexical",
            source_nature="local",
            source_locator="canonical-v2-isolated:placeholder",
            snippet=json.dumps(payload, ensure_ascii=False),
            score=1.0,
            source_authority="canonical_release",
            claim_binding=EvidenceClaimBinding(
                subject_id="professor:s12b:placeholder",
                predicate="canonical_projection",
                value="a" * 64,
                status="admitted",
            ),
        )

    degraded = serving_module._semantic_text(
        item(
            {
                "name": "张三",
                "institution": "清华大学深圳国际研究生院",
                "department": _PROFESSOR_MISSING_FIELD_FALLBACK,
                "title": _PROFESSOR_MISSING_FIELD_FALLBACK,
                "email": _PROFESSOR_MISSING_FIELD_FALLBACK,
                "profile_summary": "研究机器人技术",
            }
        ),
        "张三",
    )
    assert "Not supplied" not in degraded
    assert "职称" not in degraded
    assert degraded == "张三；机构：清华大学深圳国际研究生院；简介：研究机器人技术。"

    complete = serving_module._semantic_text(
        item(
            {
                "name": "张三",
                "institution": "清华大学深圳国际研究生院",
                "title": "副教授",
                "profile_summary": "研究机器人技术",
            }
        ),
        "张三",
    )
    assert complete == "张三；机构：清华大学深圳国际研究生院；职称：副教授；简介：研究机器人技术。"


def test_serving_semantic_text_uses_bound_company_name_for_applicant() -> None:
    """A bound patent applicant renders its company's Chinese name.

    Regression for CN117873146A: the applicant carried only the English
    name ("Shenzhen Ubtech Technology Co ltd") even though applicant-binding
    resolved it to 深圳市优必选科技股份有限公司.  The bound applicant
    sub-object now carries company_name, and _list_names prefers it.
    """
    item = EvidenceItem(
        evidence_id="evidence:s12f:patent-applicant",
        object_id="patent:s12f:cn117873146",
        domain="patent",
        lane="lexical",
        source_nature="local",
        source_locator="canonical-v2-isolated:patent",
        snippet=json.dumps(
            {
                "name": "一种机器人的落地控制方法、机器人及终端设备",
                "patent_number": "CN117873146A",
                "applicants": [
                    {
                        "name": "Shenzhen Ubtech Technology Co ltd",
                        "company_name": "深圳市优必选科技股份有限公司",
                        "canonical_company_id": "company-c-ubtech",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        score=1.0,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id="patent:s12f:cn117873146",
            predicate="canonical_projection",
            value="a" * 64,
            status="admitted",
        ),
    )
    text = serving_module._semantic_text(item, "一种机器人的落地控制方法")
    assert "深圳市优必选科技股份有限公司" in text
    assert "Shenzhen Ubtech" not in text


def _term_view_request(query: str) -> QueryPlanningRequest:
    return QueryPlanningRequest(
        request_id=f"query-request:term:{abs(hash(query))}",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
    )


def test_concept_term_view_is_appended_for_data_theme_queries() -> None:
    request = _term_view_request("在真实数据采集路线中，有哪些具体方式")
    views = serving_module._serving_query_views(
        request=request,
        search_text=request.original_query,
        retained_values=(),
        protected_slots=(),
        planner_model_id="planner-v1",
        query_rewriter=lambda _q: ("真实数据采集方式", "数据采集路线规划方法"),
    )
    texts = tuple(view.text for view in views)
    assert texts[0] == request.original_query
    assert "具身智能 机器人 数据采集 遥操作 动作捕捉 真机 仿真 方法" in texts
    assert len(texts) == 4


def test_concept_term_view_replaces_last_rewrite_when_budget_full() -> None:
    request = _term_view_request(
        "在具身智能的合成数据发展方向上，具体有几种实现方法，分别有哪些代表厂商"
    )
    views = serving_module._serving_query_views(
        request=request,
        search_text=request.original_query,
        retained_values=(),
        protected_slots=(),
        planner_model_id="planner-v1",
        query_rewriter=lambda _q: ("合成方法一", "合成方法二", "合成方法三"),
    )
    texts = tuple(view.text for view in views)
    assert "具身智能 合成数据 物理仿真引擎 生成式模型 规则 方法 厂商" in texts
    assert len(texts) == 4
    assert "合成方法三" not in texts  # the last rewrite was replaced


def test_no_concept_term_view_for_entity_questions() -> None:
    request = _term_view_request("中国有哪些成熟的酒店送餐机器人供应商")
    views = serving_module._serving_query_views(
        request=request,
        search_text=request.original_query,
        retained_values=(),
        protected_slots=(),
        planner_model_id="planner-v1",
        query_rewriter=lambda _q: ("酒店送餐机器人品牌", "酒店服务机器人头部企业名单"),
    )
    texts = tuple(view.text for view in views)
    assert len(texts) == 3
    assert all("数据采集" not in view.text for view in views)


def test_rewrite_gate_fires_for_attribute_followups() -> None:
    assert serving_module._should_rewrite_serving_query(
        "深圳银星智能科技股份有限公司的创始人的教育背景是什么"
    )
    assert serving_module._should_rewrite_serving_query(
        "华力创科学这家公司的产量特点是什么，市场竞争力怎么样"
    )
    assert not serving_module._should_rewrite_serving_query(
        "深圳银星智能科技股份有限公司"
    )
    assert not serving_module._should_rewrite_serving_query("介绍清华的丁文伯")


def test_concept_term_view_is_promoted_after_deterministic_view() -> None:
    """Data-theme concept questions must not bury the term-expansion view at
    the end of the earliest-view-wins merge: a term view appended last was
    drowned below the candidate cut by the rewrite views (T19 lost 动作捕捉
    content that only the term view recalls)."""
    request = QueryPlanningRequest(
        request_id="query-request:s12g:term-view",
        release_id=RELEASE_ID,
        original_query="在真实数据采集路线中，有哪些具体方式",
        as_of=NOW,
    )
    views = serving_module._serving_query_views(
        request=request,
        search_text="真实数据采集路线 具体方式",
        retained_values=(),
        protected_slots=(),
        planner_model_id="canonical-v2-deterministic-planner-v1",
        query_rewriter=lambda _query: ("数据采集 机器人 方法 遥操作",),
    )
    assert [view.producer_kind for view in views][:2] == [
        "deterministic",
        "term_expansion",
    ]
    term_text = serving_module._concept_term_view_text(request.original_query)
    assert term_text is not None
    assert term_text in {view.text for view in views}


def planning_request(
    *,
    soft: str | None,
    names: tuple[str, ...] = (),
    query: str = "介绍一下国际先进技术应用推进中心",
) -> QueryPlanningRequest:
    """QueryPlanningRequest factory for authority-view tests.

    The task brief references a ``planning_request(soft=..., names=...)``
    fixture; none existed, so this mirrors ``_term_view_request`` while
    adding the displayed-entity / soft-subject anchors the authority-view
    helper consumes.
    """
    return QueryPlanningRequest(
        request_id=f"query-request:authority:{abs(hash((query, soft, names)))}",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
        displayed_entity_ids=tuple(
            f"company-c:authority:{index}" for index in range(len(names))
        ),
        displayed_entity_names=names,
        soft_context_subject=soft,
    )


def test_authority_views_added_for_org_level_soft_subject() -> None:
    texts = serving_module._authority_seeking_view_texts(
        request=planning_request(soft="国际先进技术应用推进中心"),
        original_query="介绍一下国际先进技术应用推进中心",
    )
    assert texts == (
        "国际先进技术应用推进中心 百度百科",
        "国际先进技术应用推进中心 官网",
    )


def test_authority_views_absent_when_city_named() -> None:
    assert (
        serving_module._authority_seeking_view_texts(
            request=planning_request(
                soft="国际先进技术应用推进中心（深圳）",
                query="介绍一下国际先进技术应用推进中心（深圳）",
            ),
            original_query="介绍一下国际先进技术应用推进中心（深圳）",
        )
        == ()
    )


def test_authority_views_absent_without_any_anchor() -> None:
    assert (
        serving_module._authority_seeking_view_texts(
            request=planning_request(
                soft=None, names=(), query="深圳有哪些机器人公司"
            ),
            original_query="深圳有哪些机器人公司",
        )
        == ()
    )


def test_authority_views_use_first_qualifying_anchor() -> None:
    """First-qualifying-anchor rule: a city-qualified displayed name does not
    qualify (pin, don't broaden), so the org-level soft subject is used; when
    the displayed name itself qualifies it wins over the soft subject."""
    assert serving_module._authority_seeking_view_texts(
        request=planning_request(
            soft="国际先进技术应用推进中心",
            names=("国际先进技术应用推进中心（深圳）",),
            query="理事会如何组成",
        ),
        original_query="理事会如何组成",
    ) == (
        "国际先进技术应用推进中心 百度百科",
        "国际先进技术应用推进中心 官网",
    )
    assert serving_module._authority_seeking_view_texts(
        request=planning_request(
            soft="优必选",
            names=("国际先进技术应用推进中心",),
            query="理事会如何组成",
        ),
        original_query="理事会如何组成",
    ) == (
        "国际先进技术应用推进中心 百度百科",
        "国际先进技术应用推进中心 官网",
    )


def test_serving_query_views_appends_authority_views_deduped() -> None:
    request = planning_request(soft="国际先进技术应用推进中心")
    views = serving_module._serving_query_views(
        request=request,
        search_text=request.original_query,
        retained_values=(),
        protected_slots=(),
        planner_model_id="planner-v1",
        query_rewriter=None,  # deterministic phase-1 view set
    )
    texts = [view.text for view in views]
    assert len(texts) == len(set(texts))
    assert "国际先进技术应用推进中心 百度百科" in texts
    # Authority views ride last: they never displace the phase-1 views.
    assert texts[-2:] == [
        "国际先进技术应用推进中心 百度百科",
        "国际先进技术应用推进中心 官网",
    ]
    assert all(
        view.soft_context_subject == request.soft_context_subject for view in views
    )
    assert [view.producer_kind for view in views if "百度百科" in view.text] == [
        "authority_seeking"
    ]
    authority_ids = [
        view.view_id for view in views if view.producer_kind == "authority_seeking"
    ]
    assert len(authority_ids) == len(set(authority_ids))


def test_serving_query_views_authority_views_keep_protected_raw_texts() -> None:
    """Plan-level lost_protected_slot invariant: like the rewrite views, an
    authority view that dropped a protected raw text gets it appended back so
    the planner validator never rejects the proposal."""
    request = planning_request(
        soft="国际先进技术应用推进中心",
        query="国际先进技术应用推进中心2024年有哪些成果",
    )
    views = serving_module._serving_query_views(
        request=request,
        search_text=request.original_query,
        retained_values=("2024",),
        protected_slots=(ProtectedSlot(kind="year", value="2024", raw_text="2024"),),
        planner_model_id="planner-v1",
        query_rewriter=None,
    )
    assert [
        view.text for view in views if view.producer_kind == "authority_seeking"
    ] == [
        "国际先进技术应用推进中心 百度百科 2024",
        "国际先进技术应用推进中心 官网 2024",
    ]


def test_concept_off_topic_claim_filter() -> None:
    """The data-theme answer guard drops drifted claims (traffic surveys,
    crawlers, crowdsourcing) before they reach prose/fallback, but stays off
    when the query names an alternate data domain itself (网页/交通数据采集
    keep their own claims)."""
    assert serving_module._concept_theme_filter_active(
        "在真实数据采集路线中，有哪些具体方式"
    )
    assert serving_module._concept_theme_filter_active("合成数据有哪些实现方法与厂商")
    assert not serving_module._concept_theme_filter_active("网页数据采集有哪些方式")
    assert not serving_module._concept_theme_filter_active("交通数据采集有哪些方式")
    assert not serving_module._concept_theme_filter_active("介绍深圳科创")
    assert serving_module._concept_off_topic_claim(
        "使用感应环探测器与GPS采集道路交通数据"
    )
    assert serving_module._concept_off_topic_claim("通过网络爬虫抓取网页数据")
    assert not serving_module._concept_off_topic_claim(
        "通过遥操作与动作捕捉采集机器人操作数据"
    )


def test_answer_selector_drops_off_topic_claims_for_data_theme(
    tmp_path: Path,
) -> None:
    """End-to-end selector guard: for a data-theme query the drifted traffic
    claim is dropped while the embodied-AI data collection claim survives."""
    path, bundle = _write_bundle(tmp_path)
    query = "在真实数据采集路线中，有哪些具体方式"
    traffic = EvidenceItem(
        evidence_id="evidence:s12g:traffic-drift",
        object_id="web-object:s12g:traffic",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/traffic",
        snippet="使用感应环探测器与GPS采集道路交通数据的服务商",
        score=1.0,
        source_authority="other",
        claim_binding=EvidenceClaimBinding(
            subject_id="web-object:s12g:traffic",
            predicate="current_web_result",
            value="traffic",
            status="observed",
        ),
    )
    motion = EvidenceItem(
        evidence_id="evidence:s12g:motion-capture",
        object_id="web-object:s12g:motion",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://example.test/motion",
        snippet="通过遥操作与动作捕捉采集机器人操作数据",
        score=1.0,
        source_authority="other",
        claim_binding=EvidenceClaimBinding(
            subject_id="web-object:s12g:motion",
            predicate="current_web_result",
            value="motion",
            status="observed",
        ),
    )
    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=(),
        items=(traffic, motion),
        traces=(),
        limitations=(),
    )
    request = TurnRequest(
        session_id="session:s12g:concept-filter",
        turn_id="turn:s12g:concept-filter",
        query=query,
        release_id=RELEASE_ID,
        evidence_set=evidence_set,
    )
    proposal = serving_module._answer_selector(bundle=bundle)(request)
    claim_texts = [claim.text for claim in proposal.claims]
    assert any("遥操作" in text for text in claim_texts)
    assert not any("感应环" in text or "GPS" in text for text in claim_texts)


def test_person_evidence_match_accepts_name_with_education_constraint() -> None:
    """Education-constrained person probes accept the person name plus the
    constraint in the same hit; a founder marker in the same snippet is not
    required (T13 早稻田企业家 refused with "未找到" because pages stated
    the school without the role word)."""
    result = serving_module._NormalizedWebResult(
        title="许晋诚：早稻田大学机器人学硕士",
        url="https://example.test/xujincheng",
        snippet="许晋诚，深圳机器人创业者，毕业于早稻田大学。",
        summary="",
        primary_provider_version="bocha-v1",
        corroborating_provider_versions=(),
    )
    assert serving_module._person_evidence_match(
        result,
        company="许晋诚",
        constraint="早稻田",
    )
    # The founder-role marker requirement still holds without a constraint
    # (创业者 alone is not a founder marker; 企业家 is).
    assert not serving_module._person_evidence_match(
        result,
        company="许晋诚",
        constraint=None,
    )
    entrepreneur = serving_module._NormalizedWebResult(
        title="许晋诚：深圳机器人企业家",
        url="https://example.test/xujincheng-entrepreneur",
        snippet="许晋诚，深圳机器人企业家。",
        summary="",
        primary_provider_version="bocha-v1",
        corroborating_provider_versions=(),
    )
    assert serving_module._person_evidence_match(
        entrepreneur,
        company="许晋诚",
        constraint=None,
    )
    no_founder_word = serving_module._NormalizedWebResult(
        title="许晋诚：早稻田大学机器人学硕士",
        url="https://example.test/xujincheng-2",
        snippet="许晋诚在早稻田大学完成学业后进入机器人行业。",
        summary="",
        primary_provider_version="bocha-v1",
        corroborating_provider_versions=(),
    )
    assert serving_module._person_evidence_match(
        no_founder_word,
        company="许晋诚",
        constraint="早稻田",
    )
    assert not serving_module._person_evidence_match(
        no_founder_word,
        company="许晋诚",
        constraint=None,
    )
    # A different school in the hit does not satisfy the constraint.
    assert not serving_module._person_evidence_match(
        result,
        company="许晋诚",
        constraint="东京大学",
    )


def test_rewrite_views_repin_soft_subject_and_log_marker(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Plan-level view-pin invariant (deepening-turn-anchor-carryover): every
    rewrite view contains the soft subject, and the re-pin tripwire logs a
    journal marker so production can observe the drop/repin rate."""
    provider = serving_module._proposal_provider(
        bundle=_bundle(tmp_path),
        query_rewriter=lambda _query: (
            "企业培育中心 运营模式",
            "企业孵化中心 培育成效",
            "企业服务中心 入驻企业情况",
        ),
    )
    request = QueryPlanningRequest(
        request_id="query-request:deepening-view-repin",
        release_id=RELEASE_ID,
        original_query="这个中心的企业培育情况怎么样",
        as_of=NOW,
        soft_context_subject="国际先进技术应用推进中心（深圳）",
    )

    with caplog.at_level("INFO", logger="src.data_agents.canonical_v2.knowledge_serving_isolated"):
        proposal = provider(request)

    rewrite_views = [
        view for view in proposal.query_views if view.producer_kind == "llm_rewrite"
    ]
    assert rewrite_views
    for view in rewrite_views:
        assert "国际先进技术应用推进中心（深圳）" in view.text
    assert any("view repin" in record.message for record in caplog.records)
