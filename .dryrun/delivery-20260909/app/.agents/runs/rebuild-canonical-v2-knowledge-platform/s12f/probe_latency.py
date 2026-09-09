"""分解 web lane retrieval 耗时：视图搜索 / gap judge / fetch / 探针。"""
from __future__ import annotations

import sys, time
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    LaneRequest, QueryPlanningRequest, StructuredConstraints, WebSearchPolicy,
)

RUN_ROOT = AGENT_ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
RELEASE_ID = "candidate-s12f-20260801-v1"
QUERY = "介绍清华的丁文伯"


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
    lane = inputs.web_search

    # 1) 单视图单 provider 耗时
    for name, prov in (("bocha", lane._bocha), ("serper", lane._serper)):
        t0 = time.time()
        try:
            r = prov.search("丁文伯 清华大学")
            items = r if isinstance(r, list) else r.get("organic", [])
            print(f"{name} 单次搜索: {time.time()-t0:.1f}s, {len(items)} 条")
        except Exception as e:
            print(f"{name} 单次搜索: {time.time()-t0:.1f}s ERR {str(e)[:60]}")

    # 2) merged（4 视图 × 2 provider 并发）耗时
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
    queries = lane._request_view_queries(request, QUERY)
    merged = lane._merged_results_for_views(queries)
    print(f"merged({len(queries)}视图): {time.time()-t0:.1f}s, {len(merged)} 条")

    # 3) 完整 web lane（含 gap judge + fetch）
    t0 = time.time()
    result = lane(request)
    print(f"web lane 完整调用: {time.time()-t0:.1f}s, candidates={len(result.candidates)}")


if __name__ == "__main__":
    raise SystemExit(main())
