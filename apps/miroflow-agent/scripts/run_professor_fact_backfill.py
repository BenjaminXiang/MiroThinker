"""Backfill professor structured facts and profile summaries from raw text."""

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

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from run_professor_quality_re_eval import run_re_eval  # noqa: E402
from src.data_agents.professor.fact_backfill import (  # noqa: E402
    compute_fact_backfill_preflight,
    dedupe_profile_raw_text_for_llm,
    extract_professor_facts,
    persist_extracted_professor_facts,
)
from src.data_agents.professor.llm_profiles import (  # noqa: E402
    resolve_professor_llm_settings,
)
from src.data_agents.professor.profile_summary_contract import (  # noqa: E402
    is_valid_profile_summary,
    profile_summary_contract_violations,
)
from src.data_agents.professor.summary_reinforcement import (  # noqa: E402
    generate_reinforced_profile_summary,
)
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)

logger = logging.getLogger("run_professor_fact_backfill")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill professor facts and profile_summary from profile_raw_text."
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres DSN. Defaults to DATABASE_URL, then DATABASE_URL_TEST.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Offset into eligible profile_raw_text rows; useful for chunked runs.",
    )
    parser.add_argument(
        "--id",
        dest="professor_id",
        action="append",
        default=None,
        help="Professor id to process. Can be repeated.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes.")
    parser.add_argument(
        "--skip-re-eval",
        action="store_true",
        help="Do not invoke the quality re-evaluation step after backfill.",
    )
    parser.add_argument(
        "--min-summary-length",
        type=int,
        default=150,
        help="Only regenerate profile_summary below this length.",
    )
    parser.add_argument(
        "--summary-policy",
        choices=("missing-short", "invalid", "always"),
        default="missing-short",
        help=(
            "When to regenerate profile_summary: current missing/short behavior, "
            "canonical-contract invalid summaries, or every selected row."
        ),
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _open_llm_client():
    import httpx
    from openai import OpenAI

    settings = resolve_professor_llm_settings("gemma4", include_profile=True)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        http_client=httpx.Client(timeout=90.0, trust_env=False),
        timeout=90.0,
    )
    extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
    return client, settings["local_llm_model"], extra_body


def _resolve_database_url(database_url: str | None) -> str:
    dsn = (
        database_url
        or os.environ.get("DATABASE_URL")
        or os.environ.get("DATABASE_URL_TEST")
    )
    if not dsn:
        raise RuntimeError("DATABASE_URL or DATABASE_URL_TEST is required")
    return dsn


def _build_select_sql(
    *,
    limit: int | None,
    offset: int = 0,
    professor_ids: tuple[str, ...] = (),
) -> tuple[str, tuple[Any, ...]]:
    params: list[Any] = []
    conditions = [
        "p.identity_status <> 'merged_into'",
        "p.profile_raw_text IS NOT NULL",
        "length(trim(p.profile_raw_text)) > 0",
    ]
    if professor_ids:
        conditions.append("p.professor_id = ANY(%s)")
        params.append(list(professor_ids))

    sql = (
        "SELECT p.professor_id, p.canonical_name, "
        "       p.profile_summary, p.profile_raw_text, "
        "       p.primary_official_profile_page_id, "
        "       pa.institution, "
        "       COALESCE(rd.directions, ARRAY[]::text[]) AS research_directions "
        "  FROM professor p "
        "  LEFT JOIN LATERAL (SELECT institution "
        "                       FROM professor_affiliation "
        "                      WHERE professor_id = p.professor_id "
        "                      ORDER BY is_primary DESC NULLS LAST, "
        "                               is_current DESC NULLS LAST, "
        "                               start_year DESC NULLS LAST "
        "                      LIMIT 1) pa ON true "
        "  LEFT JOIN LATERAL (SELECT array_agg(value_raw ORDER BY confidence DESC NULLS LAST) "
        "                             AS directions "
        "                       FROM professor_fact "
        "                      WHERE professor_id = p.professor_id "
        "                        AND fact_type = 'research_topic' "
        "                        AND status = 'active') rd ON true "
        f" WHERE {' AND '.join(conditions)} "
        " ORDER BY p.professor_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    if offset:
        sql += " OFFSET %s"
        params.append(int(offset))
    return sql, tuple(params)


def run_backfill(args: argparse.Namespace) -> dict[str, Any]:
    dsn = _resolve_database_url(args.database_url)
    conn = _open_database_connection(dsn)
    started_at = time.monotonic()
    run_id: str | None = None
    try:
        run_id = str(
            open_pipeline_run(
                conn,
                run_kind="backfill_real",
                run_scope={
                    "task": "professor_fact_extraction_expansion",
                    "limit": args.limit,
                    "offset": args.offset,
                    "professor_ids": args.professor_id,
                    "dry_run": args.dry_run,
                    "skip_re_eval": args.skip_re_eval,
                    "summary_policy": args.summary_policy,
                },
                triggered_by="run_professor_fact_backfill",
            )
        )
        conn.commit()

        preflight = compute_fact_backfill_preflight(conn)
        llm, llm_model, extra_body = _open_llm_client()
        sql, params = _build_select_sql(
            limit=args.limit,
            offset=args.offset,
            professor_ids=tuple(args.professor_id or ()),
        )
        rows = conn.execute(sql, params).fetchall()
        report: dict[str, Any] = {
            "run_id": run_id,
            "eligible": len(rows),
            "processed": 0,
            "skipped": int(
                getattr(preflight, "skipped_no_profile_raw_text_count", 0) or 0
            ),
            "failed": 0,
            "facts_written": 0,
            "facts_updated": 0,
            "facts_skipped": 0,
            "facts_retired": 0,
            "summaries_written": 0,
            "re_evaluated": 0,
            "dry_run": bool(args.dry_run),
        }
        successful_professor_ids: list[str] = []

        for row in rows:
            row_dict = dict(row)
            professor_id = str(row_dict["professor_id"])
            report["processed"] += 1
            try:
                profile_text = dedupe_profile_raw_text_for_llm(
                    _profile_text_from_row(row_dict)
                )
                source_page_id = row_dict.get("primary_official_profile_page_id")
                if source_page_id is None:
                    report["skipped"] += 1
                    continue

                extraction = extract_professor_facts(
                    professor_id=professor_id,
                    professor_name=str(row_dict.get("canonical_name") or ""),
                    institution=str(row_dict.get("institution") or ""),
                    profile_raw_text=profile_text,
                    llm_client=llm,
                    llm_model=llm_model,
                    extra_body=extra_body,
                )
                if extraction.error:
                    report["failed"] += 1
                    continue

                if extraction.facts:
                    if args.dry_run:
                        report["facts_written"] += len(extraction.facts)
                    else:
                        fact_report = persist_extracted_professor_facts(
                            conn,
                            facts=extraction.facts,
                            source_page_id=source_page_id,
                            run_id=run_id,
                        )
                        report["facts_written"] += fact_report.facts_written
                        report["facts_updated"] += fact_report.facts_updated
                        report["facts_skipped"] += fact_report.facts_skipped
                        report["facts_retired"] += fact_report.facts_retired

                if _summary_needed(
                    row_dict.get("profile_summary"),
                    min_length=args.min_summary_length,
                    policy=args.summary_policy,
                ):
                    summary_result = generate_reinforced_profile_summary(
                        prof_name=str(row_dict.get("canonical_name") or ""),
                        institution=str(row_dict.get("institution") or ""),
                        research_directions=list(
                            row_dict.get("research_directions") or []
                        ),
                        bio=profile_text,
                        paper_contexts=[],
                        llm_client=llm,
                        llm_model=llm_model,
                        max_papers=0,
                        extra_body=extra_body,
                    )
                    if summary_result.summary:
                        if not args.dry_run:
                            _persist_summary(
                                conn,
                                professor_id=professor_id,
                                summary=summary_result.summary,
                                run_id=run_id,
                            )
                        report["summaries_written"] += 1

                if not args.dry_run:
                    conn.commit()
                successful_professor_ids.append(professor_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Professor %s backfill failed: %s", professor_id, exc)
                report["failed"] += 1
                try:
                    conn.rollback()
                except Exception:
                    pass
                continue

        if successful_professor_ids and not args.skip_re_eval:
            re_eval_report = run_re_eval(
                argparse.Namespace(
                    database_url=dsn,
                    dry_run=bool(args.dry_run),
                    professor_id=successful_professor_ids,
                    limit=None,
                )
            )
            report["re_evaluated"] = int(re_eval_report.get("evaluated", 0) or 0)

        report["duration_seconds"] = round(time.monotonic() - started_at, 2)
        close_status = "partial" if report["failed"] else "succeeded"
        try:
            close_pipeline_run(
                conn,
                run_id,
                status=close_status,
                items_processed=report["processed"],
                items_failed=report["failed"],
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("close_pipeline_run failed for %s: %s", run_id, exc)
        return report
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _profile_text_from_row(row: dict[str, Any]) -> str:
    return str(row.get("profile_raw_text") or "").strip()


def _summary_needed(
    value: object,
    *,
    min_length: int,
    policy: str = "missing-short",
) -> bool:
    text = str(value or "").strip()
    if policy == "always":
        return True
    if policy == "invalid":
        return bool(profile_summary_contract_violations(text))
    return len(text) < int(min_length)


def _persist_summary(
    conn: Any,
    *,
    professor_id: str,
    summary: str,
    run_id: str,
) -> None:
    if not is_valid_profile_summary(summary):
        violations = ",".join(profile_summary_contract_violations(summary))
        raise ValueError(f"profile_summary violates canonical contract: {violations}")
    conn.execute(
        """
        UPDATE professor
           SET profile_summary = %s,
               updated_at = now(),
               run_id = %s
         WHERE professor_id = %s
        """,
        (summary, run_id, professor_id),
    )


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    report = run_backfill(args)
    print(json.dumps(report, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
