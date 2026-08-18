#!/usr/bin/env python3
"""P4 reconciliation report: domain counts / field non-null rates / four-path
reachability sampling vs the 2026-08-17 coverage-audit baseline."""

from __future__ import annotations

import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASELINE = {
    "company": 1737,
    "paper": 563,
    "patent": 1931,
    "professor": 1428,
    "professor_attributed_to_paper": 3421,
    "patent_has_applicant": 727,
}

# The audit's field-poverty probes (non-null rates over the served pack).
COMPANY_FIELDS = [
    "profile_summary",
    "industry",
    "tech_tags",
    "geography",
    "founded_at",
    "legal_representative",
    "registered_address",
    "website",
    "team_description",
    "product_description",
]
PATENT_FIELDS = ["applicants", "patent_type", "abstract", "technology_effect"]
PAPER_FIELDS = ["abstract", "summary_zh", "venue", "year", "citation_count"]
PROFESSOR_FIELDS = [
    "institution",
    "department",
    "title",
    "email",
    "homepage",
    "research_directions",
    "profile_summary",
]


def _load_lookup(pack: Path) -> dict[str, list[dict]]:
    db = sqlite3.connect(f"file:{pack / 'lookup.sqlite3'}?mode=ro", uri=True)
    domains: dict[str, list[dict]] = defaultdict(list)
    for projection_id, document_json in db.execute(
        "select projection_id, document_json from lookup_document"
    ):
        domain = projection_id.rsplit(":", 1)[-1]
        document = json.loads(document_json)
        domains[domain].append(json.loads(document["lookup_content"]))
    db.close()
    return domains


def _non_null_rate(rows: list[dict], field: str) -> float:
    def has_value(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(
                value.strip()
                and value.strip()
                not in {
                    "Not supplied by the historical source.",
                    "No dedicated summary was supplied by the historical source.",
                    "No dedicated summary was supplied by the backfill source.",
                    "Not supplied by the backfill source.",
                    "Not supplied by the full-column patent source.",
                    "No dedicated summary was supplied by the full-column workbook source.",
                    "Not supplied by the full-column workbook source.",
                }
            )
        if isinstance(value, (list, tuple, dict)):
            return len(value) > 0
        return True

    if not rows:
        return 0.0
    hits = sum(1 for row in rows if has_value(row.get(field)))
    return hits / len(rows)


def _relationship_counts(pack: Path) -> Counter:
    counts: Counter = Counter()
    decoder = json.JSONDecoder()
    text = (pack / "relationships.json").read_text(encoding="utf-8")
    for match in re.finditer(r'"relationship_type"\s*:\s*"([a-z_]+)"', text):
        counts[match.group(1)] += 1
    return counts


def main() -> int:
    pack = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "/var/tmp/mirothinker-data-v2/serving-pack"
    )
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        "/home/longxiang/MiroThinker/.worktrees/data-rebuild/"
        ".agents/runs/full-column-serving-pack-rebuild/reconciliation-report.json"
    )
    domains = _load_lookup(pack)
    report: dict[str, object] = {
        "pack": str(pack),
        "domain_counts": {},
        "baseline_counts": BASELINE,
        "field_non_null_rates": {},
        "relationships": {},
        "reachability_samples": {},
    }
    for domain in ("company", "paper", "patent", "professor"):
        rows = domains.get(domain, [])
        report["domain_counts"][domain] = len(rows)  # type: ignore[index]
        report["domain_counts"][f"{domain}_x_baseline"] = (  # type: ignore[index]
            round(len(rows) / BASELINE[domain], 2) if BASELINE[domain] else None
        )
    field_lists = {
        "company": COMPANY_FIELDS,
        "patent": PATENT_FIELDS,
        "paper": PAPER_FIELDS,
        "professor": PROFESSOR_FIELDS,
    }
    for domain, fields in field_lists.items():
        rows = domains.get(domain, [])
        report["field_non_null_rates"][domain] = {  # type: ignore[index]
            field: round(_non_null_rate(rows, field), 4) for field in fields
        }
    if (pack / "relationships.json").exists():
        counts = _relationship_counts(pack)
        report["relationships"] = dict(counts)  # type: ignore[index]

    # Four-path reachability sampling (exact / structured / lexical / vector
    # handled by the smoke serve; here we verify the lookup-side anchors the
    # audit found missing: aliases, tech_tags vocabulary, relationship lane).
    companies = domains.get("company", [])
    sample_names = ["优必选", "UBTECH", "深圳市优必选科技股份有限公司"]
    anchors = {}
    for name in sample_names:
        anchors[name] = any(
            name in (row.get("aliases") or [])
            or (row.get("name") or "") == name
            or (row.get("normalized_name") or "") == name
            for row in companies
        )
    report["reachability_samples"]["company_alias_anchor"] = anchors  # type: ignore[index]
    vocabulary = Counter()
    for row in companies:
        for tag in row.get("tech_tags") or []:
            vocabulary[tag.get("name", "")] += 1
        industry = row.get("industry")
        if isinstance(industry, dict):
            vocabulary[industry.get("name", "")] += 1
    report["reachability_samples"]["structured_vocabulary_top20"] = (  # type: ignore[index]
        dict(vocabulary.most_common(20))
    )
    patents = domains.get("patent", [])
    bound_applicants = sum(
        1
        for row in patents
        for applicant in row.get("applicants") or []
        if isinstance(applicant, dict) and applicant.get("canonical_company_id")
    )
    report["reachability_samples"]["patent_applicants_with_canonical_company"] = (  # type: ignore[index]
        bound_applicants
    )
    papers = domains.get("paper", [])
    report["reachability_samples"]["papers_with_professor_anchor"] = sum(  # type: ignore[index]
        1 for row in papers if row.get("professor_ids")
    )
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["domain_counts"], ensure_ascii=False, indent=2))
    print(json.dumps(report["field_non_null_rates"], ensure_ascii=False, indent=2))
    print(json.dumps(report["relationships"], ensure_ascii=False, indent=2))
    print(f"written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
