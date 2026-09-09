# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Scan ``prof_page_only`` papers and reject implausible-title ones (no LLM).

The companion to ``run_paper_identity_scan`` (W0b): where W0b rejects wrong-
attribution papers via the LLM same-person gate, this scan rejects parser-garbage
titles via the pure rule-based ``is_plausible_paper_title`` guard. It marks such
rows ``paper.identity_status='rejected'`` so they drop out of Milvus retrieval
and (via the ``/paper`` list default-exclusion) the admin display. See OpenSpec
change ``paper-implausible-title-cleanup``.

No LLM is invoked. The scan is cheap and streams per-paper JSONL as it goes
(unlike W0b's LLM-gated scan, which batches JSONL after all gate calls).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from src.data_agents.paper.identity_status_writer import (
    apply_identity_status_rejection,
)
from src.data_agents.paper.title_quality import is_clearly_garbage_paper_title
from src.data_agents.storage.postgres.connection import resolve_dsn
from src.data_agents.storage.postgres.pipeline_run import (
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)

_REAL_DB_NAME = "miroflow_real"
_RUN_KIND = "backfill_real"
_TRIGGERED_BY = "paper_title_cleanup_scan"
_STAGE = "identity_gate"  # reuse the allowed pipeline_issue.stage value; title-cleanup
# issues are distinguished from W0b's by reported_by (paper_title_cleanup_scan vs
# paper_identity_scan). pipeline_issue.stage has a CHECK constraint that does not
# include a 'title_cleanup' value, so we reuse 'identity_gate'.
_REPORTED_BY = "paper_title_cleanup_scan"
_ARCHIVE_DIR = Path(__file__).resolve().parents[3] / "docs" / "source_backfills"
_ARCHIVE_PREFIX = "paper-title-cleanup-scan"
_FALSY_FLAG_VALUES = {"", "0", "false", "off", "no"}


@dataclass(frozen=True, slots=True)
class _ScanRow:
    paper_id: str
    title_clean: str
    canonical_source: str
    identity_status: str
    quality_status: str | None


@dataclass
class _ScanStats:
    examined: int = 0
    rejected: int = 0
    unchanged: int = 0
    skipped: int = 0
    issues_filed: int = 0
    identity_updates: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reject implausible-titled prof_page_only papers (no LLM)."
    )
    parser.add_argument(
        "--database-url",
        help="Postgres DSN. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write identity_status changes. Default is dry-run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only scan the first N prof_page_only rows.",
    )
    parser.add_argument(
        "--confirm-real-db",
        action="store_true",
        help="Required if the DSN targets miroflow_real.",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Stream per-paper decisions as JSONL to this path. Append mode.",
    )
    output_group.add_argument(
        "--archive",
        action="store_true",
        help=(
            "Equivalent to --json-output "
            "docs/source_backfills/paper-title-cleanup-scan-{today}.jsonl."
        ),
    )
    return parser.parse_args()


def _title_cleanup_enabled() -> bool:
    raw = os.environ.get("PAPER_TITLE_CLEANUP_ENABLED", "")
    return raw.strip().lower() not in _FALSY_FLAG_VALUES


def _load_rows(
    conn: psycopg.Connection,
    *,
    limit: int | None,
) -> list[_ScanRow]:
    sql = """
        SELECT p.paper_id,
               p.title_clean,
               p.canonical_source,
               p.identity_status,
               p.quality_status
          FROM paper p
         WHERE p.canonical_source = 'prof_page_only'
           AND p.identity_status NOT IN ('rejected', 'merged')
         ORDER BY p.paper_id
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += "\n         LIMIT %s"
        params = (limit,)
    rows = conn.execute(sql, params).fetchall()
    return [_scan_row(row) for row in rows]


def _scan_row(row: dict[str, Any]) -> _ScanRow:
    return _ScanRow(
        paper_id=str(row["paper_id"]),
        title_clean=str(row.get("title_clean") or ""),
        canonical_source=str(row.get("canonical_source") or ""),
        identity_status=str(row.get("identity_status") or "unverified"),
        quality_status=(
            str(row["quality_status"])
            if row.get("quality_status") is not None
            else None
        ),
    )


def _scan_rows(
    conn: psycopg.Connection,
    *,
    rows: list[_ScanRow],
    apply_mode: bool,
    run_id: str,
    jsonl_handle: TextIO | None,
    json_output_path: Path | None,
    scan_started_at: str,
) -> _ScanStats:
    stats = _ScanStats()
    for row in rows:
        stats.examined += 1
        clearly_garbage = is_clearly_garbage_paper_title(row.title_clean)
        action_taken = "none"
        if clearly_garbage:
            stats.rejected += 1
            action_taken = "would_reject"
            if apply_mode:
                result = apply_identity_status_rejection(
                    conn,
                    paper_id=row.paper_id,
                    run_id=run_id,
                    evidence={
                        "reason": "clearly_garbage_title",
                        "title_clean": row.title_clean,
                    },
                    prior_identity_status=row.identity_status,
                    stage=_STAGE,
                    reported_by=_REPORTED_BY,
                )
                stats.issues_filed += result.issues_filed
                if result.identity_updated:
                    stats.identity_updates += 1
                action_taken = (
                    "rejected" if result.identity_updated else "reject_noop"
                )
        else:
            stats.unchanged += 1
        _emit_jsonl(
            jsonl_handle,
            json_output_path,
            {
                "paper_id": row.paper_id,
                "title_clean": row.title_clean,
                "clearly_garbage": clearly_garbage,
                "verdict": "reject" if clearly_garbage else "no_change",
                "prior_identity_status": row.identity_status,
                "action_taken": action_taken,
                "apply_mode": apply_mode,
                "run_id": run_id,
                "scan_started_at": scan_started_at,
                "examined_index": stats.examined,
            },
        )
    return stats


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_date_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _default_archive_path() -> Path:
    return _ARCHIVE_DIR / f"{_ARCHIVE_PREFIX}-{_utc_date_slug()}.jsonl"


def _json_output_path(args: argparse.Namespace) -> Path | None:
    if args.archive:
        return _default_archive_path()
    return args.json_output


def _open_jsonl(path: Path) -> TextIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8")


def _emit_jsonl(
    handle: TextIO | None,
    path: Path | None,
    payload: dict[str, object],
) -> bool:
    if handle is None:
        return True
    try:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str))
        handle.write("\n")
        handle.flush()
    except OSError as exc:
        print(f"warning: failed to write JSONL to {path}: {exc}", file=sys.stderr)
        return False
    return True


def _strip_proxy_env() -> None:
    for key in (
        "all_proxy",
        "ALL_PROXY",
        "http_proxy",
        "HTTP_PROXY",
        "https_proxy",
        "HTTPS_PROXY",
    ):
        os.environ.pop(key, None)


def _summary_record(
    *,
    stats: _ScanStats,
    args: argparse.Namespace,
    dsn: str,
    scan_started_at: datetime,
    scan_finished_at: datetime,
) -> dict[str, object]:
    parsed = urlparse(dsn)
    host = parsed.hostname or ""
    port = parsed.port
    if port is not None:
        host = f"{host}:{port}"
    database_name = parsed.path.lstrip("/").split("/", maxsplit=1)[0] or None
    return {
        "summary": True,
        "scan_started_at": _utc_timestamp(scan_started_at),
        "scan_finished_at": _utc_timestamp(scan_finished_at),
        "duration_seconds": int(
            (scan_finished_at - scan_started_at).total_seconds()
        ),
        "apply_mode": args.apply,
        "examined": stats.examined,
        "rejected": stats.rejected,
        "unchanged": stats.unchanged,
        "skipped": stats.skipped,
        "issues_filed": stats.issues_filed,
        "identity_updates": stats.identity_updates,
        "database_dsn_host": host or None,
        "database_name": database_name,
    }


def _emit_disabled_summary(json_output_path: Path | None) -> None:
    handle: TextIO | None = None
    try:
        if json_output_path is not None:
            handle = _open_jsonl(json_output_path)
        _emit_jsonl(
            handle, json_output_path, {"summary": True, "disabled": True, "examined": 0}
        )
    finally:
        if handle is not None:
            handle.close()


def _run(args: argparse.Namespace) -> int:
    json_output_path = _json_output_path(args)
    if not _title_cleanup_enabled():
        _emit_disabled_summary(json_output_path)
        print("PAPER_TITLE_CLEANUP_ENABLED disabled; skipping title-cleanup scan.")
        return 0

    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print(
            "Refusing to scan miroflow_real without --confirm-real-db.",
            file=sys.stderr,
        )
        return 2

    _strip_proxy_env()
    jsonl_handle: TextIO | None = None
    scan_started_at = datetime.now(timezone.utc)
    scan_started_at_text = _utc_timestamp(scan_started_at)
    run_id = f"dry-run-{uuid4()}"
    stats = _ScanStats()

    if json_output_path is not None:
        try:
            jsonl_handle = _open_jsonl(json_output_path)
        except OSError as exc:
            print(
                f"Unable to open JSONL output {json_output_path}: {exc}",
                file=sys.stderr,
            )
            return 2

    try:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            if args.apply:
                run_id = str(
                    require_real_run_id(
                        open_pipeline_run(
                            conn,
                            run_kind=_RUN_KIND,
                            run_scope={
                                "task": "paper_title_cleanup_scan",
                                "limit": args.limit,
                                "dry_run": False,
                            },
                            triggered_by=_TRIGGERED_BY,
                        ),
                        writer_name="run_paper_title_cleanup_scan",
                    )
                )
                conn.commit()

            rows = _load_rows(conn, limit=args.limit)
            stats = _scan_rows(
                conn,
                rows=rows,
                apply_mode=args.apply,
                run_id=run_id,
                jsonl_handle=jsonl_handle,
                json_output_path=json_output_path,
                scan_started_at=scan_started_at_text,
            )
            if args.apply:
                close_pipeline_run(
                    conn,
                    run_id,
                    status="succeeded",
                    items_processed=stats.examined,
                    items_failed=0,
                )
                conn.commit()
            else:
                conn.rollback()

        scan_finished_at = datetime.now(timezone.utc)
        _emit_jsonl(
            jsonl_handle,
            json_output_path,
            _summary_record(
                stats=stats,
                args=args,
                dsn=dsn,
                scan_started_at=scan_started_at,
                scan_finished_at=scan_finished_at,
            ),
        )
    except Exception:
        if args.apply and not str(run_id).startswith("dry-run-"):
            try:
                with psycopg.connect(dsn, row_factory=dict_row) as conn:
                    close_pipeline_run(
                        conn,
                        run_id,
                        status="failed",
                        error_summary={"message": "title-cleanup scan failed"},
                    )
                    conn.commit()
            except Exception:
                pass
        raise
    finally:
        if jsonl_handle is not None:
            jsonl_handle.close()

    print(f"Examined: {stats.examined}")
    print(f"Rejected: {stats.rejected}")
    print(f"Unchanged: {stats.unchanged}")
    print(f"Apply mode: {args.apply}")
    if json_output_path is not None:
        print(f"archived to {json_output_path}", file=sys.stderr)
    return 0


def main() -> int:
    return _run(_parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
