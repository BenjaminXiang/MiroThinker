"""Bounded session Web-evidence carry-over for the Canonical V2 chat adapter.

Hermetic adapter-level tests with fake planner/read/answer seams: once good Web
evidence appears in a session, later continuing turns keep using it instead of
depending on per-turn web luck, while topic switches never inherit stale items.
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from typing import Any


RELEASE_ID = "candidate-s11a-release-bound-chat"
NOW = datetime(2026, 7, 20, 17, 45, tzinfo=UTC)
FIRST_QUERY = "介绍云迹科技有限公司"
FOLLOWUP_QUERY = "该公司的机器人能按电梯吗"
TOPIC_SWITCH_QUERY = "介绍大疆创新科技有限公司的无人机产品"

service = import_module("backend.services.canonical_v2_chat")
answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
read_module = import_module("src.data_agents.canonical_v2.knowledge_read")

ANCHOR = read_module.CanonicalEntityHandle(
    canonical_id="company-c-yunji",
    domain="company",
    display_name="云迹科技",
    evidence_ids=("evidence:carryover:yunji-local",),
)


def _web_item(
    evidence_id: str,
    *,
    url: str,
    snippet: str,
    observed_at: datetime = NOW,
) -> Any:
    return read_module.EvidenceItem(
        evidence_id=evidence_id,
        object_id=f"web-object:{evidence_id}",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator=url,
        snippet=snippet,
        score=0.9,
        source_authority="web_search",
        observed_at=observed_at,
        claim_binding=read_module.EvidenceClaimBinding(
            subject_id=ANCHOR.canonical_id,
            predicate="current_web_result",
            value="b" * 64,
            status="observed",
        ),
        web_snapshot=read_module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:{evidence_id}",
            content_sha256="c" * 64,
            retrieved_at=observed_at,
            byte_length=128,
        ),
    )


def _local_item() -> Any:
    return read_module.EvidenceItem(
        evidence_id="evidence:carryover:yunji-local",
        object_id=ANCHOR.canonical_id,
        domain="company",
        lane="exact",
        source_nature="local",
        source_locator="canonical-v2-isolated:yunji",
        snippet='{"name": "云迹科技"}',
        score=1.0,
        source_authority="canonical_release",
        claim_binding=read_module.EvidenceClaimBinding(
            subject_id=ANCHOR.canonical_id,
            predicate="canonical_projection",
            value="a" * 64,
            status="admitted",
        ),
    )


class _FakePlanner:
    """One Universal-Web plan per turn, echoing the requested query."""

    def plan(self, request: Any) -> Any:
        return read_module.RetrievalPlan(
            plan_version="retrieval-plan-v1",
            original_query=request.original_query,
            behavior_class="A",
            release_id=RELEASE_ID,
            domains=("company",),
            protected_slots=(),
            lanes=("exact", "web"),
            max_candidates=5,
            web_required=True,
            web_policy=read_module.WebSearchPolicy(
                mode="universal",
                max_provider_calls=1,
                timeout_ms=1000,
                max_results=5,
            ),
        )


class _FakeRead:
    """Scripted per-turn lane results; web luck varies, locals stay stable."""

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


class _FakeAnswer:
    """Grounds one claim per bound item and records every answer request."""

    def __init__(self, captured: list[Any]) -> None:
        self._captured = captured

    def answer(self, request: Any) -> Any:
        self._captured.append(request)
        claims: list[Any] = []
        mappings: list[Any] = []
        citations: list[Any] = []
        for index, item in enumerate(request.evidence_set.items):
            binding = item.claim_binding
            if binding is None:
                continue
            claim_id = f"claim:carryover:{request.turn_id}:{index}"
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
        return answer_module.TurnResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            release_id=request.release_id,
            answer_text="grounded fake answer",
            claims=tuple(claims),
            claim_evidence_map=tuple(mappings),
            citations=tuple(citations),
            context_receipt=answer_module.ContextReceipt(
                active_anchor=ANCHOR,
                displayed_result_set=answer_module.DisplayedResultSet(
                    result_set_id=f"result-set:{request.session_id}",
                    handles=(ANCHOR,),
                    handle_ids=(ANCHOR.canonical_id,),
                ),
            ),
        )


def _make_adapter(
    script: list[tuple[tuple[Any, ...], tuple[Any, ...]]],
    captured: list[Any],
) -> Any:
    return service.CanonicalV2ChatAdapter(
        release_id=RELEASE_ID,
        planner=_FakePlanner(),
        knowledge_read=_FakeRead(script),
        answer_factory=lambda: _FakeAnswer(captured),
        answer_session_fork=lambda value: value,
    )


def _answer_turn(adapter: Any, *, query: str, session_id: str) -> Any:
    return adapter.answer(
        query=query,
        session_id=session_id,
        option_id=None,
        as_of=NOW,
    )


def _evidence_ids(request: Any) -> tuple[str, ...]:
    return tuple(item.evidence_id for item in request.evidence_set.items)


def test_followup_turn_keeps_prior_web_evidence_when_web_luck_runs_out() -> None:
    hq_item = _web_item(
        "evidence:carryover:yunji-hq",
        url="https://yunji-robot.example/about",
        snippet="云迹科技总部位于北京的说法被官网否定。",
    )
    captured: list[Any] = []
    adapter = _make_adapter(
        [
            ((_local_item(), hq_item), (ANCHOR,)),
            # Turn 2 web luck runs out: only the stable local item returns.
            ((_local_item(),), (ANCHOR,)),
        ],
        captured,
    )

    first = _answer_turn(adapter, query=FIRST_QUERY, session_id="session:carry:hq")
    assert first.query_type.startswith("canonical_v2:")
    assert _evidence_ids(captured[0]) == (
        "evidence:carryover:yunji-local",
        hq_item.evidence_id,
    )

    second = _answer_turn(adapter, query=FOLLOWUP_QUERY, session_id="session:carry:hq")
    assert second.query_type.startswith("canonical_v2:")

    followup_ids = _evidence_ids(captured[1])
    assert hq_item.evidence_id in followup_ids
    carried = next(
        item
        for item in captured[1].evidence_set.items
        if item.evidence_id == hq_item.evidence_id
    )
    # Provenance survives carry-over: the revalidated item is field-identical,
    # so public citation rules (`_official_evidence_url`, snapshot binding)
    # keep working on carried items exactly as on fresh ones.
    assert carried == hq_item
    assert carried.source_nature == "current_web"
    assert carried.source_locator == "https://yunji-robot.example/about"
    assert carried.web_snapshot is not None
    # The carried item is answer-visible evidence: the adapter's own feedback
    # checkpoint binds it as part of the evidence the turn answered from.
    committed = adapter._sessions["session:carry:hq"]
    assert hq_item.evidence_id in committed.checkpoint.evidence_ids


def test_url_dedup_keeps_the_fresher_web_item() -> None:
    stale = _web_item(
        "evidence:carryover:pudu-stale",
        url="https://www.pudurobotics.com/products/flashbot-arm",
        snippet="旧快照：普渡机器人还不能按电梯。",
    )
    fresh = _web_item(
        "evidence:carryover:pudu-fresh",
        # Same normalized URL (trailing slash), fresher snapshot content.
        url="https://www.pudurobotics.com/products/flashbot-arm/",
        snippet="新快照：普渡机器人可以按电梯。",
    )
    captured: list[Any] = []
    adapter = _make_adapter(
        [
            ((_local_item(), stale), (ANCHOR,)),
            ((_local_item(), fresh), (ANCHOR,)),
        ],
        captured,
    )

    _answer_turn(adapter, query=FIRST_QUERY, session_id="session:carry:fresh")
    _answer_turn(adapter, query=FOLLOWUP_QUERY, session_id="session:carry:fresh")

    followup_ids = _evidence_ids(captured[1])
    assert fresh.evidence_id in followup_ids
    assert stale.evidence_id not in followup_ids
    committed = adapter._sessions["session:carry:fresh"]
    assert tuple(item.evidence_id for item in committed.prior_web_items) == (
        fresh.evidence_id,
    )


def test_topic_switch_turn_gets_no_carryover() -> None:
    stale = _web_item(
        "evidence:carryover:yunji-stale",
        url="https://yunji-robot.example/about",
        snippet="云迹科技相关网页快照。",
    )
    captured: list[Any] = []
    adapter = _make_adapter(
        [
            ((_local_item(), stale), (ANCHOR,)),
            ((_local_item(),), (ANCHOR,)),
        ],
        captured,
    )

    _answer_turn(adapter, query=FIRST_QUERY, session_id="session:carry:switch")
    _answer_turn(
        adapter, query=TOPIC_SWITCH_QUERY, session_id="session:carry:switch"
    )

    assert stale.evidence_id not in _evidence_ids(captured[1])
    # A topic switch also resets the retained window to the new turn's own web
    # items, so later turns cannot resurrect the stale snapshot either.
    committed = adapter._sessions["session:carry:switch"]
    assert committed.prior_web_items == ()


def test_first_turn_has_no_carryover() -> None:
    item = _web_item(
        "evidence:carryover:first-only",
        url="https://yunji-robot.example/first",
        snippet="首轮网页快照。",
    )
    captured: list[Any] = []
    adapter = _make_adapter(
        [((_local_item(), item), (ANCHOR,))],
        captured,
    )

    _answer_turn(adapter, query=FIRST_QUERY, session_id="session:carry:first")

    assert _evidence_ids(captured[0]) == (
        "evidence:carryover:yunji-local",
        item.evidence_id,
    )
    # After the first successful turn the window holds that turn's web items.
    committed = adapter._sessions["session:carry:first"]
    assert tuple(item.evidence_id for item in committed.prior_web_items) == (
        item.evidence_id,
    )


def test_carryover_window_is_bounded_to_eight_items() -> None:
    items = tuple(
        _web_item(
            f"evidence:carryover:bulk:{index}",
            url=f"https://yunji-robot.example/page-{index}",
            snippet=f"第 {index} 个网页快照。",
        )
        for index in range(10)
    )
    captured: list[Any] = []
    adapter = _make_adapter(
        [
            (items, (ANCHOR,)),
            ((_local_item(),), (ANCHOR,)),
        ],
        captured,
    )

    _answer_turn(adapter, query=FIRST_QUERY, session_id="session:carry:bound")
    _answer_turn(adapter, query=FOLLOWUP_QUERY, session_id="session:carry:bound")

    committed = adapter._sessions["session:carry:bound"]
    assert len(committed.prior_web_items) == 8
    followup_ids = _evidence_ids(captured[1])
    assert len(followup_ids) == 1 + 8
    assert followup_ids[0] == "evidence:carryover:yunji-local"
