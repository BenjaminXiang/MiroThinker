"""Stability check: run proposal+web merge for the hotel T1 query N times.

Each iteration re-runs the LLM rewriter (extras drift) and re-queries the
providers (rank drift).  Reports per-iteration extras, the rank of the 九号
news URL in each view and in the merged output, and whether it lands inside
the 24-wide enumeration window.
"""

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

RUN_ROOT = (
    AGENT_ROOT
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
)
RELEASE_ID = "candidate-s12f-20260801-v1"
NOW = datetime.now(UTC)
QUERY = "中国有哪些成熟的酒店送餐机器人供应商"
TARGET = "九号"


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
    lane = inputs.web_search
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    for attempt in range(1, rounds + 1):
        proposal = inputs.proposal_provider(
            QueryPlanningRequest(
                request_id=f"query-request:stability:{attempt}",
                release_id=RELEASE_ID,
                original_query=QUERY,
                as_of=datetime.now(UTC),
            )
        )
        views = getattr(proposal, "query_views", None) or getattr(
            proposal, "views", ()
        )
        extras = tuple(
            getattr(view, "text", None) or getattr(view, "query", "")
            for view in views[1:]
        )
        view_texts = (
            getattr(view, "text", None) or getattr(view, "query", "")
            for view in views
        )
        print(f"--- attempt {attempt} ---")
        for index, text in enumerate(view_texts):
            print(f"  proposal[{index}] {text}")
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
            max_candidates=24,
        )
        queries = lane._request_view_queries(request, QUERY)
        view_counts = len(queries)
        per_view = []
        for index in range(view_counts):
            futures = {
                provider: lane._search_provider(
                    lane._bocha if provider == "bocha-v1" else lane._serper,
                    queries[index]
                    if provider == "bocha-v1"
                    else serving._relaxed_serper_query(queries[index]),
                )
                for provider in ("bocha-v1", "serper-v1")
            }
            provider_results = {}
            for provider, future in futures.items():
                try:
                    provider_results[provider] = future.result(
                        timeout=15.0
                    )
                except Exception:  # noqa: BLE001
                    provider_results[provider] = []
            per_view.append(
                lane._normalize_and_order_results(
                    provider_results=provider_results
                )
            )
        for index, view in enumerate(per_view):
            rank = next(
                (
                    r
                    for r, item in enumerate(view, start=1)
                    if TARGET in f"{item.title}：{item.snippet}"
                ),
                None,
            )
            print(f"  view[{index}] n={len(view)} 九号_rank={rank} {queries[index][:34]}")
        merged = lane._merged_results_for_views(queries)
        merged_rank = next(
            (
                r
                for r, item in enumerate(merged, start=1)
                if TARGET in f"{item.title}：{item.snippet}"
            ),
            None,
        )
        print(
            f"  merged n={len(merged)} 九号_merged_rank={merged_rank} "
            f"in_window_24={merged_rank is not None and merged_rank <= 24}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
