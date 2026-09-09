#!/usr/bin/env python3
"""Report run_id coverage for canonical Postgres write-target tables."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402

LEGACY_BACKFILL_RUN_ID = "00000000-0000-0000-0000-000000000001"
DRY_RUN_SENTINEL_RUN_ID = "00000000-0000-0000-0000-000000000000"

CANONICAL_TABLES = (
    "company",
    "professor",
    "professor_affiliation",
    "professor_fact",
    "professor_paper_link",
    "paper",
    "paper_full_text",
    "patent",
    "source_page",
)


@dataclass(frozen=True)
class TableCoverage:
    table_name: str
    has_run_id_column: bool
    total_rows: int | None = None
    legacy_backfill_rows: int | None = None
    real_run_id_rows: int | None = None
    null_run_id_rows: int | None = None
    sentinel_run_id_rows: int | None = None


def _has_run_id_column(conn, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = %s
           AND column_name = 'run_id'
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_schema = current_schema()
           AND table_name = %s
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _coverage_for_table(conn, table_name: str) -> TableCoverage:
    if not _table_exists(conn, table_name):
        return TableCoverage(table_name=table_name, has_run_id_column=False)
    if not _has_run_id_column(conn, table_name):
        total = conn.execute(f"SELECT count(*) AS total FROM {table_name}").fetchone()
        return TableCoverage(
            table_name=table_name,
            has_run_id_column=False,
            total_rows=int(total["total"]) if total else 0,
        )
    row = conn.execute(
        f"""
        SELECT count(*)::bigint AS total_rows,
               count(*) FILTER (
                   WHERE run_id::text = %s
               )::bigint AS legacy_backfill_rows,
               count(*) FILTER (
                   WHERE run_id IS NOT NULL
                     AND run_id::text <> %s
                     AND run_id::text <> %s
               )::bigint AS real_run_id_rows,
               count(*) FILTER (
                   WHERE run_id IS NULL
               )::bigint AS null_run_id_rows,
               count(*) FILTER (
                   WHERE run_id::text = %s
               )::bigint AS sentinel_run_id_rows
          FROM {table_name}
        """,
        (
            LEGACY_BACKFILL_RUN_ID,
            LEGACY_BACKFILL_RUN_ID,
            DRY_RUN_SENTINEL_RUN_ID,
            DRY_RUN_SENTINEL_RUN_ID,
        ),
    ).fetchone()
    assert row is not None
    return TableCoverage(
        table_name=table_name,
        has_run_id_column=True,
        total_rows=int(row["total_rows"]),
        legacy_backfill_rows=int(row["legacy_backfill_rows"]),
        real_run_id_rows=int(row["real_run_id_rows"]),
        null_run_id_rows=int(row["null_run_id_rows"]),
        sentinel_run_id_rows=int(row["sentinel_run_id_rows"]),
    )


def collect_coverage(database_url: str | None = None) -> list[TableCoverage]:
    dsn = resolve_dsn(database_url or os.environ.get("DATABASE_URL"))
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        return [_coverage_for_table(conn, table) for table in CANONICAL_TABLES]


def _render_text(rows: list[TableCoverage]) -> str:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        f"run_id coverage generated_at={generated_at}",
        f"legacy_backfill_run_id={LEGACY_BACKFILL_RUN_ID}",
        f"dry_run_sentinel_run_id={DRY_RUN_SENTINEL_RUN_ID}",
        "",
        "table,total,legacy_backfill,real_run_id,null_run_id,sentinel_run_id,has_run_id_column",
    ]
    for row in rows:
        lines.append(
            ",".join(
                [
                    row.table_name,
                    _csv_value(row.total_rows),
                    _csv_value(row.legacy_backfill_rows),
                    _csv_value(row.real_run_id_rows),
                    _csv_value(row.null_run_id_rows),
                    _csv_value(row.sentinel_run_id_rows),
                    str(row.has_run_id_column).lower(),
                ]
            )
        )
    lines.append("")
    lines.append("json=" + json.dumps([asdict(row) for row in rows], ensure_ascii=False))
    return "\n".join(lines)


def _csv_value(value: Any) -> str:
    return "" if value is None else str(value)


def main() -> int:
    rows = collect_coverage()
    print(_render_text(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
