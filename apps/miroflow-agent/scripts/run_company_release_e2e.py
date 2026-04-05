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
from src.data_agents.company.release import (
    build_company_release,
    publish_company_release,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_input() -> Path:
    return _repo_root() / "docs" / "专辑项目导出1768807339.xlsx"


def _default_output_paths() -> tuple[Path, Path, Path]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = _repo_root() / "logs" / "debug" / f"company_release_e2e_{timestamp}"
    return (
        output_dir / "company_records.jsonl",
        output_dir / "released_objects.jsonl",
        output_dir / "report.json",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run company import + release e2e and emit release artifacts.",
    )
    parser.add_argument("--input", type=Path, default=_default_input())
    parser.add_argument("--sheet-name", type=str, default="sheet1")
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

    import_result = import_company_xlsx(args.input, sheet_name=args.sheet_name)
    release_result = build_company_release(
        records=import_result.records,
        source_file=args.input,
    )
    publish_company_release(
        release_result,
        company_records_path=company_output,
        released_objects_path=released_output,
    )
    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": str(args.input),
        "import_summary": asdict(import_result.report),
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
