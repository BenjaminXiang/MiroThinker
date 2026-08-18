"""Task 1.1.2 — service turn-boundary trace hook.

Hermetic adapter-level tests (fake planner/read/answer seams, mirroring
test_canonical_v2_session_evidence_carryover): every completed turn writes
exactly one TurnTrace to the journal with session snapshot, interpretation,
lane counts, and status — and error turns are traced then re-raised.
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any
import json

import pytest

RELEASE_ID = "candidate-turn-trace-hook"
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
QUERY = "介绍云迹科技有限公司"
FOLLOWUP = "该公司的机器人能按电梯吗"

service = import_module("backend.services.canonical_v2_chat")
read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
trace_module = import_module("backend.services.canonical_v2_turn_trace")

ANCHOR = read_module.CanonicalEntityHandle(
    canonical_id="company-c-yunji",
    domain="company",
    display_name="云迹科技",
    evidence_ids=("evidence:turn-trace:local",),
)


def _local_item() -> Any:
    return read_module.EvidenceItem(
        evidence_id="evidence:turn-trace:local",
        object_id=ANCHOR.canonical_id,
        domain="company",
        lane="exact",
        source_nature="local",
        source_locator="canonical-v2-isolated:yunji",
        snippet='{"name": "云迹科技", "website": "https://www.yunji-tech.com/"}',
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
    def plan(self, request: Any) -> Any:
        return read_module.RetrievalPlan(
            plan_version="retrieval-plan-v1",
            original_query=request.original_query,
            behavior_class="A",
            release_id=RELEASE_ID,
            domains=("company",),
            protected_slots=(),
            lanes=("exact",),
            max_candidates=5,
            web_required=False,
        )


class _FakeRead:
    def __init__(self, *, traces: tuple[Any, ...] = ()) -> None:
        self._traces = traces
        self.calls = 0

    def execute(self, plan: Any) -> Any:
        self.calls += 1
        return read_module.EvidenceSet(
            release_id=RELEASE_ID,
            original_query=plan.original_query,
            protected_slots=(),
            items=(_local_item(),),
            traces=self._traces,
            limitations=(),
            entity_handles=(ANCHOR,),
        )


class _ExplodingRead(_FakeRead):
    def execute(self, plan: Any) -> Any:
        raise RuntimeError("boom during retrieval")


class _FakeAnswer:
    def answer(self, request: Any) -> Any:
        citations = [
            answer_module.Citation(
                evidence_id=item.evidence_id,
                source_nature=item.source_nature,
                source_locator=item.source_locator,
            )
            for item in request.evidence_set.items
        ]
        return answer_module.TurnResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            release_id=request.release_id,
            answer_text="grounded fake answer",
            claims=(),
            claim_evidence_map=(),
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


_LANE_TRACES = (
    read_module.RetrievalTrace(
        query_view="view-1",
        lane="exact",
        attempt=1,
        release_id=RELEASE_ID,
        candidate_count=2,
    ),
    read_module.RetrievalTrace(
        query_view="view-2",
        lane="vector",
        attempt=1,
        release_id=RELEASE_ID,
        candidate_count=3,
    ),
)


def _adapter(tmp_path: Path, reader: _FakeRead) -> Any:
    adapter = service.CanonicalV2ChatAdapter(
        release_id=RELEASE_ID,
        planner=_FakePlanner(),
        knowledge_read=reader,
        answer_factory=lambda: _FakeAnswer(),
        answer_session_fork=lambda value: value,
    )
    adapter.attach_turn_trace(trace_module.TurnTraceJournalStore(root_dir=tmp_path))
    return adapter


def _journal(tmp_path: Path) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for file in sorted(tmp_path.glob("*.jsonl")):
        lines.extend(
            json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()
        )
    return lines


def _answer(adapter: Any, *, query: str, session_id: str) -> Any:
    return adapter.answer(query=query, session_id=session_id, option_id=None, as_of=NOW)


def test_successful_turn_writes_trace_with_stages(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path, _FakeRead(traces=_LANE_TRACES))
    response = _answer(adapter, query=QUERY, session_id="sess-1")
    assert response.answer_text == "grounded fake answer"
    entries = _journal(tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["session_id"] == "sess-1"
    assert entry["turn_ordinal"] == 1
    assert entry["query_raw"] == QUERY
    assert entry["inferred_domains"] == ["company"]
    assert entry["lanes"]["exact"]["in"] == 2
    assert entry["lanes"]["vector"]["in"] == 3
    assert entry["degradation"] == "none"
    assert entry["status"] == "ok"
    assert entry["citation_count"] == 1
    assert entry["answer_subject"] == "云迹科技"
    assert entry["session_snapshot"]["active_anchor_name"] is None


def test_second_turn_snapshot_carries_anchor(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path, _FakeRead(traces=_LANE_TRACES))
    _answer(adapter, query=QUERY, session_id="sess-2")
    _answer(adapter, query=FOLLOWUP, session_id="sess-2")
    entries = _journal(tmp_path)
    assert len(entries) == 2
    second = entries[1]
    assert second["turn_ordinal"] == 2
    assert second["session_snapshot"]["active_anchor_name"] == "云迹科技"
    assert second["session_snapshot"]["displayed_id_count"] == 1


def test_error_turn_writes_error_trace_and_reraises(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path, _ExplodingRead())
    with pytest.raises(RuntimeError, match="boom during retrieval"):
        _answer(adapter, query=QUERY, session_id="sess-3")
    entries = _journal(tmp_path)
    assert len(entries) == 1
    assert entries[0]["status"] == "error"
    assert entries[0]["degradation"] == "error"
    assert entries[0]["error_detail"]


def test_absent_store_is_noop(tmp_path: Path) -> None:
    adapter = service.CanonicalV2ChatAdapter(
        release_id=RELEASE_ID,
        planner=_FakePlanner(),
        knowledge_read=_FakeRead(),
        answer_factory=lambda: _FakeAnswer(),
        answer_session_fork=lambda value: value,
    )
    response = _answer(adapter, query=QUERY, session_id="sess-4")
    assert response.answer_text == "grounded fake answer"
    assert _journal(tmp_path) == []
