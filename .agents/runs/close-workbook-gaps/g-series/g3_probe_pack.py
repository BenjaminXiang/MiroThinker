#!/usr/bin/env python3
"""Probe serving-pack lookup schema (read-only)."""
import sqlite3

PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"

con = sqlite3.connect(f"file:{PACK}?mode=ro", uri=True)
cur = con.cursor()
cur.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")
rows = cur.fetchall()
for t, n, sql in rows:
    print(f"##### {t}: {n}")
    print(sql)
    print()
con.close()
