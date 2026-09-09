#!/usr/bin/env python3
"""Fetch company news from configured APIs and write company_news_item."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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

from dotenv import load_dotenv
import httpx
import psycopg
import requests
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.data_agents.company.news_connectors import (  # noqa: E402
    CNStockConnector,
    NewsConnector,
    NewsRecord,
    PitchHubNewsConnector,
    SerperNewsConnector,
    SerperSearchConnector,
    TushareConnector,
    YiouNewsConnector,
    YiouSearchContext,
    YiouSearchHints,
    build_generic_identity_queries,
    extract_yiou_search_hints_with_llm,
)
from src.data_agents.company.enrichment_batch import (  # noqa: E402
    mark_company_stage_complete,
    record_search_audit,
)
from src.data_agents.company.llm_routing import resolve_company_llm_task_settings  # noqa: E402
from src.data_agents.company.provider_rate_limit import (  # noqa: E402
    RateLimitedRequestsSession,
    wrap_openai_client,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)
from src.data_agents.taxonomy.domain_tier import resolve_tier  # noqa: E402

logger = logging.getLogger("run_company_news_ingest")
READER_FALLBACK_PREFIX = "https://r.jina.ai/http://r.jina.ai/http://"


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
        choices=("all", "tushare", "cnstock", "serper", "iyiou", "pitchhub"),
        default="all",
        help="News connector to use. all defaults to Serper only.",
    )
    parser.add_argument(
        "--serper-site",
        action="append",
        default=None,
        help="Optional Serper site filter (e.g. data.iyiou.com). Repeat for multiple.",
    )
    parser.add_argument(
        "--serper-fetch-article-text",
        action="store_true",
        help="Try fetching article body text for Serper results.",
    )
    parser.add_argument(
        "--serper-article-max-chars",
        type=int,
        default=1800,
        help="Max chars to keep when Serper article text is fetched.",
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
    parser.add_argument(
        "--company-id",
        action="append",
        default=[],
        help="Only process this canonical company_id. Repeat for multiple IDs.",
    )
    parser.add_argument(
        "--llm-search-hints",
        action="store_true",
        help="Use the configured local LLM to extract aliases/founders/keywords from XLSX text for site search.",
    )
    parser.add_argument(
        "--enrichment-batch-id",
        default=None,
        help="Optional company_enrichment_batch id for per-company search audit rows.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Reserved per-process worker concurrency for company-level web fetch.",
    )
    parser.add_argument(
        "--llm-timeout-seconds",
        type=float,
        default=None,
        help="Override per-request LLM timeout for search-hint generation.",
    )
    parser.add_argument(
        "--llm-retry-budget",
        type=int,
        default=None,
        help="Override OpenAI SDK max_retries for search-hint generation.",
    )
    parser.add_argument(
        "--checkpoint-stage",
        default=None,
        help="Optional company_enrichment stage name for runner checkpoint metadata.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def _default_since() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=7)


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _build_connectors(
    selection: str,
    *,
    serper_site_filters: list[str] | None = None,
    fetch_article_text: bool = False,
    article_max_chars: int = 1800,
) -> list[tuple[str, NewsConnector]]:
    connectors: list[tuple[str, NewsConnector]] = []
    if selection in ("all", "serper"):
        api_key = os.environ.get("SERPER_API_KEY", "").strip()
        if api_key:
            connectors.append(
                (
                    "serper",
                    SerperNewsConnector(
                        api_key,
                        session=RateLimitedRequestsSession(
                            requests.Session(),
                            provider_key="serper",
                        ),
                        site_filters=serper_site_filters,
                        fetch_article_content=fetch_article_text,
                        article_max_chars=article_max_chars,
                    ),
                )
            )
        else:
            logger.info("Skipping Serper connector: SERPER_API_KEY is not set")
    if selection == "iyiou":
        api_key = os.environ.get("SERPER_API_KEY", "").strip()
        if api_key:
            delegate = SerperSearchConnector(
                api_key,
                session=RateLimitedRequestsSession(
                    requests.Session(),
                    provider_key="serper",
                ),
                site_filters=["data.iyiou.com"],
                fetch_article_content=fetch_article_text,
                article_max_chars=article_max_chars,
            )
            connectors.append(("iyiou", YiouNewsConnector(delegate)))
        else:
            logger.info("Skipping Yiou connector: SERPER_API_KEY is not set")
    if selection == "pitchhub":
        api_key = os.environ.get("SERPER_API_KEY", "").strip()
        if api_key:
            delegate = SerperSearchConnector(
                api_key,
                session=RateLimitedRequestsSession(
                    requests.Session(),
                    provider_key="serper",
                ),
                site_filters=["pitchhub.36kr.com"],
                fetch_article_content=False,
                article_max_chars=article_max_chars,
            )
            connectors.append(
                (
                    "pitchhub",
                    PitchHubNewsConnector(
                        delegate,
                        reader_fallback_prefix=READER_FALLBACK_PREFIX,
                        article_max_chars=max(article_max_chars, 4000),
                    ),
                )
            )
        else:
            logger.info("Skipping PitchHub connector: SERPER_API_KEY is not set")
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
    *, priority: str, limit: int | None, company_ids: tuple[str, ...] = ()
) -> tuple[str, tuple[Any, ...]]:
    filters: list[str] = []
    params: list[Any] = []
    if priority == "top200":
        filters.append("priority_rank <= 200")
    elif priority == "others":
        filters.append("priority_rank > 200")
    if company_ids:
        placeholders = ", ".join(["%s"] * len(company_ids))
        filters.append(f"company_id IN ({placeholders})")
        params.extend(company_ids)

    sql = (
        "WITH ranked_company AS ("
        "  SELECT c.company_id, c.unified_credit_code, c.canonical_name, "
        "         c.registered_name, c.aliases, c.website_host, "
        "         latest_snapshot.project_name, latest_snapshot.description, latest_snapshot.team_raw, "
        "         latest_snapshot.company_name_xlsx, "
        "         row_number() OVER ("
        "           ORDER BY COALESCE(latest_snapshot.star_rating, 0) DESC, "
        "                    COALESCE(latest_snapshot.reported_news_count, 0) DESC, "
        "                    c.company_id"
        "         ) AS priority_rank "
        "    FROM company c "
        "    LEFT JOIN LATERAL ("
        "      SELECT cs.star_rating, cs.reported_news_count, "
        "             cs.project_name, cs.description, cs.team_raw, "
        "             cs.company_name_xlsx "
        "        FROM company_snapshot cs "
        "       WHERE cs.company_id = c.company_id "
        "       ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC "
        "       LIMIT 1"
        "    ) latest_snapshot ON true "
        "   WHERE c.identity_status = 'resolved' "
        # tushare/cnstock 需要 credit_code；serper 仅用 canonical_name。
        # 不强制 credit_code，让 connector 内部按需 skip 缺 token / 缺字段的公司。
        ") "
        "SELECT company_id, unified_credit_code, canonical_name, registered_name, "
        "       aliases, canonical_name AS normalized_name, website_host, "
        "       project_name, company_name_xlsx, description, team_raw, priority_rank "
        "  FROM ranked_company"
    )
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY priority_rank"
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


def _build_yiou_context_from_company_row(
    company: dict[str, Any],
    *,
    search_hints: YiouSearchHints | None = None,
) -> YiouSearchContext:
    canonical_name = str(company.get("canonical_name") or company.get("company_id") or "")
    return YiouSearchContext(
        company_name=canonical_name,
        normalized_name=str(company.get("normalized_name") or canonical_name),
        project_name=_optional_text(company.get("project_name")),
        description=_optional_text(company.get("description")),
        team_raw=_optional_text(company.get("team_raw")),
        identity_aliases=search_hints.identity_aliases if search_hints else (),
        aliases=search_hints.aliases if search_hints else (),
        founder_names=search_hints.founder_names if search_hints else (),
        keywords=search_hints.keywords if search_hints else (),
    )


def _fetch_generic_serper_identity_records(
    connector: NewsConnector,
    company: dict[str, Any],
    since: date,
    *,
    search_hints: YiouSearchHints | None = None,
) -> tuple[list[NewsRecord], dict[str, Any]]:
    canonical_name = str(company.get("canonical_name") or company.get("company_id") or "")
    queries = build_generic_identity_queries(
        canonical_name,
        registered_name=_optional_text(company.get("registered_name")),
        xlsx_company_name=_optional_text(company.get("company_name_xlsx")),
        project_name=_optional_text(company.get("project_name")),
        aliases=_company_aliases(company.get("aliases")),
        trusted_llm_aliases=_trusted_llm_identity_aliases(search_hints),
    )
    records: list[NewsRecord] = []
    records_by_query: dict[str, int] = {}
    for query in queries:
        query_records = connector.fetch(query, since)
        records_by_query[query] = len(query_records)
        records.extend(query_records)
    return records, {
        "query_kind": "generic_identity",
        "query_terms": queries,
        "records_by_query": records_by_query,
        "items_seen": len(records),
    }


def _trusted_llm_identity_aliases(
    search_hints: YiouSearchHints | None,
) -> tuple[str, ...]:
    if search_hints is None or search_hints.source != "llm":
        return ()
    return tuple(search_hints.identity_aliases)


def _company_aliases(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return (text,)
        return _company_aliases(parsed)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _open_search_hint_llm_client(
    *,
    timeout_seconds: float | None = None,
    retry_budget: int | None = None,
):
    from openai import OpenAI

    settings = resolve_company_llm_task_settings(
        "search_hint_generation",
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


def _extract_search_hints_for_company(
    company: dict[str, Any],
    *,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any],
) -> YiouSearchHints:
    canonical_name = str(company.get("canonical_name") or company.get("company_id") or "")
    return extract_yiou_search_hints_with_llm(
        company_name=canonical_name,
        project_name=_optional_text(company.get("project_name")),
        description=_optional_text(company.get("description")),
        team_raw=_optional_text(company.get("team_raw")),
        llm_client=llm_client,
        llm_model=llm_model,
        extra_body=extra_body,
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
                is_company_confirmed, refresh_run_id, confidence,
                source_adapter, extraction_diagnostics
            )
            VALUES (%s, %s, %s, %s, %s, now(), %s, %s, NULL, true, %s, %s, %s, %s)
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
                record.source_adapter,
                Jsonb(record.extraction_diagnostics or {}),
            ),
        ).fetchone()
        if row is not None:
            inserted += 1
    return inserted


def _record_fetch_audit(
    conn: Any,
    *,
    batch_id: str | None,
    company_id: str,
    connector_name: str,
    diagnostics: dict[str, Any] | None,
    search_hints: YiouSearchHints | None,
) -> int:
    if not batch_id:
        return 0
    return record_search_audit(
        conn,
        batch_id=batch_id,
        company_id=company_id,
        source_adapter="pitchhub_36kr" if connector_name == "pitchhub" else connector_name,
        diagnostics=diagnostics or {},
        search_hints=search_hints,
    )


def _checkpoint_company_stage(
    conn: Any,
    *,
    batch_id: str | None,
    stage: str | None,
    company_id: str,
    query_count: int,
    source_result_count: int,
    accepted_source_count: int,
    rejected_source_count: int,
    dry_run: bool,
) -> None:
    if not batch_id or not stage:
        return
    counters = {
        "query_count": query_count,
        "source_result_count": source_result_count,
        "accepted_source_count": accepted_source_count,
        "rejected_source_count": rejected_source_count,
    }
    mark_company_stage_complete(
        conn,
        batch_id=batch_id,
        company_id=company_id,
        stage=stage,
        counters=counters,
        details={
            "source_discovery": {
                "search_audit_rows": query_count,
                "news_fetched": accepted_source_count,
            },
            "persistence_outcome": {
                "dry_run": dry_run,
                "status": "succeeded",
            },
        },
        miss_reason="all_results_rejected" if source_result_count and not accepted_source_count else None,
        status="partial",
    )


def _query_count_from_diagnostics(diagnostics: dict[str, Any]) -> int:
    query_terms = diagnostics.get("query_terms")
    records_by_query = diagnostics.get("records_by_query")
    if isinstance(query_terms, list):
        return len(query_terms)
    if isinstance(records_by_query, dict):
        return len(records_by_query)
    return 1


def _fetch_company_records(
    *,
    company: dict[str, Any],
    connectors: list[tuple[str, NewsConnector]],
    since: date,
    sleep_seconds: float,
    search_hint_client: tuple[Any, str, dict[str, Any]] | None,
) -> dict[str, Any]:
    company_id = str(company["company_id"])
    credit_code = str(company["unified_credit_code"])
    canonical_name = str(company.get("canonical_name") or company_id)
    company_records: list[NewsRecord] = []
    search_hints: YiouSearchHints | None = None
    company_query_count = 0
    company_source_result_count = 0
    company_accepted_source_count = 0
    errors = 0
    llm_hints_used = 0
    llm_hints_failed = 0
    audit_items: list[dict[str, Any]] = []

    if search_hint_client is not None:
        llm_client, llm_model, extra_body = search_hint_client
        search_hints = _extract_search_hints_for_company(
            company,
            llm_client=llm_client,
            llm_model=llm_model,
            extra_body=extra_body,
        )
        if search_hints.source == "llm":
            llm_hints_used += 1
        else:
            llm_hints_failed += 1

    for connector_name, connector in connectors:
        diagnostics: dict[str, Any] | None = None
        fetch_key = (
            canonical_name
            if connector_name in ("serper", "iyiou", "pitchhub")
            else credit_code
        )
        try:
            if connector_name in ("iyiou", "pitchhub") and hasattr(
                connector, "fetch_with_context"
            ):
                context = _build_yiou_context_from_company_row(
                    company,
                    search_hints=search_hints,
                )
                fetch_result = connector.fetch_with_context(context, since)
                fetched = getattr(fetch_result, "records", fetch_result)
                diagnostics = getattr(fetch_result, "diagnostics", None)
            elif connector_name == "serper":
                fetched, diagnostics = _fetch_generic_serper_identity_records(
                    connector,
                    company,
                    since,
                    search_hints=search_hints,
                )
            else:
                fetched = connector.fetch(fetch_key, since)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s fetch crashed for %s: %s", connector_name, company_id, exc)
            errors += 1
            fetched = []
            diagnostics = {"error": str(exc), "records_by_query": {fetch_key: 0}}

        diagnostics_payload = diagnostics or {}
        company_query_count += _query_count_from_diagnostics(diagnostics_payload)
        company_source_result_count += int(
            diagnostics_payload.get("items_seen") or len(fetched) or 0
        )
        company_accepted_source_count += len(fetched)
        audit_items.append(
            {
                "connector_name": connector_name,
                "diagnostics": diagnostics,
                "search_hints": search_hints,
            }
        )
        company_records.extend(replace(record, company_id=company_id) for record in fetched)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return {
        "company": company,
        "company_id": company_id,
        "records": company_records,
        "news_fetched": len(company_records),
        "query_count": company_query_count,
        "source_result_count": company_source_result_count,
        "accepted_source_count": company_accepted_source_count,
        "errors": errors,
        "llm_search_hints_used": llm_hints_used,
        "llm_search_hints_failed": llm_hints_failed,
        "audit_items": audit_items,
    }


def _fetch_companies_records(
    *,
    companies: list[dict[str, Any]],
    connectors: list[tuple[str, NewsConnector]],
    since: date,
    sleep_seconds: float,
    search_hint_client: tuple[Any, str, dict[str, Any]] | None,
    concurrency: int,
) -> list[dict[str, Any]]:
    max_workers = max(1, int(concurrency or 1))
    if max_workers <= 1 or len(companies) <= 1:
        return [
            _fetch_company_records(
                company=company,
                connectors=connectors,
                since=since,
                sleep_seconds=sleep_seconds,
                search_hint_client=search_hint_client,
            )
            for company in companies
        ]
    results: list[dict[str, Any] | None] = [None] * len(companies)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(companies))) as executor:
        futures = {
            executor.submit(
                _fetch_company_records,
                company=company,
                connectors=connectors,
                since=since,
                sleep_seconds=sleep_seconds,
                search_hint_client=search_hint_client,
            ): index
            for index, company in enumerate(companies)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [result for result in results if result is not None]


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
                "company_ids": tuple(args.company_id),
                "llm_search_hints": args.llm_search_hints,
                "enrichment_batch_id": args.enrichment_batch_id,
                "dry_run": args.dry_run,
                "concurrency": args.concurrency,
                "llm_timeout_seconds": args.llm_timeout_seconds,
                "llm_retry_budget": args.llm_retry_budget,
            },
            triggered_by="run_company_news_ingest",
        )
    )
    conn.commit()

    connectors = _build_connectors(
        args.connector,
        serper_site_filters=args.serper_site,
        fetch_article_text=args.serper_fetch_article_text,
        article_max_chars=args.serper_article_max_chars,
    )
    sql, params = _build_company_select_sql(
        priority=args.priority,
        limit=args.limit,
        company_ids=tuple(args.company_id),
    )
    companies = conn.execute(sql, params).fetchall()
    search_hint_client: tuple[Any, str, dict[str, Any]] | None = None
    if args.llm_search_hints and any(
        name in {"iyiou", "pitchhub"} for name, _connector in connectors
    ):
        try:
            if args.llm_timeout_seconds is None and args.llm_retry_budget is None:
                search_hint_client = _open_search_hint_llm_client()
            else:
                search_hint_client = _open_search_hint_llm_client(
                    timeout_seconds=args.llm_timeout_seconds,
                    retry_budget=args.llm_retry_budget,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Search-hint LLM unavailable; using deterministic hints: %s", exc)
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
        "llm_search_hints_requested": args.llm_search_hints,
        "llm_search_hints_used": 0,
        "llm_search_hints_failed": 0,
        "llm_timeout_seconds": args.llm_timeout_seconds,
        "llm_retry_budget": args.llm_retry_budget,
        "search_audit_rows": 0,
        "dry_run": args.dry_run,
    }

    company_results = _fetch_companies_records(
        companies=[dict(company) for company in companies],
        connectors=connectors,
        since=since,
        sleep_seconds=args.sleep_seconds,
        search_hint_client=search_hint_client,
        concurrency=args.concurrency,
    )

    for company_result in company_results:
        company = company_result["company"]
        company_id = str(company_result["company_id"])
        report["companies_processed"] += 1
        report["companies_with_errors"] += int(company_result.get("errors") or 0)
        report["llm_search_hints_used"] += int(
            company_result.get("llm_search_hints_used") or 0
        )
        report["llm_search_hints_failed"] += int(
            company_result.get("llm_search_hints_failed") or 0
        )
        report["news_fetched"] += int(company_result.get("news_fetched") or 0)
        company_query_count = int(company_result.get("query_count") or 0)
        company_source_result_count = int(
            company_result.get("source_result_count") or 0
        )
        company_accepted_source_count = int(
            company_result.get("accepted_source_count") or 0
        )
        for audit_item in company_result.get("audit_items") or []:
            try:
                report["search_audit_rows"] += _record_fetch_audit(
                    conn,
                    batch_id=args.enrichment_batch_id,
                    company_id=company_id,
                    connector_name=str(audit_item.get("connector_name") or ""),
                    diagnostics=audit_item.get("diagnostics"),
                    search_hints=audit_item.get("search_hints"),
                )
                if args.enrichment_batch_id and not args.dry_run:
                    conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Search audit failed for %s: %s", company_id, exc)
                report["companies_with_errors"] += 1

        deduped = _dedupe_by_source_url(company_result.get("records") or [])
        _checkpoint_company_stage(
            conn,
            batch_id=args.enrichment_batch_id,
            stage=args.checkpoint_stage,
            company_id=company_id,
            query_count=company_query_count,
            source_result_count=company_source_result_count,
            accepted_source_count=company_accepted_source_count,
            rejected_source_count=max(
                0,
                company_source_result_count - company_accepted_source_count,
            ),
            dry_run=args.dry_run,
        )
        if args.enrichment_batch_id:
            conn.commit()
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
