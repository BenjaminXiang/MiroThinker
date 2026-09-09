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

from src.data_agents.company.exact_backfill import (
    build_company_release_from_import_results,
    load_company_import_results,
)
from src.data_agents.company.release import publish_company_release


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_input() -> Path:
    return _repo_root() / "docs" / "专辑项目导出1768807339.xlsx"


def _default_supplement_inputs() -> list[Path]:
    return [
        _repo_root() / "docs" / "source_backfills" / "company_workbook_critical_supplement.xlsx"
    ]


def _default_output_paths() -> tuple[Path, Path, Path]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = _repo_root() / "logs" / "debug" / f"company_release_e2e_{timestamp}"
    return (
        output_dir / "company_records.jsonl",
        output_dir / "released_objects.jsonl",
        output_dir / "report.json",
    )


def _resolve_workbook_inputs(
    primary_input: Path,
    supplement_inputs: list[Path],
    *,
    strict_missing: bool,
) -> list[Path]:
    workbook_paths = [primary_input]
    for path in supplement_inputs:
        if path.exists():
            workbook_paths.append(path)
            continue
        message = f"supplement workbook not found: {path}"
        if strict_missing:
            raise FileNotFoundError(message)
        print(f"WARNING: {message}", file=sys.stderr)
    return workbook_paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run company import + release e2e and emit release artifacts.",
    )
    parser.add_argument("--input", type=Path, default=_default_input())
    parser.add_argument("--sheet-name", type=str, default="sheet1")
    parser.add_argument(
        "--supplement-input",
        type=Path,
        action="append",
        default=None,
        help="Additional company source workbook(s) to merge into the release.",
    )
    parser.add_argument("--company-output", type=Path, default=None)
    parser.add_argument("--released-output", type=Path, default=None)
    parser.add_argument("--report-output", type=Path, default=None)
    args = parser.parse_args()

    company_output, released_output, report_output = _default_output_paths()
    if args.company_output is not None:
        company_output = args.company_output
    if args.released_output is not None:
        released_output = args.released_output
    if args.report_output is not None:
        report_output = args.report_output

    supplement_inputs = (
        args.supplement_input if args.supplement_input is not None else _default_supplement_inputs()
    )
    workbook_inputs = _resolve_workbook_inputs(
        args.input,
        supplement_inputs,
        strict_missing=args.supplement_input is not None,
    )

    import_results = load_company_import_results(
        workbook_paths=workbook_inputs,
        sheet_name=args.sheet_name,
    )
    import_summaries = [asdict(result.report) for _, result in import_results]
    release_result = build_company_release_from_import_results(
        import_results=import_results,
    )
    publish_company_release(
        release_result,
        company_records_path=company_output,
        released_objects_path=released_output,
    )
    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": str(args.input),
        "inputs": [str(path) for path in workbook_inputs],
        "import_summaries": import_summaries,
        "release_summary": asdict(release_result.report),
        "outputs": {
            "company_records_jsonl": str(company_output),
            "released_objects_jsonl": str(released_output),
        },
    }

    if str(report_output) == "-":
        print(json.dumps(report_payload, ensure_ascii=False, indent=2))
        return 0

    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(report_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
