#!/usr/bin/env python3
"""Clean upload-scoped Company enrichment validation batch state safely."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402


PROTECTED_TABLES_NOT_TOUCHED = [
    "company",
    "company_snapshot",
    "company_news_item",
    "company_signal_event",
    "company_product",
    "company_product_evidence",
    "company_application_scenario",
    "company_application_scenario_evidence",
    "milvus_company_profiles",
]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reset Company enrichment validation batch state and search-audit "
            "markers without deleting production Company facts."
        ),
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _commit_if_supported(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def cleanup_company_validation_batch(
    conn: Any,
    *,
    batch_id: UUID | str,
    apply: bool = False,
) -> dict[str, Any]:
    affected = _validation_cleanup_counts(conn, batch_id=batch_id)
    if apply:
        conn.execute(
            """
            DELETE FROM company_enrichment_search_audit
             WHERE batch_id = %(batch_id)s
            """,
            {"batch_id": batch_id},
        )
        conn.execute(
            """
            UPDATE company_enrichment_company_state
               SET status = 'queued',
                   current_stage = 'queued',
                   stage_status = '{}'::jsonb,
                   attempts = 0,
                   query_count = 0,
                   source_result_count = 0,
                   accepted_source_count = 0,
                   rejected_source_count = 0,
                   event_count = 0,
                   product_count = 0,
                   scenario_count = 0,
                   official_product_count = 0,
                   milvus_refreshed_at = NULL,
                   miss_reason = NULL,
                   last_error = NULL,
                   started_at = NULL,
                   finished_at = NULL,
                   updated_at = now()
             WHERE batch_id = %(batch_id)s
            """,
            {"batch_id": batch_id},
        )
        conn.execute(
            """
            UPDATE company_enrichment_batch
               SET status = 'queued',
                   current_stage = 'queued',
                   companies_processed = 0,
                   companies_succeeded = 0,
                   companies_failed = 0,
                   last_error = NULL,
                   started_at = NULL,
                   finished_at = NULL,
                   updated_at = now()
             WHERE batch_id = %(batch_id)s
            """,
            {"batch_id": batch_id},
        )
        _commit_if_supported(conn)
    return {
        "batch_id": str(batch_id),
        "dry_run": not apply,
        "affected": affected,
        "protected_tables_not_touched": list(PROTECTED_TABLES_NOT_TOUCHED),
    }


def _validation_cleanup_counts(
    conn: Any,
    *,
    batch_id: UUID | str,
) -> dict[str, int]:
    return {
        "company_enrichment_search_audit": _count_rows(
            conn,
            """
            SELECT count(*)::int AS affected
              FROM company_enrichment_search_audit
             WHERE batch_id = %(batch_id)s
            """,
            {"batch_id": batch_id},
        ),
        "company_enrichment_company_state": _count_rows(
            conn,
            """
            SELECT count(*)::int AS affected
              FROM company_enrichment_company_state
             WHERE batch_id = %(batch_id)s
            """,
            {"batch_id": batch_id},
        ),
        "company_enrichment_batch": _count_rows(
            conn,
            """
            SELECT count(*)::int AS affected
              FROM company_enrichment_batch
             WHERE batch_id = %(batch_id)s
            """,
            {"batch_id": batch_id},
        ),
    }


def _count_rows(conn: Any, sql: str, params: dict[str, Any]) -> int:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(row.get("affected") or 0)
    return int(row[0] or 0)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1
    conn = _open_database_connection(dsn)
    try:
        report = cleanup_company_validation_batch(
            conn,
            batch_id=UUID(args.batch_id),
            apply=args.apply,
        )
    finally:
        conn.close()
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
