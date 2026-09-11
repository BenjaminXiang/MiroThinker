#!/usr/bin/env python3
"""G2 probe 3: full lookup_content for Pudu docs; key frequency across company domain."""
import json
import sqlite3
import sys
from collections import Counter

DB = sys.argv[1] if len(sys.argv) > 1 else "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
cur = con.cursor()


def load(dj):
    d = json.loads(dj)
    lc = d.get("lookup_content")
    if isinstance(lc, str):
        lc = json.loads(lc)
    return d, lc


if len(sys.argv) > 2 and sys.argv[2] == "pudu":
    q = (
        "SELECT canonical_object_id, document_json FROM lookup_document "
        "WHERE json_extract(document_json,'$.domain')='company' AND document_json LIKE '%普渡%'"
    )
    for cid, dj in cur.execute(q):
        d, lc = load(dj)
        nm = lc.get("name", "")
        if "普渡" not in str(nm):
            continue
        keep = {
            k: v
            for k, v in lc.items()
            if k
            not in {
                "field_lineage",
                "content_sha256",
                "catalog_content_sha256",
                "identity_decision_id",
                "inclusion_decision_id",
                "release_id",
                "canonical_identity_id",
            }
        }
        print("=" * 100)
        print("cid:", cid)
        print(json.dumps(keep, ensure_ascii=False, indent=2))
    sys.exit(0)

print("== key frequency across ALL domains (top 60) ==")
c = Counter()
for pid, dj in cur.execute("SELECT projection_id, document_json FROM lookup_document"):
    _, lc = load(dj)
    if isinstance(lc, dict):
        for k in lc:
            c[(pid.split(":")[-1], k)] += 1
for (dom, k), n in sorted(c.items()):
    print(f"  {dom:10s} {k}: {n}")

con.close()
