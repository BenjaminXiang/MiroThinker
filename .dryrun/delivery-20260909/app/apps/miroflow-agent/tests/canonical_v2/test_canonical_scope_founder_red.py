from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving_module
from src.data_agents.canonical_v2.knowledge_answer import (
    AnswerSelectionProposal,
    MaterialClaimProposal,
    SessionDirective,
    TurnRequest,
    create_ephemeral_knowledge_answer,
)
from src.data_agents.canonical_v2.knowledge_read import (
    CanonicalEntityHandle,
    EvidenceClaimBinding,
    EvidenceItem,
    EvidenceSet,
)


NOW = datetime(2026, 8, 6, tzinfo=UTC)
RELEASE_ID = "candidate-canonical-v2-scope-founder-red"


class _RecordedPlainCompletions:
    def __init__(self, *contents: str) -> None:
        self._contents = contents
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        if kwargs.get("stream"):
            raise AssertionError(
                "these regressions exercise synchronous prose rendering"
            )
        call_index = len(self.calls)
        self.calls.append(kwargs)
        if call_index >= len(self._contents):
            raise AssertionError("unexpected extra prose completion")
        return SimpleNamespace(
            choices=(
                SimpleNamespace(
                    message=SimpleNamespace(content=self._contents[call_index]),
                    finish_reason="stop",
                ),
            )
        )


def _plain_renderer(*contents: str) -> tuple[Any, _RecordedPlainCompletions]:
    completions = _RecordedPlainCompletions(*contents)
    renderer = serving_module._OpenAIProseRenderer(
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=completions),
        ),
        model="recorded-chat-model",
        extra_body={"thinking": {"type": "disabled"}},
    )
    return renderer, completions


def _company_fixture(company_id: str, display_name: str) -> tuple[Any, Any]:
    evidence_id = f"evidence:{company_id}"
    item = EvidenceItem(
        evidence_id=evidence_id,
        object_id=company_id,
        domain="company",
        lane="exact",
        source_nature="local",
        source_locator=f"artifact:scope-red#{company_id}",
        snippet=f"{display_name}符合本轮筛选条件。",
        score=1.0,
        observed_at=NOW,
        claim_binding=EvidenceClaimBinding(
            subject_id=company_id,
            predicate="preferred_name",
            value=display_name,
        ),
    )
    handle = CanonicalEntityHandle(
        kind="canonical",
        canonical_id=company_id,
        domain="company",
        display_name=display_name,
        evidence_ids=(evidence_id,),
    )
    return item, handle


def _evidence_set(
    query: str,
    *,
    items: tuple[Any, ...] = (),
    handles: tuple[Any, ...] = (),
) -> EvidenceSet:
    return EvidenceSet(
        release_id=RELEASE_ID,
        original_query=query,
        protected_slots=(),
        items=items,
        traces=(),
        limitations=(),
        entity_handles=handles,
    )


def _proposal(
    request: TurnRequest,
    *,
    displayed_handle_ids: tuple[str, ...] = (),
    claims: tuple[MaterialClaimProposal, ...] = (),
) -> AnswerSelectionProposal:
    return AnswerSelectionProposal(
        selection_input_sha256=request.content_sha256,
        schema_version="answer-selection-v1",
        decision_id=f"answer-selection:{request.turn_id}",
        model_id="recorded-answer-selector",
        prompt_version="answer-selector-prompt-v1",
        decision_run_id=f"answer-selector-run:{request.turn_id}",
        answer_text=f"Recorded grounded answer for {request.turn_id}",
        claims=claims,
        displayed_handle_ids=displayed_handle_ids,
    )


def test_plain_prose_fallback_does_not_commit_wider_retrieved_scope() -> None:
    """Unframed prose has no entity selection and must not widen later “这些”."""
    session_id = "session:plain-prose-scope-red"
    visible_id = "company:scope-visible"
    hidden_ids = ("company:scope-hidden-a", "company:scope-hidden-b")
    fixtures = (
        _company_fixture(visible_id, "聚光科技"),
        _company_fixture(hidden_ids[0], "隐域甲公司"),
        _company_fixture(hidden_ids[1], "隐域乙公司"),
    )
    items = tuple(item for item, _handle in fixtures)
    handles = tuple(handle for _item, handle in fixtures)
    displayed_ids = (visible_id, *hidden_ids)

    first_query = "哪些公司符合条件"
    first_request = TurnRequest(
        session_id=session_id,
        turn_id="turn:plain-prose-scope:1",
        query=first_query,
        release_id=RELEASE_ID,
        evidence_set=_evidence_set(first_query, items=items, handles=handles),
    )
    follow_up_query = "这些公司还有哪些共同点"
    follow_up_request = TurnRequest(
        session_id=session_id,
        turn_id="turn:plain-prose-scope:2",
        query=follow_up_query,
        release_id=RELEASE_ID,
        evidence_set=_evidence_set(follow_up_query),
        session_directive=SessionDirective(referent="displayed_result_set"),
    )

    def selector(request: TurnRequest) -> AnswerSelectionProposal:
        if request.turn_id == first_request.turn_id:
            return _proposal(
                request,
                displayed_handle_ids=displayed_ids,
                claims=(
                    MaterialClaimProposal(
                        claim_id="claim:scope-visible",
                        text="聚光科技符合本轮筛选条件。",
                        subject_id=visible_id,
                        predicate="preferred_name",
                        value="聚光科技",
                        subject_handle_ids=(visible_id,),
                        evidence_ids=(items[0].evidence_id,),
                    ),
                ),
            )
        return _proposal(request)

    renderer, completions = _plain_renderer(
        "可确认聚光科技符合条件。",
        "在没有可安全解析的已展示范围时，不应扩展主体。",
    )
    answer = create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=renderer,
    )

    first = answer.answer(first_request)
    follow_up = answer.answer(follow_up_request)

    assert first.render_mode == "prose_renderer"
    assert first.answer_text == "可确认聚光科技符合条件。"
    assert all(handle.display_name not in first.answer_text for handle in handles[1:])
    assert follow_up.render_mode == "prose_renderer"
    assert len(completions.calls) == 2
    resolved = follow_up.context_receipt.resolved_referent
    resolved_ids = () if resolved is None else resolved.handle_ids
    assert resolved_ids == (), (
        "plain prose supplied no selection metadata, but the next-turn "
        f"displayed_result_set leaked selector-only handles: {resolved_ids!r}"
    )


def test_founder_prefix_uses_handles_bound_to_the_same_claim() -> None:
    """The transport prefix must not pair unrelated first professor/company handles."""
    decoy_professor = SimpleNamespace(
        canonical_id="professor:decoy",
        display_name="诱饵教授",
        domain="professor",
        evidence_ids=("evidence:decoy-professor",),
    )
    decoy_company = SimpleNamespace(
        canonical_id="company:decoy",
        display_name="诱饵公司",
        domain="company",
        evidence_ids=("evidence:decoy-company",),
    )
    bound_professor = SimpleNamespace(
        canonical_id="professor:bound",
        display_name="正确教授",
        domain="professor",
        evidence_ids=("evidence:founder",),
    )
    bound_company = SimpleNamespace(
        canonical_id="company:bound",
        display_name="正确公司",
        domain="company",
        evidence_ids=("evidence:founder",),
    )
    founder_claim = SimpleNamespace(
        claim_id="claim:founder-bound-pair",
        text="正确教授参与创立了正确公司。",
        subject_id=bound_professor.canonical_id,
        subject_handle_ids=(
            bound_professor.canonical_id,
            bound_company.canonical_id,
        ),
        predicate="professor_company_role",
        status="accepted",
        source_natures=("local",),
        evidence_ids=("evidence:founder",),
    )
    result = SimpleNamespace(
        original_query="他参与创立了哪家公司？",
        claims=(founder_claim,),
        citations=(),
        context_receipt=SimpleNamespace(
            active_anchor=decoy_professor,
            displayed_result_set=SimpleNamespace(
                handles=(decoy_company, bound_professor, bound_company),
            ),
            traversed_path_ids=(),
        ),
    )
    renderer, completions = _plain_renderer(
        "公开信息可确认该关系。",
        # The first answer never names the anchor, so the bounded correction
        # retry re-asks once; the retry's answer names it and is published.
        "诱饵教授公开信息可确认该关系。",
    )

    rendered = renderer(result)

    assert len(completions.calls) == 2
    assert rendered == "正确教授参与创立了正确公司。\n\n诱饵教授公开信息可确认该关系。"


def test_plain_prose_restores_prior_structured_scope_and_receipt() -> None:
    """A plain turn restores the last entity scope confirmed by framed prose."""
    session_id = "session:plain-prose-prior-scope-red"
    visible_id = "company:prior-visible"
    hidden_ids = ("company:prior-hidden-a", "company:prior-hidden-b")
    fixtures = (
        _company_fixture(visible_id, "先前确认公司"),
        _company_fixture(hidden_ids[0], "本轮宽召回甲公司"),
        _company_fixture(hidden_ids[1], "本轮宽召回乙公司"),
    )
    items = tuple(item for item, _handle in fixtures)
    handles = tuple(handle for _item, handle in fixtures)

    first_query = "先确认一家公司"
    first_request = TurnRequest(
        session_id=session_id,
        turn_id="turn:plain-prose-prior-scope:1",
        query=first_query,
        release_id=RELEASE_ID,
        evidence_set=_evidence_set(first_query, items=items, handles=handles),
    )
    plain_query = "再做一次宽召回"
    plain_request = TurnRequest(
        session_id=session_id,
        turn_id="turn:plain-prose-prior-scope:2",
        query=plain_query,
        release_id=RELEASE_ID,
        evidence_set=_evidence_set(plain_query, items=items, handles=handles),
    )
    follow_up_query = "这些公司还有哪些共同点"
    follow_up_request = TurnRequest(
        session_id=session_id,
        turn_id="turn:plain-prose-prior-scope:3",
        query=follow_up_query,
        release_id=RELEASE_ID,
        evidence_set=_evidence_set(follow_up_query),
        session_directive=SessionDirective(referent="displayed_result_set"),
    )

    def selector(request: TurnRequest) -> AnswerSelectionProposal:
        if request.turn_id == first_request.turn_id:
            return _proposal(
                request,
                displayed_handle_ids=(visible_id, hidden_ids[0]),
                claims=(
                    MaterialClaimProposal(
                        claim_id="claim:prior-visible",
                        text="先前确认公司符合条件。",
                        subject_id=visible_id,
                        predicate="preferred_name",
                        value="先前确认公司",
                        subject_handle_ids=(visible_id,),
                        evidence_ids=(items[0].evidence_id,),
                    ),
                ),
            )
        if request.turn_id == plain_request.turn_id:
            return _proposal(request, displayed_handle_ids=hidden_ids)
        return _proposal(request)

    first_wire = (
        "<|canonical_v2_selection_v1|>\n"
        '{"selected_claim_indexes":[1],"selected_entity_indexes":[1]}\n'
        "<|canonical_v2_answer_v1|>\n先前确认公司符合条件。"
    )
    renderer, completions = _plain_renderer(
        first_wire,
        # Turns 2 and 3 never name the anchor 先前确认公司, so each pays one
        # correction retry whose anchor-named rewrite is published instead.
        "本轮只能确认一般结论。",
        "先前确认公司本轮只能确认一般结论。",
        "继续沿用先前已确认的公司范围。",
        "先前确认公司继续沿用先前已确认的公司范围。",
    )
    answer = create_ephemeral_knowledge_answer(
        answer_selector=selector,
        prose_renderer=renderer,
    )

    first = answer.answer(first_request)
    plain = answer.answer(plain_request)
    follow_up = answer.answer(follow_up_request)

    first_context = first.context_receipt
    assert first_context is not None
    assert first_context.displayed_result_set is not None
    assert first_context.displayed_result_set.handle_ids == (visible_id,)

    plain_context = plain.context_receipt
    assert plain_context is not None
    assert plain_context.displayed_result_set is not None
    assert plain_context.displayed_result_set.handle_ids == (visible_id,)
    assert plain_context.active_anchor is not None
    assert plain_context.active_anchor.canonical_id == visible_id
    assert plain_context.resolved_referent is None

    follow_up_context = follow_up.context_receipt
    assert follow_up_context is not None
    assert follow_up_context.displayed_result_set is not None
    assert follow_up_context.displayed_result_set.handle_ids == (visible_id,)
    assert follow_up_context.resolved_referent is not None
    assert follow_up_context.resolved_referent.kind == "result_set"
    assert follow_up_context.resolved_referent.handle_ids == (visible_id,)
    assert len(completions.calls) == 5


def test_founder_prefix_rejects_missing_or_ambiguous_claim_bindings() -> None:
    """A founder prefix requires exactly one claim-local professor/company pair."""
    professor = SimpleNamespace(
        canonical_id="professor:founder-a",
        display_name="甲教授",
        domain="professor",
        evidence_ids=("evidence:founder-a",),
    )
    other_professor = SimpleNamespace(
        canonical_id="professor:founder-b",
        display_name="乙教授",
        domain="professor",
        evidence_ids=("evidence:founder-b",),
    )
    company = SimpleNamespace(
        canonical_id="company:founder-a",
        display_name="甲公司",
        domain="company",
        evidence_ids=("evidence:founder-a",),
    )
    other_company = SimpleNamespace(
        canonical_id="company:founder-b",
        display_name="乙公司",
        domain="company",
        evidence_ids=("evidence:founder-b",),
    )

    def founder_claim(
        claim_id: str,
        bound_ids: tuple[str, ...] | None,
    ) -> SimpleNamespace:
        values: dict[str, object] = {
            "claim_id": claim_id,
            "text": "教授参与创立了公司。",
            "subject_id": professor.canonical_id,
            "predicate": "professor_company_role",
            "status": "accepted",
            "source_natures": ("local",),
            "evidence_ids": ("evidence:founder-a",),
        }
        if bound_ids is not None:
            values["subject_handle_ids"] = bound_ids
        return SimpleNamespace(**values)

    cases = (
        ("missing metadata", (founder_claim("claim:missing", None),)),
        (
            "missing company",
            (founder_claim("claim:missing-company", (professor.canonical_id,)),),
        ),
        (
            "two companies",
            (
                founder_claim(
                    "claim:two-companies",
                    (
                        professor.canonical_id,
                        company.canonical_id,
                        other_company.canonical_id,
                    ),
                ),
            ),
        ),
        (
            "multiple founder claims",
            (
                founder_claim(
                    "claim:founder-a",
                    (professor.canonical_id, company.canonical_id),
                ),
                SimpleNamespace(
                    **{
                        **vars(
                            founder_claim(
                                "claim:founder-b",
                                (
                                    other_professor.canonical_id,
                                    other_company.canonical_id,
                                ),
                            )
                        ),
                        "subject_id": other_professor.canonical_id,
                        "evidence_ids": ("evidence:founder-b",),
                    }
                ),
            ),
        ),
    )
    displayed = SimpleNamespace(
        handles=(company, other_professor, other_company),
    )

    for label, claims in cases:
        result = SimpleNamespace(
            original_query="教授参与创立了哪家公司？",
            claims=claims,
            citations=(),
            context_receipt=SimpleNamespace(
                active_anchor=professor,
                displayed_result_set=displayed,
                traversed_path_ids=(),
            ),
        )
        renderer, completions = _plain_renderer(
            "公开信息可确认该关系。",
            # Off-anchor first pass triggers one correction retry; the retry
            # names the anchor and is published without any founder prefix.
            "甲教授公开信息可确认该关系。",
        )

        rendered = renderer(result)

        assert rendered == "甲教授公开信息可确认该关系。", label
        assert len(completions.calls) == 2
