"""Backfill professor academic metrics into canonical Postgres.

For each resolved professor, use professor_orcid as the OpenAlex lookup key,
write h_index/citation_count when OpenAlex matches, and always recompute
paper_count through canonical_writer.upsert_professor_metrics.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.professor.canonical_writer import (  # noqa: E402
    upsert_professor_metrics,
)
from src.data_agents.professor.openalex_metrics import fetch_metrics  # noqa: E402
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402

_LOG_DIR = _REPO_ROOT / "docs" / "source_backfills"
_BATCH_SIZE = 50
_REPORTED_BY = "professor_metrics_backfill"


@dataclass
class BackfillStats:
    profs_total: int = 0
    profs_processed: int = 0
    profs_successful: int = 0
    openalex: int = 0
    verified_link_only: int = 0
    fetch_failed: int = 0
    pipeline_issues_inserted: int = 0
    dry_run: bool = False


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill professor h_index/citation_count/paper_count."
    )
    parser.add_argument("--database-url", help="Postgres DSN. Defaults to DATABASE_URL.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Only process resolved professors whose metrics_computed_at is NULL.",
    )
    return parser.parse_args(argv)


def _open_database_connection(database_url: str | None):
    return psycopg.connect(resolve_dsn(database_url), row_factory=dict_row)


def _build_select_sql(*, limit: int | None, resume: bool) -> tuple[str, tuple[Any, ...]]:
    clauses = ["p.identity_status = 'resolved'"]
    if resume:
        clauses.append("p.metrics_computed_at IS NULL")
    sql = f"""
        SELECT p.professor_id::text AS professor_id,
               p.canonical_name,
               p.institution,
               o.orcid
          FROM professor p
          LEFT JOIN professor_orcid o
            ON o.professor_id = p.professor_id
         WHERE {' AND '.join(clauses)}
         ORDER BY p.professor_id
    """
    params: list[Any] = []
    if limit is not None:
        sql += "\n         LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _fetch_professors(conn, *, limit: int | None, resume: bool) -> list[dict[str, Any]]:
    sql, params = _build_select_sql(limit=limit, resume=resume)
    return conn.execute(sql, params).fetchall()


def _metrics_source(metrics: Any, *, has_orcid: bool) -> tuple[str, int | None, int | None]:
    has_openalex_values = (
        has_orcid
        and getattr(metrics, "source", None) == "openalex"
        and (
            getattr(metrics, "h_index", None) is not None
            or getattr(metrics, "citation_count", None) is not None
        )
    )
    if has_openalex_values:
        return (
            "openalex",
            getattr(metrics, "h_index", None),
            getattr(metrics, "citation_count", None),
        )
    return "verified_link_only", None, None


def _log_path() -> Path:
    today = datetime.now(timezone.utc).date().isoformat()
    return _LOG_DIR / f"professor-metrics-backfill-{today}.jsonl"


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _file_pipeline_issue(
    conn,
    *,
    professor_id: str,
    institution: str | None,
    run_id: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> int:
    evidence_snapshot = json.dumps(
        {
            "run_id": run_id,
            "issue_type": "metrics_fetch_failed",
            "message": message,
            "details": details or {},
        },
        ensure_ascii=False,
        default=str,
    )
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id,
            institution,
            stage,
            severity,
            description,
            evidence_snapshot,
            reported_by
        )
        VALUES (%s, %s, 'data_quality_flag', 'medium', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            professor_id,
            institution,
            f"[metrics_fetch_failed] {message}",
            evidence_snapshot,
            _REPORTED_BY,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _process_professor(
    conn,
    row: dict[str, Any],
    *,
    run_id: str,
    dry_run: bool,
    log_path: Path,
) -> tuple[bool, str | None, int]:
    professor_id = str(row["professor_id"])
    orcid = (row.get("orcid") or "").strip() or None
    institution = row.get("institution")
    metrics = None
    if orcid:
        try:
            metrics = fetch_metrics(orcid=orcid)
        except Exception as exc:  # noqa: BLE001
            message = f"OpenAlex metrics fetch failed for professor {professor_id}: {exc}"
            issues_inserted = 0
            if not dry_run:
                issues_inserted = _file_pipeline_issue(
                    conn,
                    professor_id=professor_id,
                    institution=institution,
                    run_id=run_id,
                    message=message,
                    details={"orcid": orcid, "error": str(exc)},
                )
            _append_jsonl(
                log_path,
                {
                    "run_id": run_id,
                    "professor_id": professor_id,
                    "canonical_name": row.get("canonical_name"),
                    "orcid": orcid,
                    "status": "fetch_failed",
                    "error": str(exc),
                    "pipeline_issues_inserted": issues_inserted,
                    "dry_run": dry_run,
                },
            )
            return False, None, issues_inserted

    source, h_index, citation_count = (
        _metrics_source(metrics, has_orcid=orcid is not None)
        if metrics is not None
        else ("verified_link_only", None, None)
    )
    if not dry_run:
        upsert_professor_metrics(
            conn,
            professor_id=professor_id,
            h_index=h_index,
            citation_count=citation_count,
            metrics_source=source,
            run_id=run_id,
        )
    _append_jsonl(
        log_path,
        {
            "run_id": run_id,
            "professor_id": professor_id,
            "canonical_name": row.get("canonical_name"),
            "orcid": orcid,
            "status": "dry_run_success" if dry_run else "written",
            "metrics_source": source,
            "h_index": h_index,
            "citation_count": citation_count,
            "dry_run": dry_run,
        },
    )
    return True, source, 0


def run_backfill(args: argparse.Namespace) -> BackfillStats:
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    run_id = str(uuid.uuid4())
    log_path = _log_path()
    stats = BackfillStats(dry_run=args.dry_run)

    with _open_database_connection(database_url) as conn:
        rows = _fetch_professors(conn, limit=args.limit, resume=args.resume)
        stats.profs_total = len(rows)
        batch_writes = 0
        for row in rows:
            stats.profs_processed += 1
            success, source, issues_inserted = _process_professor(
                conn,
                row,
                run_id=run_id,
                dry_run=args.dry_run,
                log_path=log_path,
            )
            if success:
                stats.profs_successful += 1
                if source == "openalex":
                    stats.openalex += 1
                elif source == "verified_link_only":
                    stats.verified_link_only += 1
            else:
                stats.fetch_failed += 1
                stats.pipeline_issues_inserted += issues_inserted

            if args.dry_run:
                continue
            batch_writes += 1
            if batch_writes >= _BATCH_SIZE:
                conn.commit()
                batch_writes = 0

        if args.dry_run:
            conn.rollback()
        elif batch_writes:
            conn.commit()

    return stats


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    stats = run_backfill(args)
    print(json.dumps(asdict(stats), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
