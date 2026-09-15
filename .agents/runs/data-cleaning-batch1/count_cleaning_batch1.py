#!/usr/bin/env python3
"""D0-a replay counter: apply the publication-cleaning rules to a serving pack.

Read-only by construction: the pack is opened with ``mode=ro&immutable=1`` and
nothing is written back.  Run it over a *copy* of a released pack to reproduce
the before/after counts and to emit the quarantine side reports that D1 (LLM
review) consumes.

Usage (from ``apps/miroflow-agent``):

    uv run python ../../.agents/runs/data-cleaning-batch1/count_cleaning_batch1.py \
        --pack /tmp/dq-batch1-scratch/lookup.sqlite3 \
        --out  ../../.agents/runs/data-cleaning-batch1/out

Baseline numbers this script reconciles against:
``.agents/runs/data-quality-assessment/placeholder-recount.txt`` and
``docs/plans/2026-09-15-data-quality-assessment.md`` (run15 pack).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sqlite3
import sys
from typing import Iterable

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "apps" / "miroflow-agent"))

from src.data_agents.canonical_v2.publication_cleaning import (  # noqa: E402
    GLUE_TOKEN,
    NO_INFORMATION_SENTENCE_RE,
    PROVINCE_RE,
    audit_projection_payload,
    clean_projected_values,
    placeholder_family,
    research_direction_rule,
)

DOMAINS = ("company", "paper", "patent", "professor")
CITY_LEVEL_RE = re.compile(r"^.+-.+市$")


def geography_class(label: str | None) -> str:
    """Classify a company geography label the way the assessment counted it."""
    if not isinstance(label, str) or not label.strip():
        return "absent"
    text = label.strip()
    if PROVINCE_RE.match(text):
        return "province_only"
    if CITY_LEVEL_RE.match(text):
        return "city_level"
    return "dirty"

# run15 baseline (assessment 2026-09-15) - the assertions this batch must hit.
BASELINE = {
    "placeholder_hits_domain": {"company": 3097, "professor": 12872},
    "whole_value_weizhaodao_exact": 1817,
    "whole_value_weizhaodao_prefix": 2,
    "glue_runs": 189,
    "geography_province_only": 4887,
    "geography_city_level": 554,
    "research_direction_entries": 10238,
}


def iter_documents(connection: sqlite3.Connection, domain: str) -> Iterable[dict]:
    for (document_json,) in connection.execute(
        "SELECT document_json FROM lookup_document WHERE projection_id = ?",
        (f"lookup:exact-lookup:{domain}",),
    ):
        document = json.loads(document_json)
        yield json.loads(document["lookup_content"])


def walk_strings(value, path: str = ""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_strings(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from walk_strings(item, f"{path}.{key}" if path else key)


def classify_baseline(text: str) -> str | None:
    """The assessment's placeholder taxonomy, for the before/after table."""
    stripped = text.strip()
    if stripped == GLUE_TOKEN:
        return "whole_value_exact"
    if stripped.startswith(GLUE_TOKEN):
        return "whole_value_prefix"
    if GLUE_TOKEN in stripped:
        return "glue_run"
    return "placeholder_family" if placeholder_family(text) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", required=True, help="path to a lookup.sqlite3 copy")
    parser.add_argument("--out", required=True, help="directory for side reports")
    args = parser.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(f"file:{args.pack}?mode=ro&immutable=1", uri=True)

    before = collections.Counter()
    after = collections.Counter()
    before_field = collections.Counter()
    after_field = collections.Counter()
    baseline_classes = collections.Counter()
    research_before = collections.Counter()
    research_after = collections.Counter()
    quarantined: list[dict] = []
    glue_kept: list[dict] = []
    geography_before = collections.Counter()
    geography_after = collections.Counter()
    dirty_examples: set[str] = set()

    for domain in DOMAINS:
        for payload in iter_documents(connection, domain):
            audit_before = audit_projection_payload(domain, payload)
            for key, value in audit_before.items():
                before[key] += value
            cleaned, records = clean_projected_values(
                domain, payload, canonical_identity_id=payload.get("id", "")
            )
            audit_after = audit_projection_payload(domain, cleaned)
            for key, value in audit_after.items():
                after[key] += value
            for record in records:
                quarantined.append(
                    {
                        "canonical_identity_id": record.canonical_identity_id,
                        "domain": record.domain,
                        "field_path": record.field_path,
                        "rule": record.rule,
                        "value": record.value,
                        "reference_id": record.reference_id,
                    }
                )
            for path, text in walk_strings(payload):
                klass = classify_baseline(text)
                if klass is not None:
                    baseline_classes[klass] += 1
                    before_field[f"{domain}.{path}"] += 1
            for path, text in walk_strings(cleaned):
                if classify_baseline(text) is not None:
                    after_field[f"{domain}.{path}"] += 1
                if GLUE_TOKEN in text and not NO_INFORMATION_SENTENCE_RE.match(
                    text.strip()
                ):
                    glue_kept.append(
                        {
                            "canonical_identity_id": payload.get("id", ""),
                            "domain": domain,
                            "field_path": path,
                            "value": text,
                        }
                    )
            if domain == "professor":
                for item in payload.get("research_directions") or []:
                    label = item.get("name") if isinstance(item, dict) else item
                    if isinstance(label, str):
                        research_before[research_direction_rule(label) or "clean"] += 1
                for item in cleaned.get("research_directions") or []:
                    label = item.get("name") if isinstance(item, dict) else item
                    if isinstance(label, str):
                        research_after[research_direction_rule(label) or "clean"] += 1
            if domain == "company":
                for payload_variant, counter in (
                    (payload, geography_before),
                    (cleaned, geography_after),
                ):
                    label = payload_variant.get("geography")
                    if isinstance(label, dict):
                        label = label.get("name")
                    klass = geography_class(label if isinstance(label, str) else None)
                    counter[klass] += 1
                    if klass == "dirty" and len(counter) < 40:
                        dirty_examples.add(label.strip())
                        counter[f"dirty:{label.strip()}"] += 1

    (out / "quarantine.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in quarantined),
        encoding="utf-8",
    )
    (out / "kept-legit-prose.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in glue_kept),
        encoding="utf-8",
    )
    counts = {
        "pack": str(args.pack),
        "before": dict(before),
        "after": dict(after),
        "baseline_classes_before": dict(baseline_classes),
        "baseline_classes_after": dict(after_field),
        "research_directions_before": dict(research_before),
        "research_directions_after": dict(research_after),
        "geography_before": dict(geography_before),
        "geography_after": dict(geography_after),
        "quarantine_records": len(quarantined),
        "quarantine_by_rule": dict(
            collections.Counter(item["rule"] for item in quarantined)
        ),
        "glue_kept_values": len(glue_kept),
    }
    (out / "counts.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("== pack:", args.pack)
    print("== documents:", before["documents"], "->", after["documents"])
    print()
    print(f"{'metric':32s} {'before':>8s} {'after':>8s}")
    for key in (
        "placeholder_hits",
        "glue_damaged_values",
        "glue_legit_values",
        "research_direction_entries",
        "research_direction_junk",
    ):
        print(f"{key:32s} {before[key]:8d} {after[key]:8d}")
    print()
    print("baseline taxonomy (field occurrences containing 未找到):")
    for key in sorted(baseline_classes):
        print(f"  before {key:22s} {baseline_classes[key]:6d}")
    print(f"  after  {'any':22s} {sum(after_field.values()):6d}")
    for key in sorted(after_field):
        print(f"     still present: {key} = {after_field[key]}")
    print()
    print("geography (company):")
    print("  before:", {k: v for k, v in geography_before.items() if not k.startswith("dirty:")})
    print("  after :", {k: v for k, v in geography_after.items() if not k.startswith("dirty:")})
    print("  dirty labels (before):", sorted(dirty_examples)[:12])
    print()
    print("research directions:", dict(research_before), "->", dict(research_after))
    print()
    print("baseline deltas vs assessment 2026-09-15:")
    print(
        f"  whole-value 未找到 exact: {baseline_classes['whole_value_exact']} "
        f"(baseline {BASELINE['whole_value_weizhaodao_exact']})"
    )
    print(
        f"  whole-value 未找到 prefix: {baseline_classes['whole_value_prefix']} "
        f"(baseline {BASELINE['whole_value_weizhaodao_prefix']})"
    )
    print(
        f"  glue runs: {baseline_classes['glue_run']} "
        f"(baseline {BASELINE['glue_runs']})"
    )
    print(
        f"  province-only geography: {geography_before['province_only']} "
        f"(baseline {BASELINE['geography_province_only']}); "
        f"city-level: {geography_before['city_level']} "
        f"(baseline {BASELINE['geography_city_level']})"
    )
    print(
        f"  research-direction entries: {sum(research_before.values())} "
        f"(baseline {BASELINE['research_direction_entries']})"
    )
    print()
    print("side reports:", out / "quarantine.jsonl", ",", out / "kept-legit-prose.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
