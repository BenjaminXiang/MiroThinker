#!/usr/bin/env python3
"""Run gated generic-web source judgment for uploaded companies."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import re
import sys
import threading
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from bs4 import BeautifulSoup
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

from src.data_agents.company.enrichment_batch import (  # noqa: E402
    mark_company_stage_complete,
    record_search_audit,
)
from src.data_agents.company.generic_source_judgment import (  # noqa: E402
    AcceptedSourceMaterial,
    GenericSearchResult,
    SourceJudgment,
    _trusted_identity_terms,
    run_generic_source_workflow,
)
from src.data_agents.company.news_connectors import (  # noqa: E402
    SerperSearchConnector,
    build_generic_identity_queries,
    extract_yiou_search_hints_with_llm,
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

logger = logging.getLogger("run_company_generic_source_judgment")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search generic web by company identity and LLM-gate source material.",
    )
    parser.add_argument("--company-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--since", type=_parse_date, default=date(2000, 1, 1))
    parser.add_argument("--result-cap", type=int, default=5)
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--max-fetches", type=int, default=3)
    parser.add_argument("--max-body-chars", type=int, default=8000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--llm-search-hints", action="store_true")
    parser.add_argument("--enrichment-batch-id", default=None)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Per-process worker concurrency for company-level search and judgment.",
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
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _open_llm_client(
    *,
    timeout_seconds: float | None = None,
    retry_budget: int | None = None,
):
    from openai import OpenAI

    settings = resolve_company_llm_task_settings(
        "source_judgment",
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
    return (
        wrap_openai_client(client, provider_key="deepseek"),
        settings.model,
        settings.extra_body,
    )


def _open_serper_connector(result_cap: int) -> SerperSearchConnector:
    api_key = os.environ.get("SERPER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SERPER_API_KEY is not set")
    return SerperSearchConnector(
        api_key,
        result_cap=result_cap,
        fetch_article_content=False,
        query_tail="",
        session=RateLimitedRequestsSession(
            requests.Session(),
            provider_key="serper",
        ),
    )


def _build_company_select_sql(
    *,
    company_ids: tuple[str, ...],
    limit: int | None,
) -> tuple[str, tuple[Any, ...]]:
    conditions = ["c.identity_status = 'resolved'"]
    params: list[Any] = []
    if company_ids:
        placeholders = ", ".join(["%s"] * len(company_ids))
        conditions.append(f"c.company_id IN ({placeholders})")
        params.extend(company_ids)
    sql = (
        "SELECT c.company_id, c.canonical_name, c.registered_name, c.aliases, "
        "       c.website_host, latest.company_name_xlsx, latest.project_name, "
        "       latest.description, latest.team_raw "
        "  FROM company c "
        "  LEFT JOIN LATERAL ("
        "       SELECT cs.company_name_xlsx, cs.project_name, cs.description, cs.team_raw "
        "         FROM company_snapshot cs "
        "        WHERE cs.company_id = c.company_id "
        "        ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC "
        "        LIMIT 1"
        "  ) latest ON true "
        f" WHERE {' AND '.join(conditions)} "
        " ORDER BY c.company_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _company_aliases(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ()
        try:
            return _company_aliases(json.loads(text))
        except json.JSONDecodeError:
            return (text,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _identity_queries(company: dict[str, Any], trusted_llm_aliases: tuple[str, ...]) -> list[str]:
    return build_generic_identity_queries(
        str(company.get("canonical_name") or company.get("company_id") or ""),
        registered_name=_optional_text(company.get("registered_name")),
        xlsx_company_name=_optional_text(company.get("company_name_xlsx")),
        project_name=_optional_text(company.get("project_name")),
        aliases=_company_aliases(company.get("aliases")),
        trusted_llm_aliases=trusted_llm_aliases,
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_identity_aliases_with_llm(
    company: dict[str, Any],
    *,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any],
) -> tuple[str, ...]:
    hints = extract_yiou_search_hints_with_llm(
        company_name=str(company.get("canonical_name") or company.get("company_id") or ""),
        project_name=_optional_text(company.get("project_name")),
        description=_optional_text(company.get("description")),
        team_raw=_optional_text(company.get("team_raw")),
        llm_client=llm_client,
        llm_model=llm_model,
        extra_body=extra_body,
    )
    return tuple(hints.identity_aliases) if hints.source == "llm" else ()


def _fetch_search_results(
    *,
    connector: Any,
    company: dict[str, Any],
    since: date,
    trusted_llm_aliases: tuple[str, ...] = (),
) -> tuple[list[GenericSearchResult], dict[str, int]]:
    results: list[GenericSearchResult] = []
    records_by_query: dict[str, int] = {}
    for query in _identity_queries(company, trusted_llm_aliases):
        records = connector.fetch(query, since)
        records_by_query[query] = len(records)
        for record in records:
            results.append(
                GenericSearchResult(
                    title=record.title,
                    url=record.source_url,
                    snippet=record.summary or record.raw_text or "",
                )
            )
    return _dedupe_results(results), records_by_query


def _dedupe_results(results: list[GenericSearchResult]) -> list[GenericSearchResult]:
    seen: set[str] = set()
    deduped: list[GenericSearchResult] = []
    for result in results:
        url = result.url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(result)
    return deduped


def _judge_source_with_llm(
    *,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any],
    company_name: str,
    identity_terms: tuple[str, ...] = (),
    title: str,
    url: str,
    snippet: str,
    page_text: str | None = None,
) -> SourceJudgment:
    identity_line = "、".join(identity_terms) if identity_terms else company_name
    prompt = "\n".join(
        [
            "Judge whether this generic web result can be used as source material for the target company.",
            "Return strict JSON with keys: status, reason, evidence_span, snippet_sufficiency, confirms_identity, confirms_fact_attribution, should_fetch.",
            "status must be accepted, rejected, or needs_review.",
            "snippet_sufficiency must be sufficient, insufficient, or irrelevant.",
            "If the snippet mentions the company but lacks product, financing, scenario, customer, team, or profile facts, set should_fetch=true.",
            "Reject recruiting/job pages and competitor or same-industry pages.",
            "Accept only when the evidence is explicitly about one of the trusted identity terms.",
            "",
            f"Target company: {company_name}",
            f"Trusted identity terms: {identity_line}",
            f"Title: {title}",
            f"URL: {url}",
            f"Snippet: {snippet[:1200]}",
            "Page text:" if page_text else "Page text: <not fetched>",
            (page_text or "")[:5000],
        ]
    )
    response = llm_client.chat.completions.create(
        model=llm_model,
        messages=[
            {
                "role": "system",
                "content": "You gate company source material. Output JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=700,
        extra_body=extra_body,
    )
    payload = _extract_json_object(response.choices[0].message.content or "")
    return _coerce_source_judgment(payload)


def _extract_json_object(raw: str) -> Any:
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw.strip(), flags=re.MULTILINE)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _coerce_source_judgment(payload: Any) -> SourceJudgment:
    if not isinstance(payload, dict):
        return SourceJudgment(
            status="rejected",
            reason="llm_response_parse_failed",
            evidence_span="",
            snippet_sufficiency="irrelevant",
            confirms_identity=False,
            confirms_fact_attribution=False,
            should_fetch=False,
        )
    status = str(payload.get("status") or "rejected").strip()
    if status not in {"accepted", "rejected", "needs_review"}:
        status = "rejected"
    sufficiency = str(payload.get("snippet_sufficiency") or "irrelevant").strip()
    if sufficiency not in {"sufficient", "insufficient", "irrelevant"}:
        sufficiency = "irrelevant"
    return SourceJudgment(
        status=status,  # type: ignore[arg-type]
        reason=str(payload.get("reason") or status),
        evidence_span=str(payload.get("evidence_span") or ""),
        snippet_sufficiency=sufficiency,  # type: ignore[arg-type]
        confirms_identity=bool(payload.get("confirms_identity")),
        confirms_fact_attribution=bool(payload.get("confirms_fact_attribution")),
        should_fetch=bool(payload.get("should_fetch")),
    )


def _fetch_page_text(url: str, *, max_chars: int) -> str:
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": "MiroThinker-Company-GenericSource/1.0"},
            timeout=20.0,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Generic web fetch failed for %s: %s", url, exc)
        return ""
    content_type = response.headers.get("content-type", "").lower()
    if content_type and not any(
        marker in content_type
        for marker in ("text/html", "application/xhtml+xml", "text/plain")
    ):
        logger.debug(
            "Generic web fetch skipped non-HTML content for %s: %s",
            url,
            content_type,
        )
        return ""
    try:
        soup = BeautifulSoup(response.text, "lxml")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Generic web parse failed for %s: %s", url, exc)
        return ""
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    text = "\n".join(
        line.strip()
        for line in re.sub(r"\s+", " ", soup.get_text("\n", strip=True)).splitlines()
        if line.strip()
    )
    return text[:max_chars]


def _process_company(
    *,
    conn: Any,
    company: dict[str, Any],
    connector: Any,
    since: date,
    batch_id: UUID | str | None,
    dry_run: bool,
    run_id: UUID | str,
    judge_source: Any,
    fetch_page: Any,
    trusted_llm_aliases: tuple[str, ...] = (),
    max_results: int = 10,
    max_fetches: int = 3,
    max_body_chars: int = 8000,
) -> dict[str, Any]:
    search_results, records_by_query = _fetch_search_results(
        connector=connector,
        company=company,
        since=since,
        trusted_llm_aliases=trusted_llm_aliases,
    )
    workflow = run_generic_source_workflow(
        company_name=str(company.get("canonical_name") or ""),
        trusted_identity_terms=_identity_terms_for_guard(
            company,
            trusted_llm_aliases=trusted_llm_aliases,
        ),
        search_results=search_results,
        judge_source=judge_source,
        fetch_page=fetch_page,
        max_results=max_results,
        max_fetches=max_fetches,
        max_body_chars=max_body_chars,
    )
    inserted = _insert_accepted_sources(
        conn,
        company=company,
        accepted_sources=workflow.accepted_sources,
        dry_run=dry_run,
        run_id=run_id,
    )
    diagnostics = _generic_diagnostics(
        records_by_query=records_by_query,
        workflow=workflow,
        identity_terms=_identity_terms_for_guard(
            company,
            trusted_llm_aliases=trusted_llm_aliases,
        ),
    )
    audit_rows = 0
    if batch_id:
        audit_rows = record_search_audit(
            conn,
            batch_id=batch_id,
            company_id=str(company["company_id"]),
            source_adapter="generic_web",
            diagnostics=diagnostics,
        )
    return {
        "company_id": str(company["company_id"]),
        "queries_run": len(records_by_query),
        "results_seen": workflow.counters.get("results_seen", 0),
        "snippet_judgments": workflow.counters.get("results_seen", 0),
        "fetch_count": workflow.counters.get("fetch_count", 0),
        "source_judgments": sum(1 for step in workflow.steps if step.tool == "judge_source"),
        "accepted_sources": len(workflow.accepted_sources),
        "rejected_sources": len(workflow.rejected_results),
        "needs_review_sources": sum(
            1 for item in workflow.rejected_results if item.reason == "needs_review"
        ),
        "inserted_sources": inserted,
        "search_audit_rows": audit_rows,
    }


def _identity_terms_for_guard(
    company: dict[str, Any],
    *,
    trusted_llm_aliases: tuple[str, ...] = (),
) -> tuple[str, ...]:
    raw_terms: list[str] = []
    for value in (
        company.get("canonical_name"),
        company.get("registered_name"),
        company.get("company_name_xlsx"),
        company.get("project_name"),
        *_company_aliases(company.get("aliases")),
        *trusted_llm_aliases,
    ):
        text = str(value or "").strip()
        if text and text not in raw_terms:
            raw_terms.append(text)
    if not raw_terms:
        return ()
    return _trusted_identity_terms(raw_terms[0], raw_terms[1:])


def _generic_diagnostics(
    *,
    records_by_query: dict[str, int],
    workflow: Any,
    identity_terms: tuple[str, ...] = (),
) -> dict[str, Any]:
    rejected_by_reason: dict[str, int] = {}
    for result in workflow.rejected_results:
        rejected_by_reason[result.reason] = rejected_by_reason.get(result.reason, 0) + 1
    return {
        "query_kind": "generic_identity",
        "records_by_query": records_by_query,
        "trusted_identity_terms": list(identity_terms),
        "items_seen": workflow.counters.get("results_seen", 0),
        "items_accepted": len(workflow.accepted_sources),
        "items_rejected_name_mismatch": rejected_by_reason.get("company_identity_failed", 0),
        "fetch_count": workflow.counters.get("fetch_count", 0),
        "source_judgment": {
            "accepted": len(workflow.accepted_sources),
            "rejected": len(workflow.rejected_results),
            "rejected_by_reason": rejected_by_reason,
        },
        "workflow_steps": [
            {
                "tool": step.tool,
                "url": step.url,
                "status": step.status,
                "reason": step.reason,
            }
            for step in workflow.steps
        ],
        "accepted_source_material": [
            {
                "url": source.url,
                "title": source.title,
                "source_id": source.source_id,
                "evidence_span": source.evidence_span,
                "trust_reason": source.trust_reason,
            }
            for source in workflow.accepted_sources
        ],
        "rejected_source_material": [
            {
                "url": result.url,
                "title": result.title,
                "reason": result.reason,
                "evidence_span": result.evidence_span,
            }
            for result in workflow.rejected_results
        ],
    }


def _insert_accepted_sources(
    conn: Any,
    *,
    company: dict[str, Any],
    accepted_sources: list[AcceptedSourceMaterial],
    dry_run: bool,
    run_id: UUID | str,
) -> int:
    if dry_run:
        return 0
    real_run_id = require_real_run_id(run_id, writer_name="_insert_accepted_sources")
    inserted = 0
    for source in accepted_sources:
        source_domain = _source_domain(source.url)
        source_domain_tier = resolve_tier(
            source_domain,
            {company.get("website_host")} if company.get("website_host") else None,
        )
        row = conn.execute(
            """
            INSERT INTO company_news_item (
                company_id, source_url, source_domain, source_domain_tier,
                published_at, fetched_at, title, summary_clean, content_clean_path,
                is_company_confirmed, refresh_run_id, confidence,
                source_adapter, extraction_diagnostics
            )
            VALUES (
                %(company_id)s, %(source_url)s, %(source_domain)s,
                %(source_domain_tier)s, NULL, now(), %(title)s, %(summary_clean)s,
                NULL, %(is_company_confirmed)s, %(run_id)s, %(confidence)s,
                %(source_adapter)s, %(diagnostics)s
            )
            ON CONFLICT (source_url) DO NOTHING
            RETURNING news_id
            """,
            {
                "company_id": company["company_id"],
                "source_url": source.url,
                "source_domain": source_domain,
                "source_domain_tier": source_domain_tier,
                "title": source.title,
                "summary_clean": source.captured_text,
                "is_company_confirmed": True,
                "run_id": real_run_id,
                "confidence": Decimal("0.65"),
                "source_adapter": "generic_web",
                "diagnostics": Jsonb(
                    {
                        "source_id": source.source_id,
                        "source_tier": source.source_tier,
                        "source_judgment_status": "accepted",
                        "trust_reason": source.trust_reason,
                        "evidence_span": source.evidence_span,
                    }
                ),
            },
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


def _process_company_worker(
    *,
    dsn: str,
    company: dict[str, Any],
    args: argparse.Namespace,
    run_id: UUID | str,
    thread_state: threading.local,
) -> dict[str, Any]:
    conn = _open_database_connection(dsn)
    try:
        connector = getattr(thread_state, "connector", None)
        if connector is None:
            connector = _open_serper_connector(args.result_cap)
            thread_state.connector = connector
        llm_bundle = getattr(thread_state, "llm_bundle", None)
        if llm_bundle is None:
            llm_bundle = _open_llm_client(
                timeout_seconds=args.llm_timeout_seconds,
                retry_budget=args.llm_retry_budget,
            )
            thread_state.llm_bundle = llm_bundle
        llm_client, llm_model, extra_body = llm_bundle
        trusted_aliases: tuple[str, ...] = ()
        if args.llm_search_hints:
            trusted_aliases = _extract_identity_aliases_with_llm(
                company,
                llm_client=llm_client,
                llm_model=llm_model,
                extra_body=extra_body,
            )
        company_report = _process_company(
            conn=conn,
            company=company,
            connector=connector,
            since=args.since,
            batch_id=args.enrichment_batch_id,
            dry_run=args.dry_run,
            run_id=run_id,
            judge_source=lambda **kwargs: _judge_source_with_llm(
                llm_client=llm_client,
                llm_model=llm_model,
                extra_body=extra_body,
                **kwargs,
            ),
            fetch_page=lambda url: _fetch_page_text(
                url,
                max_chars=args.max_body_chars,
            ),
            trusted_llm_aliases=trusted_aliases,
            max_results=args.max_results,
            max_fetches=args.max_fetches,
            max_body_chars=args.max_body_chars,
        )
        _checkpoint_company_stage(
            conn,
            batch_id=args.enrichment_batch_id,
            stage=args.checkpoint_stage,
            company_report=company_report,
        )
        if not args.dry_run or args.enrichment_batch_id:
            conn.commit()
        return company_report
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        company_report = {
            "company_id": str(company.get("company_id") or ""),
            "queries_run": 0,
            "results_seen": 0,
            "snippet_judgments": 0,
            "fetch_count": 0,
            "source_judgments": 0,
            "accepted_sources": 0,
            "rejected_sources": 0,
            "needs_review_sources": 0,
            "inserted_sources": 0,
            "search_audit_rows": 0,
            "error": str(exc),
        }
        try:
            _checkpoint_company_stage(
                conn,
                batch_id=args.enrichment_batch_id,
                stage=args.checkpoint_stage,
                company_report=company_report,
            )
            conn.commit()
        except Exception:
            conn.rollback()
        return company_report
    finally:
        conn.close()


def _checkpoint_company_stage(
    conn: Any,
    *,
    batch_id: str | None,
    stage: str | None,
    company_report: dict[str, Any],
) -> None:
    if not batch_id or not stage:
        return
    company_id = str(company_report.get("company_id") or "")
    if not company_id:
        return
    counters = {
        "query_count": int(company_report.get("queries_run") or 0),
        "source_result_count": int(company_report.get("results_seen") or 0),
        "accepted_source_count": int(company_report.get("accepted_sources") or 0),
        "rejected_source_count": int(company_report.get("rejected_sources") or 0),
    }
    details = {
        "source_discovery": {
            "query_count": int(company_report.get("queries_run") or 0),
            "result_count": int(company_report.get("results_seen") or 0),
            "fetch_attempts": int(company_report.get("fetch_count") or 0),
            "source_judgments": int(company_report.get("source_judgments") or 0),
            "search_audit_rows": int(company_report.get("search_audit_rows") or 0),
        },
        "persistence_outcome": {
            "status": "failed" if company_report.get("error") else "succeeded",
            "dry_run": False,
        },
    }
    mark_company_stage_complete(
        conn,
        batch_id=batch_id,
        company_id=company_id,
        stage=stage,
        counters=counters,
        details=details,
        miss_reason="stage_error" if company_report.get("error") else None,
        status="failed" if company_report.get("error") else "partial",
        last_error=company_report.get("error") or None,
    )


def _process_companies(
    *,
    dsn: str,
    companies: list[dict[str, Any]],
    args: argparse.Namespace,
    run_id: UUID | str,
) -> list[dict[str, Any]]:
    max_workers = max(1, int(args.concurrency or 1))
    if max_workers <= 1 or len(companies) <= 1:
        state = threading.local()
        return [
            _process_company_worker(
                dsn=dsn,
                company=company,
                args=args,
                run_id=run_id,
                thread_state=state,
            )
            for company in companies
        ]
    reports: list[dict[str, Any] | None] = [None] * len(companies)
    state = threading.local()
    with ThreadPoolExecutor(max_workers=min(max_workers, len(companies))) as executor:
        futures = {
            executor.submit(
                _process_company_worker,
                dsn=dsn,
                company=company,
                args=args,
                run_id=run_id,
                thread_state=state,
            ): index
            for index, company in enumerate(companies)
        }
        for future in as_completed(futures):
            reports[futures[future]] = future.result()
    return [report for report in reports if report is not None]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=args.log_level.upper())
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1

    conn = _open_database_connection(dsn)
    run_id = open_pipeline_run(
        conn,
        run_kind="backfill_real",
        run_scope={
            "task": "company_generic_source_judgment",
            "company_ids": list(args.company_id),
            "limit": args.limit,
            "dry_run": args.dry_run,
            "enrichment_batch_id": args.enrichment_batch_id,
            "concurrency": args.concurrency,
            "llm_timeout_seconds": args.llm_timeout_seconds,
            "llm_retry_budget": args.llm_retry_budget,
            "checkpoint_stage": args.checkpoint_stage,
        },
        triggered_by="run_company_generic_source_judgment",
    )
    conn.commit()
    try:
        sql, params = _build_company_select_sql(
            company_ids=tuple(args.company_id),
            limit=args.limit,
        )
        companies = [dict(row) for row in conn.execute(sql, params).fetchall()]
        report: dict[str, Any] = {
            "run_id": str(run_id),
            "companies_total": len(companies),
            "companies_processed": 0,
            "queries_run": 0,
            "results_seen": 0,
            "snippet_judgments": 0,
            "fetch_count": 0,
            "source_judgments": 0,
            "accepted_sources": 0,
            "rejected_sources": 0,
            "needs_review_sources": 0,
            "inserted_sources": 0,
            "search_audit_rows": 0,
            "companies_with_errors": 0,
            "dry_run": args.dry_run,
            "concurrency": max(1, int(args.concurrency or 1)),
            "llm_timeout_seconds": args.llm_timeout_seconds,
            "llm_retry_budget": args.llm_retry_budget,
            "company_reports": [],
        }
        for company_report in _process_companies(
            dsn=dsn,
            companies=companies,
            args=args,
            run_id=run_id,
        ):
            report["companies_processed"] += 1
            if company_report.get("error"):
                report.setdefault("companies_with_errors", 0)
                report["companies_with_errors"] += 1
            for key in (
                "queries_run",
                "results_seen",
                "snippet_judgments",
                "fetch_count",
                "source_judgments",
                "accepted_sources",
                "rejected_sources",
                "needs_review_sources",
                "inserted_sources",
                "search_audit_rows",
            ):
                report[key] += int(company_report.get(key) or 0)
            report["company_reports"].append(company_report)
        close_pipeline_run(
            conn,
            run_id,
            status="partial" if report.get("companies_with_errors") else "succeeded",
            items_processed=report["companies_processed"],
            items_failed=int(report.get("companies_with_errors") or 0),
        )
        conn.commit()
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
            close_pipeline_run(conn, run_id, status="failed", items_failed=1)
            conn.commit()
        except Exception:
            pass
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
