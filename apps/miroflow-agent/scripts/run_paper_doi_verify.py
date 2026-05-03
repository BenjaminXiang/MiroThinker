"""Backfill paper.identity_status via cached/OpenAlex/arXiv title resolution."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import psycopg
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.paper.doi_verifier import (  # noqa: E402
    DoiVerification,
    normalize_authors,
    verify_paper_row,
)
from src.data_agents.paper.title_cleaner import clean_paper_title  # noqa: E402
from src.data_agents.paper.title_resolver import _title_cache_key  # noqa: E402
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)
from src.data_agents.storage.postgres.title_resolution_cache import (  # noqa: E402
    PostgresTitleResolutionCache,
)

logger = logging.getLogger("run_paper_doi_verify")

_REPORTED_BY = "w13_14_paper_doi_verify"
_RUN_KIND = "backfill_real"
_ISSUE_CODE = "paper_doi_verify_failed"


@dataclass(frozen=True, slots=True)
class RowVerification:
    decision: DoiVerification | None
    cache_key: str | None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify unverified paper identities using title resolution.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max papers to scan")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip rows with an existing unresolved W13-14 failure issue",
    )
    parser.add_argument("--dry-run", action="store_true", help="No per-paper writes")
    parser.add_argument(
        "--start-from-paper-id",
        default=None,
        help="Only scan paper_id >= this value",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _open_http_client():
    return httpx.Client(timeout=30.0, trust_env=False)


def _build_select_sql(
    *,
    limit: int | None,
    resume: bool,
    start_from_paper_id: str | None,
) -> tuple[str, tuple[Any, ...]]:
    clauses = ["p.identity_status = 'unverified'"]
    params: list[Any] = []
    if start_from_paper_id:
        clauses.append("p.paper_id >= %s")
        params.append(start_from_paper_id)
    if resume:
        clauses.append(
            """
            NOT EXISTS (
                SELECT 1
                  FROM pipeline_issue pi
                 WHERE pi.institution = 'paper:' || p.paper_id
                   AND pi.stage = 'data_quality_flag'
                   AND pi.reported_by = %s
                   AND pi.resolved = false
            )
            """
        )
        params.append(_REPORTED_BY)

    sql = (
        "SELECT p.paper_id, p.title_clean, p.title_raw, p.authors_display, "
        "       p.authors_raw, p.doi, p.arxiv_id, p.openalex_id, p.year "
        "  FROM paper p "
        f" WHERE {' AND '.join(clauses)} "
        " ORDER BY p.paper_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _cache_key_for_row(row: dict[str, Any]) -> str | None:
    title = clean_paper_title(row.get("title_clean") or row.get("title_raw"))
    if not title:
        return None
    return _title_cache_key(title)


def _verify_row(
    row: dict[str, Any],
    *,
    cache: PostgresTitleResolutionCache,
    http_client,
) -> RowVerification:
    cache_key = _cache_key_for_row(row)
    cached_resolution = cache.get(cache_key) if cache_key is not None else None
    decision = verify_paper_row(
        row,
        cached_resolution=cached_resolution,
        openalex_client=http_client,
        arxiv_client=http_client,
    )
    return RowVerification(decision=decision, cache_key=cache_key)


def _mark_paper_confirmed(
    conn: Any,
    *,
    paper_id: str,
    run_id: UUID | str,
) -> int:
    run_id = require_real_run_id(run_id, writer_name="_mark_paper_confirmed")
    cursor = conn.execute(
        """
        UPDATE paper
           SET identity_status = 'confirmed',
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND identity_status = 'unverified'
        """,
        (run_id, paper_id),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _file_pipeline_issue(
    conn: Any,
    *,
    row: dict[str, Any],
    run_id: UUID | str,
) -> int:
    run_id = require_real_run_id(run_id, writer_name="_file_pipeline_issue")
    paper_id = str(row["paper_id"])
    title = clean_paper_title(row.get("title_clean") or row.get("title_raw"))
    snapshot = {
        "run_id": str(run_id),
        "issue_code": _ISSUE_CODE,
        "paper_id": paper_id,
        "title": title,
        "authors": normalize_authors(
            row.get("authors_raw") or row.get("authors_display")
        ),
        "attempted_sources": ["cache", "openalex", "arxiv"],
    }
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, institution, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (NULL, %s, 'data_quality_flag', 'medium', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            f"paper:{paper_id}",
            f"[{_ISSUE_CODE}] {paper_id}: {title[:180]}",
            json.dumps(snapshot, ensure_ascii=False, default=str),
            _REPORTED_BY,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _empty_report(
    *,
    run_id: UUID | str,
    args: argparse.Namespace,
    rows_total: int,
) -> dict[str, Any]:
    return {
        "run_id": str(run_id),
        "dry_run": bool(args.dry_run),
        "limit": args.limit,
        "resume": bool(args.resume),
        "start_from_paper_id": args.start_from_paper_id,
        "papers_total": rows_total,
        "papers_processed": 0,
        "papers_confirmed": 0,
        "papers_unverified": 0,
        "papers_with_errors": 0,
        "cache_hits": 0,
        "openalex_hits": 0,
        "arxiv_hits": 0,
        "paper_updates": 0,
        "cache_writes": 0,
        "pipeline_issues_inserted": 0,
    }


def _process_rows(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    cache: PostgresTitleResolutionCache,
    http_client,
    run_id: UUID | str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    report = _empty_report(run_id=run_id, args=args, rows_total=len(rows))
    for row in rows:
        row_dict = dict(row)
        paper_id = str(row_dict["paper_id"])
        report["papers_processed"] += 1
        try:
            verification = _verify_row(
                row_dict,
                cache=cache,
                http_client=http_client,
            )
            decision = verification.decision
            if decision is None:
                report["papers_unverified"] += 1
                if not args.dry_run:
                    report["pipeline_issues_inserted"] += _file_pipeline_issue(
                        conn,
                        row=row_dict,
                        run_id=run_id,
                    )
                    conn.commit()
                continue

            report["papers_confirmed"] += 1
            report[f"{decision.source}_hits"] += 1
            if not args.dry_run:
                report["paper_updates"] += _mark_paper_confirmed(
                    conn,
                    paper_id=paper_id,
                    run_id=run_id,
                )
                if decision.source != "cache" and verification.cache_key is not None:
                    cache.set(verification.cache_key, decision.resolved)
                    report["cache_writes"] += 1
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to verify paper %s: %s", paper_id, exc)
            report["papers_with_errors"] += 1
            try:
                conn.rollback()
            except Exception:
                pass
            continue
    return report


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
    http_client = None
    run_id: UUID | str | None = None
    try:
        run_id = open_pipeline_run(
            conn,
            run_kind=_RUN_KIND,
            run_scope={
                "task": "w13_14_paper_doi_verify",
                "limit": args.limit,
                "resume": args.resume,
                "dry_run": args.dry_run,
                "start_from_paper_id": args.start_from_paper_id,
            },
            triggered_by=_REPORTED_BY,
        )
        run_id = require_real_run_id(run_id, writer_name="run_paper_doi_verify")
        conn.commit()

        sql, params = _build_select_sql(
            limit=args.limit,
            resume=args.resume,
            start_from_paper_id=args.start_from_paper_id,
        )
        rows = conn.execute(sql, params).fetchall()
        cache = PostgresTitleResolutionCache(conn)
        http_client = _open_http_client()
        report = _process_rows(
            conn,
            list(rows),
            cache=cache,
            http_client=http_client,
            run_id=run_id,
            args=args,
        )
        close_pipeline_run(
            conn,
            run_id,
            status="partial" if report["papers_with_errors"] else "succeeded",
            items_processed=report["papers_processed"],
            items_failed=report["papers_with_errors"],
        )
        conn.commit()
        print(json.dumps(report, ensure_ascii=False, default=str))
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
        close_http = getattr(http_client, "close", None)
        if callable(close_http):
            close_http()
        close_conn = getattr(conn, "close", None)
        if callable(close_conn):
            close_conn()


if __name__ == "__main__":
    main()
