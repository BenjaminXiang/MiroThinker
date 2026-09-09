from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Callable, Literal, Sequence, TextIO

from psycopg import Connection

from .adapter_resolution import resolve_seed_adapter_name
from .models import ProfessorRosterSeed
from ..storage.postgres.connection import connect


CoverageState = Literal["resolver_covered", "approved_blocked", "missing"]
RecommendedMode = Literal["blocked", "preview", "sample", "full"]


@dataclass(frozen=True, slots=True)
class SeedReadinessInput:
    seed_id: int
    school: str
    department: str | None
    seed_url: str
    last_run_status: str
    resolver_result: str | None
    coverage_state: CoverageState
    latest_run_id: str | None
    latest_run_status: str | None
    latest_trigger_mode: str | None
    latest_failure_class: str | None
    diagnostic_profile_count: int | None
    written_profile_count: int | None
    latest_issue_id: str | None
    latest_issue_failure_class: str | None


@dataclass(frozen=True, slots=True)
class SeedReadinessResult:
    seed_id: int
    school: str
    department: str | None
    seed_url: str
    last_run_status: str
    resolver_result: str | None
    coverage_state: CoverageState
    latest_run_id: str | None
    latest_run_status: str | None
    latest_trigger_mode: str | None
    latest_failure_class: str | None
    latest_issue_id: str | None
    recommended_next_mode: RecommendedMode
    full_recollection_allowed: bool
    decision_reason: str
    evidence_reference: str


AdapterResolver = Callable[[ProfessorRosterSeed], str | None]

_HEADER = (
    "seed_id",
    "school",
    "department",
    "seed_url",
    "last_run_status",
    "resolver_result",
    "coverage_state",
    "latest_run_id",
    "latest_run_status",
    "latest_trigger_mode",
    "latest_failure_class",
    "latest_issue_id",
    "recommended_next_mode",
    "full_recollection_allowed",
    "decision_reason",
    "evidence_reference",
)


def load_readiness_inputs(
    conn: Connection,
    *,
    adapter_resolver: AdapterResolver = resolve_seed_adapter_name,
) -> list[SeedReadinessInput]:
    rows = conn.execute(
        """
        WITH seed_rows AS (
          SELECT id, school, department, seed_url, last_run_status
            FROM professor_seed
           ORDER BY id
        ), run_rows AS (
          SELECT CASE
                   WHEN run_scope->>'seed_id' ~ '^\\d+$'
                   THEN (run_scope->>'seed_id')::bigint
                 END AS seed_id,
                 run_id,
                 status,
                 run_scope,
                 started_at
            FROM pipeline_run
           WHERE run_scope ? 'seed_id'
             AND run_kind = 'roster_crawl'
             AND COALESCE(run_scope->>'trigger_mode', '') IN ('preview', 'sample', 'full')
        ), latest_run AS (
          SELECT DISTINCT ON (seed_id)
                 seed_id,
                 run_id::text AS run_id,
                 status,
                 run_scope->>'trigger_mode' AS trigger_mode,
                 run_scope->>'failure_class' AS failure_class,
                 run_scope->>'diagnostic_profile_count' AS diagnostic_profile_count,
                 run_scope->>'written_profile_count' AS written_profile_count,
                 started_at
            FROM run_rows
           WHERE seed_id IS NOT NULL
           ORDER BY seed_id, started_at DESC
        ), issue_rows AS (
          SELECT CASE
                   WHEN evidence_snapshot->>'seed_id' ~ '^\\d+$'
                   THEN (evidence_snapshot->>'seed_id')::bigint
                 END AS seed_id,
                 issue_id,
                 evidence_snapshot,
                 reported_at
            FROM pipeline_issue
           WHERE reported_by = 'professor_seed_runner'
             AND evidence_snapshot ? 'seed_id'
        ), latest_issue AS (
          SELECT DISTINCT ON (seed_id)
                 seed_id,
                 issue_id::text AS issue_id,
                 evidence_snapshot->>'failure_class' AS failure_class,
                 reported_at
            FROM issue_rows
           WHERE seed_id IS NOT NULL
           ORDER BY seed_id, reported_at DESC
        )
        SELECT s.id,
               s.school,
               s.department,
               s.seed_url,
               s.last_run_status,
               lr.run_id,
               lr.status AS latest_run_status,
               lr.trigger_mode,
               lr.failure_class AS latest_failure_class,
               lr.diagnostic_profile_count,
               lr.written_profile_count,
               li.issue_id,
               li.failure_class AS latest_issue_failure_class
          FROM seed_rows s
          LEFT JOIN latest_run lr ON lr.seed_id = s.id
          LEFT JOIN latest_issue li ON li.seed_id = s.id
         ORDER BY s.id
        """
    ).fetchall()
    inputs: list[SeedReadinessInput] = []
    for row in rows:
        seed_id = int(_record_value(row, "id", 0))
        school = str(_record_value(row, "school", 1))
        department = _optional_str(_record_value(row, "department", 2))
        seed_url = str(_record_value(row, "seed_url", 3))
        resolver_result = adapter_resolver(
            ProfessorRosterSeed(
                institution=school,
                department=department,
                roster_url=seed_url,
            )
        )
        latest_issue_failure_class = _optional_str(
            _record_value(row, "latest_issue_failure_class", 12)
        )
        inputs.append(
            SeedReadinessInput(
                seed_id=seed_id,
                school=school,
                department=department,
                seed_url=seed_url,
                last_run_status=str(_record_value(row, "last_run_status", 4)),
                resolver_result=resolver_result,
                coverage_state=_coverage_state(
                    resolver_result,
                    latest_issue_failure_class,
                ),
                latest_run_id=_optional_str(_record_value(row, "run_id", 5)),
                latest_run_status=_optional_str(
                    _record_value(row, "latest_run_status", 6)
                ),
                latest_trigger_mode=_optional_str(_record_value(row, "trigger_mode", 7)),
                latest_failure_class=_optional_str(
                    _record_value(row, "latest_failure_class", 8)
                ),
                diagnostic_profile_count=_optional_int(
                    _record_value(row, "diagnostic_profile_count", 9)
                ),
                written_profile_count=_optional_int(
                    _record_value(row, "written_profile_count", 10)
                ),
                latest_issue_id=_optional_str(_record_value(row, "issue_id", 11)),
                latest_issue_failure_class=latest_issue_failure_class,
            )
        )
    return inputs


def build_readiness_matrix(
    rows: Sequence[SeedReadinessInput],
) -> list[SeedReadinessResult]:
    return [_build_readiness_row(row) for row in rows]


def assert_complete_matrix(
    observed_seed_ids: Sequence[int],
    matrix: Sequence[SeedReadinessResult],
) -> None:
    expected = {int(seed_id) for seed_id in observed_seed_ids}
    actual = {row.seed_id for row in matrix}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing readiness rows: " + ", ".join(map(str, missing)))
        if extra:
            parts.append("unexpected readiness rows: " + ", ".join(map(str, extra)))
        raise ValueError("; ".join(parts))


def format_readiness_matrix(results: Sequence[SeedReadinessResult]) -> list[str]:
    return ["\t".join(_HEADER)] + [
        "\t".join(
            [
                str(row.seed_id),
                row.school,
                row.department or "",
                row.seed_url,
                row.last_run_status,
                row.resolver_result or "",
                row.coverage_state,
                row.latest_run_id or "",
                row.latest_run_status or "",
                row.latest_trigger_mode or "",
                row.latest_failure_class or "",
                row.latest_issue_id or "",
                row.recommended_next_mode,
                str(row.full_recollection_allowed),
                row.decision_reason,
                row.evidence_reference,
            ]
        )
        for row in results
    ]


def print_readiness_matrix(
    results: Sequence[SeedReadinessResult],
    output: TextIO = sys.stdout,
) -> None:
    for line in format_readiness_matrix(results):
        print(line, file=output)


def run(conn: Connection, *, output: TextIO = sys.stdout) -> int:
    inputs = load_readiness_inputs(conn)
    matrix = build_readiness_matrix(inputs)
    assert_complete_matrix([row.seed_id for row in inputs], matrix)
    print_readiness_matrix(matrix, output=output)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan Professor seed recollection readiness."
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


def _build_readiness_row(row: SeedReadinessInput) -> SeedReadinessResult:
    recommendation, allowed, reason, evidence = _recommend(row)
    return SeedReadinessResult(
        seed_id=row.seed_id,
        school=row.school,
        department=row.department,
        seed_url=row.seed_url,
        last_run_status=row.last_run_status,
        resolver_result=row.resolver_result,
        coverage_state=row.coverage_state,
        latest_run_id=row.latest_run_id,
        latest_run_status=row.latest_run_status,
        latest_trigger_mode=row.latest_trigger_mode,
        latest_failure_class=row.latest_failure_class,
        latest_issue_id=row.latest_issue_id,
        recommended_next_mode=recommendation,
        full_recollection_allowed=allowed,
        decision_reason=reason,
        evidence_reference=evidence,
    )


def _recommend(
    row: SeedReadinessInput,
) -> tuple[RecommendedMode, bool, str, str]:
    if row.latest_failure_class == "fetch_blocked":
        return (
            "blocked",
            False,
            "latest_run_fetch_blocked",
            _issue_or_run_reference(row),
        )
    if row.coverage_state == "approved_blocked":
        return (
            "blocked",
            False,
            "approved_blocked_without_successful_replacement",
            _issue_or_run_reference(row),
        )
    if row.coverage_state == "missing" or row.resolver_result is None:
        return (
            "blocked",
            False,
            "missing_resolver_or_unapproved_blocker",
            _issue_or_run_reference(row),
        )
    if (
        row.latest_trigger_mode == "full"
        and row.latest_run_status == "succeeded"
        and row.latest_failure_class == "success"
        and (row.written_profile_count or 0) > 0
    ):
        return ("full", False, "latest_full_success_complete", _run_reference(row))
    if (
        row.latest_trigger_mode == "sample"
        and row.latest_run_status == "succeeded"
        and row.latest_failure_class == "success"
        and (row.written_profile_count or 0) > 0
    ):
        return ("full", True, "latest_sample_success_allows_full", _run_reference(row))
    if (
        row.latest_trigger_mode == "preview"
        and row.latest_run_status == "succeeded"
        and row.latest_failure_class == "success"
        and (row.diagnostic_profile_count or 0) > 0
    ):
        return (
            "sample",
            False,
            "latest_preview_success_requires_sample",
            _run_reference(row),
        )
    return ("preview", False, "resolver_covered_needs_preview", _run_reference(row))


def _coverage_state(
    resolver_result: str | None,
    latest_issue_failure_class: str | None,
) -> CoverageState:
    if resolver_result:
        return "resolver_covered"
    if latest_issue_failure_class == "fetch_blocked":
        return "approved_blocked"
    return "missing"


def _issue_or_run_reference(row: SeedReadinessInput) -> str:
    if row.latest_issue_id:
        return f"issue:{row.latest_issue_id}"
    return _run_reference(row)


def _run_reference(row: SeedReadinessInput) -> str:
    if row.latest_run_id:
        return f"run:{row.latest_run_id}"
    if row.resolver_result:
        return f"resolver:{row.resolver_result}"
    return f"seed:{row.seed_id}"


def _record_value(record, key: str, index: int):
    if isinstance(record, dict):
        return record[key]
    return record[index]


def _optional_str(value) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
