"""Phase 3 slice 3.3 — expansion base = session subject (RED-first).

G5 evidence (V2 replay): the expansion turn's plan views carried no subject
(还有哪些类似的公司 / 类似公司 / 竞品分析) and the web lane came back
unavailable — free vector retrieval answered about 微众银行. The fix rewrites
the PLANNING query for expansion-family turns to name the session subject.
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from typing import Any

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
RELEASE_ID = "candidate-expansion-base"

service = import_module("backend.services.canonical_v2_chat")
read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")

ANCHOR = read_module.CanonicalEntityHandle(
    canonical_id="company-c-ubtech",
    domain="company",
    display_name="深圳市优必选科技股份有限公司",
    evidence_ids=("evidence:expansion:local",),
)


class TestExpansionRewriteHelper:
    def test_expansion_query_rewritten_with_subject(self) -> None:
        assert (
            service._expansion_subject_rewrite(
                "还有哪些类似的公司",
                subject_name="深圳市优必选科技股份有限公司",
            )
            == "与深圳市优必选科技股份有限公司类似的公司还有哪些"
        )

    def test_subject_already_present_no_rewrite(self) -> None:
        assert (
            service._expansion_subject_rewrite(
                "还有哪些像优必选这样的公司",
                subject_name="深圳市优必选科技股份有限公司",
            )
            is None
        )

    def test_non_expansion_query_untouched(self) -> None:
        assert (
            service._expansion_subject_rewrite(
                "该公司的专利有哪些", subject_name="深圳市优必选科技股份有限公司"
            )
            is None
        )


class _CapturingPlanner:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    def plan(self, request: Any) -> Any:
        self.requests.append(request)
        return read_module.RetrievalPlan(
            plan_version="retrieval-plan-v1",
            original_query=request.original_query,
            behavior_class="A",
            release_id=RELEASE_ID,
            domains=("company",),
            protected_slots=(),
            lanes=("exact", "vector"),
            max_candidates=5,
            web_required=False,
        )


class _FakeRead:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, plan: Any) -> Any:
        self.calls += 1
        return read_module.EvidenceSet(
            release_id=RELEASE_ID,
            original_query=plan.original_query,
            protected_slots=(),
            items=(),
            traces=(),
            limitations=(),
            entity_handles=(ANCHOR,),
        )


class _FakeAnswer:
    def answer(self, request: Any) -> Any:
        return answer_module.TurnResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            release_id=request.release_id,
            answer_text="类似公司清单",
            claims=(),
            claim_evidence_map=(),
            citations=(),
            context_receipt=answer_module.ContextReceipt(
                active_anchor=ANCHOR,
                displayed_result_set=answer_module.DisplayedResultSet(
                    result_set_id=f"rs:{request.session_id}",
                    handles=(ANCHOR,),
                    handle_ids=(ANCHOR.canonical_id,),
                ),
            ),
        )


def _adapter() -> tuple[Any, _CapturingPlanner]:
    planner = _CapturingPlanner()
    adapter = service.CanonicalV2ChatAdapter(
        release_id=RELEASE_ID,
        planner=planner,
        knowledge_read=_FakeRead(),
        answer_factory=lambda: _FakeAnswer(),
        answer_session_fork=lambda value: value,
    )
    return adapter, planner


def _turn(adapter: Any, query: str, session_id: str) -> None:
    adapter.answer(query=query, session_id=session_id, option_id=None, as_of=NOW)


class TestExpansionPlanningBindsSubject:
    def test_expansion_turn_plans_with_session_subject(self) -> None:
        adapter, planner = _adapter()
        _turn(adapter, "介绍深圳市优必选科技股份有限公司", "sess-exp")
        _turn(adapter, "还有哪些类似的公司", "sess-exp")
        assert len(planner.requests) == 2
        expansion_request = planner.requests[1]
        assert "优必选" in expansion_request.original_query
        assert "类似" in expansion_request.original_query

    def test_deepening_turn_not_rewritten(self) -> None:
        adapter, planner = _adapter()
        _turn(adapter, "介绍深圳市优必选科技股份有限公司", "sess-deep")
        _turn(adapter, "它的总部在哪里", "sess-deep")
        assert planner.requests[1].original_query == "它的总部在哪里"


class TestEnumerationNoSoftSubject:
    def test_enumeration_query_never_yields_soft_subject(self) -> None:
        # G7 fault: a lone web handle from list results must not become the
        # session's soft subject and refocus later answers.
        assert (
            service._soft_subject_name(query="深圳有哪些做具身智能的公司")
            is None
        )
