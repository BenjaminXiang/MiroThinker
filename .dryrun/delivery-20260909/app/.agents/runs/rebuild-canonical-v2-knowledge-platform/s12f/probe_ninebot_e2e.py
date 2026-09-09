"""End-to-end hotel-T1 probe: web lane -> evidence set -> answer factory.

Dumps whether 九号 survives each stage (lane candidates, selector claims,
final answer text) so the recall gap can be pinned to a stage.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving  # noqa: E402
from src.data_agents.canonical_v2.knowledge_answer import TurnRequest  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    EvidenceSet,
    LaneRequest,
    QueryPlanningRequest,
    StructuredConstraints,
    WebSearchPolicy,
)

RUN_ROOT = (
    AGENT_ROOT
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
)
RELEASE_ID = "candidate-s12f-20260801-v1"
NOW = datetime.now(UTC)
QUERY = "中国有哪些成熟的酒店送餐机器人供应商"


class _Embedding:
    model_id = "Qwen/Qwen3-Embedding-8B"


def main() -> None:
    inputs = serving.load_recorded_serving_inputs(
        path=RUN_ROOT / "s12f/serving-bundle-s12f.json",
        expected_content_sha256="93fb456012f5e9799414cd90fa2ea27bb7d58acd5d41c13ac3b9dea601aed9c0",
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12f_20260801_v1",
        expected_index_root=Path("/var/tmp/mirothinker-canonical-v2-s12f/index-v1"),
        expected_envelope_path=RUN_ROOT
        / "s12a/complete-candidate-build-envelope.json",
        embedding_adapter=_Embedding(),
    )
    proposal = inputs.proposal_provider(
        QueryPlanningRequest(
            request_id="query-request:probe-e2e",
            release_id=RELEASE_ID,
            original_query=QUERY,
            as_of=datetime.now(UTC),
        )
    )
    print("proposal max_candidates:", proposal.max_candidates)
    request = LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query=QUERY,
        behavior_class="D",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=15_000,
            max_results=16,
        ),
        query_text=QUERY,
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(displayed_entity_ids=()),
        max_candidates=proposal.max_candidates,
    )
    web_result = inputs.web_search(request)
    web_items = [
        item
        for candidate in web_result.candidates
        for item in candidate.evidence
    ]
    ninebot_items = [
        item for item in web_items if "九号" in (item.snippet or "")
    ]
    print(f"lane candidates: {len(web_result.candidates)} web items: {len(web_items)}")
    for item in web_items:
        marker = " <== 九号" if "九号" in (item.snippet or "") else ""
        print(
            "  ",
            (item.snippet or "")[:55].replace("\n", " "),
            marker,
        )
    print(f"九号 in lane items: {len(ninebot_items)}")

    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=QUERY,
        protected_slots=(),
        items=tuple(web_items),
        traces=(),
        limitations=(),
        entity_handles=(),
    )
    answer = inputs.answer_factory()
    turn = TurnRequest(
        session_id="probe-session",
        turn_id="turn:probe:e2e",
        query=QUERY,
        release_id=RELEASE_ID,
        evidence_set=evidence_set,
    )
    result = answer.answer(turn)
    claims_text = " | ".join(claim.text for claim in result.claims)
    print(f"\nclaims: {len(result.claims)} 九号_in_claims={('九号' in claims_text)}")
    for claim in result.claims:
        print("  -", claim.text[:90].replace("\n", " "))
    answer_text = result.answer_text or ""
    print(f"\n九号 in answer: {'九号' in answer_text}")
    print((answer_text or "")[:600])


if __name__ == "__main__":
    raise SystemExit(main())
