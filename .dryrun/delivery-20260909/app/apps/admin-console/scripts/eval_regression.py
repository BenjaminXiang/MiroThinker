"""Regression gate: run eval_answer, diff against committed golden baseline, exit non-zero on regression.

Exit 1 if: any L1 case regressed (a previously-hit required entity now missed) OR any L2 case
regressed (a forbidden entity now appears that wasn't in golden) OR L3 overall average < threshold.
Exit 0 otherwise.

Golden baseline: .agents/runs/retrieval-eval/golden-baseline.json (committed). Re-derive after
intentional improvements (and after adding new cases via badcase_to_case.py).

Run (from apps/admin-console), env-truth first:
  source scripts/eval_env.sh
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 UV_OFFLINE=1 uv run python scripts/eval_regression.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REGRESSION = 1
OK = 0
_DEFAULT_L3_THRESHOLD = 0.0  # 0.0 = disabled until calibrated (spec: threshold post-baseline)


def _index_by_qid(report: dict) -> dict:
    return {r["qid"]: r for r in report.get("rows", []) if "qid" in r}


def decide_exit(current: dict, golden: dict, l3_threshold: float) -> int:
    """Pure function: decide exit code from current vs golden report. L3 threshold=0 disables."""
    cur, gold = _index_by_qid(current), _index_by_qid(golden)
    for qid, g in gold.items():
        c = cur.get(qid)
        if c is None:
            return REGRESSION  # case disappeared
        # L1 regression: a previously-hit entity now missed
        g_hit = set(g.get("l1_hit", []))
        c_miss = set(c.get("l1_miss", []))
        if g_hit & c_miss:
            return REGRESSION
        # L2 regression: a forbidden entity now appears (that wasn't in golden)
        g_viol = set(g.get("l2_violations", []))
        c_viol = set(c.get("l2_violations", []))
        if c_viol - g_viol:
            return REGRESSION
    # L3 threshold (per-case floor; only when threshold > 0 = calibrated)
    if l3_threshold > 0:
        for qid, c in cur.items():
            avg = c.get("l3_avg")
            if avg is not None and avg < l3_threshold:
                return REGRESSION
    return OK


def main() -> int:
    # run eval_answer to produce current report
    script = Path(__file__).resolve().parent / "eval_answer.py"
    subprocess.run([sys.executable, str(script)], check=True)
    current_path = Path(__file__).resolve().parents[3] / ".agents" / "runs" / "retrieval-eval" / "answer-eval.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    golden_path = Path(__file__).resolve().parents[3] / ".agents" / "runs" / "retrieval-eval" / "golden-baseline.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8")) if golden_path.exists() else {"rows": []}
    l3_threshold = float(os.environ.get("EVAL_L3_THRESHOLD", _DEFAULT_L3_THRESHOLD))
    code = decide_exit(current, golden, l3_threshold)
    print(f"regression gate exit={code} (L3 threshold={l3_threshold})")
    return code


if __name__ == "__main__":
    sys.exit(main())
