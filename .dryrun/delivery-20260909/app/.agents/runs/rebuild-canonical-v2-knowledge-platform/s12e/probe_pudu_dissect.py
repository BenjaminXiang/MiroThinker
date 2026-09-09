"""Stage-by-stage dissection: where the full-name turn loses the local patent claims.

Runs ONE query ("深圳市普渡科技有限公司有哪些专利") on a fresh answer session
and prints the deterministic selector proposals, per-claim grounding outcomes,
session advance constraints, and the final claims.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import knowledge_answer as answer_module  # noqa: E402
from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving  # noqa: E402
from src.data_agents.canonical_v2.knowledge_answer import TurnRequest  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    CanonicalEntityHandle,
    EvidenceClaimBinding,
    EvidenceItem,
    EvidenceSet,
    LaneRequest,
    ProtectedSlot,
    StructuredConstraints,
    WebSearchPolicy,
)

RUN_ROOT = Path(
    "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation/.agents/runs/rebuild-canonical-v2-knowledge-platform"
)
RELEASE_ID = "candidate-s12e-20260801-v1"
PUDU_ID = "company-c-5fac6a22c980262f125f995d"
NOW = datetime.now(UTC)
QUERY = "深圳市普渡科技有限公司有哪些专利"


class _Embedding:
    model_id = "Qwen/Qwen3-Embedding-8B"


def main() -> None:
    recorded = serving.load_recorded_serving_inputs(
        path=RUN_ROOT / "s12e/serving-bundle-s12e.json",
        expected_content_sha256="5a63b566601f329ff1180c7c0e3a0285e23286d2f78d72e03eefa5b9606f0731",
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12e_20260801_v1",
        expected_index_root=Path("/var/tmp/mirothinker-canonical-v2-s12e/index"),
        expected_envelope_path=RUN_ROOT / "s12a/complete-candidate-build-envelope.json",
        embedding_adapter=_Embedding(),
    )
    bundle = serving._read_bundle(RUN_ROOT / "s12e/serving-bundle-s12e.json")

    conn = sqlite3.connect(
        "/var/tmp/mirothinker-canonical-v2-s12e/serving-pack/lookup.sqlite3"
    )
    patent_items: list[EvidenceItem] = []
    patent_handles: list[CanonicalEntityHandle] = []
    rows = conn.execute(
        "select canonical_object_id, document_json from lookup_document "
        "where projection_id='lookup:exact-lookup:patent' "
        "and document_json like '%普渡%'"
    ).fetchall()
    for object_id, doc in rows:
        d = json.loads(doc)
        lc = d["lookup_content"]
        if isinstance(lc, str):
            lc = json.loads(lc)
        payload = dict(lc)
        payload["_relationship"] = {
            "relationship_type": "patent_has_applicant",
            "roles": ["applicant"],
            "source_id": object_id,
            "target_id": PUDU_ID,
        }
        snippet = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        evidence_id = f"evidence:probe:{object_id}"
        patent_items.append(
            EvidenceItem(
                evidence_id=evidence_id,
                object_id=object_id,
                domain="patent",
                lane="relationship",
                source_nature="local",
                source_locator=f"canonical-v2-probe:{object_id}",
                snippet=snippet,
                score=1.0,
                source_authority="canonical_release",
                observed_at=NOW,
                claim_binding=EvidenceClaimBinding(
                    subject_id=f"canonical:company:{PUDU_ID}",
                    predicate="patent_has_applicant",
                    value=f"canonical:patent:{object_id}",
                    status="accepted",
                ),
            )
        )
        patent_handles.append(
            CanonicalEntityHandle(
                canonical_id=object_id,
                domain="patent",
                display_name=str(lc.get("title") or object_id),
                evidence_ids=(evidence_id,),
            )
        )
    print(f"patent items: {len(patent_items)}")

    protected_slot = ProtectedSlot(
        kind="displayed_entity_set",
        value="displayed_entity_set",
        entity_ids=(PUDU_ID,),
    )
    web_request = LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query=QUERY,
        behavior_class="D",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=10_000,
            max_results=8,
        ),
        query_text=QUERY,
        domains=("patent",),
        protected_slots=(protected_slot,),
        structured_constraints=StructuredConstraints(displayed_entity_ids=(PUDU_ID,)),
        max_candidates=24,
    )
    web_items = [
        item for candidate in recorded.web_search(web_request).candidates for item in candidate.evidence
    ]
    print(f"web items: {len(web_items)}")

    evidence_set = EvidenceSet(
        release_id=RELEASE_ID,
        original_query=QUERY,
        protected_slots=(protected_slot,),
        items=(*patent_items, *web_items),
        traces=(),
        limitations=(),
        entity_handles=tuple(patent_handles),
    )
    turn = TurnRequest(
        session_id="probe-dissect",
        turn_id="turn:probe:dissect-1",
        query=QUERY,
        release_id=RELEASE_ID,
        evidence_set=evidence_set,
    )

    selector = serving._answer_selector(bundle=bundle)
    proposal = selector(turn)
    local_proposals = [c for c in proposal.claims if c.source_natures != ("current_web",)]
    web_proposals = [c for c in proposal.claims if c.source_natures == ("current_web",)]
    print(f"selector proposals: total={len(proposal.claims)} local={len(local_proposals)} web={len(web_proposals)}")
    for c in local_proposals[:3]:
        print("  local proposal:", c.text[:70])

    evidence_by_id = {item.evidence_id: item for item in evidence_set.items}
    selector_claim_ids = frozenset(c.claim_id for c in proposal.claims)
    grounded_kept = 0
    grounded_dropped: list[str] = []
    for claim in proposal.claims:
        kept = answer_module._ground_claim(
            claim,
            evidence_set=evidence_set,
            selector_claim_ids=selector_claim_ids,
        )
        if kept is None:
            grounded_dropped.append(claim.claim_id)
        else:
            grounded_kept += 1
    print(f"grounding: kept={grounded_kept} dropped={len(grounded_dropped)}")
    for claim_id in grounded_dropped[:5]:
        claim = next(c for c in proposal.claims if c.claim_id == claim_id)
        print("  dropped:", claim.text[:70], "| evidence ok:", all(e in evidence_by_id for e in claim.evidence_ids))

    answer = recorded.answer_factory()
    result = answer.answer(turn)
    print("final response_mode:", result.response_mode)
    print("final claims:", len(result.claims))
    for claim in result.claims[:8]:
        print("  final:", claim.text[:70])
    print("answer:", (result.answer_text or "")[:240])


if __name__ == "__main__":
    main()
