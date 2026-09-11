#!/usr/bin/env python3
"""Seed catalogs/anchoring-declaration-v1.json (C1 batch 0).

Reads g3-vocabulary.json (G3 anchoring analysis) and emits the packaged
declaration consumed by `canonical_v2/anchoring_declaration.py`. The F1
scoring block is seeded byte-identical to the constants previously hardcoded
in `knowledge_read_isolated` (industry 8 / tag 4 / product 2, bigram
coverage 2, min score 2), so the consumer swap is behavior-preserving.
anchor_field for S-tier terms = the curated company field with the most hits
in the pack scan; T/N terms carry null.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# g3-vocabulary.json lives in the main repo's run artifacts (not synced into
# the s11 worktree); pass an explicit path as argv[1] to regenerate.
G3 = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps"
    "/g-series/g3-vocabulary.json"
)
OUT = (
    HERE.parents[2]
    / "apps/miroflow-agent/src/data_agents/canonical_v2/catalogs"
    / "anchoring-declaration-v1.json"
)

PACK_ID = "serving-pack:candidate-v2-20260819-r1"
# manifest.json files["lookup.sqlite3"] of the sealed run14 pack.
PACK_LOOKUP_SHA256 = "c392d559f403da928f3baeed8092c19717059b3bd1e8339fcde07fa2b7970c91"

_CONFIDENCE_BY_TIER = {
    "S": "structured_anchored",
    "T": "text_only",
    "N": "no_signal",
}
_CURATED_COMPANY_FIELDS = ("industry", "industry_tags", "tech_tags")

# AQ-S5 (A-2): declared paraphrase families for the F1 category recall. A
# member joins the query's term set only when the family head is itself an
# extracted query term (trigger gating), at the member weight from
# `_paraphrase_multiplier` — always below the extracted weight of the head,
# so expansion widens recall without outgunning the query's own words. The
# PCB vocabulary was measured against the sealed run14 pack
# (d0-probe/aq-s5-explore.json): 8 in-pack GTs 54/41/98/9/70/62/out/out ->
# 56/37/20/3/18/25/14/2 untruncated.
_PARAPHRASE_FAMILIES = {
    "PCB": (
        "印制电路板",
        "印制线路板",
        "柔性线路板",
        "柔性电路板",
        "封装基板",
        "刚挠结合",
        "PCBA",
        "电路板",
        "线路板",
        "柔性板",
        "FPC",
        "SMT",
        "打样",
        "打板",
        "制板",
        "贴片",
    ),
}


def _paraphrase_multiplier(member: str) -> int:
    # Self-delimiting phrases (>= 4 chars) carry word-grade weight 2; shorter
    # members weigh 1. Both stay at or below the extracted weight of a query
    # word (2) — the declared "expanded terms weigh less" rule.
    return 2 if len(member) >= 4 else 1


def main() -> None:
    vocabulary = json.loads(G3.read_text())["vocabulary"]
    terms = []
    for entry in sorted(vocabulary, key=lambda item: item["rank"]):
        tier = entry["tier"]
        anchor_field = None
        if tier == "S":
            hits = entry["hits"]
            best = max(
                _CURATED_COMPANY_FIELDS,
                key=lambda field: (hits.get(f"company.{field}", 0), field),
            )
            if hits.get(f"company.{best}", 0) > 0:
                anchor_field = best
        terms.append(
            {
                "term": entry["term"],
                "tier": tier,
                "anchor_field": anchor_field,
                "match_mode": "substring",
                "multiplier": 1,
                "confidence_class": _CONFIDENCE_BY_TIER[tier],
                "whitelisted": False,
            }
        )
    declared_terms = {term["term"] for term in terms}
    for head, members in _PARAPHRASE_FAMILIES.items():
        if head not in declared_terms:
            raise RuntimeError(f"paraphrase family head is not declared: {head}")
        for member in members:
            if member in declared_terms:
                raise RuntimeError(
                    f"paraphrase member duplicates a vocabulary term: {member}"
                )
            terms.append(
                {
                    "term": member,
                    "tier": "T",
                    "anchor_field": None,
                    "match_mode": "substring",
                    "multiplier": _paraphrase_multiplier(member),
                    "confidence_class": "text_only",
                    "whitelisted": False,
                    "expands": head,
                }
            )
    declaration = {
        "schema_version": "canonical-v2-anchoring-declaration-v1",
        "generated_from": {
            "pack_id": PACK_ID,
            "pack_sha256": PACK_LOOKUP_SHA256,
            "sources": [
                "g-series/g3-vocabulary.json",
                "knowledge_read_isolated F1 constants (close-workbook-gaps B1)",
                "AQ-S5 PCB paraphrase family (close-workbook-gaps A-2)",
            ],
        },
        "f1_category_scoring": {
            "field_tier_multipliers": {"industry_label": 8, "tag": 4, "product": 2},
            "min_bigram_coverage": 2,
            "min_score": 2,
        },
        "terms": terms,
    }
    OUT.write_text(
        json.dumps(declaration, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tiers = {}
    for term in terms:
        tiers[term["tier"]] = tiers.get(term["tier"], 0) + 1
    anchored = sum(1 for term in terms if term["anchor_field"])
    print(f"terms={len(terms)} tiers={tiers} anchored={anchored} -> {OUT}")


if __name__ == "__main__":
    main()
