#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

# Ensure imports work when running this script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.patent.import_xlsx import import_patent_xlsx
from src.data_agents.patent.models import PatentImportRecord


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_input_path() -> Path:
    return _repo_root() / "docs" / "2025-12-05 专利.xlsx"


def _default_output_path() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _repo_root() / "logs" / "debug" / f"patent_import_e2e_{timestamp}.json"


def _record_preview(record: PatentImportRecord) -> dict[str, Any]:
    return {
        "source_row": record.source_row,
        "sequence_number": record.sequence_number,
        "title": record.title,
        "applicants": list(record.applicants),
        "patent_number": record.patent_number,
        "publication_date": _date_to_iso(record.publication_date),
        "filing_date": _date_to_iso(record.filing_date),
        "patent_type": record.patent_type,
    }


def _date_to_iso(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run patent xlsx import e2e and emit a structured JSON report.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=_default_input_path(),
        help="Path to patent xlsx export.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_output_path(),
        help="Path to JSON report output. Use '-' to print report JSON to stdout.",
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

    result = import_patent_xlsx(args.input)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": str(args.input),
        "summary": asdict(result.report),
        "preview": [_record_preview(record) for record in result.records[:3]],
    }

    if str(args.output) == "-":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
