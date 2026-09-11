#!/usr/bin/env python3
"""Survey company taxonomy vocabulary + field fill rates in run14 pack (read-only).

Writes: g3-field-survey.json
"""
import json
import sqlite3
import time
from collections import Counter

PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
OUT = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series/g3-field-survey.json"


def load_domain(con, projection_id):
    cur = con.cursor()
    cur.execute(
        "SELECT canonical_object_id, json_extract(document_json, '$.lookup_content')"
        " FROM lookup_document WHERE projection_id = ?",
        (projection_id,),
    )
    for cid, lc in cur:
        yield cid, json.loads(lc)


def main():
    t0 = time.time()
    con = sqlite3.connect(f"file:{PACK}?mode=ro", uri=True)

    company_n = 0
    ind = Counter()
    ind_tags = Counter()
    tech_tags = Counter()
    fill = Counter()
    tag_len = Counter()

    for cid, lc in load_domain(con, "lookup:exact-lookup:company"):
        company_n += 1
        industry = lc.get("industry") or {}
        if industry.get("name"):
            ind[industry["name"]] += 1
            fill["industry.name"] += 1
        for t in lc.get("industry_tags") or []:
            if t.get("name"):
                ind_tags[t["name"]] += 1
        for t in lc.get("tech_tags") or []:
            if t.get("name"):
                tech_tags[t["name"]] += 1
        for f in (
            "industry_tags",
            "tech_tags",
            "product_description",
            "profile_summary",
            "technology_route_summary",
            "business_scenarios",
            "capabilities",
        ):
            v = lc.get(f)
            if v:
                fill[f] += 1
        fill["_total"] += 1
        nt = len(lc.get("industry_tags") or []) + len(lc.get("tech_tags") or [])
        tag_len[min(nt, 5)] += 1

    # other domains
    other_fill = {}
    for pid, fields in (
        (
            "lookup:exact-lookup:patent",
            ["title", "abstract", "summary_text", "technical_summaries", "ipc_codes", "technology_effect"],
        ),
        (
            "lookup:exact-lookup:paper",
            ["title", "title_zh", "abstract", "summary_text", "summary_zh", "keywords", "fields_of_study", "tldr"],
        ),
        (
            "lookup:exact-lookup:professor",
            ["canonical_name_zh", "research_directions", "profile_summary", "paper_summary", "patent_summary", "department", "institution"],
        ),
    ):
        c = Counter()
        n = 0
        for cid, lc in load_domain(con, pid):
            n += 1
            for f in fields:
                if lc.get(f):
                    c[f] += 1
        c["_total"] = n
        other_fill[pid] = dict(c)

    payload = {
        "pack": PACK,
        "generated_from": "run14 lookup.sqlite3 (read-only)",
        "company_total": company_n,
        "company_fill": dict(fill),
        "company_industry_top": ind.most_common(60),
        "company_industry_tag_top": ind_tags.most_common(80),
        "company_tech_tag_top": tech_tags.most_common(80),
        "company_industry_distinct": len(ind),
        "company_industry_tag_distinct": len(ind_tags),
        "company_tech_tag_distinct": len(tech_tags),
        "company_tag_count_hist": dict(tag_len),
        "other_domain_fill": other_fill,
        "elapsed_s": round(time.time() - t0, 1),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print("company_total:", company_n, "elapsed", payload["elapsed_s"])
    print()
    print("company_fill:", json.dumps(dict(fill), ensure_ascii=False))
    print()
    print("industry.name distinct:", len(ind), "top:", ind.most_common(20))
    print()
    print("industry_tags distinct:", len(ind_tags), "top:", ind_tags.most_common(30))
    print()
    print("tech_tags distinct:", len(tech_tags), "top:", tech_tags.most_common(30))
    print()
    print("tag count hist:", dict(sorted(tag_len.items())))
    print()
    for k, v in other_fill.items():
        print(k, json.dumps(v, ensure_ascii=False))
    con.close()


if __name__ == "__main__":
    main()
