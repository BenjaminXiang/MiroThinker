"""F1 — category-recall fallback: offline GT recall on the sealed run14 pack.

Re-runs the REAL lexical-lane functions from knowledge_read_isolated against
the sealed run14 serving pack (read-only): the "before" column is the
existing whole-phrase matcher (`_matches_lexical_request`, what production
runs today — trace shows lexical=0 for these turns), the "after" column is
`_category_recall_entries` (the F1 fallback the adapters call only when the
primary pass is empty).

Probe queries are verbatim run14 trace texts (worktree
var/turn-trace/2026-09-10.jsonl):
  g2-t1      中国有哪些成熟的酒店送餐机器人供应商   (session JgjH8u4M…)
  g5-t1      我想找PCB打板， 有哪些推荐             (session -YZXc4pO5…)
  pcb-list   深圳有哪些做PCB的公司                  (session PdsE2friEy…)
  embodied   深圳有哪些做具身智能的公司             (multiple sessions)

GT aliases from D0/D0.5 (d0-evidence.json / d05-findings.md). Entries are
built with the production `_public_lookup_entries` -> `_projection_terms`
chain, so the content terms matched here are exactly what the lane sees.

No network, no writes outside this directory's JSON output.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/miroflow-agent"))

from src.data_agents.canonical_v2 import (  # noqa: E402
    knowledge_read_isolated as iso,
)
from src.data_agents.canonical_v2.index_projection import (  # noqa: E402
    LookupProjectionDocument,
)
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    LaneRequest,
    StructuredConstraints,
    WebSearchPolicy,
)

PACK_LOOKUP_DB = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed/lookup.sqlite3")
OUT = Path(__file__).with_name("f1-category-recall.json")

QUERIES = (
    {
        "id": "g2-t1",
        "query": "中国有哪些成熟的酒店送餐机器人供应商",
        "gt": ("普渡", "开普勒", "云迹", "九号", "擎朗", "艾唯尔", "安赛步"),
    },
    {
        "id": "g5-t1",
        "query": "我想找PCB打板， 有哪些推荐",
        "gt": ("嘉立创", "深南电路", "一博", "顺易捷", "兴森", "则成", "上达", "精诚达"),
    },
    {
        "id": "pcb-list",
        "query": "深圳有哪些做PCB的公司",
        "gt": ("嘉立创", "深南电路", "一博", "顺易捷", "兴森", "则成", "上达", "精诚达"),
    },
    {
        "id": "embodied",
        "query": "深圳有哪些做具身智能的公司",
        "gt": (),
    },
)


def main() -> None:
    db = sqlite3.connect(f"file:{PACK_LOOKUP_DB}?mode=ro", uri=True)
    rows = db.execute("SELECT document_json FROM lookup_document").fetchall()
    documents = tuple(
        LookupProjectionDocument.model_validate(json.loads(row[0])) for row in rows
    )
    release_id = documents[0].release_id
    t0 = time.monotonic()
    entries = iso._public_lookup_entries(documents)
    build_s = time.monotonic() - t0
    company_entries = tuple(
        entry for entry in entries if entry.document.domain == "company"
    )

    report = {
        "pack": str(PACK_LOOKUP_DB),
        "release_id": release_id,
        "documents_total": len(documents),
        "public_entries": len(entries),
        "company_entries": len(company_entries),
        "entry_build_seconds": round(build_s, 2),
        "queries": [],
    }
    for spec in QUERIES:
        query = spec["query"]
        request = LaneRequest(
            lane="lexical",
            release_id=release_id,
            query_view="view:original",
            original_query=query,
            behavior_class="A",
            interaction_mode="information_retrieval",
            web_policy=WebSearchPolicy(mode="disabled"),
            query_text=query,
            domains=("company",),
            protected_slots=(),
            structured_constraints=StructuredConstraints(),
            max_candidates=48,
        )
        phrase = iso._lexical_query_phrase(query)
        before = [
            entry
            for entry in entries
            if iso._matches_lexical_request(
                request=request,
                document=entry.document,
                query_phrase=phrase,
                display_terms=entry.display_terms,
                content_terms=entry.content_terms,
            )
        ]
        t0 = time.monotonic()
        after = iso._category_recall_entries(request=request, entries=entries)
        fallback_ms = (time.monotonic() - t0) * 1000
        # Warm repeat: the first call in a process pays interpreter warm-up,
        # so the cold number above overstates steady-state serving latency.
        t0 = time.monotonic()
        iso._category_recall_entries(request=request, entries=entries)
        fallback_warm_ms = (time.monotonic() - t0) * 1000
        scored_pool = iso._category_recall_entries(
            request=request.model_copy(update={"max_candidates": 1_000_000}),
            entries=entries,
        )
        terms = iso._category_query_terms(query)
        # term coverage over the same eligible set the helper sees
        coverage = {
            term: sum(
                1
                for entry in company_entries
                if any(
                    term in content_term for content_term in entry.content_terms
                )
            )
            for term, _weight in terms
        }
        gt_rows = []
        for alias in spec["gt"]:
            gt_entries = [
                entry for entry in company_entries if alias in entry.display_name
            ]
            hits = []
            for gt_entry in gt_entries:
                rank = next(
                    (
                        index + 1
                        for index, entry in enumerate(after)
                        if entry.document.document_id == gt_entry.document.document_id
                    ),
                    None,
                )
                # Position in the full scored pool (beyond the 48 window) is
                # the near-miss evidence: pool_size + pool_rank together say
                # whether a miss is a window cut or zero term overlap.
                pool_rank = next(
                    (
                        index + 1
                        for index, entry in enumerate(scored_pool)
                        if entry.document.document_id == gt_entry.document.document_id
                    ),
                    None,
                )
                hits.append(
                    {
                        "display_name": gt_entry.display_name,
                        "document_id": gt_entry.document.document_id,
                        "rank": rank,
                        "pool_rank": pool_rank,
                    }
                )
            gt_rows.append(
                {
                    "alias": alias,
                    "identities_in_pack": len(gt_entries),
                    "recalled": sum(1 for hit in hits if hit["rank"] is not None),
                    "hits": hits,
                }
            )
        report["queries"].append(
            {
                "id": spec["id"],
                "query": query,
                "terms": [{"term": term, "weight": weight} for term, weight in terms],
                "term_coverage": coverage,
                "before_primary_hits": len(before),
                "after_fallback_hits": len(after),
                "scored_pool_size": len(scored_pool),
                "fallback_elapsed_ms": round(fallback_ms, 1),
                "fallback_elapsed_ms_warm": round(fallback_warm_ms, 1),
                "recalled_names": [entry.display_name for entry in after],
                "gt": gt_rows,
            }
        )
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    for query_report in report["queries"]:
        print(f"=== {query_report['id']}: {query_report['query']}")
        print(
            f"  terms={[(t['term'], t['weight']) for t in query_report['terms']]} "
            f"coverage={query_report['term_coverage']}"
        )
        print(
            f"  before={query_report['before_primary_hits']} "
            f"after={query_report['after_fallback_hits']} "
            f"pool={query_report['scored_pool_size']} "
            f"({query_report['fallback_elapsed_ms']} ms cold / "
            f"{query_report['fallback_elapsed_ms_warm']} ms warm)"
        )
        for gt in query_report["gt"]:
            ranks = [hit["rank"] for hit in gt["hits"] if hit["rank"] is not None]
            pool_ranks = [
                hit["pool_rank"] for hit in gt["hits"] if hit["pool_rank"] is not None
            ]
            print(
                f"  GT {gt['alias']}: identities={gt['identities_in_pack']} "
                f"recalled={gt['recalled']} ranks={ranks} pool_ranks={pool_ranks}"
            )


if __name__ == "__main__":
    main()
