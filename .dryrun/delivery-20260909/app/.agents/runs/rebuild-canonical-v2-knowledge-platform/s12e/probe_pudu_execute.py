"""Full execute() probe: does the live-shaped plan yield patent items in the evidence set?

Composes the exact serving-pack knowledge read (same factories as the runner),
plans the full-name query, executes it, and prints the evidence set inventory
(items by lane/domain, relationship-lane patent presence, handles).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving  # noqa: E402
from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader  # noqa: E402
from src.data_agents.canonical_v2.contracts import PublishedRelease  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import QueryPlanningRequest  # noqa: E402

RUN_ROOT = Path(
    "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation/.agents/runs/rebuild-canonical-v2-knowledge-platform"
)
RELEASE_ID = "candidate-s12e-20260801-v1"
NOW = datetime.now(UTC)
QUERY = "深圳市普渡科技有限公司有哪些专利"


class _Embedding:
    model_id = "Qwen/Qwen3-Embedding-8B"
    dimension = 4096

    def embed_batch(self, texts: tuple[str, ...]) -> list[list[float]]:
        return [[0.0] * self.dimension for _ in texts]


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else QUERY
    recorded = serving.load_recorded_serving_inputs(
        path=RUN_ROOT / "s12e/serving-bundle-s12e.json",
        expected_content_sha256="5a63b566601f329ff1180c7c0e3a0285e23286d2f78d72e03eefa5b9606f0731",
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12e_20260801_v1",
        expected_index_root=Path("/var/tmp/mirothinker-canonical-v2-s12e/index"),
        expected_envelope_path=RUN_ROOT / "s12a/complete-candidate-build-envelope.json",
        embedding_adapter=_Embedding(),
    )
    authority = pack_loader.open_serving_pack_authority(
        pack_dir=Path("/var/tmp/mirothinker-canonical-v2-s12e/serving-pack"),
        expected_release_id=RELEASE_ID,
        expected_index_marker_sha256=(
            "1fafb12bf8870244b34862801ccef6e6ea58434a95592c29355eee11c3ce04b1"
        ),
        expected_forbidden_milvus_path=Path(
            "/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"
        ),
    )
    published = PublishedRelease(
        release_id=RELEASE_ID,
        previous_release_id=None,
        canonical_release_id=RELEASE_ID,
        published_projection_release_id=RELEASE_ID,
        index_release_id=RELEASE_ID,
        state="active",
        changed_at=datetime(2026, 7, 22, tzinfo=UTC),
        verification_evidence_ids=tuple(authority.release_verification.evidence_ids),
    )
    planner = pack_loader.create_serving_pack_query_planner(
        authority=authority,
        published_release=published,
        planning_policy=recorded.planning_policy,
        proposal_provider=recorded.proposal_provider,
        ambiguity_policy=recorded.ambiguity_policy,
    )
    plan = planner.plan(
        QueryPlanningRequest(
            request_id="probe:execute:pudu-full-name",
            release_id=RELEASE_ID,
            original_query=query,
            as_of=NOW,
        )
    )
    print("plan lanes:", plan.lanes)
    print("plan displayed:", plan.structured_constraints.displayed_entity_ids)
    print("plan paths:", [(p.relationship_type_id, p.direction) for p in plan.relationship_paths])

    knowledge_read = pack_loader.create_serving_pack_knowledge_read(
        authority=authority,
        published_release=published,
        universal_web_policy=recorded.universal_web_policy,
        web_search=recorded.web_search,
        web_snapshot_policy=recorded.web_snapshot_policy,
        embedding_adapter=_Embedding(),
        identity_fuser=recorded.identity_fuser,
        reranker=recorded.reranker,
        sufficiency_decider=recorded.sufficiency_decider,
        supplemental_search=recorded.supplemental_search,
        web_handle_resolver=recorded.web_handle_resolver,
        accepted_identity_lookup=recorded.accepted_identity_lookup,
    )
    evidence_set = knowledge_read.execute(plan)
    print("evidence items:", len(evidence_set.items))
    by_lane: dict[str, int] = {}
    for item in evidence_set.items:
        by_lane.setdefault(f"{item.lane}/{item.domain}", 0)
        by_lane[f"{item.lane}/{item.domain}"] += 1
    print("by lane/domain:", by_lane)
    relationship_items = [item for item in evidence_set.items if item.lane == "relationship"]
    print("relationship items:", len(relationship_items))
    for item in relationship_items[:5]:
        print("  rel:", item.domain, item.object_id, (item.snippet[:60] if item.snippet else ""))
    print("handles:", [(h.domain, getattr(h, "canonical_id", None) or getattr(h, "handle_id", None)) for h in evidence_set.entity_handles][:8])
    print("fused candidates:", len(evidence_set.fused_candidates))
    for candidate in evidence_set.fused_candidates[:8]:
        print(
            "  fused:",
            getattr(candidate, "domain", None),
            getattr(candidate, "canonical_id", None),
            getattr(candidate, "display_name", None),
            type(candidate).__name__,
        )
    print("limitations:", [str(limitation)[:120] for limitation in evidence_set.limitations][:8])
    print("traces:", len(evidence_set.traces), "candidate_traces:", len(evidence_set.candidate_traces))
    from collections import Counter
    print("dispositions:", Counter(t.disposition for t in evidence_set.candidate_traces).most_common())
    print("fusion_receipt:", evidence_set.fusion_receipt)
    print("rerank_receipt:", evidence_set.rerank_receipt)
    print("sufficiency:", str(evidence_set.sufficiency_report)[:200])
    print("enumeration_coverage:", str(evidence_set.enumeration_coverage)[:200])


if __name__ == "__main__":
    main()
