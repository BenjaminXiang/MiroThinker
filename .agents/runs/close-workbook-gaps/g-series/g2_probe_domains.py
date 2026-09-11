#!/usr/bin/env python3
"""G2 probe 4: per-domain key frequency + one sample doc per domain (evidence trimmed)."""
import json
import sqlite3
import sys
from collections import Counter

DB = sys.argv[1] if len(sys.argv) > 1 else "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
cur = con.cursor()

TRIM = {"evidence", "field_lineage"}


def load(dj):
    d = json.loads(dj)
    lc = d.get("lookup_content")
    if isinstance(lc, str):
        lc = json.loads(lc)
    return d, lc


counts = {d: Counter() for d in ("company", "professor", "paper", "patent")}
samples = {}
for dom in ("professor", "paper", "patent"):
    row = cur.execute(
        "SELECT canonical_object_id, document_json FROM lookup_document "
        "WHERE json_extract(document_json,'$.domain')=? LIMIT 1",
        (dom,),
    ).fetchone()
    d, lc = load(row[1])
    samples[dom] = (row[0], lc)

for pid, dj in cur.execute("SELECT projection_id, document_json FROM lookup_document"):
    dom = pid.split(":")[-1]
    _, lc = load(dj)
    if isinstance(lc, dict):
        for k, v in lc.items():
            if v not in (None, [], {}, "", "Not supplied by the backfill source."):
                counts[dom][k] += 1

for dom in ("company", "professor", "paper", "patent"):
    print(f"== {dom} non-empty key counts ==")
    for k, n in counts[dom].most_common(60):
        print(f"  {k}: {n}")
    print()

for dom, (cid, lc) in samples.items():
    print(f"== {dom} sample ({cid}) ==")
    keep = {k: v for k, v in lc.items() if k not in TRIM}
    print(json.dumps(keep, ensure_ascii=False, indent=2)[:3500])
    print()

con.close()
