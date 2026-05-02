#!/usr/bin/env python3
"""Extract company_signal_event rows from company_news_item."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.company.signal_event_extractor import (  # noqa: E402
    SignalEventExtraction,
    extract_signal_events_from_news,
)
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings  # noqa: E402
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)

logger = logging.getLogger("run_company_signal_extract")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract company_signal_event rows from company_news_item via Gemma4.",
    )
    parser.add_argument("--since", type=_parse_date, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--include-processed",
        action="store_true",
        help="Also process news already referenced by company_signal_event.",
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def _default_since() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=7)


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


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


def _build_news_select_sql(
    *, since: date, limit: int | None, include_processed: bool
) -> tuple[str, tuple[Any, ...]]:
    conditions = [
        "(n.published_at IS NULL OR n.published_at::date >= %s)",
    ]
    params: list[Any] = [since]
    if not include_processed:
        conditions.append(
            "NOT EXISTS ("
            "  SELECT 1 FROM company_signal_event e "
            "   WHERE e.primary_news_id = n.news_id"
            ")"
        )
    sql = (
        "SELECT n.news_id::text AS news_id, n.company_id, c.canonical_name, "
        "       n.source_url, n.title, n.summary_clean, n.published_at, n.fetched_at "
        "  FROM company_news_item n "
        "  JOIN company c ON c.company_id = n.company_id "
        f" WHERE {' AND '.join(conditions)} "
        " ORDER BY n.published_at DESC NULLS LAST, n.created_at DESC"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _insert_signal_events(
    conn: Any, *, events: tuple[SignalEventExtraction, ...], run_id: str
) -> int:
    require_real_run_id(run_id, writer_name="_insert_signal_events")
    inserted = 0
    for event in events:
        row = conn.execute(
            """
            INSERT INTO company_signal_event (
                company_id, primary_news_id, event_type, event_date,
                event_subject_normalized, event_summary, confidence,
                corroborating_news_ids, dedup_key, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::uuid[], %s, 'active')
            ON CONFLICT (company_id, event_type, dedup_key) DO NOTHING
            RETURNING event_id
            """,
            (
                event.company_id,
                event.primary_news_id,
                event.event_type,
                event.event_date,
                Jsonb(event.event_subject_normalized),
                event.event_summary,
                event.confidence,
                list(event.corroborating_news_ids),
                event.dedup_key,
            ),
        ).fetchone()
        if row is not None:
            inserted += 1
    return inserted


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

    since = args.since or _default_since()
    conn = _open_database_connection(dsn)
    run_id = str(
        open_pipeline_run(
            conn,
            run_kind="news_refresh",
            run_scope={
                "task": "company_signal_extract",
                "since": since.isoformat(),
                "limit": args.limit,
                "include_processed": args.include_processed,
                "dry_run": args.dry_run,
            },
            triggered_by="run_company_signal_extract",
        )
    )
    conn.commit()

    llm, llm_model, extra_body = _open_llm_client()
    sql, params = _build_news_select_sql(
        since=since,
        limit=args.limit,
        include_processed=args.include_processed,
    )
    news_rows = conn.execute(sql, params).fetchall()
    report: dict[str, Any] = {
        "run_id": run_id,
        "since": since.isoformat(),
        "news_total": len(news_rows),
        "news_processed": 0,
        "events_extracted": 0,
        "events_would_write": 0,
        "events_inserted": 0,
        "news_with_errors": 0,
        "dry_run": args.dry_run,
    }

    for row in news_rows:
        report["news_processed"] += 1
        result = extract_signal_events_from_news(
            company_id=str(row["company_id"]),
            company_name=str(row.get("canonical_name") or ""),
            news_id=str(row["news_id"]) if row.get("news_id") else None,
            title=str(row.get("title") or ""),
            summary=row.get("summary_clean"),
            raw_text=row.get("summary_clean"),
            published_at=row.get("published_at") or row.get("fetched_at"),
            llm_client=llm,
            llm_model=llm_model,
            extra_body=extra_body,
        )
        if result.error:
            report["news_with_errors"] += 1
            logger.info(
                "Signal extraction rejected news %s: %s",
                row.get("news_id"),
                result.error,
            )
            continue
        report["events_extracted"] += len(result.events)
        if args.dry_run:
            report["events_would_write"] += len(result.events)
            continue

        try:
            inserted = _insert_signal_events(conn, events=result.events, run_id=run_id)
            conn.commit()
            report["events_inserted"] += inserted
        except Exception as exc:  # noqa: BLE001
            logger.warning("Persist failed for news %s: %s", row.get("news_id"), exc)
            report["news_with_errors"] += 1
            conn.rollback()

    close_status = "partial" if report["news_with_errors"] else "succeeded"
    close_pipeline_run(
        conn,
        run_id,
        status=close_status,
        items_processed=report["news_processed"],
        items_failed=report["news_with_errors"],
    )
    conn.commit()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
