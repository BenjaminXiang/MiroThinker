#!/usr/bin/env python3
"""G3 step 3: term -> field anchoring scan against the run14 serving pack.

Read-only over /var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3.

Input : term list (JSON) -- either g3-terms.json (raw candidates) or a {"terms":[...]}
Output: g3-anchoring.json

What is measured, per term T and per field group F:
  hits[F] = number of documents whose field-group F text contains T as a
            substring. All list-typed fields (industry_tags, tech_tags, ipc_codes,
            keywords, research_directions, ...) are joined with "\n" first.
            Placeholder values ("未找到", "Not supplied by ...") are treated as
            empty so the derived summary fields cannot fake coverage.

Field groups are split into two classes:
  structured : curated/normalized fields the serving layer can filter on
               (company industry / industry_tags / tech_tags, patent ipc_codes +
               patent_type, paper keywords + fields_of_study, professor
               research_directions)
  text       : free text (product_description, profile_summary, abstract,
               summary_text, title, entity name, ...)

Derived per term:
  anchored_docs        docs hit in >= 1 structured group
  text_only_docs       docs hit only in text groups
  structured_coverage  anchored_docs / (anchored_docs + text_only_docs)

Also builds the taxonomy lexicon L from the pack itself:
  L = {industry.name} u {industry_tags[].name} u {strip_business_suffix(tech_tags[].name)}
and reports, per term, membership + whether it appears inside any taxonomy value.
"""
import json
import re
import sqlite3
import sys
import time

PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
BASE = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series"
OUT = f"{BASE}/g3-anchoring.json"

PLACEHOLDERS = {
    "",
    "-",
    "未找到",
    "无",
    "无明确描述",
    "暂无",
    "None",
    "null",
}
PLACEHOLDER_PREFIXES = ("Not supplied", "No dedicated summary", "no dedicated summary", "未提供", "暂无")

COMPANY_FIELDS = {
    "industry": ("structured", lambda c: (c.get("industry") or {}).get("name") or ""),
    "industry_tags": ("structured", lambda c: "\n".join(t.get("name", "") for t in c.get("industry_tags") or [])),
    "tech_tags": ("structured", lambda c: "\n".join(t.get("name", "") for t in c.get("tech_tags") or [])),
    "product_description": ("text", lambda c: c.get("product_description") or ""),
    "profile_summary": ("text", lambda c: c.get("profile_summary") or ""),
    "technology_route_summary": ("text", lambda c: c.get("technology_route_summary") or ""),
    "name": ("text", lambda c: "\n".join(
        [c.get("name") or "", c.get("normalized_name") or ""]
        + [a if isinstance(a, str) else (a or {}).get("name", "") for a in c.get("aliases") or []]
    )),
}
PATENT_FIELDS = {
    "ipc_codes": ("structured", lambda p: "\n".join(str(x) for x in p.get("ipc_codes") or [])),
    "patent_type": ("structured", lambda p: p.get("patent_type") or ""),
    "title": ("text", lambda p: "\n".join([p.get("title") or "", p.get("title_en") or ""])),
    "abstract": ("text", lambda p: p.get("abstract") or ""),
    "summary_text": ("text", lambda p: p.get("summary_text") or ""),
    "technology_effect": ("text", lambda p: p.get("technology_effect") or ""),
}
PAPER_FIELDS = {
    "keywords": ("structured", lambda p: "\n".join(str(x) for x in (p.get("keywords") or []) + (p.get("fields_of_study") or []))),
    "title": ("text", lambda p: "\n".join([p.get("title") or "", p.get("title_zh") or ""])),
    "abstract": ("text", lambda p: p.get("abstract") or ""),
    "summary_text": ("text", lambda p: "\n".join(
        [p.get("summary_text") or "", p.get("summary_zh") or "", p.get("tldr") or ""]
    )),
}
PROFESSOR_FIELDS = {
    "research_directions": ("structured", lambda p: "\n".join(str(x) for x in p.get("research_directions") or [])),
    "profile_summary": ("text", lambda p: p.get("profile_summary") or ""),
    "paper_patent_summary": ("text", lambda p: "\n".join([p.get("paper_summary") or "", p.get("patent_summary") or ""])),
    "affiliation": ("text", lambda p: "\n".join([
        (p.get("department") or {}).get("name") if isinstance(p.get("department"), dict) else (p.get("department") or ""),
        p.get("institution") or "",
    ]).replace("None", "")),
    "name": ("text", lambda p: "\n".join([p.get("name") or "", p.get("canonical_name_zh") or ""])),
}

DOMAINS = [
    ("lookup:exact-lookup:company", "company", COMPANY_FIELDS),
    ("lookup:exact-lookup:patent", "patent", PATENT_FIELDS),
    ("lookup:exact-lookup:paper", "paper", PAPER_FIELDS),
    ("lookup:exact-lookup:professor", "professor", PROFESSOR_FIELDS),
]

BIZ_SUFFIX = re.compile(
    r"(研发商|产销商|供应商|生产商|服务商|代理商|分销商|集成商|销售商|提供商|制造商|运营商|"
    r"经销商|开发商|方案商|厂商|研究院|平台)$"
)


def clean(v):
    if not isinstance(v, str):
        return ""
    s = v.strip()
    if s in PLACEHOLDERS or s.startswith(PLACEHOLDER_PREFIXES):
        return ""
    return s


def load_terms(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "terms" in data:
        return list(dict.fromkeys(
            t["term"] if isinstance(t, dict) else t for t in data["terms"]
        ))
    cands = data.get("candidates") or []
    return list(dict.fromkeys(c["term"] if isinstance(c, dict) else c for c in cands))


def main():
    term_file = sys.argv[1] if len(sys.argv) > 1 else f"{BASE}/g3-scan-terms.json"
    out_file = sys.argv[2] if len(sys.argv) > 2 else OUT
    terms = load_terms(term_file)
    t0 = time.time()

    con = sqlite3.connect(f"file:{PACK}?mode=ro", uri=True)
    cur = con.cursor()

    stats = {
        "pack": PACK,
        "term_source": term_file,
        "term_count": len(terms),
        "domains": {},
        "terms": {},
        "lexicon": {},
        "taxonomy_value_count": 0,
    }
    hits = {t: {} for t in terms}
    examples = {t: {} for t in terms}
    # doc-level classes: a doc is "anchored" when the term hits >=1 structured
    # field, "text_only" when it only hits free-text fields, "both" when both.
    classes = {t: {"anchored": 0, "text_only": 0, "both": 0} for t in terms}
    classes_company = {t: {"anchored": 0, "text_only": 0, "both": 0} for t in terms}
    lexicon = set()
    taxonomy_values = []

    def note_example(t, key, name, cid):
        bucket = examples[t].setdefault(key, [])
        if len(bucket) < 6 and name:
            bucket.append({"canonical_object_id": cid, "name": name[:80]})

    for projection_id, domain, fields in DOMAINS:
        cur.execute(
            "SELECT canonical_object_id, json_extract(document_json, '$.lookup_content')"
            " FROM lookup_document WHERE projection_id = ?",
            (projection_id,),
        )
        n = 0
        field_fill = {f: 0 for f in fields}
        for cid, lc in cur:
            doc = json.loads(lc)
            n += 1
            texts = {}
            for f, (cls, getter) in fields.items():
                try:
                    texts[f] = clean(getter(doc))
                except Exception:  # noqa: BLE001
                    texts[f] = ""
                if texts[f]:
                    field_fill[f] += 1
            if domain == "company":
                for t in texts["industry"].split("\n"):
                    if t:
                        lexicon.add(t)
                        taxonomy_values.append(t)
                for t in texts["industry_tags"].split("\n"):
                    if t:
                        lexicon.add(t)
                        taxonomy_values.append(t)
                for t in texts["tech_tags"].split("\n"):
                    if t:
                        taxonomy_values.append(t)
                        lexicon.add(BIZ_SUFFIX.sub("", t).strip())
            disp = texts.get("name") or texts.get("title") or ""
            for term in terms:
                s_hit = t_hit = False
                for f, (cls, _) in fields.items():
                    if texts[f] and term in texts[f]:
                        key = f"{domain}.{f}"
                        hits[term][key] = hits[term].get(key, 0) + 1
                        note_example(term, key, disp, cid)
                        if cls == "structured":
                            s_hit = True
                        else:
                            t_hit = True
                if s_hit or t_hit:
                    bucket = classes[term]
                    if s_hit and t_hit:
                        bucket["both"] += 1
                    elif s_hit:
                        bucket["anchored"] += 1
                    else:
                        bucket["text_only"] += 1
                    if s_hit:
                        note_example(term, "structured_docs", disp, cid)
                    elif t_hit:
                        note_example(term, "text_only_docs", disp, cid)
                    if domain == "company":
                        cb = classes_company[term]
                        if s_hit and t_hit:
                            cb["both"] += 1
                        elif s_hit:
                            cb["anchored"] += 1
                        else:
                            cb["text_only"] += 1
        stats["domains"][domain] = {"docs": n, "field_fill": field_fill}

    con.close()

    lexicon.discard("")
    stats["lexicon"] = {
        "size": len(lexicon),
        "values": sorted(lexicon),
        "taxonomy_value_count": len(taxonomy_values),
    }
    stats["taxonomy_value_count"] = len(taxonomy_values)

    tax_values = sorted(set(taxonomy_values))
    tax_blob = "\n".join(tax_values)

    for term in terms:
        h = hits[term]
        per_domain = {}
        for projection_id, domain, fields in DOMAINS:
            per_domain[domain] = {
                "hits": {f: h.get(f"{domain}.{f}", 0) for f in fields},
                "classes": {f: fields[f][0] for f in fields},
                "docs": stats["domains"][domain]["docs"],
            }
        stats["terms"][term] = {
            "hits": h,
            "per_domain": per_domain,
            "in_lexicon": term in lexicon,
            "in_taxonomy_value": any(term in v for v in tax_values),
            "taxonomy_tail_matches": [v for v in tax_values if v.endswith(term)][:6],
            "taxonomy_head_matches": [v for v in tax_values if v.startswith(term)][:6],
            "doc_classes": classes[term],
            "company_doc_classes": classes_company[term],
            "examples": examples[term],
        }

    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=1)

    print(f"terms={len(terms)} lexicon={len(lexicon)} elapsed={round(time.time()-t0,1)}s")
    for d, v in stats["domains"].items():
        print(f"  {d}: docs={v['docs']} fill={v['field_fill']}")
    print()
    head = f"{'term':16s}{'lex':>4s}{'tax':>4s} | {'company ind/itags/tech':>23s} | {'prod_desc':>9s} | {'profile_s':>9s} | {'name':>6s} | {'pat t/a/s':>13s} | {'pap t/a/s':>13s} | {'prof rd/sum':>11s}"
    print(head)
    for t in terms:
        h = hits[t]
        print(
            f"{t:16s}{str(stats['terms'][t]['in_lexicon'])[0]:>4s}{str(stats['terms'][t]['in_taxonomy_value'])[0]:>4s} | "
            f"{h.get('company.industry',0):7d}/{h.get('company.industry_tags',0):7d}/{h.get('company.tech_tags',0):6d} | "
            f"{h.get('company.product_description',0):9d} | {h.get('company.profile_summary',0):9d} | "
            f"{h.get('company.name',0):6d} | "
            f"{h.get('patent.title',0):4d}/{h.get('patent.abstract',0):4d}/{h.get('patent.summary_text',0):4d} | "
            f"{h.get('paper.title',0):4d}/{h.get('paper.abstract',0):4d}/{h.get('paper.summary_text',0):4d} | "
            f"{h.get('professor.research_directions',0):5d}/{h.get('professor.profile_summary',0):5d}"
        )


if __name__ == "__main__":
    main()
