#!/usr/bin/env python3
"""G3 step 5: rank the serving pack's own category vocabulary (read-only).

Output: g3-taxonomy-ranking.json

The pack's company taxonomy is the only curated category vocabulary in the
system:
  industry.name / industry_tags[].name  -> 41 broad industry labels
  tech_tags[].name                      -> ~4.9k company category phrases, mostly
                                           "<category phrase><business suffix>"
                                           (研发商/产销商/供应商/...)

Three rankings are produced, all deterministic:
  1. industry_labels        : the 41 curated labels with company counts
  2. category_phrases       : distinct stripped tech_tag phrases with company counts
  3. tail_terms             : every 2..6 char *tail* of a stripped phrase
                              ("工业机器人" -> 机器人, 业机器人, ...), summed over
                              companies that own at least one such phrase. This is
                              the pack's own answer to "what are the category
                              words" -- a category word is what many phrases end
                              with. GENERIC = rank by reach; a term reachable as a
                              phrase tail is a real category head noun.
"""
import json
import re
import sqlite3
from collections import Counter

PACK = "/var/tmp/mirothinker-data-v2/serving-pack-run14/lookup.sqlite3"
OUT = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series/g3-taxonomy-ranking.json"

BIZ_SUFFIX = re.compile(
    r"(研发商|产销商|供应商|生产商|服务商|代理商|分销商|集成商|销售商|提供商|制造商|运营商|"
    r"经销商|开发商|方案商|厂商|研究院|平台)$"
)
GENERIC = {
    "产品", "企业", "公司", "系统", "设备", "服务", "技术", "方案", "解决方案", "平台",
    "研发", "生产", "制造", "解决方案提供商", "整体解决方案", "供应商", "研发商", "厂商",
    "系列", "工程", "项目", "中心", "基地", "应用", "领域", "行业", "市场", "品牌",
    "专业", "综合", "智能", "数字", "信息", "数据", "网络", "软件", "硬件", "材料",
    "器件", "部件", "组件", "配件", "工具", "装备", "仪器", "仪表", "装置", "设施",
}


def main():
    con = sqlite3.connect(f"file:{PACK}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute(
        "SELECT json_extract(document_json, '$.lookup_content')"
        " FROM lookup_document WHERE projection_id = 'lookup:exact-lookup:company'"
    )
    industry_terms = Counter()
    phrase_companies = {}          # whole stripped phrase -> companies hit
    tail_companies = Counter()     # tail term -> companies hit
    tail_phrases = {}              # tail term -> set of phrases using it as tail
    n = 0
    for (lc,) in cur:
        doc = json.loads(lc)
        n += 1
        ind = (doc.get("industry") or {}).get("name")
        if ind:
            industry_terms[ind] += 1
        for t in doc.get("industry_tags") or []:
            if t.get("name"):
                industry_terms[t["name"]] += 1
        stripped = set()
        for t in doc.get("tech_tags") or []:
            v = (t.get("name") or "").strip()
            if not v:
                continue
            s = BIZ_SUFFIX.sub("", v).strip()
            if s:
                stripped.add(s)
        for s in stripped:
            phrase_companies[s] = phrase_companies.get(s, 0) + 1
        tails = set()
        for s in stripped:
            for size in range(2, 7):
                if len(s) >= size:
                    t = s[-size:]
                    tails.add(t)
                    tail_phrases.setdefault(t, set()).add(s)
        for t in tails:
            tail_companies[t] += 1
    con.close()

    def ranked(counter, filt=None, top=120):
        items = [(t, c) for t, c in counter.items() if not filt or filt(t)]
        items.sort(key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
        return items[:top]

    tail_rows = []
    for t, c in ranked(tail_companies, filt=lambda t: t not in GENERIC):
        tail_rows.append({
            "term": t,
            "companies_hit_tail": c,
            "share": round(c / n, 4),
            "phrase_count": len(tail_phrases.get(t, ())),
            "phrase_examples": sorted(tail_phrases.get(t, ()))[:5],
        })

    payload = {
        "pack": PACK,
        "company_docs": n,
        "industry_labels": [{"term": t, "companies": c, "share": round(c / n, 4)}
                            for t, c in industry_terms.most_common()],
        "category_phrases": [{"phrase": p, "companies": c} for p, c in ranked(phrase_companies, top=80)],
        "tail_terms": tail_rows,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"companies={n} phrases={len(phrase_companies)} tail_terms={len(tail_companies)}")
    print()
    print("--- top 50 category tail terms by company reach ---")
    for r in tail_rows[:50]:
        print(f"  {r['companies_hit_tail']:5d} ({r['share']*100:5.1f}%) "
              f"phrases={r['phrase_count']:4d}  {r['term']:14s} {r['phrase_examples'][:3]}")


if __name__ == "__main__":
    main()
