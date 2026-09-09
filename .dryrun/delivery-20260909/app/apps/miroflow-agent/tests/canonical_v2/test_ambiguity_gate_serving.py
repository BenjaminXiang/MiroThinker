"""Serving-side enablement of the Canonical V2 entity-ambiguity gate.

The release-bound serving planner attaches same-name Professor projections as
evidence-bound ambiguity candidates, and the injected serving policy decides
whether the turn is an interpreted answer with a bounded switch option or a
clarification-only turn. These tests stay hermetic: no live LLM, Web, or DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.data_agents.canonical_v2 import (
    knowledge_read_isolated as isolated_read_module,
)
from src.data_agents.canonical_v2.knowledge_answer import (
    ContinuationSelection,
    ProseSynthesisResult,
    TurnRequest,
)
from src.data_agents.canonical_v2.knowledge_read import (
    EvidenceClaimBinding,
    EvidenceItem,
    InstitutionCatalog,
    InstitutionCatalogEntry,
    QueryPlanningRequest,
    RecallCandidate,
    RetrievalLaneResult,
    create_ephemeral_knowledge_read,
    create_ephemeral_query_planner,
)
from src.data_agents.canonical_v2.knowledge_serving_isolated import (
    RecordedServingBundle,
    load_recorded_serving_inputs,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s12b-test"
DOMINANT_ID = "professor-c-wang-xueqian-sigs"
ALTERNATIVE_ID = "professor-c-wang-xueqian-other"
SAME_NAME_QUERY = "清华的王学谦的评价如何"


class _Embedding:
    model_id = "recorded-embedding-v1"
    dimension = 32


def _timeout_prose_renderer(_: Any) -> str:
    """Keep serving tests hermetic: the deterministic grounded path is the
    contract under test; the live environment renderer must stay out of unit
    tests even when an API key is resolvable."""
    raise TimeoutError("test-owned prose renderer is unavailable")


def _write_bundle(tmp_path: Path) -> tuple[Path, RecordedServingBundle]:
    bundle = RecordedServingBundle(
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
    path = tmp_path / "serving-bundle.json"
    path.write_text(
        json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path, bundle


def _load_inputs(tmp_path: Path) -> Any:
    path, bundle = _write_bundle(tmp_path)
    return load_recorded_serving_inputs(
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


def _catalog() -> InstitutionCatalog:
    return InstitutionCatalog(
        catalog_id="institution-catalog:s12b-test",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(),
    )


def _stub_professor(
    *,
    canonical_id: str,
    name: str,
    institution: str,
    title: str,
    assertion_ids: tuple[str, ...],
) -> Any:
    return SimpleNamespace(
        canonical_identity_id=canonical_id,
        name=name,
        canonical_name_zh=name,
        aliases=(),
        institution=institution,
        title=title,
        evidence=tuple(
            SimpleNamespace(assertion_id=assertion_id) for assertion_id in assertion_ids
        ),
    )


def _same_name_professors(
    *,
    dominant_assertions: int = 4,
    alternative_assertions: int = 1,
) -> tuple[Any, Any]:
    dominant = _stub_professor(
        canonical_id=DOMINANT_ID,
        name="王学谦",
        institution="清华大学深圳国际研究生院",
        title="教授",
        assertion_ids=tuple(
            f"assertion:dominant:{index}" for index in range(dominant_assertions)
        ),
    )
    alternative = _stub_professor(
        canonical_id=ALTERNATIVE_ID,
        name="王学谦",
        institution="清华大学美术学院",
        title="副教授",
        assertion_ids=tuple(
            f"assertion:alternative:{index}" for index in range(alternative_assertions)
        ),
    )
    return dominant, alternative


def _institution_catalog() -> InstitutionCatalog:
    return InstitutionCatalog(
        catalog_id="institution-catalog:s12b-ambiguity",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(
            InstitutionCatalogEntry(
                canonical_id="institution:tsinghua",
                canonical_name="清华大学",
                aliases=("清华",),
            ),
            InstitutionCatalogEntry(
                canonical_id="institution:pku",
                canonical_name="北京大学",
                aliases=("北大",),
            ),
        ),
    )


def _serving_planner(
    inputs: Any,
    professors: tuple[Any, ...],
    *,
    with_ambiguity_policy: bool = True,
    catalog: Any | None = None,
) -> Any:
    catalog = catalog if catalog is not None else _catalog()
    delegate = create_ephemeral_query_planner(
        planning_policy=inputs.planning_policy,
        institution_catalog=catalog,
        proposal_provider=inputs.proposal_provider,
    )
    ambiguity_delegate = (
        create_ephemeral_query_planner(
            planning_policy=inputs.planning_policy,
            institution_catalog=catalog,
            proposal_provider=inputs.proposal_provider,
            ambiguity_policy=inputs.ambiguity_policy,
        )
        if with_ambiguity_policy
        else None
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
        ambiguity_delegate=ambiguity_delegate,
        named_professor_projections=professors,
        institution_catalog=catalog,
    )


def _plan(planner: Any, query: str, *, token: str) -> Any:
    return planner.plan(
        QueryPlanningRequest(
            request_id=f"query-request:serving-ambiguity:{token}",
            release_id=RELEASE_ID,
            original_query=query,
            as_of=NOW,
        )
    )


def _professor_evidence(
    *,
    canonical_id: str,
    institution: str,
    title: str,
    token: str,
) -> EvidenceItem:
    snippet = json.dumps(
        {
            "name": "王学谦",
            "institution": institution,
            "title": title,
            "profile_summary": f"{institution}{title}王学谦，有公开成果记录。",
        },
        ensure_ascii=False,
    )
    return EvidenceItem(
        evidence_id=f"evidence:serving-ambiguity:{token}",
        object_id=canonical_id,
        domain="professor",
        lane="exact",
        source_nature="local",
        source_authority="canonical_release",
        source_locator=f"canonical-v2-isolated:{token}",
        snippet=snippet,
        score=1.0,
        observed_at=NOW,
        claim_binding=EvidenceClaimBinding(
            subject_id=canonical_id,
            predicate="canonical_projection",
            value="a" * 64,
            status="admitted",
        ),
    )


def _professor_candidate(*, canonical_id: str, token: str, evidence: Any) -> Any:
    return RecallCandidate(
        raw_candidate_id=f"raw-candidate:serving-ambiguity:{token}",
        display_name="王学谦",
        domain="professor",
        identity_kind="canonical",
        canonical_id=canonical_id,
        resolution_state="resolved",
        query_view="view:original",
        lane="exact",
        attempt=1,
        release_id=RELEASE_ID,
        adapter_version="canonical-v2-isolated-exact-lookup-v1",
        provider_version=None,
        raw_score=1.0,
        evidence=(evidence,),
    )


def _execute_read(inputs: Any, plan: Any, candidates: tuple[Any, ...]) -> Any:
    def exact_adapter(_: Any) -> Any:
        return RetrievalLaneResult(candidates=candidates)

    def empty_lane(_: Any) -> Any:
        return RetrievalLaneResult()

    read = create_ephemeral_knowledge_read(
        lane_adapters={
            "exact": exact_adapter,
            "structured": empty_lane,
            "lexical": empty_lane,
            "vector": empty_lane,
            "web": empty_lane,
        },
        universal_web_policy=inputs.universal_web_policy,
    )
    return read.execute(plan)


def _answer(inputs: Any, query: str, evidence_set: Any, *, token: str) -> Any:
    return inputs.answer_factory().answer(
        TurnRequest(
            session_id=f"session:serving-ambiguity:{token}",
            turn_id=f"turn:serving-ambiguity:{token}",
            query=query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )


def test_serving_ambiguity_policy_is_versioned_and_release_bound(
    tmp_path: Path,
) -> None:
    inputs = _load_inputs(tmp_path)

    policy = inputs.ambiguity_policy
    assert policy is not None
    assert policy.policy_id == f"ambiguity-policy:serving:{RELEASE_ID}"
    assert policy.policy_version == "canonical-v2-serving-ambiguity-v1"
    assert policy.entity_type == "professor"
    assert policy.minimum_evidence_count == 1
    assert 0.0 < policy.confidence_threshold <= 1.0
    assert 0.0 < policy.minimum_lead_margin <= 1.0


def test_same_name_professors_with_dominant_candidate_interprets_with_switch_option(
    tmp_path: Path,
) -> None:
    inputs = _load_inputs(tmp_path)
    dominant, alternative = _same_name_professors(
        dominant_assertions=4,
        alternative_assertions=1,
    )
    planner = _serving_planner(inputs, (dominant, alternative))

    plan = _plan(planner, SAME_NAME_QUERY, token="dominant")

    decision = plan.ambiguity_decision
    assert decision is not None
    assert decision.mode == "non_blocking"
    assert decision.reason_code == "dominant_candidate"
    assert decision.selected_canonical_id == DOMINANT_ID
    assert decision.policy_sha256 == inputs.ambiguity_policy.content_sha256
    assert plan.interaction_mode == "information_retrieval"
    assert plan.lanes

    evidence_set = _execute_read(
        inputs,
        plan,
        (
            _professor_candidate(
                canonical_id=DOMINANT_ID,
                token="dominant",
                evidence=_professor_evidence(
                    canonical_id=DOMINANT_ID,
                    institution="清华大学深圳国际研究生院",
                    title="教授",
                    token="dominant",
                ),
            ),
            _professor_candidate(
                canonical_id=ALTERNATIVE_ID,
                token="alternative",
                evidence=_professor_evidence(
                    canonical_id=ALTERNATIVE_ID,
                    institution="清华大学美术学院",
                    title="副教授",
                    token="alternative",
                ),
            ),
        ),
    )
    successor = evidence_set.ambiguity_decision
    assert successor is not None
    assert successor.outcome == "selected"
    assert successor.selected_handle_id == DOMINANT_ID
    assert successor.viable_alternative_handle_ids == (ALTERNATIVE_ID,)
    assert tuple(handle.canonical_id for handle in evidence_set.entity_handles) == (
        DOMINANT_ID,
    )
    assert all(item.object_id == DOMINANT_ID for item in evidence_set.items)

    result = _answer(inputs, SAME_NAME_QUERY, evidence_set, token="dominant")
    assert result.response_mode == "answer"
    assert result.interpretation_notice is not None
    assert result.interpretation_notice.selected_handle_id == DOMINANT_ID
    assert result.interpretation_notice.decision_trace_id == (
        successor.decision_trace_id
    )
    assert result.continuation_offer is not None
    assert result.continuation_offer.reasons == ("ambiguity",)
    switch_options = tuple(
        option
        for option in result.continuation_offer.options
        if option.operation == "switch_candidate"
    )
    assert len(switch_options) == 1
    assert switch_options[0].target_handle_ids == (ALTERNATIVE_ID,)
    assert "清华大学美术学院" in switch_options[0].discriminator
    assert result.claims
    assert all(claim.subject_id == DOMINANT_ID for claim in result.claims)
    assert "清华大学深圳国际研究生院" in result.answer_text
    assert "清华大学美术学院" not in result.answer_text
    assert result.context_receipt is not None
    assert result.context_receipt.ambiguity_decision_trace_ids == (
        successor.decision_trace_id,
    )


def test_same_name_professors_without_margin_clarify_only(tmp_path: Path) -> None:
    inputs = _load_inputs(tmp_path)
    dominant, alternative = _same_name_professors(
        dominant_assertions=2,
        alternative_assertions=2,
    )
    planner = _serving_planner(inputs, (dominant, alternative))

    plan = _plan(planner, SAME_NAME_QUERY, token="balanced")

    decision = plan.ambiguity_decision
    assert decision is not None
    assert decision.mode == "blocking"
    assert decision.reason_code == "multiple_candidates"
    assert decision.selected_canonical_id is None
    assert plan.interaction_mode == "blocking_clarification"
    assert plan.lanes == ()

    evidence_set = _execute_read(inputs, plan, ())
    successor = evidence_set.ambiguity_decision
    assert successor is not None
    assert successor.outcome == "blocked"
    assert evidence_set.items == ()
    handle_ids = {handle.canonical_id for handle in evidence_set.entity_handles}
    assert handle_ids == {DOMINANT_ID, ALTERNATIVE_ID}
    assert {candidate.handle_id for candidate in successor.candidates} == handle_ids
    assert all(candidate.viable for candidate in successor.candidates)
    assert set(successor.viable_alternative_handle_ids) == handle_ids

    result = _answer(inputs, SAME_NAME_QUERY, evidence_set, token="balanced")
    assert result.response_mode == "clarification_only"
    assert result.claims == ()
    assert result.interpretation_notice is None
    offer = result.continuation_offer
    assert offer is not None
    assert offer.selection_kind == "clarification_selection"
    assert len(offer.options) == 2
    assert all(option.operation == "select_candidate" for option in offer.options)
    assert {
        target for option in offer.options for target in option.target_handle_ids
    } == handle_ids
    discriminators = {option.discriminator for option in offer.options}
    assert any(
        discriminator is not None and "清华大学深圳国际研究生院" in discriminator
        for discriminator in discriminators
    )
    assert any(
        discriminator is not None and "清华大学美术学院" in discriminator
        for discriminator in discriminators
    )
    assert "evidenced candidates" in result.answer_text


def test_blocked_clarification_offer_survives_the_prose_render_path(
    tmp_path: Path,
) -> None:
    inputs = _load_inputs(tmp_path)
    dominant, alternative = _same_name_professors(
        dominant_assertions=2,
        alternative_assertions=2,
    )
    planner = _serving_planner(inputs, (dominant, alternative))
    plan = _plan(planner, SAME_NAME_QUERY, token="balanced-prose")
    evidence_set = _execute_read(inputs, plan, ())

    inputs_with_prose = load_recorded_serving_inputs(
        prose_renderer=lambda _: ProseSynthesisResult(
            answer_text="目前记录到多位同名教授，请选择您想了解的那一位。",
            selected_claim_ids=(),
            selected_handle_ids=(),
        ),
        path=_write_bundle(tmp_path)[0],
        expected_content_sha256=_write_bundle(tmp_path)[1].content_sha256,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12b_test",
        expected_index_root=(tmp_path / "index").resolve(),
        expected_envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_adapter=_Embedding(),
        clock=lambda: NOW,
    )
    result = inputs_with_prose.answer_factory().answer(
        TurnRequest(
            session_id="session:serving-ambiguity:balanced-prose",
            turn_id="turn:serving-ambiguity:balanced-prose:1",
            query=SAME_NAME_QUERY,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )

    assert result.render_mode == "prose_renderer"
    assert result.response_mode == "clarification_only"
    offer = result.continuation_offer
    assert offer is not None
    assert offer.selection_kind == "clarification_selection"
    assert len(offer.options) == 2
    assert {
        target for option in offer.options for target in option.target_handle_ids
    } == {DOMINANT_ID, ALTERNATIVE_ID}


def test_blocked_clarification_selection_executes_to_the_chosen_candidate(
    tmp_path: Path,
) -> None:
    inputs = _load_inputs(tmp_path)
    dominant, alternative = _same_name_professors(
        dominant_assertions=2,
        alternative_assertions=2,
    )
    planner = _serving_planner(inputs, (dominant, alternative))
    plan = _plan(planner, SAME_NAME_QUERY, token="balanced-select")
    evidence_set = _execute_read(inputs, plan, ())

    answer = inputs.answer_factory()
    session_id = "session:serving-ambiguity:balanced-select"
    first = answer.answer(
        TurnRequest(
            session_id=session_id,
            turn_id="turn:serving-ambiguity:balanced-select:1",
            query=SAME_NAME_QUERY,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )
    offer = first.continuation_offer
    assert offer is not None
    option = next(
        value
        for value in offer.options
        if value.target_handle_ids == (ALTERNATIVE_ID,)
    )

    alternative_evidence = _professor_evidence(
        canonical_id=ALTERNATIVE_ID,
        institution="清华大学美术学院",
        title="副教授",
        token="alternative",
    )
    second = answer.answer(
        TurnRequest(
            session_id=session_id,
            turn_id="turn:serving-ambiguity:balanced-select:2",
            query=SAME_NAME_QUERY,
            release_id=RELEASE_ID,
            evidence_set=evidence_set.model_copy(
                update={
                    "items": (alternative_evidence,),
                    "entity_handles": (
                        *evidence_set.entity_handles,
                        isolated_read_module.CanonicalEntityHandle(
                            canonical_id=ALTERNATIVE_ID,
                            domain="professor",
                            display_name="王学谦",
                            evidence_ids=(alternative_evidence.evidence_id,),
                        ),
                    ),
                }
            ),
            continuation_selection=ContinuationSelection(
                offer_id=offer.offer_id,
                option_id=option.option_id,
            ),
        )
    )

    assert second.context_receipt is not None
    assert second.context_receipt.active_anchor is not None
    assert second.context_receipt.active_anchor.canonical_id == ALTERNATIVE_ID
    assert second.claims
    assert all(
        ALTERNATIVE_ID in claim.subject_handle_ids for claim in second.claims
    )


def test_unambiguous_same_name_query_is_unaffected(tmp_path: Path) -> None:
    inputs = _load_inputs(tmp_path)
    dominant, alternative = _same_name_professors()
    unique = _stub_professor(
        canonical_id="professor-c-li-lei",
        name="李雷",
        institution="清华大学计算机系",
        title="教授",
        assertion_ids=("assertion:unique:1",),
    )
    planner = _serving_planner(inputs, (dominant, alternative, unique))

    plan = _plan(planner, "清华的李雷的评价如何", token="unique")

    assert plan.ambiguity_decision is None
    assert plan.interaction_mode == "information_retrieval"
    assert plan.lanes

    evidence_set = _execute_read(
        inputs,
        plan,
        (
            _professor_candidate(
                canonical_id="professor-c-li-lei",
                token="unique",
                evidence=_professor_evidence(
                    canonical_id="professor-c-li-lei",
                    institution="清华大学计算机系",
                    title="教授",
                    token="unique",
                ),
            ),
        ),
    )
    assert evidence_set.ambiguity_decision is None

    result = _answer(inputs, "清华的李雷的评价如何", evidence_set, token="unique")
    assert result.response_mode == "answer"
    assert result.interpretation_notice is None
    assert "清华大学计算机系" in result.answer_text


def test_gate_absent_without_policy_preserves_legacy_planning(tmp_path: Path) -> None:
    inputs = _load_inputs(tmp_path)
    dominant, alternative = _same_name_professors(
        dominant_assertions=2,
        alternative_assertions=2,
    )
    planner = _serving_planner(
        inputs,
        (dominant, alternative),
        with_ambiguity_policy=False,
    )

    plan = _plan(planner, SAME_NAME_QUERY, token="legacy")

    assert plan.ambiguity_decision is None
    assert plan.interaction_mode == "information_retrieval"
    assert plan.lanes


def test_institution_constraint_selects_matching_same_name_professor(
    tmp_path: Path,
) -> None:
    inputs = _load_inputs(tmp_path)
    tsinghua = _stub_professor(
        canonical_id="professor-c-wang-tsinghua",
        name="王学谦",
        institution="清华大学",
        title="教授",
        assertion_ids=tuple(f"assertion:tsinghua:{index}" for index in range(3)),
    )
    pku = _stub_professor(
        canonical_id="professor-c-wang-pku",
        name="王学谦",
        institution="北京大学",
        title="教授",
        assertion_ids=tuple(f"assertion:pku:{index}" for index in range(4)),
    )
    planner = _serving_planner(
        inputs,
        (tsinghua, pku),
        catalog=_institution_catalog(),
    )

    constrained = _plan(planner, SAME_NAME_QUERY, token="institution-constrained")

    assert constrained.ambiguity_decision is None
    assert constrained.interaction_mode == "information_retrieval"
    assert constrained.lanes
    assert any(
        slot.resolution_state == "resolved"
        and slot.canonical_id == "institution:tsinghua"
        for slot in constrained.institution_slots
    )

    evidence_set = _execute_read(
        inputs,
        constrained,
        (
            _professor_candidate(
                canonical_id="professor-c-wang-tsinghua",
                token="tsinghua",
                evidence=_professor_evidence(
                    canonical_id="professor-c-wang-tsinghua",
                    institution="清华大学",
                    title="教授",
                    token="tsinghua",
                ),
            ),
        ),
    )
    result = _answer(inputs, SAME_NAME_QUERY, evidence_set, token="constrained")
    assert result.response_mode == "answer"
    assert result.interpretation_notice is None
    assert "清华大学" in result.answer_text

    unconstrained = _plan(planner, "王学谦", token="institution-unconstrained")
    decision = unconstrained.ambiguity_decision
    assert decision is not None
    assert decision.mode == "non_blocking"
    assert decision.selected_canonical_id == "professor-c-wang-pku"


def test_institution_constraint_without_match_attaches_no_candidates(
    tmp_path: Path,
) -> None:
    inputs = _load_inputs(tmp_path)
    pku = _stub_professor(
        canonical_id="professor-c-wang-pku",
        name="王学谦",
        institution="北京大学",
        title="教授",
        assertion_ids=("assertion:pku:1", "assertion:pku:2"),
    )
    fudan = _stub_professor(
        canonical_id="professor-c-wang-fudan",
        name="王学谦",
        institution="复旦大学",
        title="副教授",
        assertion_ids=("assertion:fudan:1", "assertion:fudan:2"),
    )
    planner = _serving_planner(
        inputs,
        (pku, fudan),
        catalog=_institution_catalog(),
    )

    plan = _plan(planner, SAME_NAME_QUERY, token="institution-no-match")

    assert plan.ambiguity_decision is None
    assert plan.interaction_mode == "information_retrieval"
    assert plan.lanes


def test_standalone_person_query_shapes_reach_the_gate(tmp_path: Path) -> None:
    inputs = _load_inputs(tmp_path)
    dominant, alternative = _same_name_professors(
        dominant_assertions=2,
        alternative_assertions=2,
    )
    planner = _serving_planner(inputs, (dominant, alternative))
    expected_candidates = {
        f"ambiguity-candidate:{DOMINANT_ID}",
        f"ambiguity-candidate:{ALTERNATIVE_ID}",
    }

    for token, query in (
        ("bare-intro", "介绍王学谦"),
        ("who-is", "王学谦是谁"),
        ("profile", "王学谦简介"),
    ):
        plan = _plan(planner, query, token=token)
        decision = plan.ambiguity_decision
        assert decision is not None, query
        assert decision.mode == "blocking", query
        assert decision.reason_code == "multiple_candidates", query
        assert set(decision.qualifying_candidate_ids) == expected_candidates, query
        assert plan.interaction_mode == "blocking_clarification", query
        assert plan.lanes == (), query
