#!/usr/bin/env python3
"""G2 probe: dump schema + row counts + one sample row per table (read-only)."""
import json
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"

con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
cur = con.cursor()

print("== tables ==")
for (name, sql) in cur.execute(
    "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
):
    print("--", name)
    print(sql)
    try:
        n = cur.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print("   rows:", n)
    except Exception as e:  # noqa: BLE001
        print("   count failed:", e)

print()
print("== columns of lookup_document ==")
for row in cur.execute("PRAGMA table_info(lookup_document)"):
    print(row)

print()
print("== sample row keys ==")
row = cur.execute(
    "SELECT * FROM lookup_document LIMIT 1"
).fetchone()
cols = [d[0] for d in cur.description]
for c, v in zip(cols, row):
    s = str(v)
    print(f"  {c}: {s[:300]!r}")

con.close()
