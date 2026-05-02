# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.17 — rescan stored canonical_name_en values with the name gate.

The script is dry-run by default. Use ``--apply`` to insert ``pipeline_issue``
rows and optionally clear obviously wrong ``canonical_name_en`` values.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
from src.data_agents.professor.name_identity_gate import (
    NameIdentityCandidate,
    batch_verify_name_identity,
)
from src.data_agents.storage.postgres.connection import resolve_dsn

_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_17_scan"
_ARCHIVE_DIR = Path(__file__).resolve().parents[3] / "docs" / "source_backfills"
_ARCHIVE_PREFIX = "round-7-17-name-identity-clear"
DESCRIPTION_TEMPLATE = (
    "canonical_name_en rejected for {canonical_name}: {candidate_name_en}"
)


@dataclass(frozen=True, slots=True)
class _ProfessorRow:
    professor_id: str
    canonical_name: str
    canonical_name_en: str
    institution: str | None
    source_url: str | None


@dataclass
class _ScanStats:
    examined: int = 0
    rejected: int = 0
    issues_inserted: int = 0
    clear_updates: int = 0
    would_clear: int = 0


def _build_llm_settings() -> tuple[object, str]:
    """Return (openai-compatible client, model string) using shared LLM profile resolver."""
    from openai import OpenAI

    settings = resolve_professor_llm_settings("gemma4")
    api_key = settings.get("local_llm_api_key") or "EMPTY"
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=api_key,
    )
    return client, settings["local_llm_model"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rescan professor.canonical_name_en with the Round 7.17 gate."
    )
    parser.add_argument(
        "--database-url",
        help="Postgres DSN. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--institution",
        help="Only scan professors whose primary institution matches this value.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Insert pipeline_issue rows (default is dry-run).",
    )
    parser.add_argument(
        "--confirm-real-db",
        action="store_true",
        help="Required if the DSN targets miroflow_real.",
    )
    parser.add_argument(
        "--auto-clear-threshold",
        type=float,
        default=None,
        help="If 1 - confidence >= threshold, also clear canonical_name_en.",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Stream per-professor decisions as JSONL to this path. Append mode.",
    )
    output_group.add_argument(
        "--archive",
        action="store_true",
        help=(
            "Equivalent to --json-output "
            "docs/source_backfills/round-7-17-name-identity-clear-{today}.jsonl. "
            "Mutually exclusive with --json-output."
        ),
    )
    return parser.parse_args()


def _load_rows(
    conn: psycopg.Connection, *, institution: str | None
) -> list[_ProfessorRow]:
    params: list[object] = []
    where = [
        "p.canonical_name IS NOT NULL",
        "btrim(p.canonical_name) <> ''",
        "p.canonical_name_en IS NOT NULL",
        "btrim(p.canonical_name_en) <> ''",
    ]
    if institution:
        where.append("pa.institution = %s")
        params.append(institution)

    rows = conn.execute(
        f"""
        SELECT p.professor_id,
               p.canonical_name,
               p.canonical_name_en,
               pa.institution,
               sp.url AS source_url
          FROM professor p
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = p.professor_id
           AND pa.is_primary = true
          LEFT JOIN source_page sp
            ON sp.page_id = p.primary_official_profile_page_id
         WHERE {" AND ".join(where)}
         ORDER BY COALESCE(pa.institution, ''), p.professor_id
        """,
        params,
    ).fetchall()
    return [
        _ProfessorRow(
            professor_id=row["professor_id"],
            canonical_name=row["canonical_name"],
            canonical_name_en=row["canonical_name_en"],
            institution=row["institution"],
            source_url=row["source_url"],
        )
        for row in rows
    ]


def _should_auto_clear(
    decision, *, threshold: float | None
) -> bool:
    if threshold is None or decision.error is not None:
        return False
    return (1.0 - decision.confidence) >= threshold


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
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")
        handle.flush()
    except OSError as exc:
        print(f"warning: failed to write JSONL to {path}: {exc}", file=sys.stderr)
        return False
    return True


def _redacted_dsn_parts(dsn: str) -> tuple[str | None, str | None]:
    parsed = urlparse(dsn)
    if not parsed.scheme or not parsed.netloc:
        return None, None

    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is not None:
        host = f"{host}:{port}"

    database_name = parsed.path.lstrip("/").split("/", maxsplit=1)[0] or None
    return host or None, database_name


def _action_taken(*, accepted: bool, apply_mode: bool, should_clear: bool) -> str:
    if accepted:
        return "none"
    if apply_mode:
        if should_clear:
            return "issue_filed_and_name_en_cleared"
        return "issue_filed"
    if should_clear:
        return "would_clear"
    return "would_file_issue"


def _professor_record(
    *,
    row: _ProfessorRow,
    decision,
    action_taken: str,
    apply_mode: bool,
    scan_started_at: str,
    examined_index: int,
) -> dict[str, object]:
    return {
        "professor_id": row.professor_id,
        "canonical_name": row.canonical_name,
        "canonical_name_en_before": row.canonical_name_en,
        "institution": row.institution,
        "source_url": row.source_url,
        "decision": "accepted" if decision.accepted else "rejected",
        "confidence": decision.confidence,
        "reason": "" if decision.accepted else (decision.reasoning or ""),
        "action_taken": action_taken,
        "apply_mode": apply_mode,
        "scan_started_at": scan_started_at,
        "examined_index": examined_index,
    }


def _summary_record(
    *,
    stats: _ScanStats,
    args: argparse.Namespace,
    dsn: str,
    scan_started_at: datetime,
    scan_finished_at: datetime,
) -> dict[str, object]:
    dsn_host, database_name = _redacted_dsn_parts(dsn)
    return {
        "summary": True,
        "scan_started_at": _utc_timestamp(scan_started_at),
        "scan_finished_at": _utc_timestamp(scan_finished_at),
        "duration_seconds": int((scan_finished_at - scan_started_at).total_seconds()),
        "institution_filter": args.institution,
        "apply_mode": args.apply,
        "examined": stats.examined,
        "rejected": stats.rejected,
        "issues_inserted": stats.issues_inserted,
        "clear_updates": stats.clear_updates,
        "would_clear": stats.would_clear,
        "auto_clear_threshold": args.auto_clear_threshold,
        "database_dsn_host": dsn_host,
        "database_name": database_name,
    }


def _issue_snapshot(row: _ProfessorRow, decision) -> dict[str, object]:
    return {
        "type": "name_extraction_report",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "professor": {
            "professor_id": row.professor_id,
            "canonical_name": row.canonical_name,
            "canonical_name_en": row.canonical_name_en,
            "institution": row.institution,
            "source_url": row.source_url,
        },
        "gate_decision": {
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
            "error": decision.error,
        },
    }


def _insert_issue(
    conn: psycopg.Connection,
    *,
    row: _ProfessorRow,
    decision,
) -> int:
    description = DESCRIPTION_TEMPLATE.format(
        canonical_name=row.canonical_name,
        candidate_name_en=row.canonical_name_en,
    )
    snapshot = json.dumps(_issue_snapshot(row, decision), ensure_ascii=False)
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
        VALUES (%s, %s, 'name_extraction', 'medium', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            row.professor_id,
            row.institution,
            description,
            snapshot,
            _REPORTED_BY,
        ),
    )
    return cursor.rowcount


def _clear_name_en(conn: psycopg.Connection, *, professor_id: str) -> int:
    cursor = conn.execute(
        """
        UPDATE professor
           SET canonical_name_en = NULL
         WHERE professor_id = %s
        """,
        (professor_id,),
    )
    return cursor.rowcount


def main() -> int:
    args = _parse_args()
    if (
        args.auto_clear_threshold is not None
        and not 0.0 <= args.auto_clear_threshold <= 1.0
    ):
        print("--auto-clear-threshold must be between 0 and 1", file=sys.stderr)
        return 2

    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print(
            "Refusing to scan miroflow_real without --confirm-real-db.",
            file=sys.stderr,
        )
        return 2

    llm_client, llm_model = _build_llm_settings()
    stats = _ScanStats()
    json_output_path = _json_output_path(args)
    jsonl_handle: TextIO | None = None
    scan_started_at = datetime.now(timezone.utc)
    scan_started_at_text = _utc_timestamp(scan_started_at)

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
            rows = _load_rows(conn, institution=args.institution)
            candidates = [
                NameIdentityCandidate(
                    canonical_name=row.canonical_name,
                    candidate_name_en=row.canonical_name_en,
                    source_url=row.source_url,
                )
                for row in rows
            ]
            decisions = batch_verify_name_identity(
                candidates,
                llm_client=llm_client,
                llm_model=llm_model,
            )

            for row, decision in zip(rows, decisions, strict=True):
                stats.examined += 1
                should_clear = False
                if not decision.accepted:
                    stats.rejected += 1
                    should_clear = _should_auto_clear(
                        decision, threshold=args.auto_clear_threshold
                    )
                    if args.apply:
                        stats.issues_inserted += _insert_issue(
                            conn, row=row, decision=decision
                        )
                        if should_clear:
                            stats.clear_updates += _clear_name_en(
                                conn, professor_id=row.professor_id
                            )
                    elif should_clear:
                        stats.would_clear += 1

                action_taken = _action_taken(
                    accepted=decision.accepted,
                    apply_mode=args.apply,
                    should_clear=should_clear,
                )
                _emit_jsonl(
                    jsonl_handle,
                    json_output_path,
                    _professor_record(
                        row=row,
                        decision=decision,
                        action_taken=action_taken,
                        apply_mode=args.apply,
                        scan_started_at=scan_started_at_text,
                        examined_index=stats.examined,
                    ),
                )

            if not args.apply:
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
    finally:
        if jsonl_handle is not None:
            jsonl_handle.close()

    print(f"Examined: {stats.examined}")
    print(f"Rejected: {stats.rejected}")
    print(f"Apply mode: {args.apply}")
    print(f"Pipeline issues inserted: {stats.issues_inserted}")
    if args.apply:
        print(f"canonical_name_en cleared: {stats.clear_updates}")
    else:
        print(f"Would clear canonical_name_en: {stats.would_clear}")
    if json_output_path is not None:
        print(f"archived to {json_output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
