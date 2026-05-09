#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Summarize professor harvest artifacts for PRD/data-quality review."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.professor.cross_domain import PaperStagingRecord  # noqa: E402
from src.data_agents.professor.models import EnrichedProfessorProfile  # noqa: E402
from src.data_agents.professor.publish_helpers import build_professor_id  # noqa: E402
from src.data_agents.professor.quality_gate import (  # noqa: E402
    QualityResult,
    evaluate_quality,
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    rows: list[dict[str, Any]] = []
    bad_lines = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            bad_lines += 1
            continue
        if isinstance(value, dict):
            rows.append(value)
        else:
            bad_lines += 1
    return rows, bad_lines


def _safe_profile(row: dict[str, Any]) -> EnrichedProfessorProfile | None:
    try:
        return EnrichedProfessorProfile.model_validate(row)
    except Exception:
        return None


def _safe_staging(row: dict[str, Any]) -> PaperStagingRecord | None:
    try:
        return PaperStagingRecord.model_validate(row)
    except Exception:
        return None


def _profile_gap_flags(
    profile: EnrichedProfessorProfile,
    quality: QualityResult,
    *,
    has_staged_paper: bool,
) -> list[str]:
    flags: list[str] = []
    if not profile.department:
        flags.append("missing_department")
    if not profile.title:
        flags.append("missing_title")
    if not profile.research_directions:
        flags.append("missing_research_directions")
    if not profile.top_papers and not has_staged_paper:
        flags.append("missing_paper_signal")
    if not profile.publication_evidence_urls and not profile.scholarly_profile_urls:
        flags.append("missing_publication_anchor")
    if "profile_summary_boilerplate" in quality.l1_failures:
        flags.append("summary_boilerplate_or_refusal")
    if "profile_summary_too_short" in quality.l1_failures:
        flags.append("summary_too_short")
    if not quality.passed_l1:
        flags.append("l1_blocked")
    return flags


def _counter_to_sorted_items(counter: Counter[str]) -> list[dict[str, int | str]]:
    return [
        {"name": key, "count": count}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def analyze_harvest(output_dir: Path) -> dict[str, Any]:
    enriched_path = output_dir / "enriched_v3.jsonl"
    paper_staging_path = output_dir / "paper_staging.jsonl"
    quality_report_path = output_dir / "quality_report.json"
    e2e_report_path = output_dir / "e2e_report.json"
    failed_tasks_path = output_dir / "failed_tasks.jsonl"

    profile_rows, profile_bad_lines = _read_jsonl(enriched_path)
    staging_rows, staging_bad_lines = _read_jsonl(paper_staging_path)
    failed_rows, failed_bad_lines = _read_jsonl(failed_tasks_path)

    profiles = [profile for row in profile_rows if (profile := _safe_profile(row))]
    staging_records = [
        record for row in staging_rows if (record := _safe_staging(row))
    ]
    staging_professor_ids = {
        record.anchoring_professor_id for record in staging_records
    }

    quality_by_status: Counter[str] = Counter()
    l1_failures: Counter[str] = Counter()
    gap_flags: Counter[str] = Counter()
    institution_rows: dict[str, dict[str, Any]] = {}
    example_gaps: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for profile in profiles:
        professor_id = build_professor_id(profile)
        quality = evaluate_quality(profile)
        quality_by_status[str(quality.quality_status)] += 1
        l1_failures.update(quality.l1_failures)
        flags = _profile_gap_flags(
            profile,
            quality,
            has_staged_paper=professor_id in staging_professor_ids,
        )
        gap_flags.update(flags)

        inst = profile.institution or "[unknown]"
        row = institution_rows.setdefault(
            inst,
            {
                "institution": inst,
                "profiles": 0,
                "released_l1": 0,
                "blocked_l1": 0,
                "ready": 0,
                "needs_review": 0,
                "needs_enrichment": 0,
                "low_confidence": 0,
                "with_top_papers": 0,
                "with_staged_papers": 0,
                "with_research_directions": 0,
                "summary_boilerplate_or_refusal": 0,
            },
        )
        row["profiles"] += 1
        row["released_l1"] += int(quality.passed_l1)
        row["blocked_l1"] += int(not quality.passed_l1)
        row[str(quality.quality_status)] = row.get(str(quality.quality_status), 0) + 1
        row["with_top_papers"] += int(bool(profile.top_papers))
        row["with_staged_papers"] += int(professor_id in staging_professor_ids)
        row["with_research_directions"] += int(bool(profile.research_directions))
        row["summary_boilerplate_or_refusal"] += int(
            "summary_boilerplate_or_refusal" in flags
        )

        for flag in flags:
            if len(example_gaps[flag]) >= 5:
                continue
            example_gaps[flag].append(
                {
                    "name": profile.name,
                    "institution": profile.institution,
                    "department": profile.department,
                    "profile_url": profile.profile_url,
                    "quality_status": quality.quality_status,
                }
            )

    staging_by_source = Counter(record.source for record in staging_records)
    staging_by_link_status = Counter(record.link_status for record in staging_records)
    staging_by_institution = Counter(
        record.anchoring_institution for record in staging_records
    )
    staging_by_professor = Counter(
        record.anchoring_professor_id for record in staging_records
    )

    institution_summary = sorted(
        institution_rows.values(),
        key=lambda item: (-int(item["profiles"]), str(item["institution"])),
    )

    e2e_report = _read_json(e2e_report_path)
    existing_quality_report = _read_json(quality_report_path)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "files": {
            "enriched_v3_jsonl": {
                "path": str(enriched_path),
                "exists": enriched_path.exists(),
                "bad_lines": profile_bad_lines,
            },
            "paper_staging_jsonl": {
                "path": str(paper_staging_path),
                "exists": paper_staging_path.exists(),
                "bad_lines": staging_bad_lines,
            },
            "quality_report_json": {
                "path": str(quality_report_path),
                "exists": quality_report_path.exists(),
            },
            "e2e_report_json": {
                "path": str(e2e_report_path),
                "exists": e2e_report_path.exists(),
            },
            "failed_tasks_jsonl": {
                "path": str(failed_tasks_path),
                "exists": failed_tasks_path.exists(),
                "bad_lines": failed_bad_lines,
            },
        },
        "profiles": {
            "jsonl_rows": len(profile_rows),
            "valid_profiles": len(profiles),
            "invalid_profiles": len(profile_rows) - len(profiles),
            "quality_status": dict(quality_by_status),
            "l1_failures": dict(l1_failures),
            "gap_flags": dict(gap_flags),
            "institutions": institution_summary,
        },
        "paper_staging": {
            "jsonl_rows": len(staging_rows),
            "valid_records": len(staging_records),
            "invalid_records": len(staging_rows) - len(staging_records),
            "distinct_professors": len(staging_by_professor),
            "by_source": _counter_to_sorted_items(staging_by_source),
            "by_link_status": _counter_to_sorted_items(staging_by_link_status),
            "by_institution": _counter_to_sorted_items(staging_by_institution),
        },
        "failed_tasks": {
            "rows": len(failed_rows),
            "bad_lines": failed_bad_lines,
            "examples": failed_rows[:10],
        },
        "existing_reports": {
            "quality_report": existing_quality_report,
            "e2e_report_summary": _extract_e2e_summary(e2e_report),
        },
        "examples": dict(example_gaps),
    }


def _extract_e2e_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return None
    nested = report.get("report")
    if not isinstance(nested, dict):
        return None
    return {
        "stage1_discovery": nested.get("stage1_discovery"),
        "stage2b_papers": nested.get("stage2b_papers"),
        "stage8_release": nested.get("stage8_release"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze professor harvest artifacts for PRD/data-quality gaps."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Pipeline output directory containing enriched_v3.jsonl.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Optional path to write the JSON report. Defaults to stdout only.",
    )
    args = parser.parse_args()

    report = analyze_harvest(args.output_dir)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report_output:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
