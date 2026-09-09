#!/usr/bin/env python3
"""Close stale running pipeline_run rows with explicit filters."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Close stale running pipeline runs.")
    parser.add_argument("--older-than-minutes", type=int, default=60)
    parser.add_argument("--run-kind", default=None)
    parser.add_argument("--triggered-by", default=None)
    parser.add_argument(
        "--status",
        choices=("failed", "partial"),
        default="failed",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _build_stale_run_update_sql(
    *,
    older_than_minutes: int,
    run_kind: str | None,
    triggered_by: str | None,
    status: str,
    dry_run: bool,
) -> tuple[str, dict[str, Any]]:
    filters = [
        "status = 'running'",
        "started_at < now() - (%(older_than_minutes)s::text || ' minutes')::interval",
    ]
    params: dict[str, Any] = {
        "older_than_minutes": older_than_minutes,
        "run_kind": run_kind,
        "triggered_by": triggered_by,
        "status": status,
        "error_summary": Jsonb(
            {
                "reason": "stale_pipeline_run_cleanup",
                "older_than_minutes": older_than_minutes,
                "run_kind": run_kind,
                "triggered_by": triggered_by,
            }
        ),
    }
    if run_kind:
        filters.append("run_kind = %(run_kind)s")
    if triggered_by:
        filters.append("triggered_by = %(triggered_by)s")
    where_clause = " AND ".join(filters)
    if dry_run:
        return (
            f"""
            SELECT run_id, run_kind, triggered_by, status, started_at, run_scope
              FROM pipeline_run
             WHERE {where_clause}
             ORDER BY started_at
            """,
            params,
        )
    return (
        f"""
        UPDATE pipeline_run
           SET status = %(status)s,
               finished_at = now(),
               error_summary = COALESCE(error_summary, %(error_summary)s),
               items_failed = COALESCE(items_failed, 1)
         WHERE {where_clause}
         RETURNING run_id, run_kind, triggered_by, status, started_at, run_scope
        """,
        params,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1
    sql, params = _build_stale_run_update_sql(
        older_than_minutes=args.older_than_minutes,
        run_kind=args.run_kind,
        triggered_by=args.triggered_by,
        status=args.status,
        dry_run=args.dry_run,
    )
    with psycopg.connect(resolve_dsn(dsn), row_factory=dict_row) as conn:
        rows = conn.execute(sql, params).fetchall()
        if not args.dry_run:
            conn.commit()
    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                "rows_matched": len(rows),
                "rows": [dict(row) for row in rows],
            },
            default=str,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
