"""Run bounded Paper full-text source acquisition without summary generation."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env")
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.paper.full_text_fetcher import (  # noqa: E402
    FullTextExtract,
    fetch_pdf_url_full_text,
)
from src.data_agents.paper.source_text_quality import (  # noqa: E402
    is_usable_paper_source_text,
)
from src.data_agents.storage.postgres.paper_full_text import (  # noqa: E402
    upsert_paper_full_text,
)
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)

logger = logging.getLogger("run_paper_full_text_source_lane")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch PDF/full-text evidence for source-gapped Paper rows without "
            "generating or writing summaries."
        ),
    )
    parser.add_argument("--limit", type=int, default=None, help="Max papers to process")
    parser.add_argument(
        "--paper-id",
        action="append",
        default=[],
        help="Restrict to one paper_id; repeatable.",
    )
    parser.add_argument(
        "--paper-id-file",
        action="append",
        default=[],
        help="Read paper_id values from a text file; one ID per line, repeatable.",
    )
    parser.add_argument(
        "--worker-count",
        type=int,
        default=1,
        help="Total number of deterministic paper_id hash shards for this run.",
    )
    parser.add_argument(
        "--worker-index",
        type=int,
        default=0,
        help="Zero-based worker shard index for this run.",
    )
    parser.add_argument("--resume", nargs="?", const="", default=None)
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=20.0,
        help="Per-request PDF fetch timeout in seconds.",
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    if args.worker_count <= 0:
        parser.error("--worker-count must be positive")
    if args.worker_index < 0 or args.worker_index >= args.worker_count:
        parser.error("--worker-index must be in [0, --worker-count)")
    try:
        args.paper_id = _merge_unique_ids(
            [*args.paper_id, *_read_paper_id_files(tuple(args.paper_id_file))]
        )
    except OSError as exc:
        parser.error(str(exc))
    return args


def _read_paper_id_files(paths: tuple[str, ...]) -> list[str]:
    paper_ids: list[str] = []
    for item in paths:
        path = Path(item)
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                value = line.strip()
                if value and not value.startswith("#"):
                    paper_ids.append(value)
    return paper_ids


def _merge_unique_ids(values: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return merged


def _open_database_connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _resolve_checkpoint_path(run_id: str) -> Path:
    base = _REPO_ROOT / "logs" / "data_agents" / "paper" / "full_text_source_runs"
    return base / f"{run_id}.jsonl"


def _load_resume_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    paper_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping corrupted resume line: %s", line[:80])
                continue
            if isinstance(row, dict) and isinstance(row.get("paper_id"), str):
                paper_ids.add(row["paper_id"])
    return paper_ids


def _append_checkpoint(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_select_sql(
    *,
    limit: int | None,
    paper_ids: tuple[str, ...] = (),
    worker_count: int = 1,
    worker_index: int = 0,
) -> tuple[str, tuple[Any, ...]]:
    conditions = [
        "pft.pdf_url IS NOT NULL",
        "length(BTRIM(pft.pdf_url)) > 0",
        "NULLIF(BTRIM(COALESCE(p.abstract_clean, '')), '') IS NULL",
        "NULLIF(BTRIM(COALESCE(pft.abstract, '')), '') IS NULL",
        "NULLIF(BTRIM(COALESCE(pft.intro, '')), '') IS NULL",
        "COALESCE(p.identity_status, 'unverified') NOT IN ('rejected', 'merged')",
        "COALESCE(p.quality_status, 'needs_enrichment') != 'rejected'",
    ]
    params: list[Any] = []
    if paper_ids:
        conditions.append("p.paper_id = ANY(%s)")
        params.append(list(paper_ids))
    if worker_count > 1:
        conditions.append("mod(abs(hashtext(p.paper_id)::bigint), %s) = %s")
        params.extend([int(worker_count), int(worker_index)])

    sql = (
        "SELECT p.paper_id, p.title_clean, p.summary_zh, p.abstract_clean, "
        "pft.abstract AS full_text_abstract, pft.intro AS full_text_intro, "
        "pft.pdf_url, pft.source AS full_text_source, "
        "pft.pdf_sha256 AS existing_pdf_sha256, pft.fetch_error "
        "  FROM paper p "
        "  JOIN paper_full_text pft ON pft.paper_id = p.paper_id "
        "  LEFT JOIN paper_merge_alias pma ON pma.old_paper_id = p.paper_id "
        f" WHERE pma.old_paper_id IS NULL AND {' AND '.join(conditions)} "
        " ORDER BY p.paper_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


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
    if args.dry_run:
        run_id = f"dry-run-{uuid4()}"
    else:
        run_id = str(
            open_pipeline_run(
                conn,
                run_kind="backfill_real",
                run_scope={
                    "task": "paper_full_text_source_lane",
                    "limit": args.limit,
                    "paper_ids": args.paper_id,
                    "paper_id_files": args.paper_id_file,
                    "worker_count": args.worker_count,
                    "worker_index": args.worker_index,
                    "request_timeout": args.request_timeout,
                    "dry_run": args.dry_run,
                    "summary_generation_enabled": False,
                },
                triggered_by="run_paper_full_text_source_lane",
            )
        )
        conn.commit()

    resume_path = Path(args.resume) if args.resume else None
    checkpoint_path = resume_path or _resolve_checkpoint_path(run_id)
    resume_ids = _load_resume_ids(resume_path)
    sql, params = _build_select_sql(
        limit=args.limit,
        paper_ids=tuple(args.paper_id or ()),
        worker_count=args.worker_count,
        worker_index=args.worker_index,
    )
    rows = conn.execute(sql, params).fetchall()
    started_at = time.monotonic()
    report = _new_report(run_id=run_id, rows_total=len(rows), dry_run=args.dry_run)
    close_status = "succeeded"
    interrupted = False
    http_client = _make_http_client(args.request_timeout)

    try:
        for row in rows:
            row_dict = dict(row)
            paper_id = str(row_dict["paper_id"])
            if paper_id in resume_ids:
                report["papers_skipped"] += 1
                continue
            _process_row(
                conn,
                row=row_dict,
                run_id=run_id,
                dry_run=args.dry_run,
                checkpoint_path=checkpoint_path,
                report=report,
                http_client=http_client,
            )
    except KeyboardInterrupt:
        interrupted = True
        close_status = "partial"
        report["interruption_reason"] = "keyboard_interrupt"
    finally:
        report["duration_seconds"] = round(time.monotonic() - started_at, 2)
        http_client.close()
        if report["papers_with_errors"]:
            close_status = "partial"
        if not args.dry_run:
            try:
                close_pipeline_run(
                    conn,
                    run_id,
                    status=close_status,
                    items_processed=report["papers_processed"],
                    items_failed=report["papers_with_errors"],
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                print(
                    json.dumps(
                        {"warn": "close_pipeline_run failed", "error": str(exc)},
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
        print(json.dumps(report, ensure_ascii=False))
    if interrupted:
        sys.exit(130)


def _new_report(*, run_id: str, rows_total: int, dry_run: bool) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "papers_total": rows_total,
        "papers_processed": 0,
        "papers_skipped": 0,
        "papers_with_errors": 0,
        "summaries_written": 0,
        "fetch_attempted": 0,
        "fetch_fetched": 0,
        "fetch_persisted": 0,
        "fetch_failed": 0,
        "fetch_skipped": 0,
        "timeouts": 0,
        "http_status_counts": {},
        "content_type_rejections": 0,
        "size_cap_rejections": 0,
        "parse_failures": 0,
        "duplicate_content": 0,
        "fetched_no_usable_text": 0,
        "failure_reason_counts": {},
        "failure_samples": [],
        "dry_run": dry_run,
        "summary_generation_enabled": False,
    }


def _process_row(
    conn: Any,
    *,
    row: dict[str, Any],
    run_id: str,
    dry_run: bool,
    checkpoint_path: Path,
    report: dict[str, Any],
    http_client: httpx.Client,
) -> None:
    paper_id = str(row["paper_id"])
    pdf_url = str(row.get("pdf_url") or "").strip()
    report["papers_processed"] += 1
    report["fetch_attempted"] += 1
    try:
        extract = fetch_pdf_url_full_text(
            pdf_url,
            paper_id=paper_id,
            source=_extract_source(row),
            http_client=http_client,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Paper %s full-text fetch crashed: %s", paper_id, exc)
        report["papers_with_errors"] += 1
        try:
            conn.rollback()
        except Exception:
            pass
        _append_checkpoint(
            checkpoint_path,
            {"paper_id": paper_id, "status": "error", "error": str(exc)},
        )
        return

    if extract.fetch_error:
        report["fetch_failed"] += 1
        _record_failure(
            report,
            paper_id=paper_id,
            pdf_url=pdf_url,
            reason=extract.fetch_error,
        )
        _append_checkpoint(
            checkpoint_path,
            {"paper_id": paper_id, "status": "fetch_failed", "reason": extract.fetch_error},
        )
        return

    report["fetch_fetched"] += 1
    if not _has_usable_extract_text(extract):
        report["fetched_no_usable_text"] += 1
        report["fetch_skipped"] += 1
        _record_failure(
            report,
            paper_id=paper_id,
            pdf_url=pdf_url,
            reason="fetched_no_usable_text",
        )
        _append_checkpoint(
            checkpoint_path,
            {"paper_id": paper_id, "status": "fetched_no_usable_text"},
        )
        return

    duplicate_paper_id = _find_duplicate_pdf_sha(
        conn,
        paper_id=paper_id,
        pdf_sha256=extract.pdf_sha256,
    )
    if duplicate_paper_id:
        report["duplicate_content"] += 1
        report["fetch_skipped"] += 1
        _record_failure(
            report,
            paper_id=paper_id,
            pdf_url=pdf_url,
            reason="duplicate_pdf_sha256",
            duplicate_paper_id=duplicate_paper_id,
        )
        _append_checkpoint(
            checkpoint_path,
            {
                "paper_id": paper_id,
                "status": "duplicate_pdf_sha256",
                "duplicate_paper_id": duplicate_paper_id,
            },
        )
        return

    if not dry_run:
        upsert_paper_full_text(conn, paper_id=paper_id, extract=extract, run_id=run_id)
        conn.commit()
    report["fetch_persisted"] += 1
    _append_checkpoint(
        checkpoint_path,
        {
            "paper_id": paper_id,
            "status": "dry_run_persistable" if dry_run else "persisted",
            "source": extract.source,
            "abstract_chars": len(extract.abstract or ""),
            "intro_chars": len(extract.intro or ""),
        },
    )


def _extract_source(row: dict[str, Any]) -> str:
    source = str(row.get("full_text_source") or "paper_full_text").strip()
    return f"full_text_lane:{source}"[:64]


def _make_http_client(request_timeout: float) -> httpx.Client:
    return httpx.Client(
        timeout=max(1.0, float(request_timeout)),
        trust_env=False,
        follow_redirects=True,
        max_redirects=5,
    )


def _has_usable_extract_text(extract: FullTextExtract) -> bool:
    return _is_usable_source_text(extract.abstract) or _is_usable_source_text(
        extract.intro
    )


def _is_usable_source_text(value: object) -> bool:
    return is_usable_paper_source_text(value)


def _find_duplicate_pdf_sha(
    conn: Any,
    *,
    paper_id: str,
    pdf_sha256: str | None,
) -> str | None:
    if not pdf_sha256:
        return None
    row = conn.execute(
        """
        SELECT paper_id
          FROM paper_full_text
         WHERE pdf_sha256 = %s
           AND paper_id != %s
         ORDER BY paper_id
         LIMIT 1
        """,
        (pdf_sha256, paper_id),
    ).fetchone()
    if isinstance(row, dict):
        return str(row.get("paper_id") or "").strip() or None
    if isinstance(row, tuple) and row:
        return str(row[0] or "").strip() or None
    return None


def _record_failure(
    report: dict[str, Any],
    *,
    paper_id: str,
    pdf_url: str,
    reason: str,
    duplicate_paper_id: str | None = None,
) -> None:
    counts = report["failure_reason_counts"]
    counts[reason] = int(counts.get(reason, 0)) + 1
    if reason == "timeout":
        report["timeouts"] += 1
    elif reason.startswith("http_"):
        status = reason.removeprefix("http_")
        http_counts = report["http_status_counts"]
        http_counts[status] = int(http_counts.get(status, 0)) + 1
    elif reason == "pdf_content_type_disallowed":
        report["content_type_rejections"] += 1
    elif reason == "pdf_too_large":
        report["size_cap_rejections"] += 1
    elif reason == "pdf_parse_error":
        report["parse_failures"] += 1

    samples = report["failure_samples"]
    if len(samples) >= 20:
        return
    sample = {
        "paper_id": paper_id,
        "source_url": pdf_url,
        "reason": reason,
        "retry_recommendation": _retry_recommendation(reason),
    }
    if duplicate_paper_id:
        sample["duplicate_paper_id"] = duplicate_paper_id
    samples.append(sample)


def _retry_recommendation(reason: str) -> str:
    if reason == "timeout":
        return "retry_later_with_lower_concurrency"
    if reason == "http_429":
        return "retry_after_rate_limit_cooldown"
    if reason in {"http_403", "http_404", "pdf_content_type_disallowed"}:
        return "find_alternate_source_or_manual_review"
    if reason == "pdf_too_large":
        return "manual_review_or_fetch_smaller_source"
    if reason in {"pdf_parse_error", "pdf_empty_text", "fetched_no_usable_text"}:
        return "parser_repair_or_manual_review"
    if reason == "duplicate_pdf_sha256":
        return "review_duplicate_mapping_before_retry"
    return "retry_or_manual_review"


if __name__ == "__main__":
    main()
