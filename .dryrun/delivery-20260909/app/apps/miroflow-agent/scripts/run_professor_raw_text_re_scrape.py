"""Re-scrape professor profile_raw_text with supplementary group/lab/CV sources."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.professor.discovery import fetch_html_with_fallback  # noqa: E402
from src.data_agents.professor.multi_source_crawler import (  # noqa: E402
    extract_main_text,
    follow_supplementary_links,
)
from src.data_agents.professor.name_selection import (  # noqa: E402
    is_obvious_non_person_name,
    looks_like_profile_blob,
)
from src.data_agents.professor.profile_summary_contract import (  # noqa: E402
    profile_summary_contract_violations,
)
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)

logger = logging.getLogger("run_professor_raw_text_re_scrape")
_RAW_TEXT_CAP = 30_000
_DEFAULT_MIN_RAW_TEXT_LENGTH = 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill professor.profile_raw_text from primary + supplementary sources.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Max professors to process"
    )
    parser.add_argument(
        "--resume",
        nargs="?",
        const="",
        default=None,
        help="Checkpoint JSONL path to skip already-processed professor_ids",
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--missing-raw-only",
        action="store_true",
        help="Only select professors whose profile_raw_text is missing or blank.",
    )
    parser.add_argument(
        "--summary-invalid-only",
        action="store_true",
        help="Only process rows whose current profile_summary violates the canonical contract.",
    )
    parser.add_argument(
        "--identity-guard",
        action="store_true",
        help="Require the fetched text to contain a non-junk canonical-name anchor.",
    )
    parser.add_argument(
        "--min-raw-text-length",
        type=int,
        default=_DEFAULT_MIN_RAW_TEXT_LENGTH,
        help="Minimum extracted raw text length required before writing.",
    )
    parser.add_argument(
        "--stem-only",
        action="store_true",
        help=(
            "Restrict to STEM disciplines: computer_science / materials / "
            "biomedical / electrical_engineering / mechanical_engineering / "
            "physics / chemistry / mathematics / interdisciplinary. "
            "Skips 'other' and NULL discipline_family."
        ),
    )
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _fetch_html(url: str, timeout: float) -> str | None:
    result = fetch_html_with_fallback(url, timeout=timeout)
    html = result.html if hasattr(result, "html") else result
    return str(html) if html else None


def _resolve_checkpoint_path(resume_arg: str | None, run_id: str) -> Path:
    if resume_arg:
        return Path(resume_arg)
    base = _REPO_ROOT / "logs" / "data_agents" / "professor" / "raw_text_rescrape_runs"
    return base / f"{run_id}.jsonl"


def _load_resume_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    professor_ids: set[str] = set()
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
            prof_id = row.get("professor_id") if isinstance(row, dict) else None
            if isinstance(prof_id, str):
                professor_ids.add(prof_id)
    return professor_ids


def _append_checkpoint(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


_STEM_DISCIPLINE_FAMILIES = (
    "computer_science",
    "materials",
    "biomedical",
    "electrical_engineering",
    "mechanical_engineering",
    "physics",
    "chemistry",
    "mathematics",
    "interdisciplinary",
)


def _build_select_sql(
    limit: int | None = None,
    *,
    stem_only: bool = False,
    missing_raw_only: bool = False,
) -> tuple[str, tuple[Any, ...]]:
    sql = (
        "SELECT p.professor_id, p.canonical_name, p.profile_summary, "
        "       p.profile_raw_text, sp.url AS profile_url "
        "  FROM professor p "
        "  JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id "
        " WHERE p.identity_status = 'resolved' "
        "   AND sp.url LIKE 'http%%' "
    )
    params: list[Any] = []
    if missing_raw_only:
        sql += (
            "   AND (p.profile_raw_text IS NULL "
            "        OR length(trim(p.profile_raw_text)) = 0) "
        )
    if stem_only:
        placeholders = ",".join(["%s"] * len(_STEM_DISCIPLINE_FAMILIES))
        sql += f"   AND p.discipline_family IN ({placeholders}) "
        params.extend(_STEM_DISCIPLINE_FAMILIES)
    sql += " ORDER BY p.professor_id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _strip_nul_bytes(text: str) -> str:
    """PG TEXT columns reject NUL (0x00) bytes; some HTML pages contain them
    (e.g. binary PDF embedded inline)."""
    return text.replace("\x00", "")


def _should_process_row(row: dict[str, Any], *, summary_invalid_only: bool) -> bool:
    if not summary_invalid_only:
        return True
    return bool(profile_summary_contract_violations(row.get("profile_summary")))


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _raw_text_passes_quality_guard(
    row: dict[str, Any],
    raw_text: str,
    *,
    min_length: int,
    identity_guard: bool,
) -> bool:
    text = raw_text.strip()
    if len(text) < max(1, int(min_length)):
        return False
    profile_url = str(row.get("profile_url") or "")
    if not profile_url.startswith(("http://", "https://")):
        return False
    if not identity_guard:
        return True

    canonical_name = str(row.get("canonical_name") or "").strip()
    if (
        not canonical_name
        or is_obvious_non_person_name(canonical_name)
        or looks_like_profile_blob(canonical_name)
    ):
        return False
    compact = _compact_text(text)
    if canonical_name in compact:
        return True
    if len(canonical_name) >= 3 and canonical_name[:2] in compact:
        return True
    return False


def _persist_raw_text(
    conn: Any,
    *,
    professor_id: str,
    raw_text: str,
    run_id: str,
) -> None:
    sanitized = _strip_nul_bytes(raw_text)
    conn.execute(
        """
        UPDATE professor
           SET profile_raw_text = %s,
               updated_at = now(),
               run_id = %s
         WHERE professor_id = %s
        """,
        (sanitized, run_id, professor_id),
    )


def _scrape_raw_text(row: dict[str, Any]) -> tuple[str | None, int]:
    profile_url = str(row.get("profile_url") or "")
    html = _fetch_html(profile_url, 10.0)
    if not html:
        return None, 0
    primary_text = extract_main_text(html)
    supplementary_segments = follow_supplementary_links(
        html,
        profile_url,
        professor_name=str(row.get("canonical_name") or ""),
        max_hops=2,
        fetch_html_fn=_fetch_html,
    )
    raw_text = "\n\n".join([primary_text, *supplementary_segments]).strip()
    return raw_text[:_RAW_TEXT_CAP] if raw_text else None, len(supplementary_segments)


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
    run_id = str(
        open_pipeline_run(
            conn,
            run_kind="backfill_real",
            run_scope={
                "task": "professor_raw_text_re_scrape",
                "limit": args.limit,
                "resume": args.resume,
                "dry_run": args.dry_run,
                "missing_raw_only": args.missing_raw_only,
                "summary_invalid_only": args.summary_invalid_only,
                "identity_guard": args.identity_guard,
                "min_raw_text_length": args.min_raw_text_length,
            },
            triggered_by="run_professor_raw_text_re_scrape",
        )
    )
    conn.commit()

    resume_path: Path | None = None
    if args.resume is not None:
        resume_path = _resolve_checkpoint_path(args.resume, run_id)
    resume_ids = _load_resume_ids(resume_path) if resume_path else set()
    checkpoint_path = _resolve_checkpoint_path(None, run_id)

    sql, params = _build_select_sql(
        args.limit,
        stem_only=args.stem_only,
        missing_raw_only=args.missing_raw_only,
    )
    rows = conn.execute(sql, params).fetchall()
    started_at = time.monotonic()
    report: dict[str, Any] = {
        "run_id": run_id,
        "profs_total": len(rows),
        "profs_processed": 0,
        "profs_skipped": 0,
        "raw_text_written": 0,
        "supplementary_segments": 0,
        "profs_with_errors": 0,
        "skipped_summary_valid": 0,
        "skipped_quality_guard": 0,
        "dry_run": args.dry_run,
    }

    for row in rows:
        professor_id = str(row["professor_id"])
        if professor_id in resume_ids:
            report["profs_skipped"] += 1
            continue
        if not _should_process_row(
            dict(row),
            summary_invalid_only=bool(args.summary_invalid_only),
        ):
            report["profs_skipped"] += 1
            report["skipped_summary_valid"] += 1
            continue

        report["profs_processed"] += 1
        try:
            raw_text, supplementary_count = _scrape_raw_text(dict(row))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Raw-text scrape crashed for prof %s: %s", professor_id, exc)
            report["profs_with_errors"] += 1
            try:
                conn.rollback()
            except Exception:
                pass
            _append_checkpoint(
                checkpoint_path,
                {"professor_id": professor_id, "status": "error", "error": str(exc)},
            )
            continue

        if not raw_text:
            report["profs_skipped"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"professor_id": professor_id, "status": "skipped_no_raw_text"},
            )
            continue
        if not _raw_text_passes_quality_guard(
            dict(row),
            raw_text,
            min_length=int(args.min_raw_text_length),
            identity_guard=bool(args.identity_guard),
        ):
            report["profs_skipped"] += 1
            report["skipped_quality_guard"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"professor_id": professor_id, "status": "skipped_quality_guard"},
            )
            continue

        report["supplementary_segments"] += supplementary_count
        if not args.dry_run:
            try:
                _persist_raw_text(
                    conn,
                    professor_id=professor_id,
                    raw_text=raw_text,
                    run_id=run_id,
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Persist failed for prof %s: %s", professor_id, exc)
                report["profs_with_errors"] += 1
                try:
                    conn.rollback()
                except Exception:
                    pass
                _append_checkpoint(
                    checkpoint_path,
                    {
                        "professor_id": professor_id,
                        "status": "persist_error",
                        "error": str(exc),
                    },
                )
                continue

        report["raw_text_written"] += 1
        _append_checkpoint(
            checkpoint_path,
            {
                "professor_id": professor_id,
                "status": "dry_run_success" if args.dry_run else "written",
                "chars": len(raw_text),
                "supplementary_segments": supplementary_count,
            },
        )

    report["duration_seconds"] = round(time.monotonic() - started_at, 2)
    close_status = "partial" if report["profs_with_errors"] else "succeeded"
    try:
        close_pipeline_run(
            conn,
            run_id,
            status=close_status,
            items_processed=report["profs_processed"],
            items_failed=report["profs_with_errors"],
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


if __name__ == "__main__":
    main()
