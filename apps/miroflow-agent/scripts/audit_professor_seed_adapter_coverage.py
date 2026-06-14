from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Callable, Literal, Sequence, TextIO

from psycopg import Connection

from src.data_agents.professor.adapter_resolution import resolve_seed_adapter_name
from src.data_agents.professor.models import ProfessorRosterSeed
from src.data_agents.storage.postgres.connection import connect


CoverageState = Literal["resolver_covered", "approved_blocked", "missing"]


@dataclass(frozen=True, slots=True)
class SeedCoverageRow:
    seed_id: int
    school: str
    department: str | None
    seed_url: str
    last_run_status: str


@dataclass(frozen=True, slots=True)
class ApprovedBlockedIssue:
    issue_id: str
    failure_class: str
    stage: str
    description: str


@dataclass(frozen=True, slots=True)
class SeedCoverageResult:
    seed_id: int
    school: str
    department: str | None
    seed_url: str
    last_run_status: str
    resolver_result: str | None
    coverage_state: CoverageState
    diagnostic_status: str
    issue_id_or_reason: str


AdapterResolver = Callable[[ProfessorRosterSeed], str | None]

_HEADER = (
    "seed_id",
    "school",
    "department",
    "seed_url",
    "last_run_status",
    "resolver_result",
    "coverage_state",
    "diagnostic_status",
    "issue_id_or_reason",
)


def load_seed_rows(conn: Connection) -> list[SeedCoverageRow]:
    rows = conn.execute(
        """
        SELECT id AS seed_id,
               school,
               department,
               seed_url,
               last_run_status
          FROM professor_seed
         ORDER BY id
        """
    ).fetchall()
    return [_seed_row_from_record(row) for row in rows]


def load_approved_blocked_issues(conn: Connection) -> dict[int, ApprovedBlockedIssue]:
    rows = conn.execute(
        """
        SELECT DISTINCT ON ((evidence_snapshot->>'seed_id')::bigint)
               (evidence_snapshot->>'seed_id')::bigint AS seed_id,
               issue_id::text AS issue_id,
               stage,
               description,
               evidence_snapshot->>'failure_class' AS failure_class
          FROM pipeline_issue
         WHERE reported_by = 'professor_seed_runner'
           AND evidence_snapshot ? 'seed_id'
           AND evidence_snapshot->>'failure_class' = 'fetch_blocked'
         ORDER BY (evidence_snapshot->>'seed_id')::bigint, reported_at DESC
        """
    ).fetchall()
    return {
        int(_record_value(row, "seed_id", 0)): ApprovedBlockedIssue(
            issue_id=str(_record_value(row, "issue_id", 1)),
            stage=str(_record_value(row, "stage", 2)),
            description=str(_record_value(row, "description", 3)),
            failure_class=str(_record_value(row, "failure_class", 4)),
        )
        for row in rows
    }


def build_coverage_matrix(
    seed_rows: Sequence[SeedCoverageRow],
    *,
    adapter_resolver: AdapterResolver = resolve_seed_adapter_name,
    approved_blocked_by_seed_id: dict[int, ApprovedBlockedIssue] | None = None,
) -> list[SeedCoverageResult]:
    approved_blocked = approved_blocked_by_seed_id or {}
    results: list[SeedCoverageResult] = []
    for row in seed_rows:
        seed = ProfessorRosterSeed(
            institution=row.school,
            department=row.department,
            roster_url=row.seed_url,
        )
        resolver_result = adapter_resolver(seed)
        blocked_issue = approved_blocked.get(row.seed_id)
        if resolver_result:
            coverage_state: CoverageState = "resolver_covered"
            diagnostic_status = f"adapter:{resolver_result}"
            issue_id_or_reason = f"resolver:{resolver_result}"
        elif blocked_issue is not None:
            coverage_state = "approved_blocked"
            diagnostic_status = blocked_issue.failure_class
            issue_id_or_reason = blocked_issue.issue_id
        else:
            coverage_state = "missing"
            diagnostic_status = "adapter_missing"
            issue_id_or_reason = "missing_resolver"

        results.append(
            SeedCoverageResult(
                seed_id=row.seed_id,
                school=row.school,
                department=row.department,
                seed_url=row.seed_url,
                last_run_status=row.last_run_status,
                resolver_result=resolver_result,
                coverage_state=coverage_state,
                diagnostic_status=diagnostic_status,
                issue_id_or_reason=issue_id_or_reason,
            )
        )
    return results


def guard_exit_code(results: Sequence[SeedCoverageResult]) -> int:
    return 1 if any(row.coverage_state == "missing" for row in results) else 0


def format_matrix(results: Sequence[SeedCoverageResult]) -> list[str]:
    return ["\t".join(_HEADER)] + [
        "\t".join(
            [
                str(result.seed_id),
                result.school,
                result.department or "",
                result.seed_url,
                result.last_run_status,
                result.resolver_result or "",
                result.coverage_state,
                result.diagnostic_status,
                result.issue_id_or_reason,
            ]
        )
        for result in results
    ]


def print_matrix(results: Sequence[SeedCoverageResult], output: TextIO) -> None:
    for line in format_matrix(results):
        print(line, file=output)


def run(conn: Connection, *, output: TextIO = sys.stdout) -> int:
    seed_rows = load_seed_rows(conn)
    blocked_issues = load_approved_blocked_issues(conn)
    results = build_coverage_matrix(
        seed_rows,
        approved_blocked_by_seed_id=blocked_issues,
    )
    print_matrix(results, output)
    return guard_exit_code(results)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit row-level professor seed adapter coverage."
    )
    parser.add_argument(
        "--database-url",
        dest="database_url",
        default=None,
        help="Postgres DSN. Defaults to DATABASE_URL.",
    )
    args = parser.parse_args(argv)
    with connect(args.database_url) as conn:
        return run(conn)


def _seed_row_from_record(record) -> SeedCoverageRow:
    return SeedCoverageRow(
        seed_id=int(_record_value(record, "seed_id", 0)),
        school=str(_record_value(record, "school", 1)),
        department=_optional_str(_record_value(record, "department", 2)),
        seed_url=str(_record_value(record, "seed_url", 3)),
        last_run_status=str(_record_value(record, "last_run_status", 4)),
    )


def _record_value(record, key: str, index: int):
    if isinstance(record, dict):
        return record[key]
    return record[index]


def _optional_str(value) -> str | None:
    if value is None:
        return None
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
