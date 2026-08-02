"""CN117873146A 查询的 web lane 实际候选——检查是否有优必选中文名证据。"""
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
QUERY = "专利 CN117873146A 的详细信息是什么"


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
            request_id="query-request:probe-patent-web",
            release_id=RELEASE_ID,
            original_query=QUERY,
            as_of=datetime.now(UTC),
        )
    )
    print("lanes:", proposal.lanes)
    print("views:", [getattr(v, "text", "") for v in proposal.query_views])
    request = LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query=QUERY,
        behavior_class="D",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal", max_provider_calls=2, timeout_ms=15_000, max_results=16
        ),
        query_text=QUERY,
        domains=("patent",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(displayed_entity_ids=()),
        max_candidates=proposal.max_candidates,
    )
    result = inputs.web_search(request)
    items = [it for c in result.candidates for it in c.evidence]
    print(f"\nweb candidates: {len(result.candidates)}")
    for i, it in enumerate(items[:12]):
        snip = (it.snippet or "")[:110].replace("\n", " ")
        marker = " <== 优必选" if "优必选" in (it.snippet or "") else ""
        print(f"  [{i}] {snip}{marker}")
    hits = [it for it in items if "优必选" in (it.snippet or "")]
    print(f"\n含'优必选'的 web items: {len(hits)}")
    for it in hits[:3]:
        print("  ", it.source_locator, "|", (it.snippet or "")[:150])


if __name__ == "__main__":
    raise SystemExit(main())
