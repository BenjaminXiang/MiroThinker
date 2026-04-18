#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.company.import_xlsx import import_company_xlsx
from src.data_agents.company.release import build_company_release
from src.data_agents.patent.exact_backfill import build_patent_release_from_sources
from src.data_agents.patent.import_xlsx import import_patent_xlsx
from src.data_agents.patent.release import publish_patent_release


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_patent_input() -> Path:
    return _repo_root() / "docs" / "2025-12-05 专利.xlsx"


def _default_company_input() -> Path:
    return _repo_root() / "docs" / "专辑项目导出1768807339.xlsx"


def _default_supplement_patent_inputs() -> list[Path]:
    path = _repo_root() / "docs" / "source_backfills" / "patent_exact_identifier_supplement.xlsx"
    return [path] if path.exists() else []


def _default_output_paths() -> tuple[Path, Path, Path]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = _repo_root() / "logs" / "debug" / f"patent_release_e2e_{timestamp}"
    return (
        output_dir / "patent_records.jsonl",
        output_dir / "released_objects.jsonl",
        output_dir / "report.json",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run patent import + release e2e and emit release artifacts.",
    )
    parser.add_argument("--patent-input", type=Path, default=_default_patent_input())
    parser.add_argument("--company-input", type=Path, default=_default_company_input())
    parser.add_argument("--patent-output", type=Path, default=None)
    parser.add_argument("--released-output", type=Path, default=None)
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument(
        "--supplement-patent-input",
        type=Path,
        action="append",
        default=None,
        help="Optional extra patent workbook(s) with exact-identifier backfills.",
    )
    args = parser.parse_args()

    patent_output, released_output, report_output = _default_output_paths()
    if args.patent_output is not None:
        patent_output = args.patent_output
    if args.released_output is not None:
        released_output = args.released_output
    if args.report_output is not None:
        report_output = args.report_output

    supplement_patent_inputs = (
        args.supplement_patent_input
        if args.supplement_patent_input is not None
        else _default_supplement_patent_inputs()
    )
    patent_inputs = [args.patent_input, *supplement_patent_inputs]
    patent_import_reports = [asdict(import_patent_xlsx(path).report) for path in patent_inputs]
    company_import_result = import_company_xlsx(args.company_input, sheet_name="sheet1")
    company_release_result = build_company_release(
        records=company_import_result.records,
        source_file=args.company_input,
    )
    company_name_to_id = {
        record.name: record.id for record in company_release_result.company_records
    }
    patent_release_result = build_patent_release_from_sources(
        workbook_paths=patent_inputs,
        company_name_to_id=company_name_to_id,
        now=datetime.now(timezone.utc),
    )
    publish_patent_release(
        patent_release_result,
        patent_records_path=patent_output,
        released_objects_path=released_output,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "patent_inputs": [str(path) for path in patent_inputs],
        "company_input": str(args.company_input),
        "patent_import_summaries": patent_import_reports,
        "patent_release_summary": asdict(patent_release_result.report),
        "outputs": {
            "patent_records_jsonl": str(patent_output),
            "released_objects_jsonl": str(released_output),
        },
    }

    if str(report_output) == "-":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(report_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
