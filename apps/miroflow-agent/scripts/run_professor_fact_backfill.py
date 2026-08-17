"""Backfill structured professor facts from profile_raw_text."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import psycopg
from psycopg.rows import dict_row

try:  # pragma: no cover - exercised via monkeypatch in tests.
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.professor.fact_extraction import (  # noqa: E402
    ProfessorFactBackfillReport,
    preflight_professor_fact_backfill,
    run_professor_fact_backfill,
)
from src.data_agents.professor.llm_profiles import (  # noqa: E402
    resolve_professor_llm_settings,
)
from src.data_agents.professor.models import (  # noqa: E402
    EnrichedProfessorProfile,
    OfficialAnchorProfile,
)
from src.data_agents.professor.summary_generator import generate_summaries  # noqa: E402
from src.data_agents.professor.translation_spec import LLM_EXTRA_BODY  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    DRY_RUN_SENTINEL_RUN_ID,
    close_pipeline_run,
    open_pipeline_run,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill professor experience facts from profile_raw_text.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--professor-id",
        dest="professor_ids",
        action="append",
        default=[],
        help="Process a specific professor id; may be repeated.",
    )
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--llm-profile", default="gemma4")
    return parser.parse_args(argv)


def _open_database_connection(dsn: str):
    return psycopg.connect(dsn, row_factory=dict_row)


def _open_llm_client(profile: str):
    if OpenAI is None:
        raise RuntimeError("openai package is required for professor fact backfill")
    settings = resolve_professor_llm_settings(profile, include_profile=True)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        timeout=90.0,
        http_client=httpx.Client(trust_env=False, timeout=90.0),
    )
    return client, settings["local_llm_model"], LLM_EXTRA_BODY


def _write_profile_summary(
    conn: Any,
    row: dict[str, Any],
    *,
    run_id: str,
    llm_client: Any,
    llm_model: str,
) -> bool:
    profile = _profile_from_row(row)
    summaries = asyncio.run(
        generate_summaries(
            profile=profile,
            llm_client=llm_client,
            llm_model=llm_model,
        )
    )
    summary = summaries.profile_summary.strip()
    if not summary:
        return False
    conn.execute(
        """
        UPDATE professor
           SET profile_summary = %s,
               run_id = %s,
               updated_at = now()
         WHERE professor_id = %s
        """,
        (summary, run_id, row["professor_id"]),
    )
    return True


def _profile_from_row(row: dict[str, Any]) -> EnrichedProfessorProfile:
    source_url = row.get("primary_source_url") or "unknown"
    return EnrichedProfessorProfile(
        name=str(row.get("canonical_name") or row["professor_id"]),
        institution="",
        department=None,
        title=None,
        profile_summary=str(row.get("profile_summary") or ""),
        evidence_urls=[source_url] if source_url != "unknown" else [],
        profile_url=source_url,
        roster_source=source_url,
        extraction_status="structured_fact_backfill",
        official_anchor_profile=OfficialAnchorProfile(
            source_url=source_url,
            bio_text=str(row.get("profile_raw_text") or ""),
            sparse_anchor=False,
        ),
    )


def _report_to_dict(report: ProfessorFactBackfillReport) -> dict[str, Any]:
    return {
        "processed": report.processed,
        "skipped": report.skipped,
        "failed": report.failed,
        "facts_written": report.facts_written,
        "summaries_written": report.summaries_written,
        "re_evaluated": report.re_evaluated,
        "errors": report.errors,
    }


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        raise SystemExit(1)

    conn = _open_database_connection(dsn)
    preflight = preflight_professor_fact_backfill(conn)
    if args.preflight_only:
        print(json.dumps(preflight.__dict__, ensure_ascii=False, sort_keys=True))
        return

    llm_client, llm_model, extra_body = _open_llm_client(args.llm_profile)
    if args.dry_run:
        run_id = DRY_RUN_SENTINEL_RUN_ID
    else:
        run_id = open_pipeline_run(
            conn,
            run_kind="backfill_real",
            run_scope={
                "task": "professor_fact_extraction_backfill",
                "limit": args.limit,
                "professor_ids": args.professor_ids,
                "dry_run": args.dry_run,
            },
            triggered_by="run_professor_fact_backfill",
        )
        conn.commit()

    try:
        report = run_professor_fact_backfill(
            conn,
            llm_client=llm_client,
            llm_model=llm_model,
            run_id=run_id,
            limit=args.limit,
            professor_ids=args.professor_ids,
            extra_body=extra_body,
            dry_run=args.dry_run,
            summary_writer=lambda conn, row, run_id: _write_profile_summary(
                conn,
                row,
                run_id=str(run_id),
                llm_client=llm_client,
                llm_model=llm_model,
            ),
        )
        if not args.dry_run:
            close_pipeline_run(
                conn,
                run_id,
                status="partial" if report.failed else "succeeded",
                items_processed=report.processed,
                items_failed=report.failed,
                error_summary={"errors": report.errors} if report.errors else None,
            )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        if not args.dry_run:
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                error_summary={"error": str(exc)},
            )
            conn.commit()
        raise
    finally:
        conn.close()

    print(
        json.dumps(
            {
                "preflight": preflight.__dict__,
                "run_id": str(run_id),
                "dry_run": args.dry_run,
                **_report_to_dict(report),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
