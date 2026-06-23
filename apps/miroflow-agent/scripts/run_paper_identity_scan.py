# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Scan prof-page-only papers and apply reversible identity-status rejections."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from scripts.run_identity_verify_candidate_links import _apply_decision
from src.data_agents.paper.identity_status_writer import (
    apply_identity_status_rejection,
    decide_identity_status_rejection,
    restore_identity_status,
)
from src.data_agents.professor.identity_verifier import ProfessorContext
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
from src.data_agents.professor.paper_identity_gate import (
    PaperIdentityCandidate,
    PaperIdentityDecision,
    batch_verify_paper_identity,
)
from src.data_agents.storage.postgres.connection import resolve_dsn
from src.data_agents.storage.postgres.pipeline_run import (
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)

_REAL_DB_NAME = "miroflow_real"
_RUN_KIND = "backfill_real"
_TRIGGERED_BY = "paper_identity_scan"
_DEFAULT_LLM_PROFILE = "gemma4"
_ARCHIVE_DIR = Path(__file__).resolve().parents[3] / "docs" / "source_backfills"
_ARCHIVE_PREFIX = "paper-identity-scan"
_FALSY_FLAG_VALUES = {"", "0", "false", "off", "no"}


@dataclass(frozen=True, slots=True)
class _ScanRow:
    paper_id: str
    title_clean: str
    authors_display: str | None
    year: int | None
    venue: str | None
    abstract_clean: str | None
    canonical_source: str
    identity_status: str
    quality_status: str | None
    link_id: str
    link_status: str
    professor_id: str
    canonical_name: str
    institution: str | None
    department: str | None
    research_directions: tuple[str, ...] = ()


@dataclass
class _ScanStats:
    examined: int = 0
    rejected: int = 0
    unchanged: int = 0
    flipped_back: int = 0
    restored: int = 0
    issues_filed: int = 0
    identity_updates: int = 0
    links_promoted: int = 0
    links_rejected: int = 0
    links_unchanged: int = 0
    gate_errors: int = 0


@dataclass(frozen=True, slots=True)
class _LinkDecision:
    row: _ScanRow
    target_status: str
    decision: PaperIdentityDecision | None = None


@dataclass
class _PaperDecisionRecord:
    row: _ScanRow
    link_decisions: list[_LinkDecision] = field(default_factory=list)

    @property
    def has_verified_link(self) -> bool:
        return any(item.target_status == "verified" for item in self.link_decisions)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan paper.identity_status against the paper identity gate."
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
        help="Only scan the first N prof-page-only paper rows.",
    )
    parser.add_argument(
        "--only-no-verified-link",
        action="store_true",
        help=(
            "Scope to prof-page-only papers with NO verified professor_paper_link. "
            "Skips re-verifying already-verified papers (avoids LLM cost) and is the "
            "scoped mode for the Gap B identity_status rejection apply."
        ),
    )
    parser.add_argument(
        "--all-sources",
        action="store_true",
        help=(
            "Include all canonical_source values (not just prof_page_only). "
            "Used for D7 link verification of crossref/dblp/s2-sourced papers."
        ),
    )
    parser.add_argument(
        "--confirm-real-db",
        action="store_true",
        help="Required if the DSN targets miroflow_real.",
    )
    parser.add_argument(
        "--llm-profile",
        default=_DEFAULT_LLM_PROFILE,
        help="LLM profile passed to the existing paper identity gate.",
    )
    parser.add_argument(
        "--use-online",
        action="store_true",
        help="Use the profile's online endpoint instead of the local endpoint.",
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
            "docs/source_backfills/paper-identity-scan-{today}.jsonl. "
            "Mutually exclusive with --json-output."
        ),
    )
    return parser.parse_args()


def _paper_identity_gate_enabled() -> bool:
    raw = os.environ.get("PAPER_IDENTITY_GATE_ENABLED", "")
    return raw.strip().lower() not in _FALSY_FLAG_VALUES


def _build_llm_settings(profile_name: str, use_online: bool) -> tuple[object, str]:
    from openai import OpenAI

    settings = resolve_professor_llm_settings(profile_name)
    if use_online:
        base_url = settings["online_llm_base_url"]
        api_key = settings["online_llm_api_key"]
        model = settings["online_llm_model"]
    else:
        base_url = settings["local_llm_base_url"]
        api_key = settings["local_llm_api_key"]
        model = settings["local_llm_model"]
    client = OpenAI(base_url=base_url, api_key=api_key or "EMPTY", timeout=60.0)
    return client, model


def _load_rows(
    conn: psycopg.Connection,
    *,
    limit: int | None,
    only_no_verified_link: bool = False,
    all_sources: bool = False,
) -> list[_ScanRow]:
    sql = """
        SELECT p.paper_id,
               p.title_clean,
               p.authors_display,
               p.year,
               p.venue,
               p.abstract_clean,
               p.canonical_source,
               p.identity_status,
               p.quality_status,
               ppl.link_id::text AS link_id,
               ppl.link_status,
               ppl.professor_id,
               prof.canonical_name,
               pa.institution,
               pa.title AS department,
               COALESCE(
                   array_remove(
                       array_agg(pf.value_raw ORDER BY pf.created_at)
                       FILTER (
                           WHERE pf.fact_type = 'research_topic'
                             AND pf.status = 'active'
                             AND pf.value_raw IS NOT NULL
                       ),
                       NULL
                   ),
                   ARRAY[]::text[]
               ) AS research_directions
          FROM paper p
          JOIN professor_paper_link ppl
            ON ppl.paper_id = p.paper_id
          JOIN professor prof
            ON prof.professor_id = ppl.professor_id
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = ppl.professor_id
           AND pa.is_primary = true
          LEFT JOIN professor_fact pf
            ON pf.professor_id = ppl.professor_id
         WHERE p.identity_status != 'merged'
           AND (%s OR p.canonical_source = 'prof_page_only')
           AND (
             NOT %s OR NOT EXISTS (
               SELECT 1 FROM professor_paper_link ppl
                WHERE ppl.paper_id = p.paper_id AND ppl.link_status = 'verified'
             )
           )
         GROUP BY p.paper_id,
                  p.title_clean,
                  p.authors_display,
                  p.year,
                  p.venue,
                  p.abstract_clean,
                  p.canonical_source,
                  p.identity_status,
                  p.quality_status,
                  ppl.link_id,
                  ppl.link_status,
                  ppl.professor_id,
                  prof.canonical_name,
                  pa.institution,
                  pa.title
         ORDER BY p.paper_id, ppl.professor_id
    """
    params: list[object] = [all_sources, only_no_verified_link]
    if limit is not None:
        sql += "\n         LIMIT %s"
        params.append(limit)
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [_scan_row(row) for row in rows]


async def _scan_rows(
    conn: psycopg.Connection,
    *,
    rows: list[_ScanRow],
    llm_client: object,
    llm_model: str,
    apply_mode: bool,
    run_id: str,
    jsonl_handle: TextIO | None,
    json_output_path: Path | None,
    scan_started_at: str,
) -> _ScanStats:
    stats = _ScanStats()
    link_decisions = await _verify_and_reconcile_links(
        conn,
        rows=rows,
        llm_client=llm_client,
        llm_model=llm_model,
        apply_mode=apply_mode,
        stats=stats,
    )
    paper_records = _paper_records(rows=rows, link_decisions=link_decisions)

    for paper_id in sorted(paper_records):
        record = paper_records[paper_id]
        stats.examined += 1
        row_decision = decide_identity_status_rejection(
            has_verified_link=record.has_verified_link,
            canonical_source=record.row.canonical_source,
            title_clean=record.row.title_clean,
        )
        gate_evidence = _gate_evidence(record)
        action_taken = "none"

        if record.row.identity_status == "rejected" and record.has_verified_link:
            stats.flipped_back += 1
            action_taken = "would_restore"
            if apply_mode:
                restore_result = restore_identity_status(conn, paper_id=paper_id)
                if restore_result.restored:
                    stats.restored += 1
                action_taken = "restored" if restore_result.restored else "restore_noop"
        elif row_decision.action == "reject":
            stats.rejected += 1
            action_taken = "would_reject"
            if apply_mode:
                result = apply_identity_status_rejection(
                    conn,
                    paper_id=paper_id,
                    run_id=run_id,
                    evidence=gate_evidence,
                    prior_identity_status=record.row.identity_status,
                )
                stats.issues_filed += result.issues_filed
                if result.identity_updated:
                    stats.identity_updates += 1
                action_taken = "rejected" if result.identity_updated else "reject_noop"
        else:
            stats.unchanged += 1

        _emit_jsonl(
            jsonl_handle,
            json_output_path,
            _paper_json_record(
                paper_id=paper_id,
                record=record,
                row_decision=row_decision.action,
                gate_evidence=gate_evidence,
                action_taken=action_taken,
                apply_mode=apply_mode,
                run_id=run_id,
                scan_started_at=scan_started_at,
                examined_index=stats.examined,
            ),
        )

    return stats


async def _verify_and_reconcile_links(
    conn: psycopg.Connection,
    *,
    rows: list[_ScanRow],
    llm_client: object,
    llm_model: str,
    apply_mode: bool,
    stats: _ScanStats,
) -> dict[str, _LinkDecision]:
    decisions: dict[str, _LinkDecision] = {
        row.link_id: _LinkDecision(row=row, target_status=row.link_status)
        for row in rows
    }
    for professor_id, professor_rows in _rows_by_professor(rows).items():
        context = _professor_context(professor_rows[0])
        candidates = [
            _candidate(row, index=index)
            for index, row in enumerate(professor_rows)
            if row.link_status in {"candidate", "verified"}
        ]
        if not candidates:
            continue
        candidate_rows = [
            row for row in professor_rows if row.link_status in {"candidate", "verified"}
        ]
        gate_decisions = await batch_verify_paper_identity(
            professor_context=context,
            candidates=candidates,
            llm_client=llm_client,
            llm_model=llm_model,
        )
        for row, decision in zip(candidate_rows, gate_decisions, strict=True):
            if decision.error is not None:
                stats.gate_errors += 1
            outcome = _apply_decision(
                conn,
                link_id=row.link_id,
                decision=decision,
                current_status=row.link_status,
                dry_run=not apply_mode,
            )
            if outcome == "promoted":
                stats.links_promoted += 1
            elif outcome == "rejected":
                stats.links_rejected += 1
            else:
                stats.links_unchanged += 1
            decisions[row.link_id] = _LinkDecision(
                row=row,
                target_status="verified" if decision.accepted else "rejected",
                decision=decision,
            )
        _ = professor_id
    return decisions


def _paper_records(
    *,
    rows: list[_ScanRow],
    link_decisions: dict[str, _LinkDecision],
) -> dict[str, _PaperDecisionRecord]:
    records: dict[str, _PaperDecisionRecord] = {}
    for row in rows:
        record = records.setdefault(row.paper_id, _PaperDecisionRecord(row=row))
        record.link_decisions.append(link_decisions[row.link_id])
    return records


def _paper_json_record(
    *,
    paper_id: str,
    record: _PaperDecisionRecord,
    row_decision: str,
    gate_evidence: dict[str, object],
    action_taken: str,
    apply_mode: bool,
    run_id: str,
    scan_started_at: str,
    examined_index: int,
) -> dict[str, object]:
    chosen = _representative_gate_decision(record)
    return {
        "paper_id": paper_id,
        "verdict": row_decision,
        "confidence": chosen.confidence if chosen is not None else None,
        "reasoning": chosen.reasoning if chosen is not None else "",
        "prior_identity_status": record.row.identity_status,
        "canonical_source": record.row.canonical_source,
        "has_verified_link": record.has_verified_link,
        "gate_source_spans": gate_evidence.get("source_spans", []),
        "gate_decisions": gate_evidence.get("gate_decisions", []),
        "action_taken": action_taken,
        "apply_mode": apply_mode,
        "run_id": run_id,
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
        "apply_mode": args.apply,
        "examined": stats.examined,
        "rejected": stats.rejected,
        "unchanged": stats.unchanged,
        "flipped_back": stats.flipped_back,
        "restored": stats.restored,
        "issues_filed": stats.issues_filed,
        "identity_updates": stats.identity_updates,
        "links_promoted": stats.links_promoted,
        "links_rejected": stats.links_rejected,
        "links_unchanged": stats.links_unchanged,
        "gate_errors": stats.gate_errors,
        "database_dsn_host": dsn_host,
        "database_name": database_name,
    }


def _gate_evidence(record: _PaperDecisionRecord) -> dict[str, object]:
    decisions = []
    source_spans = []
    for item in record.link_decisions:
        if item.decision is None:
            continue
        decisions.append(
            {
                "professor_id": item.row.professor_id,
                "link_id": item.row.link_id,
                "accepted": item.decision.accepted,
                "confidence": item.decision.confidence,
                "reasoning": item.decision.reasoning,
                "topic_consistency": item.decision.topic_consistency,
                "error": item.decision.error,
            }
        )
        source_spans.append(
            {
                "paper_id": item.row.paper_id,
                "link_id": item.row.link_id,
                "professor_id": item.row.professor_id,
                "title": item.row.title_clean,
            }
        )
    return {"gate_decisions": decisions, "source_spans": source_spans}


def _representative_gate_decision(
    record: _PaperDecisionRecord,
) -> PaperIdentityDecision | None:
    rejected = [
        item.decision
        for item in record.link_decisions
        if item.decision is not None and not item.decision.accepted
    ]
    if rejected:
        return rejected[0]
    for item in record.link_decisions:
        if item.decision is not None:
            return item.decision
    return None


def _scan_row(row: dict[str, object]) -> _ScanRow:
    return _ScanRow(
        paper_id=str(row["paper_id"]),
        title_clean=str(row.get("title_clean") or ""),
        authors_display=_optional_text(row.get("authors_display")),
        year=int(row["year"]) if row.get("year") is not None else None,
        venue=_optional_text(row.get("venue")),
        abstract_clean=_optional_text(row.get("abstract_clean")),
        canonical_source=str(row.get("canonical_source") or ""),
        identity_status=str(row.get("identity_status") or "unverified"),
        quality_status=_optional_text(row.get("quality_status")),
        link_id=str(row["link_id"]),
        link_status=str(row.get("link_status") or ""),
        professor_id=str(row["professor_id"]),
        canonical_name=str(row.get("canonical_name") or ""),
        institution=_optional_text(row.get("institution")),
        department=_optional_text(row.get("department")),
        research_directions=_research_directions(row.get("research_directions")),
    )


def _rows_by_professor(rows: list[_ScanRow]) -> dict[str, list[_ScanRow]]:
    grouped: dict[str, list[_ScanRow]] = {}
    for row in rows:
        grouped.setdefault(row.professor_id, []).append(row)
    return grouped


def _professor_context(row: _ScanRow) -> ProfessorContext:
    return ProfessorContext(
        name=row.canonical_name,
        institution=row.institution or "未知",
        department=row.department,
        research_directions=list(row.research_directions) or None,
    )


def _candidate(row: _ScanRow, *, index: int) -> PaperIdentityCandidate:
    authors = [item.strip() for item in (row.authors_display or "").split(",") if item.strip()]
    return PaperIdentityCandidate(
        index=index,
        title=row.title_clean,
        authors=authors,
        year=row.year,
        venue=row.venue,
        abstract=row.abstract_clean,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _research_directions(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    try:
        return tuple(str(item) for item in value if str(item).strip())
    except TypeError:
        return ()


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


def _emit_disabled_summary(json_output_path: Path | None) -> None:
    handle: TextIO | None = None
    try:
        if json_output_path is not None:
            handle = _open_jsonl(json_output_path)
        _emit_jsonl(handle, json_output_path, {"summary": True, "disabled": True, "examined": 0})
    finally:
        if handle is not None:
            handle.close()


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


async def _run(args: argparse.Namespace) -> int:
    json_output_path = _json_output_path(args)
    if not _paper_identity_gate_enabled():
        _emit_disabled_summary(json_output_path)
        print("PAPER_IDENTITY_GATE_ENABLED disabled; skipping paper identity scan.")
        return 0

    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print(
            "Refusing to scan miroflow_real without --confirm-real-db.",
            file=sys.stderr,
        )
        return 2

    _strip_proxy_env()
    llm_client, llm_model = _build_llm_settings(args.llm_profile, args.use_online)
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
                                "task": "paper_identity_scan",
                                "limit": args.limit,
                                "dry_run": False,
                            },
                            triggered_by=_TRIGGERED_BY,
                        ),
                        writer_name="run_paper_identity_scan",
                    )
                )
                conn.commit()

            rows = _load_rows(
                conn,
                limit=args.limit,
                only_no_verified_link=args.only_no_verified_link,
                all_sources=args.all_sources,
            )
            stats = await _scan_rows(
                conn,
                rows=rows,
                llm_client=llm_client,
                llm_model=llm_model,
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
                    status="partial" if stats.gate_errors else "succeeded",
                    items_processed=stats.examined,
                    items_failed=stats.gate_errors,
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
    except Exception as exc:
        if args.apply and not str(run_id).startswith("dry-run-"):
            try:
                with psycopg.connect(dsn, row_factory=dict_row) as conn:
                    close_pipeline_run(
                        conn,
                        run_id,
                        status="failed",
                        error_summary={"message": str(exc)},
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
    print(f"Flipped back: {stats.flipped_back}")
    print(f"Restored: {stats.restored}")
    print(f"Apply mode: {args.apply}")
    if json_output_path is not None:
        print(f"archived to {json_output_path}", file=sys.stderr)
    return 0


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
