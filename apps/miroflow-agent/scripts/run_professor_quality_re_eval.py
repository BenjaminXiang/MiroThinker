"""Re-evaluate professor quality_status from persisted canonical state."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.professor.quality_gate import (  # noqa: E402
    evaluate_professor_quality,
    load_professor_canonical_state,
    persist_professor_quality_evaluation,
)

logger = logging.getLogger("run_professor_quality_re_eval")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-evaluate professor.quality_status from canonical tables.",
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--limit", type=int, default=None, help="Max professors to scan")
    parser.add_argument(
        "--professor-id",
        action="append",
        default=[],
        help="Professor id to re-evaluate; repeatable",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_normalize_psycopg_dsn(url), row_factory=dict_row)


def _normalize_psycopg_dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _build_professor_select_sql(
    *,
    professor_ids: list[str],
    limit: int | None,
) -> tuple[str, tuple[object, ...]]:
    sql = "SELECT professor_id, quality_status FROM professor"
    params: list[object] = []
    if professor_ids:
        sql += " WHERE professor_id = ANY(%s)"
        params.append(professor_ids)
    sql += " ORDER BY professor_id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _fetch_quality_distribution(conn) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT quality_status, count(*)::int AS count
        FROM professor
        GROUP BY quality_status
        ORDER BY quality_status
        """
    ).fetchall()
    return {
        str(_row_value(row, "quality_status", 0)): int(_row_value(row, "count", 1))
        for row in rows
    }


def _fetch_open_issue_counts(conn) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT reported_by, stage, count(*)::int AS count
        FROM pipeline_issue
        WHERE resolved = false
        GROUP BY reported_by, stage
        ORDER BY reported_by, stage
        """
    ).fetchall()
    return {
        f"{_row_value(row, 'reported_by', 0)}:{_row_value(row, 'stage', 1)}": int(
            _row_value(row, "count", 2)
        )
        for row in rows
    }


def _fetch_professor_rows(
    conn,
    *,
    professor_ids: list[str],
    limit: int | None,
) -> list[Any]:
    sql, params = _build_professor_select_sql(
        professor_ids=professor_ids,
        limit=limit,
    )
    return list(conn.execute(sql, params).fetchall())


def run_re_eval(conn, args: argparse.Namespace) -> dict[str, Any]:
    before_distribution = _fetch_quality_distribution(conn)
    before_issue_counts = _fetch_open_issue_counts(conn)
    rows = _fetch_professor_rows(
        conn,
        professor_ids=list(args.professor_id or []),
        limit=args.limit,
    )

    projected_distribution = Counter(before_distribution)
    statuses_changed = 0
    issues_inserted = 0
    issues_resolved = 0
    evaluated_statuses: Counter[str] = Counter()

    for row in rows:
        professor_id = str(_row_value(row, "professor_id", 0))
        old_status = str(_row_value(row, "quality_status", 1))
        state = load_professor_canonical_state(conn, professor_id)
        evaluation = evaluate_professor_quality(state)
        new_status = str(evaluation.quality_status)
        evaluated_statuses[new_status] += 1
        if old_status != new_status:
            statuses_changed += 1
            projected_distribution[old_status] -= 1
            projected_distribution[new_status] += 1
        if not args.dry_run:
            report = persist_professor_quality_evaluation(
                conn,
                professor_id=professor_id,
                evaluation=evaluation,
            )
            issues_inserted += report.issues_inserted
            issues_resolved += report.issues_resolved

    if args.dry_run:
        after_distribution = dict(projected_distribution)
        after_issue_counts = before_issue_counts
    else:
        conn.commit()
        after_distribution = _fetch_quality_distribution(conn)
        after_issue_counts = _fetch_open_issue_counts(conn)

    return {
        "dry_run": bool(args.dry_run),
        "professors_scanned": len(rows),
        "statuses_changed": statuses_changed,
        "issues_inserted": issues_inserted,
        "issues_resolved": issues_resolved,
        "evaluated_statuses": dict(sorted(evaluated_statuses.items())),
        "before_distribution": before_distribution,
        "after_distribution": dict(sorted(after_distribution.items())),
        "before_open_issue_counts": before_issue_counts,
        "after_open_issue_counts": after_issue_counts,
    }


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print(
            "ERROR: DATABASE_URL or DATABASE_URL_TEST must be set.",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = _open_database_connection(dsn)
    try:
        report = run_re_eval(conn, args)
    except Exception:
        if not args.dry_run:
            conn.rollback()
        raise
    finally:
        conn.close()

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


def _row_value(row, key: str, index: int):
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError):
        return row[index]


if __name__ == "__main__":
    main()
