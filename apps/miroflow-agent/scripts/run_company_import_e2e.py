#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

# Ensure imports work when running this script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.company.import_xlsx import import_company_xlsx


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_input() -> Path:
    return _repo_root() / "docs" / "专辑项目导出1768807339.xlsx"


def _default_report_output() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _repo_root() / "logs" / "debug" / f"company_import_e2e_{timestamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run deterministic company xlsx import and write a structured JSON report."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=_default_input(),
        help="Path to company xlsx input file.",
    )
    parser.add_argument(
        "--sheet-name",
        type=str,
        default=None,
        help="Optional sheet name. Defaults to workbook active sheet.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_report_output(),
        help="Output JSON report path. Use '-' to print report JSON to stdout.",
    )
    parser.add_argument(
        "--preview-jsonl",
        type=Path,
        default=None,
        help="Optional output path for imported record preview JSONL.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "input": str(args.input),
            "error": f"input xlsx not found: {args.input}",
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1

    import_result = import_company_xlsx(args.input, sheet_name=args.sheet_name)
    preview_output = args.preview_jsonl
    if preview_output is not None:
        preview_output.parent.mkdir(parents=True, exist_ok=True)
        with preview_output.open("w", encoding="utf-8") as handle:
            for record in import_result.records:
                handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": str(args.input),
        "sheet_name": import_result.report.sheet_name,
        "summary": asdict(import_result.report),
        "outputs": {
            "preview_jsonl": str(preview_output) if preview_output else None,
        },
    }

    if str(args.output) == "-":
        print(json.dumps(report_payload, ensure_ascii=False, indent=2))
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
