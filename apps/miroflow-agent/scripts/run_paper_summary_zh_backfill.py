"""Backfill paper.summary_zh from paper.abstract_clean via Gemma4."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.paper.abstract_translator import (  # noqa: E402
    _zh_char_ratio,
    translate_abstract_to_zh,
)
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)

logger = logging.getLogger("run_paper_summary_zh_backfill")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill paper.summary_zh from English abstracts via Gemma4.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max papers to process")
    only_group = parser.add_mutually_exclusive_group()
    only_group.add_argument(
        "--only-missing",
        dest="only_missing",
        action="store_true",
        help="Only process papers missing summary_zh (default)",
    )
    only_group.add_argument(
        "--all",
        dest="only_missing",
        action="store_false",
        help="Process all papers with abstract_clean and overwrite summary_zh",
    )
    parser.set_defaults(only_missing=True)
    parser.add_argument(
        "--resume",
        nargs="?",
        const="",
        default=None,
        help="Checkpoint JSONL path to skip already-processed paper_ids",
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _open_llm_client():
    from openai import OpenAI

    settings = resolve_professor_llm_settings("gemma4", include_profile=True)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        timeout=90.0,
    )
    extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
    return client, settings["local_llm_model"], extra_body


def _resolve_checkpoint_path(resume_arg: str | None, run_id: str) -> Path:
    if resume_arg:
        return Path(resume_arg)
    base = _REPO_ROOT / "logs" / "data_agents" / "paper" / "summary_zh_runs"
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
    only_missing: bool,
    limit: int | None,
) -> tuple[str, tuple[Any, ...]]:
    conditions = [
        "p.abstract_clean IS NOT NULL",
        "length(trim(p.abstract_clean)) > 0",
    ]
    params: list[Any] = []
    if only_missing:
        conditions.append("(p.summary_zh IS NULL OR length(trim(p.summary_zh)) = 0)")
    sql = (
        "SELECT p.paper_id, p.title_clean, p.title_raw, p.abstract_clean, p.summary_zh "
        "  FROM paper p "
        f" WHERE {' AND '.join(conditions)} "
        " ORDER BY p.paper_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _persist_summary_zh(
    conn: Any,
    *,
    paper_id: str,
    summary_zh: str,
    run_id: str,
) -> None:
    conn.execute(
        """
        UPDATE paper
           SET summary_zh = %s,
               updated_at = now(),
               run_id = %s
         WHERE paper_id = %s
        """,
        (summary_zh, run_id, paper_id),
    )


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
                "task": "paper_summary_zh_backfill",
                "only_missing": args.only_missing,
                "limit": args.limit,
                "resume": args.resume,
                "dry_run": args.dry_run,
            },
            triggered_by="run_paper_summary_zh_backfill",
        )
    )
    conn.commit()

    resume_path: Path | None = None
    if args.resume is not None:
        resume_path = _resolve_checkpoint_path(args.resume, run_id)
    resume_ids = _load_resume_ids(resume_path) if resume_path else set()
    checkpoint_path = _resolve_checkpoint_path(None, run_id)

    llm, llm_model, extra_body = _open_llm_client()
    sql, params = _build_select_sql(only_missing=args.only_missing, limit=args.limit)
    rows = conn.execute(sql, params).fetchall()

    started_at = time.monotonic()
    report: dict[str, Any] = {
        "run_id": run_id,
        "papers_total": len(rows),
        "papers_processed": 0,
        "papers_skipped": 0,
        "summaries_written": 0,
        "summaries_rejected": 0,
        "papers_with_errors": 0,
        "dry_run": args.dry_run,
    }

    for row in rows:
        paper_id = str(row["paper_id"])
        if paper_id in resume_ids:
            report["papers_skipped"] += 1
            continue

        abstract = row.get("abstract_clean")
        if not abstract or not str(abstract).strip():
            report["papers_skipped"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "skipped_no_abstract"},
            )
            continue
        if _zh_char_ratio(str(abstract)) > 0.6:
            report["papers_skipped"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "skipped_already_zh"},
            )
            continue

        report["papers_processed"] += 1
        try:
            summary_zh = translate_abstract_to_zh(
                str(abstract),
                llm_client=llm,
                llm_model=llm_model,
                extra_body=extra_body,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Paper %s summary_zh generation crashed: %s", paper_id, exc)
            report["papers_with_errors"] += 1
            try:
                conn.rollback()
            except Exception:
                pass
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "error", "error": str(exc)},
            )
            continue

        if summary_zh:
            if not args.dry_run:
                try:
                    _persist_summary_zh(
                        conn,
                        paper_id=paper_id,
                        summary_zh=summary_zh,
                        run_id=run_id,
                    )
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Persist failed for paper %s: %s", paper_id, exc)
                    report["papers_with_errors"] += 1
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    _append_checkpoint(
                        checkpoint_path,
                        {
                            "paper_id": paper_id,
                            "status": "persist_error",
                            "error": str(exc),
                        },
                    )
                    continue
            report["summaries_written"] += 1
            _append_checkpoint(
                checkpoint_path,
                {
                    "paper_id": paper_id,
                    "status": "dry_run_success" if args.dry_run else "written",
                    "chars": len(summary_zh),
                },
            )
        else:
            report["summaries_rejected"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "rejected"},
            )

    report["duration_seconds"] = round(time.monotonic() - started_at, 2)
    close_status = (
        "partial"
        if report["papers_with_errors"] or report["summaries_rejected"]
        else "succeeded"
    )
    try:
        close_pipeline_run(
            conn,
            run_id,
            status=close_status,
            items_processed=report["papers_processed"],
            items_failed=report["papers_with_errors"] + report["summaries_rejected"],
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
