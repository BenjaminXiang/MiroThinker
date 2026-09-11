#!/usr/bin/env python3
"""Inspect serving-pack projections and one sample document per projection."""
import json
import sqlite3

PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"

con = sqlite3.connect(f"file:{PACK}?mode=ro", uri=True)
cur = con.cursor()
cur.execute("SELECT projection_id, release_id FROM lookup_manifest")
for pid, rid in cur.fetchall():
    print("projection:", pid, "release:", rid)

cur.execute("SELECT COUNT(*) FROM lookup_document")
print("lookup_document total:", cur.fetchone()[0])

cur.execute("SELECT projection_id, COUNT(*) FROM lookup_document GROUP BY projection_id")
print("per-projection:", cur.fetchall())

for pid, in cur.execute("SELECT DISTINCT projection_id FROM lookup_document").fetchall():
    row = cur.execute(
        "SELECT document_json FROM lookup_document WHERE projection_id = ? LIMIT 1", (pid,)
    ).fetchone()
    doc = json.loads(row[0])
    print()
    print("=" * 72)
    print("PROJECTION", pid, "keys:", sorted(doc.keys()))
    print(json.dumps(doc, ensure_ascii=False, indent=1)[:2500])
con.close()
