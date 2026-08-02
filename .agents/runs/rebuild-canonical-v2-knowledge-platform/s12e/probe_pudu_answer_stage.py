"""In-process answer-stage A/B: full legal name vs short name patent query.

Builds the same evidence set shape the live turn sees — the 17 source-bound
relationship patent items for Pudu (projection JSON from the pack lookup
store) plus the LIVE web lane result for each query — then runs the real
recorded answer factory (environment LLM selector + prose) on both queries.

Prints the claim materialization and the final answer text per query so the
exact stage where the full-name turn loses the patents is visible.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

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
    assert len(patent_items) == 17

    for query in (
        "深圳市普渡科技有限公司有哪些专利",
        "普渡科技的专利有哪些",
    ):
        protected_slot = ProtectedSlot(
            kind="displayed_entity_set",
            value="displayed_entity_set",
            entity_ids=(PUDU_ID,),
        )
        web_request = LaneRequest(
            lane="web",
            release_id=RELEASE_ID,
            query_view="view:original",
            original_query=query,
            behavior_class="D",
            interaction_mode="information_retrieval",
            web_policy=WebSearchPolicy(
                mode="universal",
                max_provider_calls=2,
                timeout_ms=10_000,
                max_results=8,
            ),
            query_text=query,
            domains=("patent",),
            protected_slots=(protected_slot,),
            structured_constraints=StructuredConstraints(
                displayed_entity_ids=(PUDU_ID,)
            ),
            max_candidates=24,
        )
        web_result = recorded.web_search(web_request)
        web_items = [
            item
            for candidate in web_result.candidates
            for item in candidate.evidence
        ]
        print(f"web items for {query!r}: {len(web_items)}")
        for item in web_items:
            print(
                "  web:",
                item.domain,
                (item.snippet[:60] if item.snippet else ""),
            )

        evidence_set = EvidenceSet(
            release_id=RELEASE_ID,
            original_query=query,
            protected_slots=(protected_slot,),
            items=(*patent_items, *web_items),
            traces=(),
            limitations=(),
            entity_handles=tuple(patent_handles),
        )
        answer = recorded.answer_factory()
        turn = TurnRequest(
            session_id="probe-session",
            turn_id=f"turn:probe:{abs(hash(query))}",
            query=query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
        result = answer.answer(turn)
        print(f"=== {query!r}")
        print("  response_mode:", result.response_mode)
        print("  answer:", (result.answer_text or "")[:300])
        print("  claims:", len(result.claims))
        for claim in result.claims[:6]:
            print("   -", claim.text[:80])
        for trace in result.selector_traces[:4]:
            print("  selector trace:", str(trace)[:160])


if __name__ == "__main__":
    main()
