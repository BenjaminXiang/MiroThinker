#!/usr/bin/env python3
"""Show full field content for named companies in run14 pack (read-only)."""
import json
import sqlite3
import sys

PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
NAMES = sys.argv[1:] or ["优必选", "普渡", "星桥", "岚湾"]

con = sqlite3.connect(f"file:{PACK}?mode=ro", uri=True)
cur = con.cursor()
for name in NAMES:
    cur.execute(
        "SELECT canonical_object_id, json_extract(document_json, '$.lookup_content')"
        " FROM lookup_document WHERE projection_id='lookup:exact-lookup:company'"
        " AND json_extract(document_json, '$.lookup_content') LIKE ? LIMIT 1",
        (f"%{name}%",),
    )
    row = cur.fetchone()
    if not row:
        print("NO MATCH", name)
        continue
    lc = json.loads(row[1])
    print("=" * 78)
    print(f"[{name}] cid={row[0]} name={lc.get('name')} quality={lc.get('quality_status')}")
    for f in (
        "industry",
        "industry_tags",
        "tech_tags",
        "product_description",
        "profile_summary",
        "technology_route_summary",
        "products",
        "business_scenarios",
        "capabilities",
    ):
        v = lc.get(f)
        s = json.dumps(v, ensure_ascii=False)
        print(f"  {f} = {s[:400]}")
    print()
con.close()
