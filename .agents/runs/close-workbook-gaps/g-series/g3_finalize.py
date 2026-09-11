#!/usr/bin/env python3
"""G3 step 4 (final): build g3-vocabulary.json -- every number used by the report.

Inputs
  g3-terms.json           traffic counts per candidate (two scopes)
  g3-anchoring.json       run14 pack field coverage per term (candidates + pack tails)
  g3-taxonomy-ranking.json pack's own category vocabulary, ranked
  g3-scan-terms.json      which terms the anchoring scan covered

Output sections
  corpus_vocabulary      §1A  terms extracted from the category-query corpus,
                              ranked by category traffic
  extension_vocabulary   §1B  pack-validated category head nouns the log never
                              asked for, ranked by company reach (from the pack)
  vocabulary             §1   both tables with a global rank (top 30)
  verification_table     §3   anchored-vs-text-only contrast for the top 15
  gap_list               §4   tier T (summary-only) / N (no signal) by traffic
  rejected               appendix: generic words / fragments / shorthands

Deterministic keep rules (see g3-category-anchoring.md for the narrative):

  admit(T) := T not in GENERIC and T not in SHORTHAND
              and ( cat_turns > 0                                     # traffic lens
                 or in_lexicon                                        # exact taxonomy entry
                 or taxonomy_tail_matches                             # head noun of a taxonomy phrase
                 or (taxonomy_head_matches and len >= 3)              # modifier of a taxonomy phrase
                 or (in_taxonomy_value and full_turns >= 3 and len >= 3) )
  fragment suppression: drop S when a longer admitted T contains S and either
              traffic(T) >= traffic(S), or S has no standalone evidence
              (cat_whole_run / full_whole_run == 0) and traffic(T) >= 0.5 * traffic(S).
              Exact taxonomy entries (in_lexicon) are protected: that keeps head
              nouns such as 机器人 while dropping fragments such as 智能/具身/器人.

  tier S = structured-anchored   : >=1 company doc hits a curated field and
                                   company structured coverage >= 20%
  tier T = text-only             : documents hit free-text fields only
  tier N = no signal             : term hits no scanned field anywhere in the pack
"""
import json

BASE = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series"
TERMS = f"{BASE}/g3-terms.json"
ANCHOR = f"{BASE}/g3-anchoring.json"
TAX = f"{BASE}/g3-taxonomy-ranking.json"
SCAN_TERMS = f"{BASE}/g3-scan-terms.json"
OUT = f"{BASE}/g3-vocabulary.json"

GENERIC = {
    "他们", "我们", "你们", "地方", "属于", "不同", "不能去", "展开说", "更详细", "详细",
    "上述", "是否", "什么", "怎么", "如何", "应用", "使用", "采用", "生成", "操作", "运动",
    "自主", "落地", "科学", "旅游", "电梯", "模拟器", "创始", "科技", "有限公司",
    "股份", "信息", "情况", "方式", "方法", "路线", "数据", "能力", "场景", "技术", "产品",
    "服务", "解决方案", "布局", "进展", "创始人", "企业家", "教授", "论文", "专利", "中心",
    "平台", "机构", "研究院", "学院", "大学", "公司", "企业", "厂商", "供应商", "模式",
    "趋势", "政策", "标准", "人才", "团队", "项目", "资本", "投资", "融资", "战略", "业务",
    "收入", "规模", "份额", "市场", "市场竞争力", "发展", "合成", "培育", "评价", "采集",
    "创立", "产业链", "供应链", "国际先进", "应用推进", "国先", "国际", "先进", "推进",
    "能科技", "用机", "器生", "无界", "智航", "需求", "链接", "真实", "一点", "能再",
    "毕业", "毕业于", "人力", "人机", "方案", "决方案", "研发", "设计", "开发", "销售",
    "生产", "制造", "系统", "设备", "集成", "服务商", "提供商", "研发商", "厂商", "企业",
    "项目", "工程", "贸易", "进出口", "投资管理", "咨询",
}
SHORTHAND = {
    "智能", "具身", "机器", "器人", "工智能", "人工智", "身智能", "身智", "具身智",
    "打板", "送餐", "餐机", "送餐机", "酒店", "餐机器人", "送餐机器", "灵巧", "巧手",
    "触觉", "视触", "传感", "人形", "水下", "机器臂", "决方案", "方案", "设计商",
    "件产品", "控产品", "联网", "及产品", "软硬件",
}


def main():
    with open(TERMS, encoding="utf-8") as fh:
        terms_doc = json.load(fh)
    with open(ANCHOR, encoding="utf-8") as fh:
        anchor = json.load(fh)
    with open(TAX, encoding="utf-8") as fh:
        tax = json.load(fh)
    with open(SCAN_TERMS, encoding="utf-8") as fh:
        scan_terms = json.load(fh)

    by_term = {t["term"]: t for t in terms_doc["terms"]}
    tax_reach = {r["term"]: r for r in tax["tail_terms"]}
    tax_reach_all = {r["term"]: r["companies_hit_tail"] for r in tax.get("tail_terms_all", [])}
    for r in tax["tail_terms"]:
        tax_reach_all.setdefault(r["term"], r["companies_hit_tail"])
    probe_terms = scan_terms.get("probe_terms", [])
    industry_labels = [r["term"] for r in tax["industry_labels"] if r["term"] != "-"]

    def traffic(t):
        r = by_term.get(t)
        return max(r["cat_turns"], r["full_turns"]) if r else 0

    def strength(t):
        return max(traffic(t), tax_reach_all.get(t, 0))

    def blank(t):
        return {"term": t, "cat_turns": 0, "cat_whole_run_turns": 0, "full_turns": 0,
                "full_whole_run_turns": 0, "cat_distinct_queries": 0, "cat_sessions": 0,
                "full_distinct_queries": 0, "cat_examples": [], "full_examples": []}

    terms_all = [t for t in scan_terms["terms"]]
    admitted, why = [], {}
    for t in terms_all:
        rec = by_term.get(t) or blank(t)
        if t in GENERIC or t in SHORTHAND:
            continue
        a = anchor["terms"].get(t, {})
        reasons = []
        if rec["cat_turns"] > 0:
            reasons.append("category_traffic")
        if a.get("in_lexicon"):
            reasons.append("taxonomy_entry")
        if a.get("taxonomy_tail_matches"):
            reasons.append("taxonomy_head")
        if a.get("taxonomy_head_matches") and len(t) >= 3:
            reasons.append("taxonomy_modifier")
        if a.get("in_taxonomy_value") and rec["full_turns"] >= 3 and len(t) >= 3:
            reasons.append("taxonomy_substring")
        if reasons:
            admitted.append(t)
            why[t] = reasons

    admitted_set = set(admitted)
    partners = admitted_set | GENERIC | SHORTHAND
    suppressed = {}
    for s in admitted:
        a = anchor["terms"].get(s, {})
        if a.get("in_lexicon"):
            continue  # exact taxonomy entries are protected head nouns
        s_strength = strength(s)
        for t in partners:
            if t == s or len(t) <= len(s) or s not in t:
                continue
            if strength(t) >= 0.9 * s_strength:
                suppressed[s] = t
                break
    kept = [t for t in admitted if t not in suppressed]

    def row(t, lens):
        rec = by_term.get(t) or blank(t)
        a = anchor["terms"].get(t, {})
        cls = a.get("doc_classes") or {"anchored": 0, "text_only": 0, "both": 0}
        ccls = a.get("company_doc_classes") or {"anchored": 0, "text_only": 0, "both": 0}
        total = sum(cls.values())
        c_total = sum(ccls.values())
        c_anchored = ccls["anchored"] + ccls["both"]
        c_cov = (c_anchored / c_total) if c_total else 0.0
        if total == 0:
            tier = "N"
        elif c_anchored > 0 and c_cov >= 0.20:
            tier = "S"
        else:
            tier = "T"
        tr = tax_reach.get(t)
        return {
            "term": t,
            "lens": lens,
            "traffic": traffic(t),
            "cat_turns": rec["cat_turns"],
            "cat_distinct_queries": rec["cat_distinct_queries"],
            "cat_sessions": rec["cat_sessions"],
            "cat_whole_run_turns": rec["cat_whole_run_turns"],
            "full_turns": rec["full_turns"],
            "full_whole_run_turns": rec["full_whole_run_turns"],
            "full_distinct_queries": rec["full_distinct_queries"],
            "example_query": (rec["cat_examples"] or rec["full_examples"] or [""])[0],
            "admitted_by": why.get(t, []),
            "in_lexicon": a.get("in_lexicon", False),
            "in_taxonomy_value": a.get("in_taxonomy_value", False),
            "taxonomy_tail_matches": (a.get("taxonomy_tail_matches") or [])[:6],
            "taxonomy_head_matches": (a.get("taxonomy_head_matches") or [])[:6],
            "pack_tail_reach": tr["companies_hit_tail"] if tr else 0,
            "pack_tail_phrases": tr["phrase_count"] if tr else 0,
            "hits": a.get("hits", {}),
            "per_domain": a.get("per_domain", {}),
            "doc_classes": cls,
            "company_doc_classes": ccls,
            "total_hit_docs": total,
            "company_hit_docs": c_total,
            "company_structured_docs": c_anchored,
            "company_structured_coverage": round(c_cov, 4),
            "tier": tier,
            "examples_structured": (a.get("examples") or {}).get("structured_docs", []),
            "examples_text_only": (a.get("examples") or {}).get("text_only_docs", []),
        }

    corpus = sorted((t for t in kept if (by_term.get(t) or blank(t))["cat_turns"] > 0
                     or t in tax_reach and t in by_term),
                    key=lambda t: (-traffic(t), t))
    corpus = [t for t in corpus if (by_term.get(t) or blank(t))["cat_turns"] > 0]
    corpus.sort(key=lambda t: (-traffic(t), t))
    extension = [t for t in kept if t not in corpus]
    extension.sort(key=lambda t: (-(tax_reach.get(t, {}).get("companies_hit_tail", 0)), t))

    corpus_rows = [row(t, "corpus") for t in corpus]
    extension_rows = [row(t, "pack_taxonomy") for t in extension]
    vocabulary = corpus_rows + extension_rows
    for i, r in enumerate(vocabulary, 1):
        r["rank"] = i

    probe_rows = [row(t, "probe") for t in probe_terms if t not in kept]
    for r in probe_rows:
        r["admitted"] = False
    probe_kept = [row(t, "probe_in_vocabulary") for t in probe_terms if t in kept]
    industry_rows = [row(t, "industry_label") for t in industry_labels]

    gap_rows = [r for r in vocabulary if r["tier"] in ("T", "N")]
    gap_rows.sort(key=lambda r: (-r["cat_turns"], -r["full_turns"], r["term"]))

    rejected = []
    for t in terms_all:
        rec = by_term.get(t) or blank(t)
        if t in kept or not (rec["cat_turns"] or rec["full_turns"] >= 3):
            continue
        if t in GENERIC:
            reason = "generic"
        elif t in SHORTHAND:
            reason = "shorthand"
        elif t in suppressed:
            reason = f"fragment_of:{suppressed[t]}"
        else:
            reason = "no_pack_signature"
        rejected.append({
            "term": t, "reason": reason, "traffic": traffic(t),
            "cat_turns": rec["cat_turns"], "full_turns": rec["full_turns"],
            "cat_whole_run_turns": rec["cat_whole_run_turns"],
        })
    rejected.sort(key=lambda r: (-r["cat_turns"], -r["full_turns"], r["term"]))

    payload = {
        "generated_by": "g3_finalize.py",
        "inputs": {"terms": TERMS, "anchoring": ANCHOR, "taxonomy": TAX, "scan_terms": SCAN_TERMS},
        "pack": anchor["pack"],
        "pack_domain_docs": {k: v["docs"] for k, v in anchor["domains"].items()},
        "pack_field_fill": {k: v["field_fill"] for k, v in anchor["domains"].items()},
        "lexicon_size": anchor["lexicon"]["size"],
        "taxonomy_value_count": anchor["taxonomy_value_count"],
        "scope": terms_doc["scope_category"],
        "scope_full": terms_doc["scope_full"],
        "kept_category_queries": terms_doc["kept_category_queries"],
        "dropped_anaphoric_distinct": terms_doc["dropped_anaphoric_distinct"],
        "generic_stoplist": sorted(GENERIC),
        "shorthand_stoplist": sorted(SHORTHAND),
        "industry_labels": tax["industry_labels"],
        "tier_definition": {
            "S": "structured-anchored: >=1 company doc hits a curated field and company structured coverage >= 20%",
            "T": "text-only: documents hit free-text fields only (structured coverage < 20%)",
            "N": "no signal: term appears in no scanned field of the pack",
        },
        "corpus_vocabulary": corpus_rows,
        "extension_vocabulary": extension_rows,
        "vocabulary": vocabulary,
        "verification_table": vocabulary[:15],
        "gap_list": gap_rows,
        "probe_table": probe_rows + probe_kept,
        "industry_label_table": industry_rows,
        "rejected": rejected[:120],
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"admitted={len(admitted)} kept={len(kept)} corpus={len(corpus_rows)} "
          f"extension={len(extension_rows)} gap={len(gap_rows)}")
    print()
    print(f"{'#':>3} {'term':16s} {'lens':13s} {'catT':>5} {'fullT':>5} {'reach':>5} | "
          f"{'anch':>5}{'txt':>5}{'both':>5} {'cCov':>6} {'tier':4s} | fields (company ind/itag/tech, prod, prof)")
    for i, r in enumerate(vocabulary, 1):
        h = r["hits"]
        c = r["company_doc_classes"]
        print(
            f"{i:>3} {r['term']:16s} {r['lens']:13s} {r['cat_turns']:5d} {r['full_turns']:5d} "
            f"{r['pack_tail_reach']:5d} | {c['anchored']:5d}{c['text_only']:5d}{c['both']:5d} "
            f"{r['company_structured_coverage']*100:5.1f}% {r['tier']:4s} | "
            f"{h.get('company.industry',0):4d}/{h.get('company.industry_tags',0):4d}/{h.get('company.tech_tags',0):4d} "
            f"{h.get('company.product_description',0):4d} {h.get('company.profile_summary',0):5d}"
        )
    print()
    print("--- gap list (tier T/N) ---")
    for r in gap_rows:
        print(f"  {r['tier']} catT={r['cat_turns']:4d} fullT={r['full_turns']:4d} "
              f"docs={r['total_hit_docs']:5d} cCov={r['company_structured_coverage']*100:5.1f}%  {r['term']}")


if __name__ == "__main__":
    main()
