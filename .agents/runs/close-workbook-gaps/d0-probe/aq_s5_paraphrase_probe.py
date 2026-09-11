"""AQ-S5 paraphrase probe — before/after GT ranks on the sealed run14 pack.

"before" = the validated scoring mirror without expansion (its baseline ranks
were cross-checked against the production chain in aq_s2_window_probe:
54/41/98/9/70/62/out/out at g5-t1). "after" = the PRODUCTION
`_category_recall_entries` with the declaration-driven PCB paraphrase family
active, plus the mirror-with-expansion for untruncated ranks; the probe
asserts the mirror's top-64 equals the production window-64 output so the
untruncated ranks are trustworthy.

No network, no writes outside this directory's JSON output.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/miroflow-agent"))

from src.data_agents.canonical_v2 import (  # noqa: E402
    knowledge_read_isolated as iso,
)
from src.data_agents.canonical_v2.index_projection import (  # noqa: E402
    LookupProjectionDocument,
)
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    LaneRequest,
    StructuredConstraints,
    WebSearchPolicy,
)

PACK_LOOKUP_DB = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed/lookup.sqlite3")
OUT = Path(__file__).with_name("aq-s5-paraphrase-probe.json")

GTS = ("顺易捷", "深南电路", "嘉立创", "则成", "兴森", "一博", "上达", "精诚达")
QUERIES = {
    "g5-t1": "我想找PCB打板， 有哪些推荐",
    "pcb-list": "深圳有哪些做PCB的公司",
    "g2-t1": "中国有哪些成熟的酒店送餐机器人供应商",
}
G2_GTS = ("普渡", "开普勒", "云迹", "九号", "擎朗", "艾唯尔", "安赛步", "锐曼")
WINDOWS = (32, 64)


def _score_table(entries, terms):
    """Mirror of _category_recall_entries scoring without the window cut."""
    scoring = iso._F1_CATEGORY_SCORING
    matched_by_entry = []
    tier_hits = []
    coverage: dict[str, int] = {}
    for entry in entries:
        if entry.document.domain != "company":
            continue
        matched = frozenset(
            term
            for term, _weight in terms
            if any(term in content_term for content_term in entry.content_terms)
        )
        tiers = {
            "industry": frozenset(
                term
                for term in matched
                if any(term in v for v in entry.industry_label_terms)
            ),
            "tag": frozenset(
                term
                for term in matched
                if any(term in v for v in entry.tag_category_terms)
            ),
            "product": frozenset(
                term
                for term in matched
                if any(term in v for v in entry.product_category_terms)
            ),
        }
        matched_by_entry.append((entry, matched))
        tier_hits.append(tiers)
        for term in matched:
            coverage[term] = coverage.get(term, 0) + 1
    surviving = {
        term: weight
        for term, weight in terms
        if coverage.get(term, 0) >= (scoring.min_bigram_coverage if weight < 2 else 1)
    }
    scored = []
    for (entry, matched), tiers in zip(matched_by_entry, tier_hits):
        score = sum(
            surviving[term]
            * (
                scoring.field_tier_multipliers.industry_label
                if term in tiers["industry"]
                else scoring.field_tier_multipliers.tag
                if term in tiers["tag"]
                else scoring.field_tier_multipliers.product
                if term in tiers["product"]
                else 1
            )
            for term in matched
            if term in surviving
        )
        if score >= scoring.min_score:
            scored.append((score, entry))
    scored.sort(
        key=lambda pair: (
            -pair[0],
            pair[1].document.domain or "",
            pair[1].document.canonical_object_id,
            pair[1].document.document_id,
        )
    )
    return scored


def _request(release_id: str, query: str, window: int) -> LaneRequest:
    return LaneRequest(
        lane="lexical",
        release_id=release_id,
        query_view="view:original",
        original_query=query,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(mode="disabled"),
        query_text=query,
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=window,
    )


def main() -> None:
    db = sqlite3.connect(f"file:{PACK_LOOKUP_DB}?mode=ro&immutable=1", uri=True)
    rows = db.execute("SELECT document_json FROM lookup_document").fetchall()
    documents = tuple(
        LookupProjectionDocument.model_validate(json.loads(row[0])) for row in rows
    )
    release_id = documents[0].release_id
    entries = iso._public_lookup_entries(documents)

    report: dict = {
        "pack": str(PACK_LOOKUP_DB),
        "release_id": release_id,
        "expansions": {
            head: list(members)
            for head, members in iso._CATEGORY_TERM_EXPANSIONS.items()
        },
        "queries": {},
    }
    for qid, query in QUERIES.items():
        gts = G2_GTS if qid == "g2-t1" else GTS
        base_terms = iso._category_query_terms(query)
        expanded_terms = iso._expand_category_query_terms(base_terms)
        before = _score_table(entries, base_terms)
        after_mirror = _score_table(entries, expanded_terms)

        # Equivalence: mirror-with-expansion top-64 must equal the production
        # chain's window-64 output exactly.
        production_64 = iso._category_recall_entries(
            request=_request(release_id, query, 64), entries=entries
        )
        mirror_64_ids = [entry.document.canonical_object_id for _s, entry in after_mirror[:64]]
        production_64_ids = [
            entry.document.canonical_object_id for entry in production_64
        ]
        assert mirror_64_ids == production_64_ids, f"mirror drifted on {qid}"

        def gt_ranks(scored):
            ranks = {}
            for alias in gts:
                hit = next(
                    (
                        (index + 1, score)
                        for index, (score, entry) in enumerate(scored)
                        if alias in entry.display_name
                    ),
                    None,
                )
                ranks[alias] = {"rank": hit[0], "score": hit[1]} if hit else None
            return ranks

        windows = {}
        for window in WINDOWS:
            production = iso._category_recall_entries(
                request=_request(release_id, query, window), entries=entries
            )
            windows[str(window)] = {
                "recalled": len(production),
                "gt_in_window": [
                    alias
                    for alias in gts
                    if any(alias in entry.display_name for entry in production)
                ],
            }
        report["queries"][qid] = {
            "query": query,
            "base_terms": list(base_terms),
            "expanded_terms": list(expanded_terms),
            "before": {
                "total_scored": len(before),
                "gt": gt_ranks(before),
            },
            "after": {
                "total_scored": len(after_mirror),
                "gt": gt_ranks(after_mirror),
                "score_histogram": {
                    str(score): sum(1 for s, _e in after_mirror if s == score)
                    for score in sorted({s for s, _e in after_mirror}, reverse=True)[:14]
                },
                "top40": [
                    [score, entry.display_name] for score, entry in after_mirror[:40]
                ],
            },
            "production_windows": windows,
        }

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    for qid, data in report["queries"].items():
        print(f"=== {qid}: {data['query']}")
        print(f"  before: {data['before']['gt']}")
        print(f"  after:  {data['after']['gt']}")
        for window, view in data["production_windows"].items():
            print(f"  production window={window}: gt_in_window={view['gt_in_window']}")


if __name__ == "__main__":
    main()
