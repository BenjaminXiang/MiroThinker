"""Latency oracle (快). Measures /api/chat wall-clock, bucketed by query_type.
Retrieval SLO (synthesis OFF): p95 <= 6s. End-to-end SLO (synthesis ON): p95 <= 15s.
e2e needs CHAT_LLM_SYNTHESIS=on + DeepSeek key; run separately (design §1.3).

Run (from apps/admin-console):
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
  uv run python scripts/eval_latency.py [--runs 3]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real",
)
os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_recall import CASES  # noqa: E402

from backend.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

RETRIEVAL_SLO_P95 = 6.0   # seconds; synthesis off
E2E_SLO_P95 = 15.0        # seconds; synthesis on (separate run)


def _percentile(samples: list[float], pct: float) -> float:
    # Nearest-rank method: rank = ceil(pct/100 * n), 1-indexed, clamped to [1, n].
    # Returns an actual observed sample, so for a small set p95 is the max —
    # the smallest value such that >= pct% of samples fall at or below it.
    # (Linear interpolation would yield a smoothed 4.8 for p95 of [1,2,3,4,5],
    # below the real worst sample; nearest-rank reports the true max.)
    if not samples:
        return 0.0
    s = sorted(samples)
    rank = max(1, math.ceil(pct / 100.0 * len(s)))
    rank = min(rank, len(s))
    return float(s[rank - 1])


def _slo_verdict(p95: float, *, kind: str) -> str:
    limit = RETRIEVAL_SLO_P95 if kind == "retrieval" else E2E_SLO_P95
    return "PASS" if p95 <= limit else "FAIL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    client = TestClient(app)
    synthesis_off = os.environ.get("CHAT_LLM_SYNTHESIS", "off") == "off"
    kind = "retrieval" if synthesis_off else "e2e"
    rows: list[dict] = []
    all_p95: list[float] = []
    print(f"{'qid':>3} {'qtype':<20} {'p50':>6} {'p95':>6} {'max':>6}  verdict  query")
    print("-" * 88)
    for c in CASES:
        samples: list[float] = []
        qtype = "?"
        for _ in range(args.runs):
            t0 = time.perf_counter()
            try:
                r = client.post("/api/chat", json={"query": c.query})
            except Exception as e:  # noqa: BLE001
                print(f"{c.qid:>3} ERR {type(e).__name__}")
                break
            samples.append(time.perf_counter() - t0)
            if qtype == "?":
                qtype = str(r.json().get("query_type", "?"))
        if not samples:
            rows.append({"qid": c.qid, "error": "request_failed"})
            continue
        p50 = _percentile(samples, 50)
        p95 = _percentile(samples, 95)
        mx = max(samples)
        all_p95.append(p95)
        verdict = _slo_verdict(p95, kind=kind)
        rows.append({"qid": c.qid, "query_type": qtype, "p50": p50, "p95": p95,
                     "max": mx, "verdict": verdict})
        print(f"{c.qid:>3} {qtype[:20]:<20} {p50:>6.2f} {p95:>6.2f} {mx:>6.2f}  {verdict:<7} {c.query[:30]}")
    print("-" * 88)
    overall_p95 = _percentile(all_p95, 95) if all_p95 else 0.0
    print(f"{kind.upper()} p95 (across cases): {overall_p95:.2f}s — SLO {_slo_verdict(overall_p95, kind=kind)}")
    out = os.path.join(os.path.dirname(__file__), "..", "..", ".agents",
                       "runs", "retrieval-generation-alignment", "latency-baseline.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"kind": kind, "runs": args.runs, "rows": rows,
                   "overall_p95": overall_p95, "slo_verdict": _slo_verdict(overall_p95, kind=kind)},
                  fh, ensure_ascii=False, indent=2)
    print(f"WRITTEN: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
