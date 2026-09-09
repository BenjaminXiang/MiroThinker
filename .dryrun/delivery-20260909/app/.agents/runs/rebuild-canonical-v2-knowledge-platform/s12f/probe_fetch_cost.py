"""测 web lane 在带 page_fetcher 时的耗时（fetch 是否瓶颈）。"""
from __future__ import annotations

import sys, time
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving  # noqa: E402
from src.data_agents.providers.page_fetch import create_tiered_page_fetcher  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    LaneRequest, QueryPlanningRequest, StructuredConstraints, WebSearchPolicy,
)

RUN_ROOT = AGENT_ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
RELEASE_ID = "candidate-s12f-20260801-v1"
QUERY = "介绍清华的丁文伯"


class _Embedding:
    model_id = "Qwen/Qwen3-Embedding-8B"


def main() -> None:
    fetcher = create_tiered_page_fetcher()
    inputs = serving.load_recorded_serving_inputs(
        path=RUN_ROOT / "s12f/serving-bundle-s12f.json",
        expected_content_sha256="93fb456012f5e9799414cd90fa2ea27bb7d58acd5d41c13ac3b9dea601aed9c0",
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12f_20260801_v1",
        expected_index_root=Path("/var/tmp/mirothinker-canonical-v2-s12f/index-v1"),
        expected_envelope_path=RUN_ROOT / "s12a/complete-candidate-build-envelope.json",
        embedding_adapter=_Embedding(),
        page_fetcher=fetcher,
    )
    lane = inputs.web_search
    request = LaneRequest(
        lane="web", release_id=RELEASE_ID, query_view="view:original",
        original_query=QUERY, behavior_class="D",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(mode="universal", max_provider_calls=2, timeout_ms=15_000, max_results=16),
        query_text=QUERY, domains=("professor",),
        protected_slots=(), structured_constraints=StructuredConstraints(displayed_entity_ids=()),
        max_candidates=24,
    )
    t0 = time.time()
    result = lane(request)  # 含 fetch（depth=2）
    print(f"web lane + fetch: {time.time()-t0:.1f}s")
    t0 = time.time()
    result = lane(request)  # 第二次（浏览器池已预热）
    print(f"web lane + fetch (预热后): {time.time()-t0:.1f}s")


if __name__ == "__main__":
    raise SystemExit(main())
