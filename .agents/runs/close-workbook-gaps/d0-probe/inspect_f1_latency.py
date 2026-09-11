"""F1 latency diagnostic — profile _category_recall_entries on g2.

Times the phases (eligibility scan, matched/content scan, bucket scans,
scoring) separately to explain the per-query cost on the sealed run14 pack.
Read-only, no network.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
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
QUERY = "中国有哪些成熟的酒店送餐机器人供应商"


def main() -> None:
    db = sqlite3.connect(f"file:{PACK_LOOKUP_DB}?mode=ro", uri=True)
    rows = db.execute("SELECT document_json FROM lookup_document").fetchall()
    documents = tuple(
        LookupProjectionDocument.model_validate(json.loads(row[0])) for row in rows
    )
    entries = iso._public_lookup_entries(documents)
    request = LaneRequest(
        lane="lexical",
        release_id=documents[0].release_id,
        query_view="view:original",
        original_query=QUERY,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(mode="disabled"),
        query_text=QUERY,
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(),
        max_candidates=48,
    )
    terms = iso._category_query_terms(QUERY)

    company_entries = [
        entry for entry in entries if entry.document.domain == "company"
    ]
    print(f"entries={len(entries)} companies={len(company_entries)}")
    content_values = sum(len(entry.content_terms) for entry in company_entries)
    content_chars = sum(
        len(term) for entry in company_entries for term in entry.content_terms
    )
    print(f"content_terms values={content_values} chars={content_chars}")

    # phase 1: matched/content scan only
    t0 = time.monotonic()
    matched_all = []
    for entry in company_entries:
        matched_all.append(
            frozenset(
                term
                for term, _weight in terms
                if any(term in ct for ct in entry.content_terms)
            )
        )
    print(f"content scan: {(time.monotonic() - t0) * 1000:.1f} ms")

    # phase 2: bucket scans only
    t0 = time.monotonic()
    for entry, matched in zip(company_entries, matched_all, strict=True):
        for bucket in (
            entry.industry_label_terms,
            entry.tag_category_terms,
            entry.product_category_terms,
        ):
            frozenset(
                term
                for term in matched
                if any(term in value for value in bucket)
            )
    print(f"bucket scans: {(time.monotonic() - t0) * 1000:.1f} ms")

    # full function, three repetitions
    for _ in range(3):
        t0 = time.monotonic()
        iso._category_recall_entries(request=request, entries=entries)
        print(f"full recall: {(time.monotonic() - t0) * 1000:.1f} ms")


if __name__ == "__main__":
    main()
