"""Promote high-confidence needs_review rows to ready under W13-D2 rules."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.quality.promotion_rules import (  # noqa: E402
    PipelineIssueCode,
    PromotionStatus,
    evaluate_company,
    evaluate_paper,
    evaluate_professor,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)

logger = logging.getLogger("run_quality_promote")
_REPORTED_BY = "w13_d2_quality_promote"
_RUN_KIND = "backfill_real"

DomainName = Literal["professor", "company", "paper"]
Evaluator = Callable[
    [Mapping[str, Any]], tuple[PromotionStatus, PipelineIssueCode | None]
]


@dataclass(frozen=True, slots=True)
class DomainConfig:
    name: DomainName
    table: str
    id_column: str
    select_columns: tuple[str, ...]
    evaluator: Evaluator


DOMAIN_CONFIGS: dict[DomainName, DomainConfig] = {
    "professor": DomainConfig(
        name="professor",
        table="professor",
        id_column="professor_id",
        select_columns=("professor_id", "profile_summary", "identity_status"),
        evaluator=evaluate_professor,
    ),
    "company": DomainConfig(
        name="company",
        table="company",
        id_column="company_id",
        select_columns=(
            "company_id",
            "profile_summary",
            "technology_route_summary",
        ),
        evaluator=evaluate_company,
    ),
    "paper": DomainConfig(
        name="paper",
        table="paper",
        id_column="paper_id",
        select_columns=("paper_id", "summary_zh", "abstract_clean", "identity_status"),
        evaluator=evaluate_paper,
    ),
}
DOMAIN_ORDER: tuple[DomainName, ...] = ("professor", "company", "paper")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote high-confidence quality_status rows to ready.",
    )
    parser.add_argument(
        "--domain",
        choices=("professor", "company", "paper", "all"),
        default="all",
        help="Domain to scan",
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--limit", type=int, default=None, help="Max rows per domain")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _selected_domains(domain: str) -> tuple[DomainName, ...]:
    if domain == "all":
        return DOMAIN_ORDER
    return (domain,)  # type: ignore[return-value]


def _build_select_sql(
    config: DomainConfig,
    limit: int | None,
    *,
    paper_identity_status_available: bool = True,
) -> tuple[str, tuple[Any, ...]]:
    select_columns = config.select_columns
    if config.name == "paper" and not paper_identity_status_available:
        select_columns = ("paper_id", "summary_zh", "abstract_clean")
    columns = ", ".join(select_columns)
    if config.name == "paper" and not paper_identity_status_available:
        columns += ", 'unverified'::text AS identity_status"
    sql = (
        f"SELECT {columns} "
        f"  FROM {config.table} "
        " WHERE quality_status = 'needs_review' "
        f" ORDER BY {config.id_column}"
    )
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _paper_has_identity_status_column(conn: Any) -> bool:
    row = conn.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'paper'
           AND column_name = 'identity_status'
         LIMIT 1
        """
    ).fetchone()
    return row is not None


def _empty_domain_report() -> dict[str, int]:
    return {
        "scanned": 0,
        "ready": 0,
        "needs_review": 0,
        "updated": 0,
        "pipeline_issues": 0,
        "pipeline_issues_inserted": 0,
        "failed": 0,
    }


def _update_quality_status(
    conn: Any,
    *,
    config: DomainConfig,
    record_id: Any,
    new_status: PromotionStatus,
    run_id: UUID | str,
) -> int:
    run_id = require_real_run_id(run_id, writer_name="_update_quality_status")
    cursor = conn.execute(
        f"""
        UPDATE {config.table}
           SET quality_status = %s,
               run_id = %s,
               updated_at = now()
         WHERE {config.id_column} = %s
           AND quality_status = 'needs_review'
        """,
        (new_status, run_id, record_id),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _file_pipeline_issue(
    conn: Any,
    *,
    config: DomainConfig,
    row: dict[str, Any],
    new_status: PromotionStatus,
    issue_code: PipelineIssueCode,
    run_id: UUID | str,
) -> int:
    run_id = require_real_run_id(run_id, writer_name="_file_pipeline_issue")
    record_id = row.get(config.id_column)
    snapshot = {
        "domain": config.name,
        "record_id": record_id,
        "issue_code": issue_code,
        "new_status": new_status,
        "run_id": str(run_id),
        "profile_summary_length": len(str(row.get("profile_summary") or "").strip()),
        "technology_route_summary_length": len(
            str(row.get("technology_route_summary") or "").strip()
        ),
        "summary_zh_length": len(str(row.get("summary_zh") or "").strip()),
        "abstract_clean_present": bool(str(row.get("abstract_clean") or "").strip()),
        "identity_status": row.get("identity_status"),
    }
    professor_id = record_id if config.name == "professor" else None
    institution = None if config.name == "professor" else f"{config.name}:{record_id}"
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, institution, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (%s, %s, 'data_quality_flag', 'medium', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            professor_id,
            institution,
            f"[quality_status_promotion] {issue_code}: {config.name}:{record_id}",
            json.dumps(snapshot, ensure_ascii=False, default=str),
            _REPORTED_BY,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _process_domain(
    conn: Any,
    *,
    config: DomainConfig,
    dry_run: bool,
    limit: int | None,
    run_id: UUID | str | None,
) -> dict[str, int]:
    paper_identity_status_available = True
    if config.name == "paper":
        paper_identity_status_available = _paper_has_identity_status_column(conn)
    sql, params = _build_select_sql(
        config,
        limit,
        paper_identity_status_available=paper_identity_status_available,
    )
    rows = conn.execute(sql, params).fetchall()
    report = _empty_domain_report()
    report["scanned"] = len(rows)

    for row in rows:
        row_dict = dict(row)
        new_status, issue_code = config.evaluator(row_dict)
        report[new_status] += 1

        if dry_run:
            if issue_code is not None:
                report["pipeline_issues"] += 1
            continue

        try:
            if new_status == "ready":
                if run_id is None:
                    raise ValueError("run_quality_promote requires run_id for writes")
                report["updated"] += _update_quality_status(
                    conn,
                    config=config,
                    record_id=row_dict.get(config.id_column),
                    new_status=new_status,
                    run_id=run_id,
                )
            if issue_code is not None:
                if run_id is None:
                    raise ValueError("run_quality_promote requires run_id for writes")
                inserted = _file_pipeline_issue(
                    conn,
                    config=config,
                    row=row_dict,
                    new_status=new_status,
                    issue_code=issue_code,
                    run_id=run_id,
                )
                report["pipeline_issues"] += 1
                report["pipeline_issues_inserted"] += inserted
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to process %s row %s: %s",
                config.name,
                row_dict.get(config.id_column),
                exc,
            )
            report["failed"] += 1
            conn.rollback()
            continue

    logger.info(
        "domain=%s scanned=%s ready=%s needs_review=%s issues=%s updated=%s dry_run=%s",
        config.name,
        report["scanned"],
        report["ready"],
        report["needs_review"],
        report["pipeline_issues"],
        report["updated"],
        dry_run,
    )
    return report


def _totals(domain_reports: dict[str, dict[str, int]]) -> dict[str, int]:
    totals = _empty_domain_report()
    for report in domain_reports.values():
        for key in totals:
            totals[key] += report[key]
    return totals


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

    domains = _selected_domains(args.domain)
    conn = _open_database_connection(dsn)
    run_id: UUID | str | None = None
    domain_reports: dict[str, dict[str, int]] = {}
    try:
        if not args.dry_run:
            run_id = open_pipeline_run(
                conn,
                run_kind=_RUN_KIND,
                run_scope={
                    "task": "w13_d2_quality_promote",
                    "domain": args.domain,
                    "domains": list(domains),
                    "limit": args.limit,
                    "dry_run": args.dry_run,
                },
                triggered_by=_REPORTED_BY,
            )
            run_id = require_real_run_id(run_id, writer_name="run_quality_promote")
            conn.commit()

        for domain in domains:
            config = DOMAIN_CONFIGS[domain]
            domain_reports[domain] = _process_domain(
                conn,
                config=config,
                dry_run=args.dry_run,
                limit=args.limit,
                run_id=run_id,
            )

        totals = _totals(domain_reports)
        if run_id is not None:
            close_pipeline_run(
                conn,
                run_id,
                status="partial" if totals["failed"] else "succeeded",
                items_processed=totals["scanned"],
                items_failed=totals["failed"],
            )
            conn.commit()
        print(
            json.dumps(
                {
                    "dry_run": args.dry_run,
                    "domain": args.domain,
                    "limit": args.limit,
                    "domains": domain_reports,
                    "totals": totals,
                },
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        if run_id is not None:
            conn.rollback()
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                error_summary={"message": str(exc)},
            )
            conn.commit()
        raise
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()
