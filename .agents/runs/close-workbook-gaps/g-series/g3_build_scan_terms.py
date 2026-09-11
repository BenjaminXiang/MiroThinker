#!/usr/bin/env python3
"""G3 step 6: build the term file that the anchoring scan should cover.

Union of
  a) every candidate produced by g3_terms.py (713 terms), and
  b) the pack's own category head nouns: top 60 tail terms from
     g3-taxonomy-ranking.json after fragment suppression.

Output: g3-scan-terms.json  {"terms": [...]}
"""
import json

BASE = "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/g-series"
TERMS = f"{BASE}/g3-terms.json"
TAX = f"{BASE}/g3-taxonomy-ranking.json"
OUT = f"{BASE}/g3-scan-terms.json"
TOP_TAILS = 60


def main():
    with open(TERMS, encoding="utf-8") as fh:
        cand = [t["term"] for t in json.load(fh)["terms"]]
    with open(TAX, encoding="utf-8") as fh:
        tails = json.load(fh)["tail_terms"]

    counts = {r["term"]: r["companies_hit_tail"] for r in tails}
    suppressed = {}
    for s in counts:
        for t in counts:
            if t != s and len(t) > len(s) and s in t and counts[t] >= counts[s]:
                suppressed[s] = t
                break
    kept_tails = [r["term"] for r in tails if r["term"] not in suppressed][:TOP_TAILS]

    terms = list(dict.fromkeys(cand + kept_tails))
    payload = {
        "candidates": len(cand),
        "taxonomy_tails": kept_tails,
        "taxonomy_tails_suppressed": suppressed,
        "terms": terms,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"candidates={len(cand)} tails_kept={len(kept_tails)} union={len(terms)}")
    print("taxonomy tails:", ", ".join(kept_tails))


if __name__ == "__main__":
    main()
