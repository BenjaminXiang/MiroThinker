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
    declaration = {
        "schema_version": "canonical-v2-anchoring-declaration-v1",
        "generated_from": {
            "pack_id": PACK_ID,
            "pack_sha256": PACK_LOOKUP_SHA256,
            "sources": [
                "g-series/g3-vocabulary.json",
                "knowledge_read_isolated F1 constants (close-workbook-gaps B1)",
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
