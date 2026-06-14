#!/usr/bin/env python3
"""Extract company_signal_event rows from company_news_item."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.data_agents.company.signal_event_extractor import (  # noqa: E402
    SignalEventExtraction,
    SignalExtractionResult,
    extract_signal_events_from_news,
)
from src.data_agents.company.llm_routing import resolve_company_llm_task_settings  # noqa: E402
from src.data_agents.company.provider_rate_limit import wrap_openai_client  # noqa: E402
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)

logger = logging.getLogger("run_company_signal_extract")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract company_signal_event rows from company_news_item via the configured LLM.",
    )
    parser.add_argument("--since", type=_parse_date, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--include-processed",
        action="store_true",
        help="Also process news already referenced by company_signal_event.",
    )
    parser.add_argument(
        "--source-adapter",
        action="append",
        default=[],
        help=(
            "Only process rows from this source_adapter. Repeat for multiple, "
            "for example --source-adapter iyiou --source-adapter pitchhub_36kr."
        ),
    )
    parser.add_argument(
        "--company-id",
        action="append",
        default=[],
        help="Only process this canonical company_id. Repeat for multiple IDs.",
    )
    parser.add_argument(
        "--enrichment-batch-id",
        default=None,
        help="Optional company_enrichment_batch id for reports/checkpoints.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Reserved per-process worker concurrency for signal extraction.",
    )
    parser.add_argument(
        "--llm-timeout-seconds",
        type=float,
        default=None,
        help="Override per-request LLM timeout for this child process.",
    )
    parser.add_argument(
        "--llm-retry-budget",
        type=int,
        default=None,
        help="Override OpenAI SDK max_retries for this child process.",
    )
    parser.add_argument(
        "--checkpoint-stage",
        default=None,
        help="Optional company_enrichment stage name for runner checkpoint metadata.",
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


def _open_llm_client(
    *,
    timeout_seconds: float | None = None,
    retry_budget: int | None = None,
):
    from openai import OpenAI

    settings = resolve_company_llm_task_settings(
        "financing_extraction",
        timeout_seconds=timeout_seconds,
        retry_budget=retry_budget,
    )
    client = OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key or "EMPTY",
        http_client=httpx.Client(timeout=settings.timeout_seconds, trust_env=False),
        timeout=settings.timeout_seconds,
        max_retries=settings.retry_budget,
    )
    return wrap_openai_client(client, provider_key="deepseek"), settings.model, settings.extra_body


def _open_llm_client_with_policy(
    *,
    timeout_seconds: float | None,
    retry_budget: int | None,
):
    if timeout_seconds is None and retry_budget is None:
        return _open_llm_client()
    return _open_llm_client(
        timeout_seconds=timeout_seconds,
        retry_budget=retry_budget,
    )


def _published_context_for_row(row: dict[str, Any]) -> Any:
    published_context = row.get("published_at")
    if row.get("source_adapter") not in {"iyiou", "pitchhub_36kr"}:
        published_context = published_context or row.get("fetched_at")
    return published_context


def _process_news_row(
    row: dict[str, Any],
    *,
    thread_state: threading.local,
    llm_timeout_seconds: float | None,
    llm_retry_budget: int | None,
) -> dict[str, Any]:
    try:
        llm_bundle = getattr(thread_state, "llm_bundle", None)
        if llm_bundle is None:
            llm_bundle = _open_llm_client_with_policy(
                timeout_seconds=llm_timeout_seconds,
                retry_budget=llm_retry_budget,
            )
            thread_state.llm_bundle = llm_bundle
        llm, llm_model, extra_body = llm_bundle
        result = extract_signal_events_from_news(
            company_id=str(row["company_id"]),
            company_name=str(row.get("canonical_name") or ""),
            news_id=str(row["news_id"]) if row.get("news_id") else None,
            title=str(row.get("title") or ""),
            summary=row.get("summary_clean"),
            raw_text=row.get("summary_clean"),
            published_at=_published_context_for_row(row),
            llm_client=llm,
            llm_model=llm_model,
            extra_body=extra_body,
            source_adapter=row.get("source_adapter"),
            source_url=row.get("source_url"),
            baseline_latest_funding_round=row.get("latest_funding_round"),
            baseline_latest_funding_date=row.get("latest_funding_time"),
        )
    except Exception as exc:  # noqa: BLE001
        result = SignalExtractionResult(events=(), error=str(exc))
    return {"row": row, "result": result}


def _process_news_rows(
    rows: list[dict[str, Any]],
    *,
    concurrency: int,
    llm_timeout_seconds: float | None,
    llm_retry_budget: int | None,
) -> list[dict[str, Any]]:
    max_workers = max(1, int(concurrency or 1))
    if max_workers <= 1 or len(rows) <= 1:
        state = threading.local()
        return [
            _process_news_row(
                row,
                thread_state=state,
                llm_timeout_seconds=llm_timeout_seconds,
                llm_retry_budget=llm_retry_budget,
            )
            for row in rows
        ]
    results: list[dict[str, Any] | None] = [None] * len(rows)
    state = threading.local()
    with ThreadPoolExecutor(max_workers=min(max_workers, len(rows))) as executor:
        futures = {
            executor.submit(
                _process_news_row,
                row,
                thread_state=state,
                llm_timeout_seconds=llm_timeout_seconds,
                llm_retry_budget=llm_retry_budget,
            ): index
            for index, row in enumerate(rows)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [result for result in results if result is not None]


def _build_news_select_sql(
    *,
    since: date,
    limit: int | None,
    include_processed: bool,
    source_adapters: tuple[str, ...] = (),
    company_ids: tuple[str, ...] = (),
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
    if source_adapters:
        placeholders = ", ".join(["%s"] * len(source_adapters))
        conditions.append(f"n.source_adapter IN ({placeholders})")
        params.extend(source_adapters)
    if company_ids:
        placeholders = ", ".join(["%s"] * len(company_ids))
        conditions.append(f"n.company_id IN ({placeholders})")
        params.extend(company_ids)
    sql = (
        "SELECT n.news_id::text AS news_id, n.company_id, c.canonical_name, "
        "       n.source_url, n.source_adapter, n.title, n.summary_clean, "
        "       n.published_at, n.fetched_at, "
        "       latest.latest_funding_round, latest.latest_funding_time "
        "  FROM company_news_item n "
        "  JOIN company c ON c.company_id = n.company_id "
        "  LEFT JOIN LATERAL ("
        "    SELECT cs.latest_funding_round, cs.latest_funding_time "
        "      FROM company_snapshot cs "
        "     WHERE cs.company_id = n.company_id "
        "     ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC "
        "     LIMIT 1"
        "  ) latest ON TRUE "
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::uuid[], %s, %s)
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
                event.status,
            ),
        ).fetchone()
        if row is not None:
            inserted += 1
    return inserted


def _source_report_bucket(
    report: dict[str, Any], source_adapter: str | None
) -> dict[str, int]:
    source = source_adapter or "unknown"
    counts = report.setdefault("source_adapter_counts", {})
    if source not in counts:
        counts[source] = {
            "news_processed": 0,
            "events_extracted": 0,
            "events_would_write": 0,
            "events_inserted": 0,
        }
    return counts[source]


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
                "source_adapters": tuple(args.source_adapter),
                "company_ids": tuple(args.company_id),
                "enrichment_batch_id": args.enrichment_batch_id,
                "dry_run": args.dry_run,
                "concurrency": args.concurrency,
                "llm_timeout_seconds": args.llm_timeout_seconds,
                "llm_retry_budget": args.llm_retry_budget,
            },
            triggered_by="run_company_signal_extract",
        )
    )
    conn.commit()

    sql, params = _build_news_select_sql(
        since=since,
        limit=args.limit,
        include_processed=args.include_processed,
        source_adapters=tuple(args.source_adapter),
        company_ids=tuple(args.company_id),
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
        "source_adapters": list(args.source_adapter),
        "enrichment_batch_id": args.enrichment_batch_id,
        "source_adapter_counts": {},
        "dry_run": args.dry_run,
        "concurrency": max(1, int(args.concurrency or 1)),
        "llm_timeout_seconds": args.llm_timeout_seconds,
        "llm_retry_budget": args.llm_retry_budget,
    }

    news_results = _process_news_rows(
        [dict(row) for row in news_rows],
        concurrency=max(1, int(args.concurrency or 1)),
        llm_timeout_seconds=args.llm_timeout_seconds,
        llm_retry_budget=args.llm_retry_budget,
    )

    for news_result in news_results:
        row = news_result["row"]
        result = news_result["result"]
        report["news_processed"] += 1
        source_bucket = _source_report_bucket(report, row.get("source_adapter"))
        source_bucket["news_processed"] += 1
        if result.error:
            report["news_with_errors"] += 1
            logger.info(
                "Signal extraction rejected news %s: %s",
                row.get("news_id"),
                result.error,
            )
            continue
        report["events_extracted"] += len(result.events)
        source_bucket["events_extracted"] += len(result.events)
        if args.dry_run:
            report["events_would_write"] += len(result.events)
            source_bucket["events_would_write"] += len(result.events)
            continue

        try:
            inserted = _insert_signal_events(conn, events=result.events, run_id=run_id)
            conn.commit()
            report["events_inserted"] += inserted
            source_bucket["events_inserted"] += inserted
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
