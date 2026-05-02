#!/usr/bin/env python3
"""Fetch company news from configured APIs and write company_news_item."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.company.news_connectors import (  # noqa: E402
    CNStockConnector,
    NewsConnector,
    NewsRecord,
    SerperNewsConnector,
    TushareConnector,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)
from src.data_agents.taxonomy.domain_tier import resolve_tier  # noqa: E402

logger = logging.getLogger("run_company_news_ingest")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch company news and write company_news_item.",
    )
    parser.add_argument(
        "--priority",
        choices=("top200", "others", "all"),
        default="top200",
        help="Company priority group to process.",
    )
    parser.add_argument(
        "--connector",
        choices=("all", "tushare", "cnstock", "serper"),
        default="all",
        help="News connector to use. all defaults to Serper only.",
    )
    parser.add_argument("--since", type=_parse_date, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=1.0,
        help="Throttle between API calls. Keep at 1-2 sec for Tushare.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Fetch but do not write rows"
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def _default_since() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=7)


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _build_connectors(selection: str) -> list[tuple[str, NewsConnector]]:
    connectors: list[tuple[str, NewsConnector]] = []
    if selection in ("all", "serper"):
        api_key = os.environ.get("SERPER_API_KEY", "").strip()
        if api_key:
            connectors.append(("serper", SerperNewsConnector(api_key)))
        else:
            logger.info("Skipping Serper connector: SERPER_API_KEY is not set")
    if selection == "tushare":
        token = os.environ.get("TUSHARE_TOKEN", "").strip()
        if token:
            connectors.append(("tushare", TushareConnector(token)))
        else:
            logger.info("Skipping Tushare connector: TUSHARE_TOKEN is not set")
    if selection == "cnstock":
        token = os.environ.get("CNSTOCK_TOKEN", "").strip()
        if token:
            connectors.append(("cnstock", CNStockConnector(token)))
        else:
            logger.info("Skipping CNStock connector: CNSTOCK_TOKEN is not set")
    return connectors


def _build_company_select_sql(
    *, priority: str, limit: int | None
) -> tuple[str, tuple[Any, ...]]:
    where_rank = ""
    if priority == "top200":
        where_rank = " WHERE priority_rank <= 200"
    elif priority == "others":
        where_rank = " WHERE priority_rank > 200"

    sql = (
        "WITH ranked_company AS ("
        "  SELECT c.company_id, c.unified_credit_code, c.canonical_name, c.website_host, "
        "         row_number() OVER ("
        "           ORDER BY COALESCE(latest_snapshot.star_rating, 0) DESC, "
        "                    COALESCE(latest_snapshot.reported_news_count, 0) DESC, "
        "                    c.company_id"
        "         ) AS priority_rank "
        "    FROM company c "
        "    LEFT JOIN LATERAL ("
        "      SELECT cs.star_rating, cs.reported_news_count "
        "        FROM company_snapshot cs "
        "       WHERE cs.company_id = c.company_id "
        "       ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC "
        "       LIMIT 1"
        "    ) latest_snapshot ON true "
        "   WHERE c.identity_status = 'resolved' "
        "     AND c.unified_credit_code IS NOT NULL "
        "     AND btrim(c.unified_credit_code) <> ''"
        ") "
        "SELECT company_id, unified_credit_code, canonical_name, website_host, priority_rank "
        "  FROM ranked_company"
        f"{where_rank}"
        " ORDER BY priority_rank"
    )
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _dedupe_by_source_url(records: list[NewsRecord]) -> list[NewsRecord]:
    seen: set[str] = set()
    deduped: list[NewsRecord] = []
    for record in records:
        url = record.source_url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(record)
    return deduped


def _insert_news_records(
    conn: Any,
    *,
    records: list[NewsRecord],
    run_id: str,
    company_host: str | None,
) -> int:
    run_id = require_real_run_id(run_id, writer_name="_insert_news_records")
    inserted = 0
    for record in records:
        source_domain = _source_domain(record.source_url)
        source_domain_tier = resolve_tier(
            source_domain, {company_host} if company_host else None
        )
        confidence = _confidence_for_tier(source_domain_tier)
        row = conn.execute(
            """
            INSERT INTO company_news_item (
                company_id, source_url, source_domain, source_domain_tier,
                published_at, fetched_at, title, summary_clean, content_clean_path,
                is_company_confirmed, refresh_run_id, confidence
            )
            VALUES (%s, %s, %s, %s, %s, now(), %s, %s, NULL, true, %s, %s)
            ON CONFLICT (source_url) DO NOTHING
            RETURNING news_id
            """,
            (
                record.company_id,
                record.source_url,
                source_domain,
                source_domain_tier,
                record.published_at,
                record.title,
                record.summary,
                run_id,
                confidence,
            ),
        ).fetchone()
        if row is not None:
            inserted += 1
    return inserted


def _source_domain(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc and "://" not in url:
        parsed = urlparse(f"https://{url}")
    host = (parsed.netloc or parsed.path.split("/", 1)[0]).lower()
    host = host.split("@")[-1].split(":", 1)[0]
    return host.removeprefix("www.") or "unknown"


def _confidence_for_tier(tier: str) -> Decimal:
    if tier == "official":
        return Decimal("0.90")
    if tier == "trusted":
        return Decimal("0.80")
    return Decimal("0.60")


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
                "task": "company_news_ingest",
                "priority": args.priority,
                "connector": args.connector,
                "since": since.isoformat(),
                "limit": args.limit,
                "dry_run": args.dry_run,
            },
            triggered_by="run_company_news_ingest",
        )
    )
    conn.commit()

    connectors = _build_connectors(args.connector)
    sql, params = _build_company_select_sql(priority=args.priority, limit=args.limit)
    companies = conn.execute(sql, params).fetchall()
    report: dict[str, Any] = {
        "run_id": run_id,
        "priority": args.priority,
        "since": since.isoformat(),
        "companies_total": len(companies),
        "companies_processed": 0,
        "connectors_enabled": [name for name, _connector in connectors],
        "news_fetched": 0,
        "news_would_write": 0,
        "news_inserted": 0,
        "companies_with_errors": 0,
        "dry_run": args.dry_run,
    }

    for company in companies:
        company_id = str(company["company_id"])
        credit_code = str(company["unified_credit_code"])
        canonical_name = str(company.get("canonical_name") or company_id)
        report["companies_processed"] += 1
        company_records: list[NewsRecord] = []
        for connector_name, connector in connectors:
            try:
                fetch_key = canonical_name if connector_name == "serper" else credit_code
                fetched = connector.fetch(fetch_key, since)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "%s fetch crashed for %s: %s", connector_name, company_id, exc
                )
                report["companies_with_errors"] += 1
                fetched = []
            report["news_fetched"] += len(fetched)
            company_records.extend(
                replace(record, company_id=company_id) for record in fetched
            )
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

        deduped = _dedupe_by_source_url(company_records)
        if args.dry_run:
            report["news_would_write"] += len(deduped)
            continue

        try:
            inserted = _insert_news_records(
                conn,
                records=deduped,
                run_id=run_id,
                company_host=company.get("website_host"),
            )
            conn.commit()
            report["news_inserted"] += inserted
        except Exception as exc:  # noqa: BLE001
            logger.warning("Persist failed for company %s: %s", company_id, exc)
            report["companies_with_errors"] += 1
            conn.rollback()

    close_status = "partial" if report["companies_with_errors"] else "succeeded"
    close_pipeline_run(
        conn,
        run_id,
        status=close_status,
        items_processed=report["companies_processed"],
        items_failed=report["companies_with_errors"],
    )
    conn.commit()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
