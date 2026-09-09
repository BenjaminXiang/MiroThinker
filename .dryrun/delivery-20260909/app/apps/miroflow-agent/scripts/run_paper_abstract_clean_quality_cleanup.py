"""Clear unusable paper.abstract_clean values with pipeline evidence."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env")
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.paper.source_text_quality import (  # noqa: E402
    is_usable_paper_source_text,
)
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)

logger = logging.getLogger("run_paper_abstract_clean_quality_cleanup")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear non-abstract paper.abstract_clean values from active Papers.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--paper-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _load_rows(conn: Any, *, limit: int | None, paper_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    conditions = [
        "COALESCE(identity_status, 'unverified') NOT IN ('rejected', 'merged')",
        "COALESCE(quality_status, 'needs_enrichment') != 'rejected'",
        "NULLIF(BTRIM(COALESCE(abstract_clean, '')), '') IS NOT NULL",
    ]
    params: list[Any] = []
    if paper_ids:
        conditions.append("paper_id = ANY(%s)")
        params.append(list(paper_ids))
    sql = (
        "SELECT paper_id, title_clean, abstract_clean, summary_zh, quality_status, "
        "canonical_source "
        "FROM paper "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY paper_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def _process_rows(
    conn: Any,
    *,
    rows: list[dict[str, Any]],
    run_id: str,
    dry_run: bool,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "run_id": run_id,
        "rows_scanned": len(rows),
        "abstracts_cleared": 0,
        "ready_demoted": 0,
        "samples": [],
        "dry_run": dry_run,
    }
    for row in rows:
        abstract = row.get("abstract_clean")
        if is_usable_paper_source_text(abstract):
            continue
        paper_id = str(row["paper_id"])
        old_status = str(row.get("quality_status") or "needs_enrichment")
        next_status = "partial" if old_status == "ready" else old_status
        if not dry_run:
            conn.execute(
                """
                UPDATE paper
                   SET abstract_clean = NULL,
                       quality_status = %s,
                       updated_at = now(),
                       run_id = %s
                 WHERE paper_id = %s
                """,
                (next_status, run_id, paper_id),
            )
        report["abstracts_cleared"] += 1
        if next_status != old_status:
            report["ready_demoted"] += 1
        _append_sample(report, row=row, next_status=next_status)
    if not dry_run:
        conn.commit()
    return report


def _append_sample(report: dict[str, Any], *, row: dict[str, Any], next_status: str) -> None:
    samples = report["samples"]
    if len(samples) >= 20:
        return
    samples.append(
        {
            "paper_id": row.get("paper_id"),
            "title": str(row.get("title_clean") or "")[:160],
            "canonical_source": row.get("canonical_source"),
            "old_quality_status": row.get("quality_status"),
            "new_quality_status": next_status,
            "abstract_prefix": str(row.get("abstract_clean") or "")[:240],
            "has_summary_zh": bool(str(row.get("summary_zh") or "").strip()),
        }
    )


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print(
            "ERROR: DATABASE_URL not set. Run with DATABASE_URL=postgresql://...",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = _open_database_connection(dsn)
    if args.dry_run:
        run_id = f"dry-run-{uuid4()}"
    else:
        run_id = str(
            open_pipeline_run(
                conn,
                run_kind="backfill_real",
                run_scope={
                    "task": "paper_abstract_clean_quality_cleanup",
                    "limit": args.limit,
                    "paper_ids": args.paper_id,
                    "dry_run": args.dry_run,
                },
                triggered_by="run_paper_abstract_clean_quality_cleanup",
            )
        )
        conn.commit()

    started_at = time.monotonic()
    rows = _load_rows(conn, limit=args.limit, paper_ids=tuple(args.paper_id or ()))
    report = _process_rows(conn, rows=rows, run_id=run_id, dry_run=args.dry_run)
    report["duration_seconds"] = round(time.monotonic() - started_at, 2)
    if not args.dry_run:
        close_pipeline_run(
            conn,
            run_id,
            status="succeeded",
            items_processed=report["rows_scanned"],
            items_failed=0,
        )
        conn.commit()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
