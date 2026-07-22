from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_answer"
READ_TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_read"


def _answer_module() -> Any:
    return import_module(TARGET_MODULE)


def _read_module() -> Any:
    return import_module(READ_TARGET_MODULE)


def test_turn_request_and_recorded_selection_are_content_bound_and_fail_closed() -> (
    None
):
    module = _answer_module()
    read_module = _read_module()
    evidence_item = read_module.EvidenceItem(
        evidence_id="evidence:alpha-name",
        object_id="company:alpha",
        domain="company",
        lane="exact",
        source_nature="local",
        source_locator="artifact:company-alpha#name",
        snippet="Alpha Robotics is the accepted Company name.",
        score=1.0,
        claim_binding=read_module.EvidenceClaimBinding(
            subject_id="company:alpha",
            predicate="preferred_name",
            value="Alpha Robotics",
        ),
    )
    evidence_set = read_module.EvidenceSet(
        release_id="candidate-r1",
        original_query="介绍 Alpha Robotics",
        protected_slots=(),
        items=(evidence_item,),
        traces=(),
        limitations=(),
    )
    request = module.TurnRequest(
        session_id="session:s9ag:trust",
        turn_id="turn:s9ag:trust:1",
        query=evidence_set.original_query,
        release_id=evidence_set.release_id,
        evidence_set=evidence_set,
    )
    assert request.content_sha256 != "0" * 64
    assert module.TurnRequest.model_validate(request.model_dump(mode="json")) == request

    changed_query = "介绍 Bound Robotics"
    query_evidence_set = evidence_set.model_copy(
        update={"original_query": changed_query}
    )
    query_request = module.TurnRequest(
        session_id=request.session_id,
        turn_id=request.turn_id,
        query=changed_query,
        release_id=request.release_id,
        evidence_set=query_evidence_set,
    )
    release_evidence_set = evidence_set.model_copy(
        update={"release_id": "candidate-r2"}
    )
    release_request = module.TurnRequest(
        session_id=request.session_id,
        turn_id=request.turn_id,
        query=request.query,
        release_id="candidate-r2",
        evidence_set=release_evidence_set,
    )
    changed_item = evidence_item.model_copy(
        update={"snippet": "Alpha Robotics has a changed evidence payload."}
    )
    changed_evidence_set = evidence_set.model_copy(update={"items": (changed_item,)})
    changed_request = module.TurnRequest(
        session_id=request.session_id,
        turn_id=request.turn_id,
        query=request.query,
        release_id=request.release_id,
        evidence_set=changed_evidence_set,
    )
    assert (
        len(
            {
                request.content_sha256,
                query_request.content_sha256,
                release_request.content_sha256,
                changed_request.content_sha256,
            }
        )
        == 4
    )

    supported_claim = module.MaterialClaimProposal(
        claim_id="claim:alpha-name",
        claim_type="identity",
        text="Alpha Robotics is the accepted Company name.",
        subject_id="company:alpha",
        predicate="preferred_name",
        value="Alpha Robotics",
        subject_handle_ids=("company:alpha",),
        evidence_ids=(evidence_item.evidence_id,),
    )
    valid_constructed_proposal = module.AnswerSelectionProposal.model_construct(
        selection_input_sha256=request.content_sha256,
        schema_version="answer-selection-v1",
        decision_id="answer-selection:valid-constructed",
        model_id="recorded-answer-selector",
        prompt_version="answer-selector-prompt-v1",
        decision_run_id="answer-selector-run:valid-constructed",
        answer_text="Alpha Robotics is the accepted Company name.",
        claims=(supported_claim,),
        displayed_handle_ids=(),
        displayed_entity_ids=(),
        coverage_claim=None,
        continuation_candidate_ids=(),
    )
    selector_calls: list[str] = []

    def recording_selector(value: Any) -> Any:
        selector_calls.append(value.turn_id)
        return valid_constructed_proposal

    boundary_answer = module.create_ephemeral_knowledge_answer(
        answer_selector=recording_selector
    )
    for field, wrong_value in (
        ("query", "介绍另一家公司"),
        ("release_id", "candidate-r2"),
    ):
        values = request.model_dump(mode="python")
        values[field] = wrong_value
        forged_request = module.TurnRequest.model_construct(**values)
        with pytest.raises(
            ValueError, match=("query" if field == "query" else "release")
        ):
            boundary_answer.answer(forged_request)
    for changed_value in (query_request, release_request, changed_request):
        values = changed_value.model_dump(mode="python")
        values["content_sha256"] = request.content_sha256
        forged_request = module.TurnRequest.model_construct(**values)
        with pytest.raises(ValueError, match="content_sha256"):
            boundary_answer.answer(forged_request)
    assert selector_calls == []

    forged_evidence_set = read_module.EvidenceSet.model_construct(
        release_id=evidence_set.release_id,
        original_query=evidence_set.original_query,
        protected_slots=(),
        items=("not-an-evidence-item",),
        traces=(),
        limitations=(),
    )
    with pytest.raises(ValueError, match="evidence"):
        module.TurnRequest(
            session_id=request.session_id,
            turn_id="turn:s9ag:forged-evidence",
            query=request.query,
            release_id=request.release_id,
            evidence_set=forged_evidence_set,
        )

    accepted = module.create_ephemeral_knowledge_answer(
        answer_selector=lambda _: valid_constructed_proposal
    ).answer(request)
    assert tuple(claim.claim_id for claim in accepted.claims) == (
        supported_claim.claim_id,
    )
    assert accepted.claims[0].evidence_ids == (evidence_item.evidence_id,)

    def proposal(
        *,
        selection_input_sha256: str = request.content_sha256,
        schema_version: str = "answer-selection-v1",
        claims: tuple[Any, ...] = (supported_claim,),
        answer_text: str,
    ) -> Any:
        return module.AnswerSelectionProposal.model_construct(
            selection_input_sha256=selection_input_sha256,
            schema_version=schema_version,
            decision_id=f"answer-selection:{answer_text}",
            model_id="recorded-answer-selector",
            prompt_version="answer-selector-prompt-v1",
            decision_run_id=f"answer-selector-run:{answer_text}",
            answer_text=answer_text,
            claims=claims,
            displayed_handle_ids=(),
            displayed_entity_ids=(),
            coverage_claim=None,
            continuation_candidate_ids=(),
        )

    unsupported_claim = module.MaterialClaimProposal(
        claim_id="claim:model-memory",
        text="A model-memory claim must not survive.",
        subject_handle_ids=("company:alpha",),
        evidence_ids=("model-memory:alpha",),
    )
    hostile_cases = (
        (
            proposal(
                selection_input_sha256="f" * 64,
                answer_text="poisoned wrong-input draft",
            ),
            "input_binding_mismatch",
        ),
        (
            proposal(
                schema_version="answer-selection-v999",
                answer_text="poisoned wrong-schema draft",
            ),
            "schema_mismatch",
        ),
        (
            proposal(
                claims=("not-a-material-claim",),
                answer_text="poisoned invalid-output draft",
            ),
            "invalid_output",
        ),
        (
            proposal(
                claims=(unsupported_claim,),
                answer_text="poisoned unsupported-claim draft",
            ),
            "unsupported_material_claim",
        ),
    )
    for hostile_proposal, expected_failure_kind in hostile_cases:
        degraded = module.create_ephemeral_knowledge_answer(
            answer_selector=lambda _, value=hostile_proposal: value
        ).answer(request)
        assert degraded.claims == ()
        assert degraded.claim_evidence_map == ()
        assert degraded.citations == ()
        assert hostile_proposal.answer_text not in degraded.answer_text
        assert hostile_proposal.answer_text not in degraded.model_dump_json()
        matching_limitations = tuple(
            limitation
            for limitation in degraded.limitations
            if limitation.code == "answer_selection_rejected"
        )
        assert len(matching_limitations) == 1
        assert matching_limitations[0].reason == expected_failure_kind
        assert matching_limitations[0].material is True

    poisoned_handle = read_module.CanonicalEntityHandle(
        kind="canonical",
        canonical_id="company:alpha",
        domain="company",
        display_name="Alpha Robotics",
        evidence_ids=(evidence_item.evidence_id,),
    )
    poisoned_candidate = read_module.ContinuationCandidate(
        candidate_id="continuation:poisoned",
        reason="eligible_next_hop",
        label="Follow a poisoned next hop",
        operation="traverse_relationship",
        target_kind="current_handle",
        target_handle_ids=(poisoned_handle.canonical_id,),
        constraint_pairs=(),
        relation_type="company_has_product",
        coverage_state=None,
        evidence_ids=(evidence_item.evidence_id,),
        available=True,
    )
    stateful_evidence_set = evidence_set.model_copy(
        update={
            "entity_handles": (poisoned_handle,),
            "continuation_candidates": (poisoned_candidate,),
        }
    )
    stateful_request = module.TurnRequest(
        session_id="session:s9ag:state-rejection",
        turn_id="turn:s9ag:state-rejection:1",
        query=stateful_evidence_set.original_query,
        release_id=stateful_evidence_set.release_id,
        evidence_set=stateful_evidence_set,
    )
    stateful_hostile_proposal = module.AnswerSelectionProposal(
        selection_input_sha256=stateful_request.content_sha256,
        schema_version="answer-selection-v1",
        decision_id="answer-selection:stateful-hostile",
        model_id="recorded-answer-selector",
        prompt_version="answer-selector-prompt-v1",
        decision_run_id="answer-selector-run:stateful-hostile",
        answer_text="A poisoned proposal must not establish answer or session state.",
        claims=(unsupported_claim,),
        displayed_handle_ids=(poisoned_handle.canonical_id,),
        continuation_candidate_ids=(poisoned_candidate.candidate_id,),
    )

    def stateful_selector(value: Any) -> Any:
        if value.turn_id == stateful_request.turn_id:
            return stateful_hostile_proposal
        return module.AnswerSelectionProposal(
            selection_input_sha256=value.content_sha256,
            schema_version="answer-selection-v1",
            decision_id="answer-selection:state-rejection-followup",
            model_id="recorded-answer-selector",
            prompt_version="answer-selector-prompt-v1",
            decision_run_id="answer-selector-run:state-rejection-followup",
            answer_text="No prior state is available.",
        )

    stateful_answer = module.create_ephemeral_knowledge_answer(
        answer_selector=stateful_selector
    )
    stateful_rejection = stateful_answer.answer(stateful_request)
    assert stateful_rejection.claims == ()
    assert stateful_rejection.continuation_offer is None
    assert stateful_hostile_proposal.answer_text not in stateful_rejection.answer_text
    assert any(
        limitation.code == "answer_selection_rejected"
        and limitation.reason == "unsupported_material_claim"
        for limitation in stateful_rejection.limitations
    )

    followup_query = "它还有什么信息？"
    followup_request = module.TurnRequest(
        session_id=stateful_request.session_id,
        turn_id="turn:s9ag:state-rejection:2",
        query=followup_query,
        release_id=stateful_request.release_id,
        evidence_set=read_module.EvidenceSet(
            release_id=stateful_request.release_id,
            original_query=followup_query,
            protected_slots=(),
            items=(),
            traces=(),
            limitations=(),
        ),
    )
    followup = stateful_answer.answer(followup_request)
    assert followup.context_receipt is not None
    assert followup.context_receipt.active_anchor is None
    assert followup.context_receipt.displayed_result_set is None
    assert followup.context_receipt.resolved_referent is None
