#!/usr/bin/env python3
"""Dump parsed lookup_content structure for one object per domain."""
import json
import sqlite3

PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"

con = sqlite3.connect(f"file:{PACK}?mode=ro", uri=True)
cur = con.cursor()


def walk(obj, prefix="", out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk(v, f"{prefix}.{k}" if prefix else k, out)
    elif isinstance(obj, list):
        out.append((prefix + "[]", f"list[{len(obj)}]", repr(obj[:2])[:200]))
    else:
        out.append((prefix, type(obj).__name__, repr(obj)[:200]))
    return out


for pid in (
    "lookup:exact-lookup:company",
    "lookup:exact-lookup:patent",
    "lookup:exact-lookup:paper",
    "lookup:exact-lookup:professor",
):
    row = cur.execute(
        "SELECT document_json FROM lookup_document WHERE projection_id = ? LIMIT 1", (pid,)
    ).fetchone()
    doc = json.loads(row[0])
    lc = json.loads(doc["lookup_content"])
    print("=" * 78)
    print("PROJECTION", pid)
    print("lookup_content top keys:", sorted(lc.keys()))
    print("-" * 78)
    for path, typ, val in walk(lc):
        if path.startswith("field_lineage"):
            continue
        print(f"  {path} :: {typ} :: {val}")
    print()
con.close()
