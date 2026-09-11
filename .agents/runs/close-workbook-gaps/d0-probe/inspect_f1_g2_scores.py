"""F1 field-tier diagnostic — g2 score distribution on the sealed run14 pack.

Recomputes the exact `_category_recall_entries` scoring inline (same
constants, same guardrails) so individual scores are visible: where the
eight industry=机器人 companies land, and what the companies ahead of them
score. Read-only, no network.
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

PACK_LOOKUP_DB = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed/lookup.sqlite3")
QUERY = "中国有哪些成熟的酒店送餐机器人供应商"
GT_ALIASES = ("普渡", "开普勒", "云迹", "九号", "擎朗", "艾唯尔", "安赛步")


def main() -> None:
    db = sqlite3.connect(f"file:{PACK_LOOKUP_DB}?mode=ro", uri=True)
    rows = db.execute("SELECT document_json FROM lookup_document").fetchall()
    documents = tuple(
        LookupProjectionDocument.model_validate(json.loads(row[0])) for row in rows
    )
    entries = tuple(
        entry
        for entry in iso._public_lookup_entries(documents)
        if entry.document.domain == "company"
    )
    terms = iso._category_query_terms(QUERY)
    print(f"terms={terms}")

    matched_by_entry: list[frozenset[str]] = []
    industry_by_entry: list[frozenset[str]] = []
    tags_by_entry: list[frozenset[str]] = []
    product_by_entry: list[frozenset[str]] = []
    coverage: dict[str, int] = {}
    for entry in entries:
        matched = frozenset(
            term
            for term, _weight in terms
            if any(term in content_term for content_term in entry.content_terms)
        )
        matched_by_entry.append(matched)
        industry_by_entry.append(
            frozenset(
                term
                for term in matched
                if any(term in value for value in entry.industry_label_terms)
            )
        )
        tags_by_entry.append(
            frozenset(
                term
                for term in matched
                if any(term in value for value in entry.tag_category_terms)
            )
        )
        product_by_entry.append(
            frozenset(
                term
                for term in matched
                if any(term in value for value in entry.product_category_terms)
            )
        )
        for term in matched:
            coverage[term] = coverage.get(term, 0) + 1
    surviving = {
        term: weight
        for term, weight in terms
        if coverage.get(term, 0)
        >= (iso._CATEGORY_RECALL_MIN_BIGRAM_COVERAGE if weight < 2 else 1)
    }
    print(f"coverage={coverage}")
    print(f"surviving={surviving}")

    scored: list[tuple[int, str, object]] = []
    for entry, matched, industry, tags, product in zip(
        entries,
        matched_by_entry,
        industry_by_entry,
        tags_by_entry,
        product_by_entry,
        strict=True,
    ):
        score = sum(
            surviving[term]
            * (
                iso._CATEGORY_INDUSTRY_LABEL_MULTIPLIER
                if term in industry
                else iso._CATEGORY_TAG_FIELD_MULTIPLIER
                if term in tags
                else iso._CATEGORY_PRODUCT_FIELD_MULTIPLIER
                if term in product
                else 1
            )
            for term in matched
            if term in surviving
        )
        if score >= iso._CATEGORY_RECALL_MIN_SCORE:
            scored.append((score, entry.display_name, entry))
    scored.sort(
        key=lambda row: (
            -row[0],
            row[2].document.domain or "",
            row[2].document.canonical_object_id,
            row[2].document.document_id,
        )
    )
    print(f"pool={len(scored)}")
    print("-- top 30 --")
    for rank, (score, name, entry) in enumerate(scored[:30], start=1):
        projection = iso._validated_public_projection(entry.document)
        industry = (
            projection.industry.name if projection.industry is not None else None
        )
        print(f"  {rank:>3} score={score:<3} industry={industry!r:<10} {name}")
    print("-- GT --")
    for alias in GT_ALIASES:
        for rank, (score, name, entry) in enumerate(scored, start=1):
            if alias in name:
                projection = iso._validated_public_projection(entry.document)
                industry = (
                    projection.industry.name
                    if projection.industry is not None
                    else None
                )
                print(
                    f"  {alias} rank={rank} score={score} industry={industry!r} "
                    f"{name}"
                )
    # score histogram of the top tiers
    histogram: dict[int, int] = {}
    for score, _name, _entry in scored:
        histogram[score] = histogram.get(score, 0) + 1
    print(f"-- histogram (score: count) --")
    for score in sorted(histogram, reverse=True)[:12]:
        print(f"  {score}: {histogram[score]}")


if __name__ == "__main__":
    main()
