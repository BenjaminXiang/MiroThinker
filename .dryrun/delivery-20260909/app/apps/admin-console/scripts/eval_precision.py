"""Precision oracle (准). Surfaces returned candidates + unsourced-web provenance
per case so false positives can be labeled. v1 does NOT score precision (no labels
yet) — it produces the labeling substrate (design §1.2: first run = baseline).

Run (from apps/admin-console):
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
  uv run python scripts/eval_precision.py
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real",
)
os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")
os.environ.setdefault("CHAT_LLM_SYNTHESIS", "off")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_recall import CASES  # noqa: E402

from backend.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_WEB_TYPES = {"web"}


def _walk_candidates(node: object) -> Iterator[dict]:
    """Recursively yield dicts that look like evidence candidates (carry a known type)."""
    if isinstance(node, dict):
        t = node.get("type") or node.get("source_type")
        if t in {"professor", "paper", "company", "web"}:
            yield node
        for v in node.values():
            yield from _walk_candidates(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_candidates(item)


def _display_name(cand: dict) -> str:
    # Chat response renders the name as "label"; Evidence-shaped dicts use name/title.
    return (cand.get("label") or cand.get("name") or cand.get("title")
            or cand.get("snippet") or "").strip()


def _count_unsourced_web(response: dict) -> int:
    n = 0
    for cand in _walk_candidates(response):
        if (cand.get("type") or cand.get("source_type")) in _WEB_TYPES:
            url = cand.get("url") or cand.get("source_url")
            if not url:
                n += 1
    return n


def main() -> int:
    client = TestClient(app)
    rows: list[dict] = []
    total_unsourced = 0
    print(f"{'qid':>3} {'qtype':<22} {'cands':>5} {'unsourced_web':>13}  candidates")
    print("-" * 96)
    for c in CASES:
        try:
            r = client.post("/api/chat", json={"query": c.query})
        except Exception as e:  # noqa: BLE001
            print(f"{c.qid:>3} ERR {type(e).__name__}: {str(e)[:80]}")
            rows.append({"qid": c.qid, "error": str(e)})
            continue
        if r.status_code != 200:
            print(f"{c.qid:>3} HTTP{r.status_code} {r.text[:80]}")
            rows.append({"qid": c.qid, "http": r.status_code})
            continue
        j = r.json()
        cands = list(_walk_candidates(j))
        names = [_display_name(x) for x in cands]
        unsourced = _count_unsourced_web(j)
        total_unsourced += unsourced
        qtype = str(j.get("query_type", "?"))
        rows.append({
            "qid": c.qid, "query": c.query, "query_type": qtype,
            "candidate_names": names, "unsourced_web": unsourced,
            "required": c.required, "false_positives": c.false_positives,
        })
        print(f"{c.qid:>3} {qtype[:22]:<22} {len(names):>5} {unsourced:>13}  {names[:4]}")
    print("-" * 96)
    print(f"UNSOURCED WEB (§5 provenance risk): {total_unsourced}")
    out = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".agents",
                       "runs", "retrieval-generation-alignment", "precision-baseline.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"rows": rows, "total_unsourced_web": total_unsourced}, fh,
                  ensure_ascii=False, indent=2)
    print(f"WRITTEN: {out}")
    print("NOTE: v1 surfaces candidates for labeling. Score precision in v2 after labels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
