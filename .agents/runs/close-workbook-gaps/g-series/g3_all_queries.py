#!/usr/bin/env python3
"""Dump every distinct query in the access log with turn counts (context for corpus sizing)."""
import sqlite3
from collections import Counter

ACCESS = "/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3"

con = sqlite3.connect(f"file:{ACCESS}?mode=ro", uri=True)
cur = con.cursor()
cur.execute("SELECT query FROM turns")
c = Counter((q or "").strip() for q, in cur.fetchall())
con.close()
print(f"turns={sum(c.values())} distinct={len(c)}")
print()
for q, n in c.most_common():
    print(f"{n:4d}  {q}")
