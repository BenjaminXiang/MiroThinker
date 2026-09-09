"""Read-only Paper source-gap lane audit."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env")
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.paper.source_gap_audit import (  # noqa: E402
    build_source_gap_audit_report,
    load_source_gap_rows,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify active Paper source gaps into remediation lanes.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres URL. Defaults to DATABASE_URL from the environment.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row limit for bounded read-only audits.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=20,
        help="Maximum sampled paper_ids per lane in the report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path. Defaults to stdout.",
    )
    parser.add_argument(
        "--include-rows",
        action="store_true",
        help="Include row-level classifications. Default report is compact.",
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.sample_limit < 0:
        parser.error("--sample-limit must be non-negative")
    return args


def _open_database_connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _database_url_label(args: argparse.Namespace) -> str:
    if args.database_url:
        return "arg:database-url"
    return "env:DATABASE_URL"


def build_payload(
    rows: list[dict[str, Any]],
    *,
    sample_limit: int,
    database_url_label: str,
    include_rows: bool = False,
) -> dict[str, Any]:
    report = build_source_gap_audit_report(rows, sample_limit=sample_limit)
    payload = asdict(report)
    if not include_rows:
        payload.pop("rows", None)
    payload["artifact_type"] = "paper_source_gap_audit"
    payload["database_url_label"] = database_url_label
    payload["generated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    payload["read_only"] = True
    return payload


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("ERROR: DATABASE_URL not set. Run with DATABASE_URL=postgresql://...")

    conn = _open_database_connection(database_url)
    try:
        rows = load_source_gap_rows(conn, limit=args.limit)
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()

    payload = build_payload(
        rows,
        sample_limit=args.sample_limit,
        database_url_label=_database_url_label(args),
        include_rows=args.include_rows,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
