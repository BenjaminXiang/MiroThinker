#!/usr/bin/env python3
"""Run the read-only Professor core profile and paper quality baseline audit."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Sequence, TextIO

import psycopg
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.professor.core_profile_paper_quality_audit import (  # noqa: E402
    CoreProfilePaperQualityAuditInputs,
    build_core_profile_paper_quality_report,
    evaluate_case_definitions,
    format_core_profile_paper_quality_report,
    load_baseline_paper_metrics,
    load_baseline_professor_metrics,
    load_case_definitions,
    load_dataset_closure_buckets,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402


_DEFAULT_CASES_PATH = (
    _APP_ROOT
    / "tests"
    / "data_agents"
    / "professor"
    / "fixtures"
    / "core_profile_paper_quality_cases.json"
)


def load_audit_inputs(
    conn,
    *,
    cases_path: str | Path | None = None,
) -> CoreProfilePaperQualityAuditInputs:
    case_definitions = load_case_definitions(cases_path or _DEFAULT_CASES_PATH)
    return CoreProfilePaperQualityAuditInputs(
        professor_metrics=load_baseline_professor_metrics(conn),
        paper_metrics=load_baseline_paper_metrics(conn),
        cases=evaluate_case_definitions(conn, case_definitions),
    )


def run(
    *,
    conn,
    output: TextIO = sys.stdout,
    cases_path: str | Path | None = None,
    include_buckets: bool = False,
    bucket_limit: int = 20,
) -> int:
    inputs = load_audit_inputs(conn, cases_path=cases_path)
    report = build_core_profile_paper_quality_report(
        professor_metrics=inputs.professor_metrics,
        paper_metrics=inputs.paper_metrics,
        cases=inputs.cases,
    )
    closure_buckets = (
        load_dataset_closure_buckets(
            conn,
            professor_metrics=inputs.professor_metrics,
            paper_metrics=inputs.paper_metrics,
            bucket_limit=bucket_limit,
        )
        if include_buckets
        else None
    )
    output.write(
        format_core_profile_paper_quality_report(
            report,
            closure_buckets=closure_buckets,
        )
    )
    return 0 if report.readiness == "ready" else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = args.database_url or os.environ.get("DATABASE_URL") or os.environ.get(
        "DATABASE_URL_TEST"
    )
    if not dsn:
        sys.stderr.write("DATABASE_URL or --database-url is required.\n")
        return 2
    with psycopg.connect(resolve_dsn(dsn), row_factory=dict_row) as conn:
        return run(
            conn=conn,
            cases_path=args.cases_path,
            include_buckets=args.include_buckets,
            bucket_limit=args.bucket_limit,
        )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a read-only Professor core profile and paper quality baseline "
            "audit. The command exits 1 when the baseline is blocked."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres DSN. Defaults to DATABASE_URL, then DATABASE_URL_TEST.",
    )
    parser.add_argument(
        "--cases-path",
        default=None,
        help="JSON case definitions. Defaults to the core profile-paper fixture.",
    )
    parser.add_argument(
        "--include-buckets",
        action="store_true",
        help="Include read-only dataset closure bucket samples in the JSON output.",
    )
    parser.add_argument(
        "--bucket-limit",
        type=int,
        default=20,
        help="Maximum rows per blocker class when --include-buckets is used.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
