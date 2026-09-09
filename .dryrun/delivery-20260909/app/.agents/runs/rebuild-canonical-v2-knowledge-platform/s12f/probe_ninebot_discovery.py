"""Diagnose where 九号 sits in the merged web views for the hotel T1 query.

Dumps the literal-view merge order (pre-cut) and reports the rank/url of
every result whose title or snippet mentions 九号, so the recall gap can be
traced to the view, the rank, or the theme probe.
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
    ProtectedSlot,
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
    lane = inputs.web_search
    proposal = inputs.proposal_provider(
        serving.QueryPlanningRequest(
            request_id="query-request:probe-ninebot",
            release_id=RELEASE_ID,
            original_query=QUERY,
            as_of=NOW,
        )
    )
    print(
        "proposal: max_candidates=",
        proposal.max_candidates,
        "max_web_results=",
        proposal.max_web_results,
    )
    view_proposals = getattr(proposal, "query_views", None)
    if view_proposals is None:
        view_proposals = getattr(proposal, "views", None)
    if view_proposals is not None:
        print("proposal views:")
        for index, view in enumerate(view_proposals):
            text = getattr(view, "text", None) or getattr(view, "query", view)
            kind = getattr(view, "kind", "")
            print(f"  [{index}] kind={kind} text={text}")
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
    print("view queries:")
    for index, q in enumerate(queries):
        print(f"  [{index}] {q}")
    merged = lane._merged_results_for_views(queries)
    print(f"\nmerged total: {len(merged)}")
    for rank, result in enumerate(merged, start=1):
        text = f"{result.title}：{result.snippet[:60]}".replace("\n", " ")
        marker = " <== 九号" if "九号" in text else ""
        print(f"{rank:3d} {result.url[:70]:70s} {marker}{text[:70]}")
    hits = [
        (rank, result)
        for rank, result in enumerate(merged, start=1)
        if "九号" in f"{result.title}：{result.snippet}"
    ]
    print(f"\n九号 hits: {len(hits)}")
    for rank, result in hits:
        print(f"  rank {rank}: {result.url}")

    # Trace the lane's internal merge on THIS invocation (each call re-queries
    # the providers, so ranks differ between calls).
    # Trace the lane's internal merge on THIS invocation (each call re-queries
    # the providers, so ranks differ between calls).
    original_merge = lane._merged_results_for_views
    original_proposal = inputs.proposal_provider
    original_views = lane._request_view_queries
    original_normalize = lane._normalize_and_order_results
    view_sequence: list[int] = []
    ninebot_by_view: dict[int, int] = {}
    view_sizes: dict[int, int] = {}
    global_trace: dict[int, dict] = {}
    attempt_number = 0

    def traced_normalize(provider_results):
        view_index = len(view_sequence)
        view_sequence.append(view_index)
        out = original_normalize(provider_results=provider_results)
        view_sizes[view_index] = len(out)
        for rank, result in enumerate(out, start=1):
            if "九号" in f"{result.title}：{result.snippet}":
                ninebot_by_view[view_index] = rank
        return out

    def traced_views(request, query_text):
        out = original_views(request, query_text)
        print(f"TRACE view queries: {len(out)}")
        for index, q in enumerate(out):
            print(f"  TRACE [{index}] {q}")
        return out

    def traced_merge(queries):
        out = original_merge(queries)
        print(f"TRACE merged total: {len(out)}")
        for index, query in enumerate(queries):
            print(
                f"  TRACE view[{index}] size={view_sizes.get(index, '?')} "
                f"九号_rank={ninebot_by_view.get(index, 'absent')} {query[:40]}"
            )
        for rank, result in enumerate(out, start=1):
            if "九号" in f"{result.title}：{result.snippet}":
                print(f"TRACE lane-internal merged rank {rank}: {result.url}")
        return out

    lane._request_view_queries = traced_views
    lane._normalize_and_order_results = traced_normalize
    lane._merged_results_for_views = traced_merge
    web_result = lane(request)
    web_items = [
        item
        for candidate in web_result.candidates
        for item in candidate.evidence
    ]
    print(f"\nweb lane candidates: {len(web_result.candidates)}")
    for index, candidate in enumerate(web_result.candidates):
        snippets = " | ".join(
            (item.snippet or "")[:50].replace("\n", " ")
            for item in candidate.evidence
        )
        marker = " <== 九号" if "九号" in snippets else ""
        print(f"  {index}: {candidate.raw_candidate_id[:40]} {marker} {snippets[:90]}")
    ninebot = [
        item
        for candidate in web_result.candidates
        for item in candidate.evidence
        if "九号" in (item.snippet or "")
    ]
    print(f"\n九号 in lane candidates: {len(ninebot)}")
    for item in ninebot:
        print("  ", item.source_locator, (item.snippet or "")[:120])


if __name__ == "__main__":
    raise SystemExit(main())
