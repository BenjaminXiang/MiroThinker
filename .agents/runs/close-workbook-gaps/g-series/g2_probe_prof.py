#!/usr/bin/env python3
"""G2 probe: professor same-name clusters with institution detail (run14)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g2_lib as L  # noqa: E402

docs = [r for r in L.load_lookup(L.RUN14_DB) if r["domain"] == "professor"]
groups = {}
for r in docs:
    k = L.professor_name_key(
        r["content"].get("canonical_name_zh") or r["content"].get("name")
    )
    groups.setdefault(k, []).append(r)

for k, members in sorted(groups.items()):
    if len(members) < 2:
        continue
    print(f"== {k} ({len(members)} docs) ==")
    for m in members:
        c = m["content"]
        print(
            f"  {m['cid']} | institution={c.get('institution')!r} "
            f"| dept={L.name_of(c.get('department'))!r} | title={c.get('title')!r} "
            f"| email={str(c.get('email'))[:40]!r} | homepage={str(c.get('homepage'))[:60]!r} "
            f"| family={L.assertion_family(c)}"
        )
