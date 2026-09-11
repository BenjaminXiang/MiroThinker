#!/usr/bin/env python3
"""G2 probe: paper title-normalization duplicate pairs — DOI/venue/year detail."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g2_lib as L  # noqa: E402

docs = [r for r in L.load_lookup(L.RUN14_DB) if r["domain"] == "paper"]
groups = {}
for r in docs:
    k = L.paper_title_key(r["content"].get("title"))
    if k:
        groups.setdefault(k, []).append(r)

for k, members in sorted(groups.items()):
    if len(members) < 2:
        continue
    print(f"== {k[:70]} ({len(members)}) ==")
    for m in members:
        c = m["content"]
        print(
            f"  {m['cid']} | title={c.get('title')!r}\n"
            f"      doi={c.get('doi')!r} venue={c.get('venue')!r} year={c.get('year')!r} "
            f"family={L.assertion_family(c)}"
        )
