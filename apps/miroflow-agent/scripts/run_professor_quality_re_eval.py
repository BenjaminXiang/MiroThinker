"""Re-evaluate professor quality_status from canonical Postgres state."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
from typing import Any

import psycopg
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.professor.quality_gate import (  # noqa: E402
    evaluate_professor_quality,
    load_professor_canonical_states,
    persist_professor_quality_evaluation,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-evaluate professor quality_status from canonical state."
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres DSN. Defaults to DATABASE_URL, then DATABASE_URL_TEST.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes.")
    parser.add_argument(
        "--id",
        dest="professor_id",
        action="append",
        default=None,
        help="Professor id to re-evaluate. Can be repeated.",
    )
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args(argv)


def _open_database_connection(database_url: str | None):
    return psycopg.connect(_resolve_database_url(database_url), row_factory=dict_row)


def _resolve_database_url(database_url: str | None) -> str:
    if database_url:
        return resolve_dsn(database_url)
    return resolve_dsn(os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST"))


def run_re_eval(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_database_connection(args.database_url)
    try:
        before_distribution = _fetch_quality_distribution(conn)
        before_issue_counts = _fetch_quality_gate_issue_counts(conn)
        states = load_professor_canonical_states(conn, args.professor_id)
        if args.limit is not None:
            states = states[: int(args.limit)]

        evaluations = [evaluate_professor_quality(state) for state in states]
        after_counter = Counter(evaluation.quality_status for evaluation in evaluations)
        reason_counter = Counter(
            reason.rule_id
            for evaluation in evaluations
            for reason in evaluation.reasons
        )

        written = 0
        if not args.dry_run:
            for evaluation in evaluations:
                persist_professor_quality_evaluation(conn, evaluation)
                written += 1
            conn.commit()

        report = {
            "dry_run": bool(args.dry_run),
            "evaluated": len(evaluations),
            "written": written,
            "before_distribution": before_distribution,
            "after_distribution": dict(after_counter),
            "before_quality_gate_issue_counts": before_issue_counts,
            "after_quality_gate_issue_counts": (
                before_issue_counts
                if args.dry_run
                else _fetch_quality_gate_issue_counts(conn)
            ),
            "reason_counts": dict(reason_counter),
        }
        return report
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _fetch_quality_distribution(conn: Any) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT quality_status, count(*)::int AS n
          FROM professor
         GROUP BY quality_status
         ORDER BY quality_status
        """
    ).fetchall()
    return {str(_row_get(row, "quality_status", 0)): int(_row_get(row, "n", 1) or 0) for row in rows}


def _fetch_quality_gate_issue_counts(conn: Any) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT reported_by, stage, count(*)::int AS n
          FROM pipeline_issue
         WHERE reported_by = 'professor_quality_gate'
           AND resolved = false
         GROUP BY reported_by, stage
         ORDER BY reported_by, stage
        """
    ).fetchall()
    return {
        f"{_row_get(row, 'reported_by', 0)}:{_row_get(row, 'stage', 1)}": int(
            _row_get(row, "n", 2) or 0
        )
        for row in rows
    }


def _row_get(row: object, key: str, index: int) -> object:
    if isinstance(row, dict):
        return row.get(key)
    return row[index]  # type: ignore[index]


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    report = run_re_eval(args)
    print(json.dumps(report, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
