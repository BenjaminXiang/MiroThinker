#!/usr/bin/env python3
"""Extract the free-text tag vocabulary of a serving pack, read-only.

Reads the run15 pack copy in /tmp/d1a-scratch (never the production directory)
and writes the induction inputs plus the "before" counters the D1-a verification
contract compares against:

  * every distinct ``tech_tags`` value with its company frequency
  * every distinct ``industry`` value with its company frequency
  * ``industry_tags`` redundancy check
  * tags-per-company distribution
  * category-probe support in the tag fields (verbatim method of
    ``analysis_company.py`` section 6 so before/after are comparable)
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Sequence
import json
from pathlib import Path
import sqlite3
from typing import Any

DEFAULT_LOOKUP = Path("/tmp/d1a-scratch/lookup-run15.sqlite3")
DEFAULT_OUT = Path(".agents/runs/d1a-tech-vocabulary/out")
COMPANY_PROJECTION_ID = "lookup:exact-lookup:company"
TAG_FIELDS = ("industry", "industry_tags", "tech_tags")

CATEGORY_PROBES = (
    "机器人",
    "配送机器人",
    "餐饮机器人",
    "具身智能",
    "灵巧手",
    "协作机器人",
    "工业机器人",
    "PCB",
    "激光雷达",
    "传感器",
    "送餐",
)


def load_documents(path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT document_json FROM lookup_document WHERE projection_id = ?",
            (COMPANY_PROJECTION_ID,),
        )
        documents = []
        for (raw,) in rows:
            document = json.loads(raw)
            content = document["lookup_content"]
            documents.append(
                json.loads(content) if isinstance(content, str) else content
            )
        return documents
    finally:
        connection.close()


def reference_names(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    names: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"].strip())
    return names


def tag_field_blob(document: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in TAG_FIELDS:
        parts.extend(reference_names(document.get(field)))
    return " ".join(parts)


def probe_support(
    documents: Sequence[dict[str, Any]], probes: Iterable[str]
) -> dict[str, int]:
    return {
        probe: sum(1 for document in documents if probe in tag_field_blob(document))
        for probe in probes
    }


def histogram(counts: Counter[str]) -> dict[str, int]:
    buckets: Counter[str] = Counter()
    for count in counts.values():
        if count <= 1:
            buckets["1"] += 1
        elif count <= 4:
            buckets["2-4"] += 1
        elif count <= 9:
            buckets["5-9"] += 1
        elif count <= 49:
            buckets["10-49"] += 1
        else:
            buckets["50+"] += 1
    return dict(sorted(buckets.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookup", type=Path, default=DEFAULT_LOOKUP)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--label", default="run15")
    args = parser.parse_args()

    documents = load_documents(args.lookup)
    tech_tag_counts: Counter[str] = Counter()
    industry_counts: Counter[str] = Counter()
    tags_per_company: Counter[str] = Counter()
    industry_tags_matches_industry = 0
    industry_tags_other = 0
    for document in documents:
        tech_tags = reference_names(document.get("tech_tags"))
        industry = reference_names(document.get("industry"))
        industry_tags = reference_names(document.get("industry_tags"))
        tech_tag_counts.update(tech_tags)
        industry_counts.update(industry)
        tags_per_company[str(len(tech_tags))] += 1
        if industry_tags and industry_tags == industry:
            industry_tags_matches_industry += 1
        elif industry_tags:
            industry_tags_other += 1

    common = {
        "label": args.label,
        "lookup_path": str(args.lookup),
        "company_documents": len(documents),
        "tech_tag_rows": sum(tech_tag_counts.values()),
        "tech_tag_distinct_values": len(tech_tag_counts),
        "tech_tag_singletons": sum(1 for c in tech_tag_counts.values() if c == 1),
        "industry_distinct_values": len(industry_counts),
        "companies_without_tech_tags": tags_per_company.get("0", 0),
        "tags_per_company": dict(
            sorted(tags_per_company.items(), key=lambda kv: int(kv[0]))
        ),
        "industry_tags_equal_industry": industry_tags_matches_industry,
        "industry_tags_differing": industry_tags_other,
        "category_probe_support_tag_fields": probe_support(documents, CATEGORY_PROBES),
        "tech_tag_value_histogram": histogram(tech_tag_counts),
        "industry_value_histogram": histogram(industry_counts),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "vocabulary-inputs.json").write_text(
        json.dumps(
            {
                **common,
                "tech_tag_values": [
                    {"value": value, "companies": count}
                    for value, count in sorted(
                        tech_tag_counts.items(), key=lambda kv: (-kv[1], kv[0])
                    )
                ],
                "industry_values": [
                    {"value": value, "companies": count}
                    for value, count in sorted(
                        industry_counts.items(), key=lambda kv: (-kv[1], kv[0])
                    )
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(common, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
