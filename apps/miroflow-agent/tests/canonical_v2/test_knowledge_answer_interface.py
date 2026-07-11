from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


RED_REASON = "Task 3.1 RED: Canonical V2 KnowledgeAnswer interface is not implemented"


@pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason=RED_REASON)
def test_knowledge_answer_maps_material_claims_to_distinct_local_and_web_evidence() -> None:
    read_module: Any = import_module("src.data_agents.canonical_v2.knowledge_read")
    answer_module: Any = import_module("src.data_agents.canonical_v2.knowledge_answer")
    evidence = read_module.EvidenceSet(
        release_id="release-r1",
        original_query="这项专利的申请人是谁，有没有最新状态？",
        protected_slots=(
            read_module.ProtectedSlot(kind="exact_identifier", value="CN117873146A"),
        ),
        items=(
            read_module.EvidenceItem(
                evidence_id="local-e1",
                object_id="patent-1",
                domain="patent",
                lane="exact",
                source_nature="local",
                source_locator="artifact:patent-export#line:1",
                snippet="Applicant: Example Company",
                score=1.0,
            ),
            read_module.EvidenceItem(
                evidence_id="web-e1",
                object_id="patent-1",
                domain="patent",
                lane="web",
                source_nature="current_web",
                source_locator="https://example.test/patent/CN117873146A",
                snippet="Current status corroboration",
                score=0.9,
            ),
        ),
        traces=(),
        limitations=(),
    )
    request = answer_module.TurnRequest(
        session_id="session-1",
        turn_id="turn-1",
        query=evidence.original_query,
        release_id=evidence.release_id,
        evidence_set=evidence,
    )

    class RecordingAnswer(answer_module.KnowledgeAnswer):
        def answer(self, value: Any) -> Any:
            assert value is request
            return answer_module.TurnResult(
                session_id=value.session_id,
                turn_id=value.turn_id,
                release_id=value.release_id,
                answer_text="申请人为 Example Company；最新状态由 Web 证据补充。",
                claims=(
                    answer_module.MaterialClaim(
                        claim_id="claim-1",
                        text="申请人为 Example Company",
                        evidence_ids=("local-e1",),
                        source_natures=("local",),
                        synthesis=False,
                    ),
                    answer_module.MaterialClaim(
                        claim_id="claim-2",
                        text="最新状态由当前 Web 信息补充",
                        evidence_ids=("web-e1",),
                        source_natures=("current_web",),
                        synthesis=False,
                    ),
                ),
                limitations=(),
                suggested_followups=(),
            )

    result = RecordingAnswer().answer(request)
    evidence_ids = {item.evidence_id for item in evidence.items}

    assert isinstance(result, answer_module.TurnResult)
    assert (result.session_id, result.turn_id, result.release_id) == (
        request.session_id,
        request.turn_id,
        request.release_id,
    )
    assert all(claim.evidence_ids for claim in result.claims)
    assert all(set(claim.evidence_ids) <= evidence_ids for claim in result.claims)
    assert {nature for claim in result.claims for nature in claim.source_natures} == {
        "local",
        "current_web",
    }
    assert all(claim.synthesis is False for claim in result.claims)
    assert result.limitations == ()
    assert result.suggested_followups == ()
