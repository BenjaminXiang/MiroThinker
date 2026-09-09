"""Check 深南电路/一博科技 in the PCB enumeration pipeline."""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    LaneRequest,
    QueryPlanningRequest,
    StructuredConstraints,
    WebSearchPolicy,
)

RUN_ROOT = AGENT_ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
RELEASE_ID = "candidate-s12f-20260801-v1"
QUERY = "我想找PCB打板， 有哪些推荐"


class _Embedding:
    model_id = "Qwen/Qwen3-Embedding-8B"


def main() -> None:
    inputs = serving.load_recorded_serving_inputs(
        path=RUN_ROOT / "s12f/serving-bundle-s12f.json",
        expected_content_sha256="93fb456012f5e9799414cd90fa2ea27bb7d58acd5d41c13ac3b9dea601aed9c0",
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12f_20260801_v1",
        expected_index_root=Path("/var/tmp/mirothinker-canonical-v2-s12f/index-v1"),
        expected_envelope_path=RUN_ROOT / "s12a/complete-candidate-build-envelope.json",
        embedding_adapter=_Embedding(),
    )
    proposal = inputs.proposal_provider(
        QueryPlanningRequest(
            request_id="query-request:probe-pcb",
            release_id=RELEASE_ID,
            original_query=QUERY,
            as_of=datetime.now(UTC),
        )
    )
    print("views:", [getattr(v, "text", "") for v in proposal.query_views])
    request = LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query=QUERY,
        behavior_class="D",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal", max_provider_calls=2, timeout_ms=15_000, max_results=48
        ),
        query_text=QUERY,
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(displayed_entity_ids=()),
        max_candidates=48,
    )
    queries = inputs.web_search._request_view_queries(request, QUERY)
    merged = inputs.web_search._merged_results_for_views(queries)
    for target in ("深南", "一博"):
        hits = [
            (rank, r)
            for rank, r in enumerate(merged, start=1)
            if target in f"{r.title}：{r.snippet}"
        ]
        print(f"{target}: hits={len(hits)}")
        for rank, r in hits[:5]:
            print(f"  rank {rank}: {r.title[:45]} | {r.url[:55]}")


if __name__ == "__main__":
    raise SystemExit(main())
