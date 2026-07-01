"""Three-layer eval of /api/chat generated answers (synthesis ON) vs golden test_cases.yaml.

L1 required-entity coverage (deterministic); L2 forbidden-entity gate (deterministic);
L3 answer-vs-golden judge (异模型 LLM, six PRD dimensions) — added in Task 3.

Run (from apps/admin-console), env-truth first:
  source scripts/eval_env.sh
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 UV_OFFLINE=1 uv run python scripts/eval_answer.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

os.environ.setdefault("CHAT_LLM_SYNTHESIS", "on")


def _load_cases() -> list[dict]:
    p = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_cases.yaml"
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["cases"]


def score_l1_required(case: dict, answer: str) -> tuple[list[str], list[str]]:
    """L1: required_entities must appear in the generated answer. Returns (hit, miss)."""
    req = case.get("required_entities") or []
    hit = [e for e in req if e in answer]
    miss = [e for e in req if e not in answer]
    return hit, miss


def score_l2_forbidden(case: dict, answer: str) -> list[str]:
    """L2: forbidden_entities must NOT appear. Returns violations."""
    forb = case.get("forbidden_entities") or []
    return [e for e in forb if e in answer]


def _run_chat(query: str) -> dict:
    """Run /api/chat (synthesis ON) and return the response JSON."""
    from backend.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    return client.post("/api/chat", json={"query": query}).json()


def main() -> int:
    cases = _load_cases()
    rows: list[dict] = []
    print(f"{'qid':>3} {'L1 hit/req':>10} {'L2 viol':>8}  query")
    print("-" * 80)
    for c in cases:
        try:
            j = _run_chat(c["query"])
        except Exception as e:  # noqa: BLE001
            rows.append({"qid": c["qid"], "error": str(e)})
            print(f"{c['qid']:>3} ERR {type(e).__name__}")
            continue
        answer = str(j.get("answer_text") or j.get("answer") or "")
        hit, miss = score_l1_required(c, answer)
        viol = score_l2_forbidden(c, answer)
        rows.append({
            "qid": c["qid"], "query": c["query"],
            "l1_hit": hit, "l1_miss": miss, "l2_violations": viol,
        })
        print(f"{c['qid']:>3} {len(hit)}/{len(c.get('required_entities') or []):>3}    "
              f"{len(viol):>4}     {c['query'][:30]}")
    # scripts/ -> apps/ -> admin-console/ -> apps/ -> repo root (parents[3])
    out = Path(__file__).resolve().parents[3] / ".agents" / "runs" / "retrieval-eval" / "l1l2-run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"rows": rows}, fh, ensure_ascii=False, indent=2)
    print(f"WRITTEN: {out}")
    print("NOTE: L3 (judge) added in Task 3. Run eval_answer.py again after Task 3 for full eval.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
