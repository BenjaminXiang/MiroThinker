#!/usr/bin/env python3
"""G1 sample probe: inspect suspicious field value distributions (read-only)."""
import json
import sqlite3
from collections import Counter

DB = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
cur = con.cursor()

rows = cur.execute(
    "SELECT document_json FROM lookup_document "
    "WHERE projection_id = 'lookup:exact-lookup:professor'"
).fetchall()

en = Counter()
emails = []
titles = Counter()
dept_ph = 0
for (dj,) in rows:
    doc = json.loads(dj)
    c = doc.get("lookup_content")
    if isinstance(c, str):
        c = json.loads(c)
    if c.get("canonical_name_en"):
        en[c["canonical_name_en"]] += 1
    if c.get("email"):
        emails.append(c["email"])
    if c.get("title"):
        titles[c["title"]] += 1
    if isinstance(c.get("department"), dict) and c["department"].get("name") == "Not supplied by the historical source.":
        dept_ph += 1

print("== professor.canonical_name_en top values ==")
for v, n in en.most_common(15):
    print(f"  {n:4d}  {v!r}")
print(f"  distinct={len(en)}")

print()
print("== professor.email: concat/dirty samples ==")
import re as _re

PH = "Not supplied by the historical source."
phone_prefix = [
    e for e in emails if e != PH and _re.match(r"^0\d{6,}", e.split("@")[0])
]
cjk = [e for e in emails if e != PH and _re.search(r"[\u4e00-\u9fff]", e)]
other_weird = [
    e
    for e in emails
    if e != PH and (" " in e or e.count("@") != 1 or "." not in e.split("@")[-1])
]
print(
    f"  total={len(emails)}, placeholder={sum(1 for e in emails if e == PH)}, "
    f"phone-prefixed={len(phone_prefix)}, cjk={len(cjk)}, other-weird={len(other_weird)}"
)
for e in (phone_prefix + cjk + other_weird)[:10]:
    print(f"  {e!r}")

print()
print("== professor.title top values ==")
for v, n in titles.most_common(15):
    print(f"  {n:4d}  {v!r}")

print()
print(f"== professor.department placeholder count = {dept_ph}")
con.close()
