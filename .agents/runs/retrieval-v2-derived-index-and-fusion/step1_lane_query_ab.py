#!/usr/bin/env python3
"""Step 1 evidence: raw-question OR fill vs content-residue OR fill.

Runs the lane's document selection directly against the deployed derived
index (no serving pack needed) and maps hits back to company names through
the bound lookup pack, so the two query shapes can be compared on the same
artifact. Usage:

  cd <worktree>/apps/miroflow-agent
  uv run python /home/longxiang/MiroThinker/.agents/runs/retrieval-v2-derived-index-and-fusion/step1_lane_query_ab.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ARTIFACT_ROOT = Path("/var/tmp/mirothinker-data-v2/derived/lexical")
RELEASE_ID = "candidate-v2-20260819-r1"
LOOKUP = Path("/var/tmp/mirothinker-data-v2/index-v1/lookup.sqlite3")

sys.path.insert(0, str(Path("/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation/apps/miroflow-agent")))

from src.data_agents.canonical_v2.knowledge_read_isolated import (  # noqa: E402
    _indexed_lexical_document_ids,
    _is_wide_recall_query,
    _lexical_index_query_text,
)
from src.data_agents.canonical_v2.lexical_index import open_lexical_index  # noqa: E402

QUERIES = (
    "深圳有哪些做激光雷达的公司",
    "中国有哪些成熟的酒店送餐机器人供应商",
    "我想找PCB打板, 有哪些推荐",
)
GT = {"云迹", "普渡", "开普勒", "九号", "擎朗"}


def main() -> int:
    index = open_lexical_index(
        artifact_root=ARTIFACT_ROOT, release_id=RELEASE_ID, lookup_sqlite=LOOKUP
    )
    assert index is not None, "artifact not open"
    names: dict[str, str] = {}
    with sqlite3.connect(f"file:{LOOKUP}?mode=ro", uri=True) as connection:
        for document_id, payload in connection.execute(
            "SELECT document_id, document_json FROM lookup_document"
        ):
            document = json.loads(payload)
            content = document.get("lookup_content") or "{}"
            try:
                fields = json.loads(content)
            except json.JSONDecodeError:
                fields = {}
            names[document_id] = str(
                fields.get("name") or fields.get("title") or document_id
            )

    for query in QUERIES:
        residue = _lexical_index_query_text(query)
        for label, phrase in (("raw", query), ("residue", residue)):
            selected = _indexed_lexical_document_ids(
                index=index,
                query_phrase=phrase,
                domains=("company",),
                max_candidates=128,
                wide_recall=_is_wide_recall_query(query),
            )
            listed = [names.get(document_id, document_id) for document_id in selected]
            hits = [name for name in listed if any(g in name for g in GT)]
            print(
                f"{query} [{label}={phrase!r}] selected={len(selected)} "
                f"gt={hits} top5={listed[:5]}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
