#!/usr/bin/env python3
"""Pre-launch risk sweep: does every risky input field have a cleaning rule?

Why: the 2026-09-15/16 run16 attempts died three times, each ~1-3.5 h into an
8 h build, on data-shaped defects that a five-minute scan of the staged inputs
would have flagged:

  * a placeholder venue fallback reached the pack (no cleaning rule for
    `venue`);
  * the build's fallback sentences leaked through the supplementary channel.

What it does: scans **every** P4 batch with the production classifiers
(`placeholder_family`, `glue_damaged`, `research_direction_rule`) plus the
fallback-trigger fields (a field left empty is what makes the build write a
placeholder fallback), maps each risky record field to the published
domain.field_path, and asserts that field is covered by the cleaning tables
(`CLEANED_TEXT_FIELDS` / `CLEANED_REFERENCE_FIELDS`, or the special-cased
research directions).

Exit code 0 = every risky field is covered; 1 = uncovered fields listed.
This is a **gate**, not a report: risky *values* are expected (that is what
cleaning is for); an uncovered *field* is the defect class we are hunting.

NOTE: a full-pipeline rehearsal (`build-mini.sh`) exists but is not a speed-up
for run16's input set — with the batches it must include to cover the risky
paths it equals the full manifest (111 MB, same 15 members); the fast gate is
this sweep plus the per-bug RED/GREEN tests.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
import unicodedata

REPO_ROOT = Path("/home/longxiang/MiroThinker")
APP_ROOT = REPO_ROOT / ".worktrees/data-rebuild/apps/miroflow-agent"
sys.path.insert(0, str(APP_ROOT))

from src.data_agents.canonical_v2.publication_cleaning import (  # noqa: E402
    CLEANED_REFERENCE_FIELDS,
    CLEANED_TEXT_FIELDS,
    glue_damaged,
    placeholder_family,
    research_direction_rule,
)

RESTORE_ROOT = Path("/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z")
BACKFILLS = RESTORE_ROOT / "workspace/docs/source_backfills"
OUT_DIR = Path(__file__).resolve().parent / "risk_sweep"

# Reviewed mapping: record field -> published (domain, field_path).  Mirrors the
# P4 record builders in knowledge_build_isolated._p4_*_record.  `fallback_fields`
# is the subset whose absence makes the build write a placeholder fallback.
BATCHES: dict[str, dict] = {
    "p4-paper-salvage-v1": {
        "file": "p4-paper-salvage-v1.jsonl",
        "fallback_fields": ("venue",),
        "fields": {
            "venue": ("paper", "venue"),
            "title": ("paper", "title"),
            "abstract": ("paper", "abstract"),
            "summary_zh": ("paper", "summary_zh"),
        },
    },
    "p4-company-full-v1": {
        "file": "p4-company-full-v1.jsonl",
        "fallback_fields": ("product_summary", "business", "geography"),
        "fields": {
            "product_summary": ("company", "product_description"),
            "business": ("company", "technology_route_summary"),
            # `_p4_company_record` publishes application_scenarios as the route
            # summary (`route_summary = scenarios or _P4_COMPANY_ROUTE_FALLBACK`),
            # not as business_scenarios.
            "application_scenarios": ("company", "technology_route_summary"),
            "team": ("company", "team_description"),
            "industry": ("company", "industry"),
            "geography": ("company", "geography"),
            "website": ("company", "website"),
        },
        # Fields the P4 record builders never read (their values cannot publish).
        "unused_fields": ("product_features",),
    },
    "p4-patent-full-v1": {
        "file": "p4-patent-full-v1.jsonl",
        "fallback_fields": ("summary_text", "technology_effect", "abstract"),
        "fields": {
            "summary_text": ("patent", "summary_text"),
            "technology_effect": ("patent", "technology_effect"),
            "abstract": ("patent", "abstract"),
        },
    },
    "p4-professor-full-v1": {
        "file": "p4-professor-full-v1.jsonl",
        "fallback_fields": (
            "department",
            "email",
            "homepage",
            "title",
            "profile_summary",
        ),
        "fields": {
            "department": ("professor", "department"),
            "email": ("professor", "email"),
            "homepage": ("professor", "homepage"),
            "title": ("professor", "title"),
            "profile_summary": ("professor", "profile_summary"),
            "research_directions": ("professor", "research_directions"),
        },
    },
    "p4-professor-paper-links-v1": {
        "file": "p4-professor-paper-links-v1.jsonl",
        "fallback_fields": (),
        "fields": {},
    },
    "p4-applicant-binding-full-v1": {
        "file": "p4-applicant-binding-full-v1.jsonl",
        "fallback_fields": ("resolved_company",),
        "fields": {
            "applicant_name": ("patent", "applicants"),
            "resolved_company": ("patent", "applicants"),
        },
    },
}

SPECIAL_CASED = {("professor", "research_directions")}


def _domain_module():
    return importlib.import_module(
        "src.data_agents.canonical_v2.publication_cleaning"
    )


def _covered(domain: str, field_path: str) -> bool:
    if (domain, field_path) in SPECIAL_CASED:
        return True
    text_fields = CLEANED_TEXT_FIELDS.get(domain, ())
    reference_fields = CLEANED_REFERENCE_FIELDS.get(domain, ())
    return field_path in text_fields or field_path in reference_fields


def _iter_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _scan_record(record: dict, spec: dict) -> dict[str, int]:
    """Count risky findings per top-level record field (empty = fallback trigger)."""
    findings: dict[str, int] = {}
    for field, value in record.items():
        for text in _iter_strings(value):
            if placeholder_family(text) is not None:
                findings[field] = findings.get(field, 0) + 1
            elif glue_damaged(text):
                findings[field] = findings.get(field, 0) + 1
    directions = record.get("research_directions")
    if isinstance(directions, list):
        for item in directions:
            label = item.get("name") if isinstance(item, dict) else item
            if isinstance(label, str) and research_direction_rule(label) is not None:
                findings["research_directions"] = (
                    findings.get("research_directions", 0) + 1
                )
    for field in spec["fallback_fields"]:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            findings[f"missing:{field}"] = findings.get(f"missing:{field}", 0) + 1
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR / "risk-sweep.json")
    args = parser.parse_args()

    report: dict[str, dict] = {}
    uncovered: dict[str, list[str]] = {}
    for batch_id, spec in sorted(BATCHES.items()):
        source = BACKFILLS / spec["file"]
        if not source.is_file():
            raise SystemExit(f"missing source batch: {source}")
        field_hits: dict[str, int] = {}
        records = 0
        for line in source.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            records += 1
            for field, count in _scan_record(record, spec).items():
                field_hits[field] = field_hits.get(field, 0) + count
        published = {}
        for field, count in sorted(field_hits.items()):
            base = field.removeprefix("missing:")
            if base in spec.get("unused_fields", ()):
                published[field] = {
                    "count": count,
                    "published": "(unused by the builder)",
                    "covered": True,
                }
                continue
            mapped = spec["fields"].get(base)
            if mapped is None:
                published[field] = {"count": count, "published": None, "covered": None}
                continue
            domain, field_path = mapped
            ok = _covered(domain, field_path)
            published[field] = {
                "count": count,
                "published": f"{domain}.{field_path}",
                "covered": ok,
            }
            if not ok:
                uncovered.setdefault(batch_id, []).append(
                    f"{field} -> {domain}.{field_path} ({count} hits)"
                )
        report[batch_id] = {
            "records": records,
            "fields": published,
        }
        print(f"== {batch_id} ({records} records)")
        for field, info in published.items():
            marker = (
                ""
                if info["covered"] is None
                else ("  OK" if info["covered"] else "  ** UNCOVERED **")
            )
            print(
                f"   {info['count']:7d}  {field:28s} -> "
                f"{info['published'] or '(unmapped)'}{marker}"
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {"batches": report, "uncovered": uncovered},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {args.out}")
    if uncovered:
        print("\nUNCOVERED RISKY FIELDS (the defect class this gate hunts):")
        for batch_id, items in uncovered.items():
            for item in items:
                print(f"  {batch_id}: {item}")
        return 1
    print("all risky fields are covered by the cleaning tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
