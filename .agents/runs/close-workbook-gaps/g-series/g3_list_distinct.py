#!/usr/bin/env python3
"""List distinct matched category queries with occurrence counts."""
import json
import sys
from collections import Counter

SRC = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series/g3-category-queries.json"

with open(SRC, encoding="utf-8") as fh:
    data = json.load(fh)

rows = data["rows"]
c = Counter(r["query"] for r in rows)
print(f"category_turns={len(rows)} distinct={len(c)}")
print()
for q, n in c.most_common():
    print(f"{n:5d}  {q}")
