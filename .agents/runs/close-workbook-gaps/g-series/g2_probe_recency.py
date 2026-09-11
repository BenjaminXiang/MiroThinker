#!/usr/bin/env python3
"""G2 probe: recency + quality_status per provenance family (company domain)."""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g2_lib as L  # noqa: E402

docs = [r for r in L.load_lookup(L.RUN14_DB) if r["domain"] == "company"]
by_fam = defaultdict(list)
qual = defaultdict(Counter)
for r in docs:
    fam = L.assertion_family(r["content"])
    fam = "COMP-legacy" if fam.startswith("COMP-") else fam
    ts = str(r["content"].get("last_updated") or "")
    if ts:
        by_fam[fam].append(ts)
    qual[fam][str(r["content"].get("quality_status"))] += 1

for fam in sorted(by_fam):
    ts = sorted(by_fam[fam])
    print(f"{fam:18s} n={len(ts):5d} min={ts[0]} median={ts[len(ts)//2]} max={ts[-1]}")
    print(f"   quality_status: {dict(qual[fam].most_common())}")
    days = Counter(t[:10] for t in ts)
    top = ", ".join(f"{d}:{n}" for d, n in days.most_common(5))
    print(f"   dates: {top}")
