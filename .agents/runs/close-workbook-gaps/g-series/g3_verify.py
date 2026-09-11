#!/usr/bin/env python3
"""G3 independent verification: re-derive the report's headline numbers from the
raw sources and assert the JSON artifacts agree.

    cd /home/longxiang/MiroThinker
    python3 .agents/runs/close-workbook-gaps/g-series/g3_verify.py

Every check re-reads the access log / serving pack directly (read-only) instead
of trusting g3-vocabulary.json. Exit code 0 = all checks pass.
"""
import json
import re
import sqlite3
import sys

BASE = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series"
ACCESS = "/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3"
PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"

FAMILIES = re.compile(
    r"有哪些|哪几家|哪几家公司|哪家|哪些公司|哪些企业|有什么公司|有什么企业|"
    r"推荐|值得关注|值得投|知名|头部|龙头|代表(企业|公司|性)|标杆|"
    r"供应商|厂商|制造商|生产商|服务商|代理商|分销商|集成商|厂家|供应链|"
    r"做[^？。，,]{0,10}的(公司|企业|厂)|从事[^？。，,]{0,10}的(公司|企业)|生产[^？。，,]{0,8}的|"
    r"还有哪些|都有哪些|列举|清单一?下|盘点|梳理"
)

RESULTS = []


def check(name, got, want, note=""):
    ok = got == want
    RESULTS.append((ok, name, got, want, note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got={got} want={want} {note}")
    return ok


def load(name):
    with open(f"{BASE}/{name}", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    # ---------- access log -------------------------------------------------
    con = sqlite3.connect(f"file:{ACCESS}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM turns")
    turns = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT query) FROM turns")
    distinct_q = cur.fetchone()[0]
    cur.execute("SELECT query FROM turns")
    rows = [(q or "").strip() for q, in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM sessions")
    sessions = cur.fetchone()[0]
    con.close()

    cat_turns = sum(1 for q in rows if FAMILIES.search(q))
    cat_具身智能 = sum(1 for q in rows if FAMILIES.search(q) and "具身智能" in q)

    check("access log turns", turns, 914)
    check("access log distinct queries", distinct_q, 76)
    check("access log sessions", sessions, 560)
    check("classified category turns (~353 in task brief)", cat_turns, 361)
    check("category turns containing 具身智能", cat_具身智能, 134)

    # ---------- serving pack ----------------------------------------------
    con = sqlite3.connect(f"file:{PACK}?mode=ro", uri=True)
    cur = con.cursor()
    docs = {}
    for pid, dom in (
        ("lookup:exact-lookup:company", "company"),
        ("lookup:exact-lookup:patent", "patent"),
        ("lookup:exact-lookup:paper", "paper"),
        ("lookup:exact-lookup:professor", "professor"),
    ):
        cur.execute("SELECT COUNT(*) FROM lookup_document WHERE projection_id = ?", (pid,))
        docs[dom] = cur.fetchone()[0]
    check("pack company docs", docs["company"], 7089)
    check("pack patent docs", docs["patent"], 11504)
    check("pack paper docs", docs["paper"], 24520)
    check("pack professor docs", docs["professor"], 3958)

    # independent per-field substring counts for a few decisive terms
    def count_company(pred_field, needle):
        cur.execute(
            "SELECT json_extract(document_json, '$.lookup_content')"
            " FROM lookup_document WHERE projection_id = 'lookup:exact-lookup:company'"
        )
        n = 0
        for (lc,) in cur:
            doc = json.loads(lc)
            if needle in (pred_field(doc) or ""):
                n += 1
        return n

    ind = lambda d: (d.get("industry") or {}).get("name") or ""
    ttags = lambda d: "\n".join(t.get("name", "") for t in d.get("tech_tags") or [])
    itags = lambda d: "\n".join(t.get("name", "") for t in d.get("industry_tags") or [])
    summ = lambda d: d.get("profile_summary") or ""
    prod = lambda d: d.get("product_description") or ""

    check("company.industry contains 人工智能", count_company(ind, "人工智能"), 1297)
    check("company.industry_tags contains 人工智能", count_company(itags, "人工智能"), 851)
    check("company.tech_tags contains 机器人", count_company(ttags, "机器人"), 414)
    check("company.tech_tags contains 具身智能", count_company(ttags, "具身智能"), 11)
    check("company.tech_tags contains 酒店送餐机器人", count_company(ttags, "酒店送餐机器人"), 0)
    check("company.profile_summary contains 酒店送餐机器人", count_company(summ, "酒店送餐机器人"), 0)
    check("company.product_description contains 具身智能", count_company(prod, "具身智能"), 23)
    cur.execute(
        "SELECT COUNT(DISTINCT json_extract(json_extract(document_json,"
        " '$.lookup_content'), '$.industry.name'))"
        " FROM lookup_document WHERE projection_id = 'lookup:exact-lookup:company'"
    )
    print(f"[info] distinct industry labels (raw, incl. null): {cur.fetchone()[0]}")
    con.close()

    # ---------- artifacts vs raw ------------------------------------------
    vocab = load("g3-vocabulary.json")
    terms = load("g3-terms.json")
    anchor = load("g3-anchoring.json")

    check("artifact: classified turns", vocab["scope"]["classified_turns"], cat_turns)
    check("artifact: kept category turns", vocab["scope"]["kept_turns"], 190)
    check("artifact: corpus vocabulary size", len(vocab["corpus_vocabulary"]), 9)
    top30 = vocab["corpus_vocabulary"] + [
        r for r in vocab["extension_vocabulary"] if r["lens"] == "pack_taxonomy"
    ][:21]
    check("report top-30 size (9 corpus + 21 extension)", len(top30), 30)

    by_term = {t["term"]: t for t in terms["terms"]}
    check("artifact: 具身智能 cat_turns", by_term["具身智能"]["cat_turns"], cat_具身智能)
    check("artifact: 机器人 tech_tags hits",
          anchor["terms"]["机器人"]["hits"].get("company.tech_tags"), 414)
    check("artifact: 具身智能 tech_tags hits",
          anchor["terms"]["具身智能"]["hits"].get("company.tech_tags"), 11)
    check("artifact: 酒店送餐机器人 total_hit_docs",
          sum(anchor["terms"]["酒店送餐机器人"]["doc_classes"].values()), 0)

    # tier invariant: N means zero hits everywhere
    bad_n = [r["term"] for r in vocab["vocabulary"] if r["tier"] == "N" and r["total_hit_docs"] != 0]
    check("tier N implies zero document hits", bad_n, [])
    bad_s = [r["term"] for r in vocab["vocabulary"]
             if r["tier"] == "S" and r["company_structured_coverage"] < 0.20]
    check("tier S implies >=20% structured coverage", bad_s, [])

    # no corpus term may be missing from the top-30
    missing = [r["term"] for r in vocab["corpus_vocabulary"] if r["term"] not in [x["term"] for x in top30]]
    check("all corpus terms present in top 30", missing, [])

    failed = [r for r in RESULTS if not r[0]]
    print()
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED:", [r[1] for r in failed])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
