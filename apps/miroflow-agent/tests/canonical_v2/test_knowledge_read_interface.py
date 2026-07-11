from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


RED_REASON = "Task 3.1 RED: Canonical V2 KnowledgeRead interface is not implemented"


@pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason=RED_REASON)
def test_knowledge_read_preserves_query_constraints_release_and_evidence_trace() -> None:
    module: Any = import_module("src.data_agents.canonical_v2.knowledge_read")
    slot = module.ProtectedSlot(kind="exact_identifier", value="CN117873146A")
    plan = module.RetrievalPlan(
        plan_version="retrieval-plan-v1",
        original_query="介绍专利 CN117873146A，并补充最新进展",
        behavior_class="A",
        release_id="release-r1",
        domains=("patent",),
        protected_slots=(slot,),
        lanes=("exact", "vector", "web"),
        max_candidates=20,
        web_required=True,
    )

    class RecordingRead(module.KnowledgeRead):
        def execute(self, value: Any) -> Any:
            assert value is plan
            items = (
                module.EvidenceItem(
                    evidence_id="local-e1",
                    object_id="patent-1",
                    domain="patent",
                    lane="exact",
                    source_nature="local",
                    source_locator="artifact:patent-export#line:1",
                    snippet="CN117873146A",
                    score=1.0,
                ),
                module.EvidenceItem(
                    evidence_id="web-e1",
                    object_id="patent-1",
                    domain="patent",
                    lane="web",
                    source_nature="current_web",
                    source_locator="https://example.test/patent/CN117873146A",
                    snippet="Current corroboration",
                    score=0.9,
                ),
            )
            traces = tuple(
                module.RetrievalTrace(
                    query_view=value.original_query,
                    lane=lane,
                    attempt=1,
                    release_id=value.release_id,
                    candidate_count=(1 if lane != "vector" else 0),
                )
                for lane in value.lanes
            )
            return module.EvidenceSet(
                release_id=value.release_id,
                original_query=value.original_query,
                protected_slots=value.protected_slots,
                items=items,
                traces=traces,
                limitations=(),
            )

    evidence = RecordingRead().execute(plan)

    assert isinstance(evidence, module.EvidenceSet)
    assert evidence.release_id == plan.release_id
    assert evidence.original_query == plan.original_query
    assert evidence.protected_slots == (slot,)
    assert {item.source_nature for item in evidence.items} == {"local", "current_web"}
    assert all(item.object_id == "patent-1" for item in evidence.items)
    assert {trace.lane for trace in evidence.traces} == set(plan.lanes)
    assert all(trace.release_id == plan.release_id for trace in evidence.traces)
    assert all(trace.query_view == plan.original_query for trace in evidence.traces)
