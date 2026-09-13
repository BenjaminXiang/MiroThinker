#!/usr/bin/env python3
"""Alias-closure dry run (run14 C1; read-only, no rebuild).

Replays the real build functions over the full p4 company batch and
simulates the field-merge alias union against the CURRENT serving pack's
aliases, so the effect of the change is known before any rebuild:

    cd apps/miroflow-agent
    uv run python <this script> --out <report.json>

Uses `_p4_company_record` (alias emission) and `_p4_company_field_merge`
(union semantics) from the build module itself — the report measures the
shipping code, not a reimplementation.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rows",
        default=(
            "/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z/"
            "workspace/docs/source_backfills/p4-company-full-v1.jsonl"
        ),
    )
    parser.add_argument(
        "--pack-lookup",
        default="/var/tmp/mirothinker-data-v2/index-v1/lookup.sqlite3",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(Path.cwd()))
    from src.data_agents.canonical_v2 import knowledge_build_isolated as build

    now = datetime.now(timezone.utc)

    existing_by_name: dict[str, list[str]] = {}
    con = sqlite3.connect(f"file:{args.pack_lookup}?mode=ro", uri=True)
    for (document_json,) in con.execute(
        "SELECT document_json FROM lookup_document "
        "WHERE projection_id='lookup:exact-lookup:company'"
    ):
        payload = json.loads(json.loads(document_json)["lookup_content"])
        name = payload.get("name")
        if isinstance(name, str):
            existing_by_name[name.strip()] = [
                alias
                for alias in (payload.get("aliases") or [])
                if isinstance(alias, str)
            ]
    con.close()
    pack_with_alias = sum(1 for aliases in existing_by_name.values() if aliases)

    rows_total = 0
    rows_invalid = 0
    rows_pack_miss = 0
    rows_with_candidate = 0
    union_gained_companies = 0
    union_gained_aliases = 0
    already_covered = 0
    collisions: defaultdict[str, set[str]] = defaultdict(set)
    samples: list[list[str]] = []

    with open(args.rows, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows_total += 1
            payload = json.loads(line)
            built = build._p4_company_record(payload, now=now)
            if built is None:
                rows_invalid += 1
                continue
            _, _, _, selected = built
            name = selected.get("name")
            aliases = [
                alias
                for alias in (selected.get("aliases") or [])
                if isinstance(alias, str)
            ]
            if aliases:
                rows_with_candidate += 1
                for alias in aliases:
                    collisions[alias.casefold()].add(name)
                if len(samples) < 20:
                    samples.append([name, aliases])
            if name not in existing_by_name:
                rows_pack_miss += 1
                continue
            existing_aliases = existing_by_name[name]
            existing = {
                "name": name,
                "normalized_name": selected.get("normalized_name") or name,
                "aliases": list(existing_aliases),
            }
            build._p4_company_field_merge(
                existing=existing,
                fill={"aliases": aliases},
                object_id="alias-dry-run",
                source_record_id="alias-dry-run",
                run_id="alias-dry-run",
                observed_at=now,
                assertions=[],
            )
            final = [
                alias
                for alias in (existing.get("aliases") or [])
                if isinstance(alias, str)
            ]
            known = {alias.casefold() for alias in existing_aliases}
            gained = [alias for alias in final if alias.casefold() not in known]
            if gained:
                union_gained_companies += 1
                union_gained_aliases += len(gained)
            elif aliases:
                already_covered += 1

    multi = {
        form: sorted(names) for form, names in collisions.items() if len(names) > 1
    }
    report = {
        "generated_at": now.isoformat(),
        "rows_file": args.rows,
        "pack_lookup": args.pack_lookup,
        "rows_total": rows_total,
        "rows_invalid": rows_invalid,
        "rows_with_alias_candidate": rows_with_candidate,
        "rows_pack_miss": rows_pack_miss,
        "pack_companies": len(existing_by_name),
        "pack_companies_with_alias_before": pack_with_alias,
        "union_gained_companies": union_gained_companies,
        "union_gained_aliases": union_gained_aliases,
        "already_covered_by_pack_alias": already_covered,
        "estimated_pack_companies_with_alias_after": (
            pack_with_alias + union_gained_companies
        ),
        "estimated_coverage_after": round(
            (pack_with_alias + union_gained_companies)
            / max(len(existing_by_name), 1),
            4,
        ),
        "collision_forms": {form: names for form, names in sorted(multi.items())},
        "collision_form_count": len(multi),
        "samples": samples,
    }
    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, ensure_ascii=False, indent=1))
    for sample in samples[:10]:
        print("sample:", sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
