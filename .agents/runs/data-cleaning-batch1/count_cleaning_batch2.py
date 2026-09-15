#!/usr/bin/env python3
"""D0-b replay counter: venue merge / edge dedup / applicants / geography.

Read-only by construction: ``lookup.sqlite3`` is opened
``mode=ro&immutable=1`` and ``relationships.json`` is only read.  Run it over a
*copy* of a released pack (or the sealed pack itself, since nothing is written).

Usage (from ``apps/miroflow-agent``):

    uv run python ../../.agents/runs/data-cleaning-batch1/count_cleaning_batch2.py \
        --pack-dir /var/tmp/mirothinker-data-v2/serving-pack-run15-sealed \
        --out      ../../.agents/runs/data-cleaning-batch1/out2
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sqlite3
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "apps" / "miroflow-agent"))

from src.data_agents.canonical_v2.publication_cleaning import (  # noqa: E402
    audit_lookup_documents,
    audit_patent_applicants,
    canonicalize_venue_reference,
    derive_company_geography,
    venue_canonical_map,
)

DOMAINS = ("company", "paper", "patent", "professor")

# run15 baseline (assessment 2026-09-15)
BASELINE = {
    "venue_labels": 5204,
    "venue_groups": 121,
    "venue_group_labels": 244,
    "venue_group_rows": 1979,
    "edges": 10773,
    "edge_pairs": 10742,
    "duplicate_pairs": 31,
    "applicant_rows": 12565,
    "applicant_bound": 7614,
    "applicant_unbound": 4951,
    "dirty_geography": 3,
    "dead_fields": 46,
}


def iter_documents(connection: sqlite3.Connection, domain: str):
    for (document_json,) in connection.execute(
        "SELECT document_json FROM lookup_document WHERE projection_id = ?",
        (f"lookup:exact-lookup:{domain}",),
    ):
        yield json.loads(json.loads(document_json)["lookup_content"])


def label_of(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("name")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--skip-relationships",
        action="store_true",
        help="skip the 3.4 GB relationships.json pass (venue/geography/applicants only)",
    )
    args = parser.parse_args()

    pack_dir = pathlib.Path(args.pack_dir)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        f"file:{pack_dir / 'lookup.sqlite3'}?mode=ro&immutable=1", uri=True
    )

    venues = collections.Counter()
    company_ids: set[str] = set()
    for payload in iter_documents(connection, "company"):
        company_ids.add(payload["id"])
    applicants_before = collections.Counter()
    geography_changes: list[dict[str, Any]] = []
    geography_before = collections.Counter()
    geography_after = collections.Counter()

    documents_by_domain: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for domain in DOMAINS:
        for payload in iter_documents(connection, domain):
            documents_by_domain[domain].append(payload)
            if domain == "paper":
                label = label_of(payload.get("venue"))
                if isinstance(label, str):
                    venues[label] += 1
            elif domain == "company":
                label = label_of(payload.get("geography"))
                outcome = derive_company_geography(label, payload.get("registered_address"))
                before = label if isinstance(label, str) and label.strip() else None
                after = label_of(outcome.value)
                if outcome.disposition != "clean":
                    geography_changes.append(
                        {
                            "canonical_identity_id": payload["id"],
                            "before": before,
                            "after": after,
                            "rule": outcome.disposition,
                        }
                    )
                for counter, value in (
                    (geography_before, before),
                    (geography_after, after),
                ):
                    if not isinstance(value, str) or not value.strip():
                        counter["absent"] += 1
                    elif "-" in value:
                        counter["city_level"] += 1
                    else:
                        counter["province_only"] += 1
            elif domain == "patent":
                audit = audit_patent_applicants(
                    payload, released_company_ids=frozenset(company_ids)
                )
                applicants_before["rows"] += audit.rows
                applicants_before["bound"] += audit.bound_rows
                applicants_before["unbound"] += audit.unbound_rows
                applicants_before["nameless"] += audit.nameless_rows
                applicants_before["invalid"] += audit.invalid_binding_rows

    class _Doc:
        def __init__(self, domain: str, payload: dict[str, Any]) -> None:
            self.domain = domain
            self.lookup_content = json.dumps(payload, ensure_ascii=False)

    audit = audit_lookup_documents(
        _Doc(domain, payload)
        for domain in DOMAINS
        for payload in documents_by_domain[domain]
    )
    venue_map = venue_canonical_map(venues)
    merged = collections.Counter()
    venue_groups: dict[str, set[str]] = collections.defaultdict(set)
    for label, count in venues.items():
        from src.data_agents.canonical_v2.publication_cleaning import (
            venue_group_key,
        )

        outcome = canonicalize_venue_reference(label, venue_map)
        merged[label_of(outcome.value)] += count
        venue_groups[venue_group_key(label)].add(label)
    multi_groups = {k: v for k, v in venue_groups.items() if len(v) > 1}

    edges = collections.Counter()
    duplicate_samples: list[dict[str, Any]] = []
    if not args.skip_relationships:
        raw = json.loads((pack_dir / "relationships.json").read_text(encoding="utf-8"))
        relationships = raw["relationship_projection_result"]["current_relationships"]
        for relationship in relationships:
            if relationship["relationship_type_id"] != "professor_attributed_to_paper":
                continue
            key = (
                relationship["source_endpoint"]["canonical_identity_id"],
                relationship["target_endpoint"]["canonical_identity_id"],
            )
            edges[key] += 1
        duplicate_pairs = {k: v for k, v in edges.items() if v > 1}
        for key, count in sorted(duplicate_pairs.items())[:5]:
            duplicate_samples.append({"pair": list(key), "rows": count})
    else:
        duplicate_pairs = {}

    counts = {
        "pack_dir": str(pack_dir),
        "venue": {
            "distinct_labels_before": len(venues),
            "distinct_labels_after": len(merged),
            "groups_with_multiple_labels": len(multi_groups),
            "labels_in_groups": sum(len(v) for v in multi_groups.values()),
            "rows_in_groups": sum(
                venues[label] for group in multi_groups.values() for label in group
            ),
            "top_after": merged.most_common(8),
        },
        "edges": {
            "edges_before": sum(edges.values()),
            "pairs_before": len(edges),
            "duplicate_pairs_before": len({k: v for k, v in edges.items() if v > 1}),
            "edges_after": len(edges),
            "pairs_after": len(edges),
            "duplicate_samples": duplicate_samples,
        },
        "applicants": dict(applicants_before),
        "geography": {
            "before": dict(geography_before),
            "after": dict(geography_after),
            "changed": geography_changes,
        },
        "dead_fields": {
            "declared_never_filled_fields": audit.as_dict()[
                "declared_never_filled_fields"
            ],
            "declared_never_filled_field_count": audit.as_dict()[
                "declared_never_filled_field_count"
            ],
        },
    }
    (out / "counts-batch2.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"== pack: {pack_dir}")
    print()
    print("venue:")
    print(
        f"  distinct labels {len(venues)} -> {len(merged)} "
        f"(groups>1: {len(multi_groups)}, labels {sum(len(v) for v in multi_groups.values())}, "
        f"rows {sum(venues[label] for group in multi_groups.values() for label in group)})"
    )
    print(f"  baseline groups/labels/rows: "
          f"{BASELINE['venue_groups']}/{BASELINE['venue_group_labels']}/{BASELINE['venue_group_rows']}")
    print(f"  top after: {merged.most_common(5)}")
    print()
    print("edges (professor_attributed_to_paper):")
    if args.skip_relationships:
        print("  skipped")
    else:
        dup = len({k: v for k, v in edges.items() if v > 1})
        print(
            f"  {sum(edges.values())} edges / {len(edges)} pairs "
            f"(baseline {BASELINE['edges']}/{BASELINE['edge_pairs']}); "
            f"duplicate pairs {dup} -> 0 after de-duplication"
        )
        for sample in duplicate_samples:
            print(f"    dup sample: {sample}")
    print()
    print("applicants:", dict(applicants_before))
    print(
        "  baseline: rows 12565, bound 7614, unbound 4951 (all named, 0 invalid bindings)"
    )
    print()
    print("geography (company):", dict(geography_before), "->", dict(geography_after))
    for change in geography_changes:
        print(f"    {change['rule']}: {change['before']!r} -> {change['after']!r}")
    print()
    per_domain = audit.as_dict()["declared_never_filled_fields"]
    print(
        "dead declarations (declared on every document of a domain, filled on none):",
    )
    for domain in DOMAINS:
        fields = per_domain.get(domain, [])
        print(f"  {domain:10s} {len(fields):2d}  {', '.join(fields)}")
    print(
        f"  total {audit.as_dict()['declared_never_filled_field_count']} "
        f"(baseline assessment: {BASELINE['dead_fields']})"
    )
    print("side report:", out / "counts-batch2.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
