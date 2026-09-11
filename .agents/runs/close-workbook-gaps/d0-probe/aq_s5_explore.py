"""AQ-S5 exploration: GT profile vocabulary + full-rank baseline for g5.

Read-only against the sealed run14 pack. Dumps, for each of the 8 in-pack
g5 GTs, the industry/tag/product/content fields, which candidate PCB-family
paraphrase terms appear where, and each GT's untruncated baseline rank/score
under the CURRENT `_category_query_terms` (mirrors `_category_recall_entries`
scoring exactly, minus the window cut).
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
OUT = Path(__file__).with_name("aq-s5-explore.json")

GTS = ("嘉立创", "深南电路", "一博", "顺易捷", "兴森", "则成", "上达", "精诚达")
CANDIDATE_FAMILY = (
    "pcb",
    "打板",
    "打样",
    "印制电路板",
    "印制线路板",
    "线路板",
    "电路板",
    "fpc",
    "柔性板",
    "柔性线路板",
    "柔性电路板",
    "刚挠结合",
    "hdi",
    "smt",
    "贴片",
)
QUERIES = {
    "g5-t1": "我想找PCB打板， 有哪些推荐",
    "pcb-list": "深圳有哪些做PCB的公司",
}

# Candidate PCB paraphrase family (head: pcb). Weight rule under test:
# >= 4 chars -> 2 (self-delimiting phrase), else 1.
FAMILY_V1 = {
    "pcb": {
        "印制电路板": 2,
        "印制线路板": 2,
        "柔性线路板": 2,
        "柔性电路板": 2,
        "封装基板": 2,
        "刚挠结合": 2,
        "pcba": 2,
        "电路板": 1,
        "线路板": 1,
        "柔性板": 1,
        "fpc": 1,
        "smt": 1,
        "打样": 1,
        "打板": 1,
        "制板": 1,
        "贴片": 1,
    }
}


def _expand(terms):
    heads = {term for term, _weight in terms}
    expanded = dict(terms)
    for head, members in FAMILY_V1.items():
        if head in heads:
            for member, weight in members.items():
                expanded.setdefault(member, weight)
    return tuple(sorted(expanded.items()))


def _score_table(entries, terms):
    """Mirror of _category_recall_entries scoring without the window cut."""
    scoring = iso._F1_CATEGORY_SCORING
    matched_by_entry = []
    industry_by_entry = []
    tags_by_entry = []
    product_by_entry = []
    coverage: dict[str, int] = {}
    for entry in entries:
        if entry.document.domain != "company":
            continue
        matched = frozenset(
            term
            for term, _weight in terms
            if any(term in content_term for content_term in entry.content_terms)
        )
        matched_by_entry.append((entry, matched))
        industry = frozenset(
            term
            for term in matched
            if any(term in v for v in entry.industry_label_terms)
        )
        tags = frozenset(
            term for term in matched if any(term in v for v in entry.tag_category_terms)
        )
        product = frozenset(
            term
            for term in matched
            if any(term in v for v in entry.product_category_terms)
        )
        industry_by_entry.append(industry)
        tags_by_entry.append(tags)
        product_by_entry.append(product)
        for term in matched:
            coverage[term] = coverage.get(term, 0) + 1
    surviving = {
        term: weight
        for term, weight in terms
        if coverage.get(term, 0) >= (scoring.min_bigram_coverage if weight < 2 else 1)
    }
    scored = []
    for (entry, matched), industry, tags, product in zip(
        matched_by_entry, industry_by_entry, tags_by_entry, product_by_entry
    ):
        score = sum(
            surviving[term]
            * (
                scoring.field_tier_multipliers.industry_label
                if term in industry
                else scoring.field_tier_multipliers.tag
                if term in tags
                else scoring.field_tier_multipliers.product
                if term in product
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
    return scored, surviving, coverage


def main() -> None:
    db = sqlite3.connect(f"file:{PACK_LOOKUP_DB}?mode=ro&immutable=1", uri=True)
    rows = db.execute("SELECT document_json FROM lookup_document").fetchall()
    documents = tuple(
        LookupProjectionDocument.model_validate(json.loads(row[0])) for row in rows
    )
    entries = iso._public_lookup_entries(documents)
    companies = tuple(e for e in entries if e.document.domain == "company")

    # 1) GT profiles: which candidate family terms appear in which field bucket.
    profiles = {}
    for alias in GTS:
        entry = next((e for e in companies if alias in e.display_name), None)
        if entry is None:
            profiles[alias] = None
            continue
        payload = json.loads(entry.document.lookup_content)
        buckets = {
            "industry": sorted(entry.industry_label_terms),
            "tags": sorted(entry.tag_category_terms),
            "product": sorted(entry.product_category_terms),
        }
        hits = {}
        for term in CANDIDATE_FAMILY:
            places = [
                bucket
                for bucket, values in buckets.items()
                if any(term in value for value in values)
            ]
            if any(term in ct for ct in entry.content_terms):
                places.append("content")
            if places:
                hits[term] = places
        profiles[alias] = {
            "canonical_id": entry.document.canonical_object_id,
            "display_name": entry.display_name,
            "family_hits": hits,
            "industry": payload.get("industry"),
            "industry_tags": payload.get("industry_tags"),
            "tech_tags": payload.get("tech_tags"),
        }

    # 2) Untruncated baseline ranks/scores for the GTs per query.
    baselines = {}
    for qid, query in QUERIES.items():
        terms = iso._category_query_terms(query)
        scored, surviving, coverage = _score_table(entries, terms)
        gt = {}
        for alias in GTS:
            hit = next(
                (
                    (index + 1, score)
                    for index, (score, entry) in enumerate(scored)
                    if alias in entry.display_name
                ),
                None,
            )
            gt[alias] = {"rank": hit[0], "score": hit[1]} if hit else None
        baselines[qid] = {
            "query_terms": list(terms),
            "surviving": surviving,
            "coverage": coverage,
            "total_scored": len(scored),
            "gt": gt,
            "score_histogram": {
                str(score): sum(1 for s, _e in scored if s == score)
                for score in sorted({s for s, _e in scored}, reverse=True)[:12]
            },
        }

    # 3) Same measurement with the candidate family expansion applied.
    expanded_view = {}
    for qid, query in QUERIES.items():
        terms = _expand(iso._category_query_terms(query))
        scored, surviving, coverage = _score_table(entries, terms)
        gt = {}
        for alias in GTS:
            hit = next(
                (
                    (index + 1, score)
                    for index, (score, entry) in enumerate(scored)
                    if alias in entry.display_name
                ),
                None,
            )
            gt[alias] = {"rank": hit[0], "score": hit[1]} if hit else None
        # Newly recalled / newly promoted docs: score >= 5 names for an
        # eyeball false-recall pass.
        promoted = [
            (score, entry.display_name)
            for score, entry in scored[:40]
        ]
        expanded_view[qid] = {
            "expanded_terms": list(terms),
            "total_scored": len(scored),
            "gt": gt,
            "score_histogram": {
                str(score): sum(1 for s, _e in scored if s == score)
                for score in sorted({s for s, _e in scored}, reverse=True)[:14]
            },
            "top40": promoted,
        }

    OUT.write_text(
        json.dumps(
            {
                "profiles": profiles,
                "baselines": baselines,
                "expanded_v1": expanded_view,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    for alias, profile in profiles.items():
        if profile is None:
            print(f"{alias}: NOT IN PACK")
            continue
        print(f"{alias}: {profile['display_name']}")
        print(f"  family_hits={profile['family_hits']}")
        print(f"  industry={profile['industry']} tags={profile['industry_tags']} tech={profile['tech_tags']}")
    for qid, data in baselines.items():
        print(f"=== {qid} terms={data['query_terms']} surviving={data['surviving']}")
        print(f"    total_scored={data['total_scored']} hist={data['score_histogram']}")
        print(f"    gt={data['gt']}")
    for qid, data in expanded_view.items():
        print(f"=== EXPANDED {qid} total_scored={data['total_scored']}")
        print(f"    hist={data['score_histogram']}")
        print(f"    gt={data['gt']}")
        print(f"    top40={data['top40']}")


if __name__ == "__main__":
    main()
