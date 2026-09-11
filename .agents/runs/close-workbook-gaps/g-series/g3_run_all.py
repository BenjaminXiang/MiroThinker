#!/usr/bin/env python3
"""G3 reproducibility runner: regenerate every artifact in order.

    cd /home/longxiang/MiroThinker
    python3 .agents/runs/close-workbook-gaps/g-series/g3_run_all.py

Reads (read-only):
    /var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3
    /var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3
Writes (all inside this directory):
    g3-category-queries.json, g3-terms.json, g3-taxonomy-ranking.json,
    g3-scan-terms.json, g3-anchoring.json, g3-vocabulary.json
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    ("classify access-log turns", "g3_classify_queries.py"),
    ("extract category terms", "g3_terms.py"),
    ("rank pack taxonomy", "g3_taxonomy_ranking.py"),
    ("build scan term list", "g3_build_scan_terms.py"),
    ("anchor scan (read-only)", "g3_anchor_scan.py", f"{BASE}/g3-scan-terms.json"),
    ("finalize vocabulary", "g3_finalize.py"),
    ("render appendix tables", "g3_tables.py"),
]


def main():
    for step in STEPS:
        name, script, *extra = step
        print(f"\n===== {name}: {script} =====", flush=True)
        rc = subprocess.call([sys.executable, os.path.join(BASE, script)] + extra)
        if rc != 0:
            print(f"FAILED ({rc}): {script}")
            return rc
    print("\nall G3 artifacts regenerated")


if __name__ == "__main__":
    raise SystemExit(main())
