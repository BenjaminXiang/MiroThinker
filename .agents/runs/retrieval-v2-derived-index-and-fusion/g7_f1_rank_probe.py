#!/usr/bin/env python3
"""G7 recall RED evidence: F1 category-recall rank of the flagship companies
for the 具身智能 query and its view variants, offline on the sealed pack.

Runs the real `_category_recall_entries` (no reimplementation) over the
serving pack's company documents with an effectively uncapped window
(max_candidates) so the ranking position of each flagship is measurable
against the 64/128 cut points.

Usage:
  cd <serving-worktree>/apps/miroflow-agent
  uv run python \
    /home/longxiang/MiroThinker/.agents/runs/retrieval-v2-derived-index-and-fusion/g7_f1_rank_probe.py \
    [--out <report.json>]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

WORKTREE = Path(
    "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation"
)
sys.path.insert(0, str(WORKTREE / "apps/miroflow-agent"))

from src.data_agents.canonical_v2 import knowledge_read as read_mod  # noqa: E402
from src.data_agents.canonical_v2 import knowledge_read_isolated as read_iso  # noqa: E402
from src.data_agents.canonical_v2.index_projection_isolated import (  # noqa: E402
    _read_lookup_documents_from_path,
)

LOOKUP = Path("/var/tmp/mirothinker-data-v2/index-v1/lookup.sqlite3")
RELEASE_ID = "candidate-v2-20260819-r1"
QUERY = "深圳有哪些做具身智能的公司"
VIEWS = (
    QUERY,
    "深圳 具身智能 公司",
    "深圳 人形机器人 企业",
    "深圳 具身智能 厂商 产业链",
    "深圳有哪些做人形机器人的公司",
)
TARGETS = ("优必选", "越疆", "乐聚", "众擎", "逐际", "智平方", "自变量", "星尘")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    documents = _read_lookup_documents_from_path(LOOKUP)
    entries = read_iso._public_lookup_entries(documents)
    report: dict[str, object] = {
        "lookup": str(LOOKUP),
        "release_id": RELEASE_ID,
        "total_documents": len(documents),
        "views": [],
    }
    for view in VIEWS:
        request = read_mod.LaneRequest(
            lane="lexical",
            release_id=RELEASE_ID,
            query_view=view,
            original_query=QUERY,
            behavior_class="A",
            interaction_mode="information_retrieval",
            web_policy=read_mod.WebSearchPolicy(mode="universal"),
            query_text=view,
            domains=("company",),
            protected_slots=(),
            structured_constraints=read_mod.StructuredConstraints(),
            max_candidates=100000,
        )
        ranked = read_iso._category_recall_entries(request=request, entries=entries)
        names = [entry.display_name for entry in ranked]
        rows = []
        for target in TARGETS:
            rank = next(
                (index + 1 for index, name in enumerate(names) if target in name),
                None,
            )
            rows.append({"target": target, "rank": rank})
        view_report = {
            "view": view,
            "matched_total": len(ranked),
            "in_top64": {
                row["target"]: row["rank"] is not None and row["rank"] <= 64
                for row in rows
            },
            "in_top128": {
                row["target"]: row["rank"] is not None and row["rank"] <= 128
                for row in rows
            },
            "ranks": rows,
            "top10": names[:10],
        }
        report["views"].append(view_report)  # type: ignore[attr-defined]
        print("=" * 30, view)
        print("matched_total:", len(ranked))
        for row in rows:
            print(f"  {row['target']}: rank={row['rank']}")
        print("  top10:", names[:10])

    if args.out:
        Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
