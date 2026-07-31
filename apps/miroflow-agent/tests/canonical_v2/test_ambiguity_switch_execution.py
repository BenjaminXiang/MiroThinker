"""Execution of the Canonical V2 same-name ``switch_candidate`` continuation.

The serving ambiguity gate answers with the dominant same-name Professor and
offers a bounded switch option targeting the viable alternative. These tests
prove the offered switch actually executes end to end: the selection turn
re-plans with the option's canonical targets bound as the displayed entity
scope (the chat adapter's selection-turn contract, which replaces rather than
narrows the anchor), retrieval fetches the alternative's evidence, the answer
session registers its handle, and the continuation selection re-anchors. A
switch whose target has no retrievable evidence surfaces an honest limitation
instead of a silent anchor no-op. Hermetic: no live LLM, Web, or DB.
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
    TurnRequest,
)
from src.data_agents.canonical_v2.knowledge_read import (
    EvidenceClaimBinding,
    EvidenceItem,
    InstitutionCatalog,
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
DOMINANT_INSTITUTION = "清华大学深圳国际研究生院"
ALTERNATIVE_INSTITUTION = "清华大学美术学院"
SESSION_ID = "session:switch-execution:test"


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


def _same_name_professors() -> tuple[Any, Any]:
    dominant = _stub_professor(
        canonical_id=DOMINANT_ID,
        name="王学谦",
        institution=DOMINANT_INSTITUTION,
        title="教授",
        assertion_ids=tuple(f"assertion:dominant:{index}" for index in range(4)),
    )
    alternative = _stub_professor(
        canonical_id=ALTERNATIVE_ID,
        name="王学谦",
        institution=ALTERNATIVE_INSTITUTION,
        title="副教授",
        assertion_ids=("assertion:alternative:0",),
    )
    return dominant, alternative


def _serving_planner(inputs: Any, professors: tuple[Any, ...]) -> Any:
    catalog = _catalog()
    delegate = create_ephemeral_query_planner(
        planning_policy=inputs.planning_policy,
        institution_catalog=catalog,
        proposal_provider=inputs.proposal_provider,
    )
    ambiguity_delegate = create_ephemeral_query_planner(
        planning_policy=inputs.planning_policy,
        institution_catalog=catalog,
        proposal_provider=inputs.proposal_provider,
        ambiguity_policy=inputs.ambiguity_policy,
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
        evidence_id=f"evidence:switch-execution:{token}",
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
        raw_candidate_id=f"raw-candidate:switch-execution:{token}",
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


def _both_professor_candidates() -> tuple[Any, Any]:
    return (
        _professor_candidate(
            canonical_id=DOMINANT_ID,
            token="dominant",
            evidence=_professor_evidence(
                canonical_id=DOMINANT_ID,
                institution=DOMINANT_INSTITUTION,
                title="教授",
                token="dominant",
            ),
        ),
        _professor_candidate(
            canonical_id=ALTERNATIVE_ID,
            token="alternative",
            evidence=_professor_evidence(
                canonical_id=ALTERNATIVE_ID,
                institution=ALTERNATIVE_INSTITUTION,
                title="副教授",
                token="alternative",
            ),
        ),
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


def _planning_request(
    query: str,
    *,
    token: str,
    displayed_entity_ids: tuple[str, ...] = (),
) -> Any:
    return QueryPlanningRequest(
        request_id=f"query-request:switch-execution:{token}",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
        displayed_entity_ids=displayed_entity_ids,
    )


def _turn_request(
    evidence_set: Any,
    *,
    turn_token: str,
    selection: ContinuationSelection | None = None,
) -> TurnRequest:
    return TurnRequest(
        session_id=SESSION_ID,
        turn_id=f"turn:switch-execution:{turn_token}",
        query=SAME_NAME_QUERY,
        release_id=RELEASE_ID,
        evidence_set=evidence_set,
        continuation_selection=selection,
    )


def _dominant_first_turn(
    inputs: Any,
    planner: Any,
    answer: Any,
) -> tuple[Any, Any]:
    """Turn 1: dominant same-name answer carrying one switch option."""
    first_plan = planner.plan(_planning_request(SAME_NAME_QUERY, token="first"))
    decision = first_plan.ambiguity_decision
    assert decision is not None
    assert decision.mode == "non_blocking"
    assert decision.selected_canonical_id == DOMINANT_ID

    first_evidence = _execute_read(inputs, first_plan, _both_professor_candidates())
    successor = first_evidence.ambiguity_decision
    assert successor is not None
    assert successor.outcome == "selected"
    assert successor.selected_handle_id == DOMINANT_ID
    assert successor.viable_alternative_handle_ids == (ALTERNATIVE_ID,)
    # The non-blocking handoff filters the turn to the dominant candidate: the
    # alternative's handle is never registered by this turn's evidence.
    assert tuple(handle.canonical_id for handle in first_evidence.entity_handles) == (
        DOMINANT_ID,
    )

    first = answer.answer(_turn_request(first_evidence, turn_token="first"))
    assert first.response_mode == "answer"
    assert first.interpretation_notice is not None
    assert first.interpretation_notice.selected_handle_id == DOMINANT_ID
    assert first.continuation_offer is not None
    assert first.continuation_offer.reasons == ("ambiguity",)
    switch_options = tuple(
        option
        for option in first.continuation_offer.options
        if option.operation == "switch_candidate"
    )
    assert len(switch_options) == 1
    assert switch_options[0].target_handle_ids == (ALTERNATIVE_ID,)
    assert first.context_receipt is not None
    assert first.context_receipt.active_anchor is not None
    assert first.context_receipt.active_anchor.canonical_id == DOMINANT_ID
    assert all(claim.subject_id == DOMINANT_ID for claim in first.claims)
    return first, switch_options[0]


def test_switch_candidate_selection_reanchors_to_the_alternative(
    tmp_path: Path,
) -> None:
    inputs = _load_inputs(tmp_path)
    planner = _serving_planner(inputs, _same_name_professors())
    answer = inputs.answer_factory()
    first, switch_option = _dominant_first_turn(inputs, planner, answer)

    # Turn 2: the chat adapter binds the selected option's canonical targets
    # as the planning scope (replacing, not narrowing, the current anchor) and
    # passes the validated continuation selection to the answer session.
    second_plan = planner.plan(
        _planning_request(
            SAME_NAME_QUERY,
            token="second",
            displayed_entity_ids=switch_option.target_handle_ids,
        )
    )
    # The ambiguity gate must not re-fire on the selection turn, and the
    # displayed scope binds only the alternative, never the dominant anchor.
    assert second_plan.ambiguity_decision is None
    assert second_plan.structured_constraints.displayed_entity_ids == (
        ALTERNATIVE_ID,
    )

    second_evidence = _execute_read(inputs, second_plan, _both_professor_candidates())
    # Retrieval is scoped to the switch target: its handle is materialized so
    # the answer session can register it before the selection executes.
    assert tuple(handle.canonical_id for handle in second_evidence.entity_handles) == (
        ALTERNATIVE_ID,
    )

    second = answer.answer(
        _turn_request(
            second_evidence,
            turn_token="second",
            selection=ContinuationSelection(
                offer_id=first.continuation_offer.offer_id,
                option_id=switch_option.option_id,
            ),
        )
    )

    receipt = second.context_receipt
    assert receipt is not None
    assert receipt.active_anchor is not None
    assert receipt.active_anchor.canonical_id == ALTERNATIVE_ID
    assert receipt.transition_kind == "continuation_selection"
    assert receipt.selected_option_id == switch_option.option_id
    assert receipt.selected_operation == "switch_candidate"
    assert receipt.performed_operation is None
    assert second.response_mode == "answer"
    assert second.claims
    assert all(claim.subject_id == ALTERNATIVE_ID for claim in second.claims)
    alternative_evidence_ids = set(second_evidence.entity_handles[0].evidence_ids)
    assert all(
        set(claim.evidence_ids) <= alternative_evidence_ids for claim in second.claims
    )
    assert ALTERNATIVE_INSTITUTION in second.answer_text
    assert DOMINANT_INSTITUTION not in second.answer_text
    assert all(
        limitation.code != "continuation_target_unavailable"
        for limitation in second.limitations
    )


def test_switch_candidate_without_target_evidence_is_an_honest_limitation(
    tmp_path: Path,
) -> None:
    inputs = _load_inputs(tmp_path)
    planner = _serving_planner(inputs, _same_name_professors())
    answer = inputs.answer_factory()
    first, switch_option = _dominant_first_turn(inputs, planner, answer)

    second_plan = planner.plan(
        _planning_request(
            SAME_NAME_QUERY,
            token="second-missing",
            displayed_entity_ids=switch_option.target_handle_ids,
        )
    )
    # The alternative is gone from the release: the exact lane can only return
    # the dominant candidate, which the displayed-entity scope then rejects.
    second_evidence = _execute_read(
        inputs,
        second_plan,
        _both_professor_candidates()[:1],
    )
    assert second_evidence.entity_handles == ()
    assert second_evidence.items == ()

    second = answer.answer(
        _turn_request(
            second_evidence,
            turn_token="second-missing",
            selection=ContinuationSelection(
                offer_id=first.continuation_offer.offer_id,
                option_id=switch_option.option_id,
            ),
        )
    )

    receipt = second.context_receipt
    assert receipt is not None
    # The anchor honestly stays on the dominant candidate and the receipt does
    # not record the selection as if the switch had happened.
    assert receipt.active_anchor is not None
    assert receipt.active_anchor.canonical_id == DOMINANT_ID
    assert receipt.performed_operation == "continuation_target_unavailable"
    assert receipt.selected_option_id is None
    assert receipt.selected_operation is None
    assert receipt.resolved_evidence_ids == ()
    unavailable = tuple(
        limitation
        for limitation in second.limitations
        if limitation.code == "continuation_target_unavailable"
    )
    assert len(unavailable) == 1
    assert unavailable[0].material
    assert unavailable[0].handle_id == ALTERNATIVE_ID
    assert second.claims == ()
    assert second.response_mode == "answer"
    assert ALTERNATIVE_INSTITUTION not in second.answer_text
