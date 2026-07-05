"""Multi-run median stability harness for /api/chat recall.

Runs `eval_recall_chat.py` N times (default 3) and reports the MEDIAN per-case
hit/req + overall, plus the run-to-run swing. Addresses benchmark-completion-spec
criterion 4 (Stability) — the LLM classifier + L3 judge swing qid11/17/20 run-to-run,
so a single run is not a reliable gate; the median over N runs is.

Usage (backend DOWN — TestClient opens Milvus in-process; proxy unset):
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
  uv run python scripts/eval_recall_chat_stable.py --runs 3

Output: per-case median hit/req + overall median + max swing (stability signal).
A case is STABLE if its hit/req is identical across runs; UNSTABLE otherwise
(those are the L3-variance cases to watch / average).
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EVAL = REPO / "apps" / "admin-console" / "scripts" / "eval_recall_chat.py"


def _run_once(env: dict, offline: bool) -> dict:
    """Run eval_recall_chat.py once; parse its JSON output (total_hit/total_req/rows)."""
    cmd = [sys.executable, str(EVAL)]
    out = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    # eval_recall_chat writes JSON to the post-fix-recall.json path; read it.
    artifact = REPO / ".agents" / "runs" / "retrieval-generation-alignment" / "post-fix-recall.json"
    if not artifact.exists():
        raise RuntimeError(f"eval produced no artifact; stderr:\n{out.stderr[-800:]}")
    return json.loads(artifact.read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    import os

    env = dict(os.environ)
    env.setdefault("CHAT_LLM_SYNTHESIS", "off")
    if env.get("UV_OFFLINE") is None:
        env["UV_OFFLINE"] = "1"

    per_case: dict[str, list[int]] = defaultdict(list)  # qid -> [hits per run]
    per_case_req: dict[str, int] = {}
    overalls: list[tuple[int, int]] = []
    for i in range(args.runs):
        print(f"=== run {i + 1}/{args.runs} ===", file=sys.stderr)
        rep = _run_once(env, True)
        overalls.append((rep["total_hit"], rep["total_req"]))
        for row in rep["rows"]:
            qid = str(row["qid"])
            per_case[qid].append(len(row["hits"]))
            per_case_req[qid] = row.get("misses") and (len(row["hits"]) + len(row["misses"])) or len(row["hits"])

    print("\n=== MEDIAN per-case (over {} runs) ===".format(args.runs))
    print(f"{'qid':>4} {'median_hit':>10} {'req':>4} {'swing':>10} {'stable':>7}")
    unstable = []
    total_hit_med = 0
    for qid in sorted(per_case, key=lambda x: int(x)):
        hits = per_case[qid]
        med = int(statistics.median(hits))
        swing = max(hits) - min(hits)
        req = per_case_req.get(qid, max(hits))
        stable = swing == 0
        if not stable:
            unstable.append(qid)
        total_hit_med += med
        print(f"{qid:>4} {med:>10} {req:>4} {swing:>10} {('OK' if stable else 'VAR'):>7}")

    total_req = overalls[0][1]
    print(f"\nMEDIAN overall: {total_hit_med}/{total_req} ({100 * total_hit_med / total_req:.0f}%)")
    print(f"per-run overall hit: {[h for h, _ in overalls]}")
    print(f"UNSTABLE cases (L3 variance — average/median handles these): {unstable or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
