"""Backfill company.profile_summary and technology_route_summary via Gemma4."""

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

from src.data_agents.company.narrative_enrichment import (  # noqa: E402
    NarrativeResult,
    generate_company_narrative,
)
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)

logger = logging.getLogger("run_company_narrative_backfill")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill company narrative summary fields via Gemma4.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max companies to process")
    only_group = parser.add_mutually_exclusive_group()
    only_group.add_argument(
        "--only-missing",
        dest="only_missing",
        action="store_true",
        help="Only process companies missing either narrative field (default)",
    )
    only_group.add_argument(
        "--all",
        dest="only_missing",
        action="store_false",
        help="Process all resolved companies and overwrite narrative fields",
    )
    parser.set_defaults(only_missing=True)
    parser.add_argument(
        "--resume",
        nargs="?",
        const="",
        default=None,
        help="Checkpoint JSONL path to skip already-processed company_ids",
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
    base = _REPO_ROOT / "logs" / "data_agents" / "company" / "narrative_backfill_runs"
    return base / f"{run_id}.jsonl"


def _load_resume_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    company_ids: set[str] = set()
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
            if isinstance(row, dict) and isinstance(row.get("company_id"), str):
                company_ids.add(row["company_id"])
    return company_ids


def _append_checkpoint(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_select_sql(
    *,
    only_missing: bool,
    limit: int | None,
) -> tuple[str, tuple[Any, ...]]:
    conditions = ["c.identity_status = 'resolved'"]
    params: list[Any] = []
    if only_missing:
        conditions.append(
            "(c.profile_summary IS NULL OR c.technology_route_summary IS NULL)"
        )
    sql = (
        "SELECT c.company_id, c.canonical_name, latest_snapshot.industry, c.hq_city, "
        "       c.profile_summary, c.technology_route_summary, "
        "       latest_snapshot.description "
        "  FROM company c "
        "  LEFT JOIN LATERAL ("
        "       SELECT cs.industry, cs.description "
        "         FROM company_snapshot cs "
        "        WHERE cs.company_id = c.company_id "
        "        ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC "
        "        LIMIT 1"
        "  ) latest_snapshot ON true "
        f" WHERE {' AND '.join(conditions)} "
        " ORDER BY c.company_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _persist_narrative(
    conn: Any,
    *,
    company_id: str,
    result: NarrativeResult,
    run_id: str,
) -> None:
    conn.execute(
        """
        UPDATE company
           SET profile_summary = %s,
               technology_route_summary = %s,
               updated_at = now(),
               run_id = %s
         WHERE company_id = %s
        """,
        (
            result.profile_summary,
            result.technology_route_summary,
            run_id,
            company_id,
        ),
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
                "task": "company_narrative_backfill",
                "only_missing": args.only_missing,
                "limit": args.limit,
                "resume": args.resume,
                "dry_run": args.dry_run,
            },
            triggered_by="run_company_narrative_backfill",
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
        "companies_total": len(rows),
        "companies_processed": 0,
        "companies_skipped": 0,
        "narratives_written": 0,
        "narratives_rejected": 0,
        "companies_with_errors": 0,
        "dry_run": args.dry_run,
    }

    for row in rows:
        company_id = str(row["company_id"])
        if company_id in resume_ids:
            report["companies_skipped"] += 1
            continue

        description = row.get("description")
        if len((description or "").strip()) < 30:
            report["companies_skipped"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"company_id": company_id, "status": "skipped_short_input"},
            )
            continue

        report["companies_processed"] += 1
        try:
            result = generate_company_narrative(
                company_name=str(row.get("canonical_name") or ""),
                industry=row.get("industry"),
                hq_city=row.get("hq_city"),
                description=description,
                llm_client=llm,
                llm_model=llm_model,
                extra_body=extra_body,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Company %s narrative generation crashed: %s", company_id, exc)
            report["companies_with_errors"] += 1
            try:
                conn.rollback()
            except Exception:
                pass
            _append_checkpoint(
                checkpoint_path,
                {"company_id": company_id, "status": "error", "error": str(exc)},
            )
            continue

        if result.error is None:
            if not args.dry_run:
                try:
                    _persist_narrative(
                        conn,
                        company_id=company_id,
                        result=result,
                        run_id=run_id,
                    )
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Persist failed for company %s: %s", company_id, exc)
                    report["companies_with_errors"] += 1
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    _append_checkpoint(
                        checkpoint_path,
                        {
                            "company_id": company_id,
                            "status": "persist_error",
                            "error": str(exc),
                        },
                    )
                    continue
            report["narratives_written"] += 1
            _append_checkpoint(
                checkpoint_path,
                {
                    "company_id": company_id,
                    "status": "dry_run_success" if args.dry_run else "written",
                    "profile_chars": len(result.profile_summary),
                    "technology_route_chars": len(result.technology_route_summary),
                },
            )
        else:
            report["narratives_rejected"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"company_id": company_id, "status": "rejected", "error": result.error},
            )

    report["duration_seconds"] = round(time.monotonic() - started_at, 2)
    close_status = (
        "partial"
        if report["companies_with_errors"] or report["narratives_rejected"]
        else "succeeded"
    )
    try:
        close_pipeline_run(
            conn,
            run_id,
            status=close_status,
            items_processed=report["companies_processed"],
            items_failed=report["companies_with_errors"] + report["narratives_rejected"],
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
