"""Reassess ready professor rows against the profile_summary quality gate."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.professor.models import EnrichedProfessorProfile  # noqa: E402
from src.data_agents.professor.quality_gate import (  # noqa: E402
    CheckResult,
    _check_profile_summary_boilerplate,
    _check_profile_summary_length,
)

logger = logging.getLogger("run_quality_gate_reassess")
_REPORTED_BY = "w12_7_quality_gate_reassess"


@dataclass(frozen=True, slots=True)
class ReassessDecision:
    professor_id: str
    should_demote: bool
    failure_code: str | None
    failure_message: str | None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Demote ready professor rows with invalid profile_summary.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Max professors to scan"
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _build_select_sql(limit: int | None = None) -> tuple[str, tuple[Any, ...]]:
    sql = (
        "SELECT p.professor_id, p.canonical_name, p.profile_summary, "
        "       COALESCE(pa.institution, '') AS institution, "
        "       COALESCE(sp.url, '') AS profile_url "
        "  FROM professor p "
        "  LEFT JOIN LATERAL ("
        "       SELECT institution FROM professor_affiliation "
        "        WHERE professor_id = p.professor_id "
        "        ORDER BY is_primary DESC NULLS LAST, is_current DESC NULLS LAST "
        "        LIMIT 1"
        "  ) pa ON true "
        "  LEFT JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id "
        " WHERE p.quality_status = 'ready' "
        " ORDER BY p.professor_id"
    )
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _profile_from_row(row: dict[str, Any]) -> EnrichedProfessorProfile:
    profile_url = str(row.get("profile_url") or "https://unknown.invalid/profile")
    return EnrichedProfessorProfile(
        name=str(row.get("canonical_name") or ""),
        institution=str(row.get("institution") or "UNKNOWN_INSTITUTION"),
        profile_summary=str(row.get("profile_summary") or ""),
        evidence_urls=[profile_url],
        profile_url=profile_url,
        roster_source=profile_url,
        extraction_status="structured",
    )


def _first_summary_failure(profile: EnrichedProfessorProfile) -> CheckResult:
    text = (profile.profile_summary or "").strip()
    if not text:
        return CheckResult(
            passed=False,
            code="summary_missing",
            message="profile_summary missing",
        )
    length_result = _check_profile_summary_length(profile)
    if not length_result.passed:
        return length_result
    return _check_profile_summary_boilerplate(profile)


def _decide_reassess(row: dict[str, Any]) -> ReassessDecision:
    profile = _profile_from_row(row)
    result = _first_summary_failure(profile)
    return ReassessDecision(
        professor_id=str(row["professor_id"]),
        should_demote=not result.passed,
        failure_code=result.code,
        failure_message=result.message,
    )


def _demote_professor(conn: Any, *, professor_id: str) -> int:
    cursor = conn.execute(
        """
        UPDATE professor
           SET quality_status = 'partial',
               updated_at = now()
         WHERE professor_id = %s
           AND quality_status = 'ready'
        """,
        (professor_id,),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _file_pipeline_issue(
    conn: Any,
    *,
    row: dict[str, Any],
    decision: ReassessDecision,
) -> int:
    snapshot = {
        "professor_id": decision.professor_id,
        "canonical_name": row.get("canonical_name"),
        "failure_code": decision.failure_code,
        "failure_message": decision.failure_message,
        "profile_summary_length": len((row.get("profile_summary") or "").strip()),
    }
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, stage, severity, description, evidence_snapshot, reported_by
        )
        VALUES (%s, 'data_quality_flag', 'medium', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            decision.professor_id,
            f"[profile_summary_quality_gate] {decision.failure_code}: "
            f"{row.get('canonical_name') or decision.professor_id}",
            json.dumps(snapshot, ensure_ascii=False),
            _REPORTED_BY,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


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
    sql, params = _build_select_sql(args.limit)
    rows = conn.execute(sql, params).fetchall()
    report = {
        "profs_total": len(rows),
        "profs_reassessed": 0,
        "profs_demoted": 0,
        "pipeline_issues_inserted": 0,
        "dry_run": args.dry_run,
    }

    for row in rows:
        report["profs_reassessed"] += 1
        decision = _decide_reassess(dict(row))
        if not decision.should_demote:
            continue

        if not args.dry_run:
            try:
                report["profs_demoted"] += _demote_professor(
                    conn, professor_id=decision.professor_id
                )
                report["pipeline_issues_inserted"] += _file_pipeline_issue(
                    conn, row=dict(row), decision=decision
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to demote professor %s: %s", decision.professor_id, exc
                )
                conn.rollback()
                continue
        else:
            report["profs_demoted"] += 1

    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
