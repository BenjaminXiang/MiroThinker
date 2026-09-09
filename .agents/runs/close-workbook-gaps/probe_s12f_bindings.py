#!/usr/bin/env python3
"""B1 evidence probe: s12f serving-pack company→patent bindings (read-only).

Verifies, independent of the serving stack:
1. 优必选's canonical company id and aliases (planner binding inputs).
2. Patent lookup docs whose applicants[].canonical_company_id binds that id.
3. relationships.json: public_path_eligibility_results relationship-scoping,
   current_relationships coverage for the same company, and whether the bound
   patents are present in candidate_projection_result.public_domain_projections
   (the exact structure the ported G3-simple scan reads).

Usage: python3 probe_s12f_bindings.py
"""

import json
import sqlite3
from collections import Counter

PACK = "/var/tmp/mirothinker-canonical-v2-s12f/serving-pack"

con = sqlite3.connect(f"file://{PACK}/lookup.sqlite3?mode=ro", uri=True)
cur = con.cursor()

rows = cur.execute(
    "SELECT canonical_object_id, document_json FROM lookup_document "
    "WHERE json_extract(document_json,'$.domain')='company' "
    "AND document_json LIKE '%优必选%'"
).fetchall()
assert len(rows) == 1, rows
company_doc = json.loads(rows[0][1])
company = json.loads(company_doc["lookup_content"])
CID = company["canonical_identity_id"]
print("company:", CID, "| name:", company["name"], "| aliases:", company["aliases"])

rows = cur.execute(
    "SELECT canonical_object_id, document_json FROM lookup_document "
    "WHERE json_extract(document_json,'$.domain')='patent'"
).fetchall()
bound = []
for oid, dj in rows:
    inner = json.loads(json.loads(dj)["lookup_content"])
    if any(a.get("canonical_company_id") == CID for a in inner.get("applicants", [])):
        bound.append((inner.get("patent_number"), inner.get("canonical_identity_id"), inner.get("title")))
print("patent lookup docs:", len(rows), "| bound to", CID, ":", len(bound))
for num, pid, title in sorted(bound, key=lambda x: (x[0] or "")):
    print(f"  {num} | {pid} | {title}")

d = json.load(open(f"{PACK}/relationships.json"))
elig = d["public_path_eligibility_results"]
print(
    "path_eligibility_results:", len(elig),
    "| with relationship_decision_ids:", sum(1 for e in elig if e.get("relationship_decision_ids")),
)
pub = d["candidate_projection_result"]["public_domain_projections"]
print("public_domain_projections:", len(pub), Counter(p.get("entity_type") for p in pub))
bound_in_pub = [
    p for p in pub
    if p.get("entity_type") == "patent"
    and any(a.get("canonical_company_id") == CID for a in p.get("applicants", []))
]
print("patents bound to", CID, "in public_domain_projections:", len(bound_in_pub))
cur_rels = d["relationship_projection_result"]["current_relationships"]
pa = [c for c in cur_rels if c.get("relationship_type_id") == "patent_has_applicant"]
print(
    "current_relationships:", len(cur_rels),
    "| patent_has_applicant:", len(pa),
    "| mentioning", CID, ":", sum(1 for c in cur_rels if CID in json.dumps(c)),
)
