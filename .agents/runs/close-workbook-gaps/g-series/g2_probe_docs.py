#!/usr/bin/env python3
"""G2 probe 2: projection kinds, domain counts, one full company doc, Pudu hits."""
import json
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
cur = con.cursor()

print("== build_metadata ==")
for k, v in cur.execute("SELECT key, value FROM build_metadata"):
    print(f"  {k} = {str(v)[:200]}")

print()
print("== projection_id counts ==")
for pid, n in cur.execute(
    "SELECT projection_id, COUNT(*) FROM lookup_document GROUP BY 1 ORDER BY 2 DESC"
):
    print(f"  {pid}: {n}")

print()
print("== domain counts (json) ==")
for d, n in cur.execute(
    "SELECT json_extract(document_json,'$.domain'), COUNT(*) FROM lookup_document GROUP BY 1 ORDER BY 2 DESC"
):
    print(f"  {d}: {n}")

print()
print("== distinct canonical_object_id per domain ==")
for d, n in cur.execute(
    "SELECT json_extract(document_json,'$.domain'), COUNT(DISTINCT canonical_object_id) FROM lookup_document GROUP BY 1 ORDER BY 2 DESC"
):
    print(f"  {d}: {n}")

print()
print("== sample company doc (pretty) ==")
row = cur.execute(
    "SELECT canonical_object_id, document_json FROM lookup_document "
    "WHERE json_extract(document_json,'$.domain')='company' LIMIT 1"
).fetchone()
doc = json.loads(row[1])
print("canonical_object_id:", row[0])
print(json.dumps(doc, ensure_ascii=False, indent=2)[:6000])

print()
print("== Pudu hits (company, name field) ==")
q = (
    "SELECT canonical_object_id, projection_id, document_json FROM lookup_document "
    "WHERE json_extract(document_json,'$.domain')='company' AND document_json LIKE '%普渡%'"
)
for cid, pid, dj in cur.execute(q):
    d = json.loads(dj)
    lc = d.get("lookup_content")
    if isinstance(lc, str):
        lc = json.loads(lc)
    nm = None
    if isinstance(lc, dict):
        nm = lc.get("name") or lc.get("company_name") or lc.get("display_name")
    print(f"  cid={cid} pid={pid} name={nm!r}")

con.close()
