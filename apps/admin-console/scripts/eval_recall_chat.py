"""Faithful end-to-end retrieval baseline via /api/chat (TestClient, no server).

Runs each single-turn case through the REAL /api/chat path (classification -> routing
-> recall/SQL) with LLM synthesis OFF (isolates retrieval+routing; no LLM-knowledge
confound). Counts a required entity as "recalled" if it appears ANYWHERE in the JSON
response (candidates or template answer). This is what the user actually experiences.

Run (from apps/admin-console):
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
  uv run python scripts/eval_recall_chat.py
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real",
)
os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")
os.environ.setdefault("CHAT_LLM_SYNTHESIS", "off")

# CASES + TestClient import must come after env defaults.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_recall import CASES  # noqa: E402

from backend.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def main() -> int:
    client = TestClient(app)
    total_req = total_hit = 0
    rows: list[dict] = []
    print(f"{'qid':>3} {'qtype':<24} {'hit/req':>8}  misses")
    print("-" * 92)
    for c in CASES:
        try:
            r = client.post("/api/chat", json={"query": c.query})
        except Exception as e:  # noqa: BLE001
            print(f"{c.qid:>3} {'ERR':<24} {'-':>8}  {type(e).__name__}: {str(e)[:120]}")
            total_req += len(c.required)
            rows.append({"qid": c.qid, "error": str(e)})
            continue
        if r.status_code != 200:
            print(f"{c.qid:>3} {'HTTP'+str(r.status_code):<24} {'-':>8}  {r.text[:120]}")
            total_req += len(c.required)
            rows.append({"qid": c.qid, "http": r.status_code})
            continue
        j = r.json()
        qtype = str(j.get("query_type", "?"))
        blob = json.dumps(j, ensure_ascii=False)
        hits = [req for req in c.required if req in blob]
        miss = [req for req in c.required if req not in blob]
        total_req += len(c.required)
        total_hit += len(hits)
        flag = "OK  " if not miss else "MISS"
        rows.append({"qid": c.qid, "query_type": qtype, "hits": hits, "misses": miss})
        print(f"{c.qid:>3} {qtype[:24]:<24} {len(hits)}/{len(c.required):>5} {flag}  {miss}")
    print("-" * 92)
    pct = 100.0 * total_hit / total_req if total_req else 0.0
    print(f"END-TO-END ENTITY RECALL (/api/chat, synthesis off): "
          f"{total_hit}/{total_req} ({pct:.0f}%)")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                       ".agents", "runs", "retrieval-generation-alignment", "post-fix-recall.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"total_hit": total_hit, "total_req": total_req, "pct": pct, "rows": rows},
                  fh, ensure_ascii=False, indent=2)
    print(f"WRITTEN: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
