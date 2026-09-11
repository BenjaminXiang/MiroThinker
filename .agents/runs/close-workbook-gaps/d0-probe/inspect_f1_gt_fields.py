"""F1 field-tier probe — which projection fields actually carry the GT
companies' category text in the sealed run14 pack.

Prints, per GT alias, the populated buckets the recall scorer sees
(structured = industry/industry_tags/tech_tags, product =
name/normalized_name/product_description) so the field-tier weighting can be
checked against ground truth instead of assumed. Read-only, no network.
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

ALIASES = (
    "普渡",
    "开普勒",
    "云迹",
    "九号",
    "擎朗",
    "艾唯尔",
    "安赛步",
    "嘉立创",
    "深南电路",
    "一博",
    "顺易捷",
    "兴森",
    "则成",
    "上达",
    "精诚达",
)


def main() -> None:
    db = sqlite3.connect(f"file:{PACK_LOOKUP_DB}?mode=ro", uri=True)
    rows = db.execute("SELECT document_json FROM lookup_document").fetchall()
    documents = tuple(
        LookupProjectionDocument.model_validate(json.loads(row[0])) for row in rows
    )
    entries = iso._public_lookup_entries(documents)
    for alias in ALIASES:
        for entry in entries:
            if entry.document.domain != "company" or alias not in entry.display_name:
                continue
            projection = iso._validated_public_projection(entry.document)
            industry = (
                projection.industry.name if projection.industry is not None else None
            )
            print(f"== {alias} :: {entry.display_name}")
            print(f"  industry={industry!r}")
            print(
                "  industry_tags="
                f"{[tag.name for tag in projection.industry_tags]!r}"
            )
            print(f"  tech_tags={[tag.name for tag in projection.tech_tags]!r}")
            print(f"  product_description={projection.product_description!r}")
            print(f"  industry_label={sorted(entry.industry_label_terms)!r}")
            print(f"  tags={sorted(entry.tag_category_terms)!r}")
            print(f"  product={sorted(entry.product_category_terms)!r}")


if __name__ == "__main__":
    main()
