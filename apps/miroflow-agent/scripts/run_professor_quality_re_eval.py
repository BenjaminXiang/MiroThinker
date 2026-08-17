"""Re-evaluate professor quality_status from persisted canonical state."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.professor.quality_gate import (  # noqa: E402
    evaluate_professor_quality,
    load_professor_canonical_state,
    persist_professor_quality_evaluation,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-evaluate professor quality_status from canonical state.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not persist writes.")
    parser.add_argument(
        "--professor-id",
        dest="professor_ids",
        action="append",
        default=[],
        help="Evaluate one professor id; may be repeated.",
    )
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args(argv)


def _open_database_connection(dsn: str):
    return psycopg.connect(dsn, row_factory=dict_row)


def _select_professor_rows(conn, *, professor_ids: list[str], limit: int | None):
    sql = "SELECT professor_id, quality_status FROM professor"
    params: list[Any] = []
    conditions: list[str] = []
    if professor_ids:
        placeholders = ", ".join(["%s"] * len(professor_ids))
        conditions.append(f"professor_id IN ({placeholders})")
        params.extend(professor_ids)
    if conditions:
        sql += f" WHERE {' AND '.join(conditions)}"
    sql += " ORDER BY professor_id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return conn.execute(sql, tuple(params)).fetchall()


def _row_get(row: object, key: str, index: int) -> object:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[index]  # type: ignore[index]
    except (IndexError, TypeError):
        return None


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        raise SystemExit(1)

    conn = _open_database_connection(dsn)
    rows = _select_professor_rows(
        conn,
        professor_ids=args.professor_ids,
        limit=args.limit,
    )
    before_distribution: Counter[str] = Counter()
    after_distribution: Counter[str] = Counter()
    issues_upserted = 0
    stale_issues_reconciled = 0
    evaluated_ids: list[str] = []

    try:
        for row in rows:
            professor_id = str(_row_get(row, "professor_id", 0))
            before_status = str(_row_get(row, "quality_status", 1) or "needs_review")
            before_distribution[before_status] += 1
            evaluated_ids.append(professor_id)

            state = load_professor_canonical_state(conn, professor_id)
            evaluation = evaluate_professor_quality(state)
            after_distribution[evaluation.quality_status] += 1

            if args.dry_run:
                continue

            persist_report = persist_professor_quality_evaluation(
                conn,
                professor_id=professor_id,
                evaluation=evaluation,
            )
            issues_upserted += int(persist_report.get("issues_upserted", 0))
            stale_issues_reconciled += int(
                persist_report.get("stale_issues_reconciled", 0)
            )

        if not args.dry_run:
            conn.commit()
    except Exception:
        if not args.dry_run:
            conn.rollback()
        raise
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()

    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                "selected_professor_ids": args.professor_ids,
                "professors_total": len(rows),
                "professor_ids": evaluated_ids,
                "before_distribution": dict(sorted(before_distribution.items())),
                "after_distribution": dict(sorted(after_distribution.items())),
                "issues_upserted": issues_upserted,
                "stale_issues_reconciled": stale_issues_reconciled,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
