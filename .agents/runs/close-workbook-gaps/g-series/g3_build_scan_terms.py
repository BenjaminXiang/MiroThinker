#!/usr/bin/env python3
"""G3 step 6: build the term file that the anchoring scan should cover.

Union of
  a) every candidate produced by g3_terms.py,
  b) the pack's own category head nouns: 2..6-char tails of stripped tech_tag
     phrases (g3-taxonomy-ranking.json), top 200 by company reach after the
     category-noun filter,
  c) the pack's 41 curated industry labels,
  d) PROBE: hand-picked boundary terms (hot Shenzhen categories the extractor
     cannot reach from this log). Used only for the appendix / boundary analysis,
     never for the vocabulary export.

Output: g3-scan-terms.json  {"terms": [...], ...}
"""
import json

BASE = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series"
TERMS = f"{BASE}/g3-terms.json"
TAX = f"{BASE}/g3-taxonomy-ranking.json"
OUT = f"{BASE}/g3-scan-terms.json"
TOP_TAILS = 200

PROBE = [
    "储能", "水下机器人", "人形机器人", "半导体", "新能源", "机器视觉", "激光雷达",
    "物联网", "低空经济", "生物医药", "医疗器械", "自动驾驶", "工业互联网",
    "六维力传感器", "电子皮肤", "大模型", "伺服电机", "减速器", "智能网联汽车",
    "数字经济", "云计算", "边缘计算", "智能制造", "具身智能", "灵巧手", "机械臂",
]


def main():
    with open(TERMS, encoding="utf-8") as fh:
        cand = [t["term"] for t in json.load(fh)["terms"]]
    with open(TAX, encoding="utf-8") as fh:
        tax = json.load(fh)

    tails = tax["tail_terms"]
    counts = {r["term"]: r["companies_hit_tail"] for r in tails}
    all_counts = {r["term"]: r["companies_hit_tail"] for r in tax.get("tail_terms_all", [])}
    all_counts.update(counts)

    suppressed = {}
    for s in all_counts:
        for t in all_counts:
            if t != s and len(t) > len(s) and s in t and all_counts[t] >= all_counts[s]:
                suppressed[s] = t
                break
    kept_tails = [r["term"] for r in tails if r["term"] not in suppressed][:TOP_TAILS]

    industry = [r["term"] for r in tax["industry_labels"] if r["term"] != "-"]
    terms = list(dict.fromkeys(cand + kept_tails + industry + PROBE))
    payload = {
        "candidates": len(cand),
        "taxonomy_tails_kept": kept_tails,
        "industry_labels": industry,
        "probe_terms": PROBE,
        "taxonomy_tails_suppressed": suppressed,
        "terms": terms,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"candidates={len(cand)} tails={len(kept_tails)} industry={len(industry)} "
          f"probe={len(PROBE)} union={len(terms)}")


if __name__ == "__main__":
    main()
