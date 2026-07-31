"""Cross-topic-switch referent history for the Canonical V2 chat adapter.

Hermetic adapter-level tests with fake planner/read/answer seams: a referent
that was live when a topic switch replaced it stays bindable from a bounded
per-session history, while clean new-topic turns never resurrect it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
import json
from types import SimpleNamespace
from typing import Any

import pytest


RELEASE_ID = "candidate-s11a-release-bound-chat"
NOW = datetime(2026, 7, 20, 17, 45, tzinfo=UTC)
PERSON_QUERY = "介绍清华的丁文伯"
COMPANY_SET_QUERY = "中国有哪些成熟的酒店送餐机器人供应商"
SINGULAR_FOLLOWUP_QUERY = "他的代表性论文有哪些"
SET_FOLLOWUP_QUERY = "这些公司的总部在哪"
CLEAN_SWITCH_QUERY = "介绍大疆创新科技有限公司"

service = import_module("backend.services.canonical_v2_chat")
answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
read_module = import_module("src.data_agents.canonical_v2.knowledge_read")

PERSON = read_module.CanonicalEntityHandle(
    canonical_id="professor-c-ding-wenbo",
    domain="professor",
    display_name="丁文伯",
    evidence_ids=("evidence:history:professor-c-ding-wenbo",),
)
YUNJI = read_module.CanonicalEntityHandle(
    canonical_id="company-c-yunji",
    domain="company",
    display_name="云迹科技",
    evidence_ids=("evidence:history:company-c-yunji",),
)
PUDU = read_module.CanonicalEntityHandle(
    canonical_id="company-c-pudu",
    domain="company",
    display_name="普渡机器人",
    evidence_ids=("evidence:history:company-c-pudu",),
)
KEENON = read_module.CanonicalEntityHandle(
    canonical_id="company-c-keenon",
    domain="company",
    display_name="擎朗智能",
    evidence_ids=("evidence:history:company-c-keenon",),
)
DJI = read_module.CanonicalEntityHandle(
    canonical_id="company-c-dji",
    domain="company",
    display_name="大疆创新",
    evidence_ids=("evidence:history:company-c-dji",),
)
UBTECH = read_module.CanonicalEntityHandle(
    canonical_id="company-c-ubtech",
    domain="company",
    display_name="优必选",
    evidence_ids=("evidence:history:company-c-ubtech",),
)
ORION = read_module.CanonicalEntityHandle(
    canonical_id="company-c-orion",
    domain="company",
    display_name="猎户星空",
    evidence_ids=("evidence:history:company-c-orion",),
)
PAPER_ALPHA = read_module.CanonicalEntityHandle(
    canonical_id="paper-c-alpha",
    domain="paper",
    display_name="扩散模型综述",
    evidence_ids=("evidence:history:paper-c-alpha",),
)
PAPER_BETA = read_module.CanonicalEntityHandle(
    canonical_id="paper-c-beta",
    domain="paper",
    display_name="联邦学习新论",
    evidence_ids=("evidence:history:paper-c-beta",),
)


def _local_item(handle: Any) -> Any:
    return read_module.EvidenceItem(
        evidence_id=f"evidence:history:{handle.canonical_id}",
        object_id=handle.canonical_id,
        domain=handle.domain,
        lane="exact",
        source_nature="local",
        source_locator=f"canonical-v2-isolated:{handle.canonical_id}",
        snippet=json.dumps({"name": handle.display_name}, ensure_ascii=False),
        score=1.0,
        source_authority="canonical_release",
        claim_binding=read_module.EvidenceClaimBinding(
            subject_id=handle.canonical_id,
            predicate="canonical_projection",
            value="a" * 64,
            status="admitted",
        ),
    )


def _receipt(
    *,
    session_id: str,
    anchor: Any | None = None,
    displayed: tuple[Any, ...] = (),
) -> Any:
    result_set = None
    if displayed:
        result_set = answer_module.DisplayedResultSet(
            result_set_id=f"result-set:{session_id}",
            handles=displayed,
            handle_ids=tuple(handle.canonical_id for handle in displayed),
        )
    return answer_module.ContextReceipt(
        active_anchor=anchor,
        displayed_result_set=result_set,
    )


class _RecordingPlanner:
    """One retrieval plan per turn, recording every planning request."""

    def __init__(self, captured: list[Any]) -> None:
        self._captured = captured

    def plan(self, request: Any) -> Any:
        self._captured.append(request)
        return read_module.RetrievalPlan(
            plan_version="retrieval-plan-v1",
            original_query=request.original_query,
            behavior_class="A",
            release_id=RELEASE_ID,
            domains=("professor", "company", "paper", "patent"),
            protected_slots=(),
            lanes=("exact",),
            max_candidates=5,
            web_required=False,
        )


class _ScriptedRead:
    """Scripted per-turn lane results, one entry per planned turn."""

    def __init__(self, script: list[tuple[tuple[Any, ...], tuple[Any, ...]]]) -> None:
        self._script = script

    def execute(self, plan: Any) -> Any:
        items, handles = self._script.pop(0)
        return read_module.EvidenceSet(
            release_id=RELEASE_ID,
            original_query=plan.original_query,
            protected_slots=(),
            items=items,
            traces=(),
            limitations=(),
            entity_handles=handles,
        )


class _ScriptedAnswer:
    """Grounds one claim per bound item and returns scripted context receipts."""

    def __init__(self, captured: list[Any], receipts: list[Any]) -> None:
        self._captured = captured
        self._receipts = receipts

    def answer(self, request: Any) -> Any:
        self._captured.append(request)
        claims: list[Any] = []
        mappings: list[Any] = []
        citations: list[Any] = []
        for index, item in enumerate(request.evidence_set.items):
            binding = item.claim_binding
            if binding is None:
                continue
            claim_id = f"claim:history:{request.turn_id}:{index}"
            claims.append(
                answer_module.MaterialClaim(
                    claim_id=claim_id,
                    text=f"{binding.subject_id} {binding.predicate}",
                    evidence_ids=(item.evidence_id,),
                    source_natures=(item.source_nature,),
                    synthesis=False,
                    subject_id=binding.subject_id,
                    predicate=binding.predicate,
                    value=binding.value,
                    status=binding.status,
                )
            )
            mappings.append(
                answer_module.ClaimEvidenceMapping(
                    claim_id=claim_id,
                    subject_id=binding.subject_id,
                    predicate=binding.predicate,
                    value=binding.value,
                    evidence_ids=(item.evidence_id,),
                    status=binding.status,
                )
            )
            citations.append(
                answer_module.Citation(
                    evidence_id=item.evidence_id,
                    source_nature=item.source_nature,
                    source_locator=item.source_locator,
                )
            )
        receipt = self._receipts.pop(0) if self._receipts else None
        return answer_module.TurnResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            release_id=request.release_id,
            answer_text="grounded fake answer",
            claims=tuple(claims),
            claim_evidence_map=tuple(mappings),
            citations=tuple(citations),
            context_receipt=receipt,
        )


def _make_adapter(
    *,
    read_script: list[tuple[tuple[Any, ...], tuple[Any, ...]]],
    answer_receipts: list[Any],
    planning_requests: list[Any],
    answer_requests: list[Any],
) -> Any:
    return service.CanonicalV2ChatAdapter(
        release_id=RELEASE_ID,
        planner=_RecordingPlanner(planning_requests),
        knowledge_read=_ScriptedRead(read_script),
        answer_factory=lambda: _ScriptedAnswer(answer_requests, answer_receipts),
        answer_session_fork=lambda value: value,
    )


def _answer_turn(adapter: Any, *, query: str, session_id: str) -> Any:
    return adapter.answer(
        query=query,
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )


def _history_entry(
    *,
    kind: str,
    domain: str | None,
    canonical_ids: tuple[str, ...],
    display_names: tuple[str, ...],
    turn_count: int = 1,
) -> Any:
    return service._ReferentHistoryEntry(
        kind=kind,
        domain=domain,
        canonical_ids=canonical_ids,
        display_names=display_names,
        turn_count=turn_count,
    )


def test_singular_referent_binds_pre_switch_anchor_across_topic_switch() -> None:
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    session_id = "session:history:singular"
    adapter = _make_adapter(
        read_script=[
            ((_local_item(PERSON),), (PERSON,)),
            (
                (_local_item(YUNJI), _local_item(PUDU)),
                (YUNJI, PUDU),
            ),
            ((_local_item(PERSON),), (PERSON,)),
        ],
        answer_receipts=[
            _receipt(session_id=session_id, anchor=PERSON),
            _receipt(session_id=session_id, displayed=(YUNJI, PUDU)),
            _receipt(session_id=session_id, anchor=PERSON, displayed=(PERSON,)),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    _answer_turn(adapter, query=PERSON_QUERY, session_id=session_id)
    _answer_turn(adapter, query=COMPANY_SET_QUERY, session_id=session_id)

    # The topic switch archived the outgoing person anchor, most recent first.
    history = adapter._sessions[session_id].referent_history
    assert [entry.kind for entry in history] == ["anchor"]
    assert history[0].canonical_ids == (PERSON.canonical_id,)
    assert history[0].display_names == (PERSON.display_name,)
    assert history[0].domain == "professor"
    assert history[0].turn_count == 1

    response = _answer_turn(
        adapter, query=SINGULAR_FOLLOWUP_QUERY, session_id=session_id
    )

    # The history-bound id reaches retrieval with its display name, and the
    # turn is still a topic switch, so the answer session wipes the company
    # context and rebuilds around the fresh person evidence.
    assert len(planning_requests) == 3
    assert planning_requests[2].displayed_entity_ids == (PERSON.canonical_id,)
    assert planning_requests[2].displayed_entity_names == (PERSON.display_name,)
    directive = answer_requests[2].session_directive
    assert directive is not None
    assert directive.transition == "topic_switch"
    assert response.query_type != "canonical_v2:G:clarification_only"
    assert response.clarification is None
    # The switching turn archived the company set it replaced, ahead of the
    # older person anchor.
    history = adapter._sessions[session_id].referent_history
    assert [entry.kind for entry in history] == ["result_set", "anchor"]
    assert history[0].canonical_ids == (YUNJI.canonical_id, PUDU.canonical_id)
    assert history[0].turn_count == 2


def test_typed_person_pronoun_skips_current_company_anchor() -> None:
    """A list turn re-anchors to its first displayed member, so the naive
    current-session bind pins 他 onto that company; the typed person pronoun
    must skip the mismatched anchor and bind the professor archived before
    the switch (live-derived: T2's receipt carries a company anchor)."""
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    session_id = "session:history:typed-singular"
    adapter = _make_adapter(
        read_script=[
            ((_local_item(PERSON),), (PERSON,)),
            (
                (_local_item(YUNJI), _local_item(PUDU)),
                (YUNJI, PUDU),
            ),
            ((_local_item(PERSON),), (PERSON,)),
        ],
        answer_receipts=[
            _receipt(session_id=session_id, anchor=PERSON),
            # Mirrors the live answer side: after a topic-switch list answer
            # the anchor is rebuilt onto the first displayed company.
            _receipt(
                session_id=session_id,
                anchor=YUNJI,
                displayed=(YUNJI, PUDU),
            ),
            _receipt(session_id=session_id, anchor=PERSON, displayed=(PERSON,)),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    _answer_turn(adapter, query=PERSON_QUERY, session_id=session_id)
    _answer_turn(adapter, query=COMPANY_SET_QUERY, session_id=session_id)
    response = _answer_turn(
        adapter, query=SINGULAR_FOLLOWUP_QUERY, session_id=session_id
    )

    assert planning_requests[2].displayed_entity_ids == (PERSON.canonical_id,)
    assert planning_requests[2].displayed_entity_names == (PERSON.display_name,)
    directive = answer_requests[2].session_directive
    assert directive is not None
    assert directive.transition == "topic_switch"
    assert response.clarification is None


def test_set_referent_with_domain_hint_binds_pre_switch_result_set() -> None:
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    session_id = "session:history:set"
    adapter = _make_adapter(
        read_script=[
            (
                (_local_item(YUNJI), _local_item(PUDU)),
                (YUNJI, PUDU),
            ),
            ((_local_item(PERSON),), (PERSON,)),
            (
                (_local_item(YUNJI), _local_item(PUDU)),
                (YUNJI, PUDU),
            ),
        ],
        answer_receipts=[
            _receipt(session_id=session_id, displayed=(YUNJI, PUDU)),
            _receipt(session_id=session_id, anchor=PERSON),
            _receipt(session_id=session_id, displayed=(YUNJI, PUDU)),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    _answer_turn(adapter, query=COMPANY_SET_QUERY, session_id=session_id)
    _answer_turn(adapter, query=PERSON_QUERY, session_id=session_id)

    history = adapter._sessions[session_id].referent_history
    assert [entry.kind for entry in history] == ["result_set"]
    assert history[0].domain == "company"

    response = _answer_turn(adapter, query=SET_FOLLOWUP_QUERY, session_id=session_id)

    # The company noun hint binds the archived company set, not anything from
    # the current person context.
    assert planning_requests[2].displayed_entity_ids == (
        YUNJI.canonical_id,
        PUDU.canonical_id,
    )
    assert planning_requests[2].displayed_entity_names == (
        YUNJI.display_name,
        PUDU.display_name,
    )
    directive = answer_requests[2].session_directive
    assert directive is not None
    assert directive.transition == "topic_switch"
    assert response.query_type != "canonical_v2:G:clarification_only"


def test_unmatched_referent_after_switch_still_clarifies_without_retrieval() -> None:
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    session_id = "session:history:clarify"
    adapter = _make_adapter(
        read_script=[
            ((_local_item(PERSON),), (PERSON,)),
            ((_local_item(DJI),), (DJI,)),
        ],
        answer_receipts=[
            _receipt(session_id=session_id, anchor=PERSON),
            _receipt(session_id=session_id, anchor=DJI),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    _answer_turn(adapter, query=PERSON_QUERY, session_id=session_id)
    _answer_turn(adapter, query=CLEAN_SWITCH_QUERY, session_id=session_id)
    response = _answer_turn(
        adapter,
        query="这些专利的申请年份是什么",
        session_id=session_id,
    )

    # Only an anchor sits in history; a set referent cannot bind it, so the
    # no-target clarification path is unchanged and retrieval never runs.
    assert response.query_type == "canonical_v2:G:clarification_only"
    assert response.clarification is not None
    assert len(planning_requests) == 2
    assert len(answer_requests) == 2


def test_clean_new_topic_after_switch_stays_pure_topic_switch() -> None:
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    session_id = "session:history:clean"
    adapter = _make_adapter(
        read_script=[
            ((_local_item(PERSON),), (PERSON,)),
            (
                (_local_item(YUNJI), _local_item(PUDU)),
                (YUNJI, PUDU),
            ),
            ((_local_item(DJI),), (DJI,)),
        ],
        answer_receipts=[
            _receipt(session_id=session_id, anchor=PERSON),
            _receipt(session_id=session_id, displayed=(YUNJI, PUDU)),
            _receipt(session_id=session_id, anchor=DJI),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    _answer_turn(adapter, query=PERSON_QUERY, session_id=session_id)
    _answer_turn(adapter, query=COMPANY_SET_QUERY, session_id=session_id)
    _answer_turn(adapter, query=CLEAN_SWITCH_QUERY, session_id=session_id)

    # No anaphoric marker: history must not resurrect the archived anchor.
    assert planning_requests[2].displayed_entity_ids == ()
    directive = answer_requests[2].session_directive
    assert directive is not None
    assert directive.transition == "topic_switch"


def test_current_session_binding_wins_over_history() -> None:
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    session_id = "session:history:precedence"
    adapter = _make_adapter(
        read_script=[
            ((_local_item(YUNJI),), (YUNJI,)),
            ((_local_item(PERSON),), (PERSON,)),
            ((_local_item(PERSON),), (PERSON,)),
        ],
        answer_receipts=[
            _receipt(session_id=session_id, anchor=YUNJI),
            _receipt(session_id=session_id, anchor=PERSON, displayed=(PERSON,)),
            _receipt(session_id=session_id, anchor=PERSON, displayed=(PERSON,)),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    _answer_turn(adapter, query="介绍云迹科技", session_id=session_id)
    _answer_turn(adapter, query=PERSON_QUERY, session_id=session_id)
    _answer_turn(adapter, query=SINGULAR_FOLLOWUP_QUERY, session_id=session_id)

    # The current session's anchor binds the pronoun; the archived company
    # anchor stays untouched and the turn continues rather than switching.
    assert planning_requests[2].displayed_entity_ids == (PERSON.canonical_id,)
    assert answer_requests[2].session_directive is None
    history = adapter._sessions[session_id].referent_history
    assert [entry.kind for entry in history] == ["anchor"]
    assert history[0].canonical_ids == (YUNJI.canonical_id,)


def test_switch_commit_archives_both_anchor_and_displayed_set() -> None:
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    session_id = "session:history:archive"
    adapter = _make_adapter(
        read_script=[
            (
                (
                    _local_item(PERSON),
                    _local_item(PAPER_ALPHA),
                    _local_item(PAPER_BETA),
                ),
                (PERSON, PAPER_ALPHA, PAPER_BETA),
            ),
            ((_local_item(DJI),), (DJI,)),
        ],
        answer_receipts=[
            _receipt(
                session_id=session_id,
                anchor=PERSON,
                displayed=(PAPER_ALPHA, PAPER_BETA),
            ),
            _receipt(session_id=session_id, anchor=DJI),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    _answer_turn(adapter, query=PERSON_QUERY, session_id=session_id)
    _answer_turn(adapter, query=CLEAN_SWITCH_QUERY, session_id=session_id)

    history = adapter._sessions[session_id].referent_history
    assert [entry.kind for entry in history] == ["anchor", "result_set"]
    anchor_entry, set_entry = history
    assert anchor_entry.canonical_ids == (PERSON.canonical_id,)
    assert anchor_entry.domain == "professor"
    assert set_entry.canonical_ids == (
        PAPER_ALPHA.canonical_id,
        PAPER_BETA.canonical_id,
    )
    assert set_entry.display_names == (
        PAPER_ALPHA.display_name,
        PAPER_BETA.display_name,
    )
    assert set_entry.domain == "paper"
    assert all(entry.turn_count == 1 for entry in history)


def test_referent_history_is_bounded_to_four_entries_oldest_dropped() -> None:
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    session_id = "session:history:bounded"
    companies = (YUNJI, PUDU, KEENON, DJI, UBTECH, ORION)
    adapter = _make_adapter(
        read_script=[((_local_item(handle),), (handle,)) for handle in companies],
        answer_receipts=[
            _receipt(session_id=session_id, anchor=handle) for handle in companies
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    for handle in companies:
        _answer_turn(adapter, query=f"介绍{handle.display_name}", session_id=session_id)

    # Every turn after the first is a clean topic switch archiving the outgoing
    # anchor; the window keeps only the four most recent entries.
    history = adapter._sessions[session_id].referent_history
    assert len(history) == 4
    assert [entry.canonical_ids for entry in history] == [
        (UBTECH.canonical_id,),
        (DJI.canonical_id,),
        (KEENON.canonical_id,),
        (PUDU.canonical_id,),
    ]
    assert [entry.turn_count for entry in history] == [5, 4, 3, 2]


def test_history_binding_prefers_hint_compatible_anchor() -> None:
    history = (
        _history_entry(
            kind="anchor",
            domain="professor",
            canonical_ids=("professor:wenbo",),
            display_names=("丁文伯",),
            turn_count=3,
        ),
        _history_entry(
            kind="anchor",
            domain="company",
            canonical_ids=("company:yunji",),
            display_names=("云迹科技",),
            turn_count=1,
        ),
    )

    # The company noun hint prefers the older company anchor.
    assert service._history_displayed_ids(
        query="这家公司的专利有哪些",
        history=history,
    ) == ("company:yunji",)
    # A hint that matches no anchor falls back to the most recent one.
    assert service._history_displayed_ids(
        query="他的代表性论文有哪些",
        history=history,
    ) == ("professor:wenbo",)
    # No anaphoric marker never binds history.
    assert (
        service._history_displayed_ids(
            query="介绍大疆创新科技有限公司",
            history=history,
        )
        == ()
    )
    # A set referent cannot bind anchor entries at all.
    assert (
        service._history_displayed_ids(
            query="这些公司的总部在哪",
            history=history,
        )
        == ()
    )


def test_history_binding_prefers_hint_compatible_result_set() -> None:
    history = (
        _history_entry(
            kind="result_set",
            domain="paper",
            canonical_ids=("paper:alpha", "paper:beta"),
            display_names=("扩散模型综述", "联邦学习新论"),
            turn_count=3,
        ),
        _history_entry(
            kind="result_set",
            domain="company",
            canonical_ids=("company:yunji", "company:pudu"),
            display_names=("云迹科技", "普渡机器人"),
            turn_count=1,
        ),
    )

    assert service._history_displayed_ids(
        query="这些公司的总部在哪",
        history=history,
    ) == ("company:yunji", "company:pudu")
    assert service._history_displayed_ids(
        query="上述论文的区别是什么",
        history=history,
    ) == ("paper:alpha", "paper:beta")
    # Without a hint the most recent compatible entry wins.
    assert service._history_displayed_ids(
        query="它们分别是什么",
        history=history,
    ) == ("paper:alpha", "paper:beta")


def test_referent_clarification_respects_history_binding() -> None:
    anchor_only_history = (
        _history_entry(
            kind="anchor",
            domain="professor",
            canonical_ids=("professor:wenbo",),
            display_names=("丁文伯",),
        ),
    )
    committed = SimpleNamespace(
        context_receipt=SimpleNamespace(
            active_anchor=None,
            displayed_result_set=None,
        ),
        referent_history=anchor_only_history,
    )

    # The pronoun binds the archived anchor, so no clarification fires.
    assert not service._referent_clarification_needed(
        query="他的代表性论文有哪些",
        committed=committed,
    )
    # A set referent binds nothing anywhere, so clarification still fires.
    assert service._referent_clarification_needed(
        query="这些专利的申请年份是什么",
        committed=committed,
    )


def test_intra_query_set_antecedent_never_clarifies() -> None:
    """"…厂商，他们…" resolves inside the query: no session is needed.

    Live-derived （问题14): "目前深圳有哪些具身智能、灵巧手厂商，他们在数据
    层面分别是什么路线" was rejected with the no-referent clarification even
    though the antecedent 厂商 is in the question itself.
    """
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    session_id = "session:history:intra-query-set"
    adapter = _make_adapter(
        read_script=[
            (
                (_local_item(PUDU), _local_item(ORION)),
                (PUDU, ORION),
            ),
        ],
        answer_receipts=[
            _receipt(session_id=session_id, displayed=(PUDU, ORION)),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    response = _answer_turn(
        adapter,
        query="目前深圳有哪些具身智能、灵巧手厂商，他们在数据层面分别是什么路线",
        session_id=session_id,
    )

    assert response.query_type != "canonical_v2:G:clarification_only"
    assert response.clarification is None
    assert len(planning_requests) == 1
    # No displayed-set binding is invented for the intra-query antecedent:
    # the turn plans as a fresh standalone question.
    assert planning_requests[0].displayed_entity_ids == ()


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        ("目前深圳有哪些具身智能、灵巧手厂商，他们在数据层面分别是什么路线", True),
        ("这些公司的总部在哪", False),
        ("他们的论文有哪些", False),
        ("上述企业里总部在深圳的企业有哪些", False),
        ("深圳有哪些机器人公司", False),
    ),
)
def test_internal_set_antecedent_detection(query: str, expected: bool) -> None:
    assert service.has_internal_set_antecedent(query) is expected


def test_explicit_new_subject_wins_over_session_anchor() -> None:
    """A query naming a different subject must not bind the session anchor.

    Live-derived (single-session 问题8): after PCB turns anchored on 一博,
    "华力创科学这家公司相关信息，这家公司的产量特点是什么…" bound the
    referent 这家公司 to 一博 instead of retrieving 华力创科学 — the
    explicitly named subject always wins.
    """
    planning_requests: list[Any] = []
    answer_requests: list[Any] = []
    session_id = "session:history:explicit-subject"
    adapter = _make_adapter(
        read_script=[
            ((_local_item(PUDU),), (PUDU,)),
            ((_local_item(UBTECH),), (UBTECH,)),
        ],
        answer_receipts=[
            _receipt(session_id=session_id, anchor=PUDU, displayed=(PUDU,)),
            _receipt(session_id=session_id, anchor=UBTECH, displayed=(UBTECH,)),
        ],
        planning_requests=planning_requests,
        answer_requests=answer_requests,
    )

    _answer_turn(adapter, query="深圳市一博科技股份有限公司怎么样", session_id=session_id)
    response = _answer_turn(
        adapter,
        query="华力创科学这家公司相关信息，这家公司的产量特点是什么，市场竞争力怎么样",
        session_id=session_id,
    )

    # No referent binding: the explicitly named subject drives a fresh plan,
    # and the turn is a topic switch away from the PCB anchor.
    assert planning_requests[1].displayed_entity_ids == ()
    directive = answer_requests[1].session_directive
    assert directive is not None
    assert directive.transition == "topic_switch"
    assert response.clarification is None
