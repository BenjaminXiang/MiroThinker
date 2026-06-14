#!/usr/bin/env python3
"""Extract company_product rows from accepted source-profile news text."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import threading
from typing import Any

import httpx
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.data_agents.company.official_product_capture import (  # noqa: E402
    CompanyApplicationScenarioCandidate,
    CompanyProductCandidate,
    application_scenario_to_json,
    upsert_company_application_scenario,
    upsert_company_product,
)
from src.data_agents.company.source_product_extractor import (  # noqa: E402
    extract_application_scenarios_from_source_text,
    extract_products_and_scenarios_with_llm_fallback,
    extract_products_from_source_text,
)
from src.data_agents.company.llm_routing import resolve_company_llm_task_settings  # noqa: E402
from src.data_agents.company.provider_rate_limit import wrap_openai_client  # noqa: E402
from src.data_agents.company.enrichment_batch import mark_company_stage_complete  # noqa: E402
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract company_product rows from Yiou/PitchHub source text.",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--source-adapter",
        action="append",
        default=[],
        help="Only process this source_adapter. Repeat for multiple.",
    )
    parser.add_argument(
        "--company-id",
        action="append",
        default=[],
        help="Only process this canonical company_id. Repeat for multiple IDs.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--enrichment-batch-id",
        default=None,
        help="Optional company_enrichment_batch id for reports/checkpoints.",
    )
    parser.add_argument(
        "--llm-structured-extract",
        action="store_true",
        help="Use the configured LLM as a fallback when deterministic extraction misses.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Per-process worker concurrency for source LLM extraction.",
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
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _open_llm_client(
    *,
    timeout_seconds: float | None = None,
    retry_budget: int | None = None,
):
    from openai import OpenAI

    settings = resolve_company_llm_task_settings(
        "generic_product_admission",
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


def _build_source_news_select_sql(
    *,
    limit: int | None,
    source_adapters: tuple[str, ...],
    company_ids: tuple[str, ...] = (),
) -> tuple[str, tuple[Any, ...]]:
    conditions = [
        "n.is_company_confirmed = true",
        "n.summary_clean IS NOT NULL",
        "n.summary_clean != ''",
    ]
    params: list[Any] = []
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
        "       n.source_url, n.source_adapter, n.title, n.summary_clean "
        "  FROM company_news_item n "
        "  JOIN company c ON c.company_id = n.company_id "
        f" WHERE {' AND '.join(conditions)} "
        " ORDER BY n.fetched_at DESC, n.news_id DESC"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _insert_products(
    conn: Any,
    products: list[CompanyProductCandidate],
    *,
    source_tier: str | None = None,
) -> int:
    inserted = 0
    for product in products:
        upsert_company_product(
            conn,
            product,
            extractor_version="source_product_extractor.v1",
            source_tier=source_tier,
        )
        inserted += 1
    return inserted


def _insert_application_scenarios(
    conn: Any,
    scenarios: list[CompanyApplicationScenarioCandidate],
    *,
    source_tier: str | None = None,
) -> int:
    inserted = 0
    for scenario in scenarios:
        upsert_company_application_scenario(
            conn,
            scenario,
            extractor_version="source_product_extractor.v1",
            source_tier=source_tier,
        )
        inserted += 1
    return inserted


def _product_business_fields_to_json(product: CompanyProductCandidate) -> dict[str, Any]:
    return {
        "product_name": product.product_name,
        "product_description": product.short_description,
        "product_category": product.product_category,
        "technical_tags": list(product.technical_tags),
        "target_customers": list(product.target_customers),
        "application_scenarios": list(product.application_scenarios),
    }


def _is_supported_source_url(url: str, *, source_adapter: str | None = None) -> bool:
    if source_adapter == "generic_web":
        return True
    if "pitchhub.36kr.com/organization/" in url:
        return False
    return (
        "pitchhub.36kr.com/project/" in url
        or "data.iyiou.com/company/details/" in url
        or "data.iyiou.com/intelligence/details/" in url
        or "data.iyiou.com/news/" in url
    )


def _source_bucket(report: dict[str, Any], source_adapter: str | None) -> dict[str, int]:
    source = source_adapter or "unknown"
    counts = report.setdefault("source_adapter_counts", {})
    if source not in counts:
        counts[source] = {
            "news_processed": 0,
            "products_extracted": 0,
            "products_inserted": 0,
            "scenarios_extracted": 0,
            "scenarios_inserted": 0,
            "product_gate_rejected": 0,
            "candidate_gate_rejected": 0,
        }
    return counts[source]


def _rejection_detail(
    row: dict[str, Any],
    *,
    gate: str,
    reason: str,
    rejected_count: int,
) -> dict[str, Any]:
    return {
        "news_id": str(row.get("news_id") or ""),
        "company_id": str(row.get("company_id") or ""),
        "source_adapter": str(row.get("source_adapter") or ""),
        "source_url": str(row.get("source_url") or ""),
        "gate": gate,
        "reason": str(reason or "").strip() or "unknown_rejection_reason",
        "rejected_count": int(rejected_count),
    }


def _record_rejection_details(
    report: dict[str, Any],
    details: list[dict[str, Any]],
) -> None:
    if not details:
        return
    rejected_candidates = report.setdefault("rejected_candidates", [])
    rejected_reasons = report.setdefault("rejected_candidate_reasons", {})
    assert isinstance(rejected_candidates, list)
    assert isinstance(rejected_reasons, dict)
    for detail in details:
        rejected_candidates.append(detail)
        reason = str(detail.get("reason") or "unknown_rejection_reason")
        rejected_reasons[reason] = int(rejected_reasons.get(reason) or 0) + int(
            detail.get("rejected_count") or 0
        )


def _empty_company_stage_stats() -> dict[str, int]:
    return {
        "source_rows_processed": 0,
        "product_count": 0,
        "scenario_count": 0,
        "products_with_target_customers": 0,
        "llm_fallback_used": 0,
        "llm_fallback_failed": 0,
        "product_gate_rejected": 0,
        "candidate_gate_rejected": 0,
        "unsupported_source_rows": 0,
    }


def _checkpoint_company_stages(
    conn: Any,
    *,
    batch_id: str | None,
    stage: str | None,
    company_stats: dict[str, dict[str, int]],
    dry_run: bool,
) -> None:
    if not batch_id or not stage:
        return
    for company_id, counters in sorted(company_stats.items()):
        source_rows = int(counters.get("source_rows_processed") or 0)
        product_count = int(counters.get("product_count") or 0)
        scenario_count = int(counters.get("scenario_count") or 0)
        rejected_count = int(counters.get("candidate_gate_rejected") or 0) + int(
            counters.get("product_gate_rejected") or 0
        )
        miss_reason = None
        if source_rows == 0:
            miss_reason = "source_product_no_source_rows"
        elif product_count + scenario_count == 0:
            miss_reason = "source_product_no_facts"
        mark_company_stage_complete(
            conn,
            batch_id=batch_id,
            company_id=company_id,
            stage=stage,
            counters={
                "source_rows_processed": source_rows,
                "product_count": product_count,
                "scenario_count": scenario_count,
                "products_with_target_customers": int(
                    counters.get("products_with_target_customers") or 0
                ),
                "rejected_candidate_count": rejected_count,
            },
            details={
                "source_product_extract": {
                    "dry_run": dry_run,
                    "llm_fallback_used": int(counters.get("llm_fallback_used") or 0),
                    "llm_fallback_failed": int(
                        counters.get("llm_fallback_failed") or 0
                    ),
                    "product_gate_rejected": int(
                        counters.get("product_gate_rejected") or 0
                    ),
                    "candidate_gate_rejected": int(
                        counters.get("candidate_gate_rejected") or 0
                    ),
                    "unsupported_source_rows": int(
                        counters.get("unsupported_source_rows") or 0
                    ),
                },
                "persistence_outcome": {
                    "dry_run": dry_run,
                    "status": "succeeded",
                },
            },
            miss_reason=miss_reason,
            status="partial",
        )


def _requires_llm_product_confirmation(source_adapter: str | None) -> bool:
    return (source_adapter or "").strip().lower() == "generic_web"


def _requires_llm_candidate_confirmation(source_adapter: str | None) -> bool:
    return (source_adapter or "").strip().lower() in {
        "generic_web",
        "iyiou",
        "pitchhub_36kr",
    }


def _generic_web_product_gate_result(
    *,
    row: dict[str, Any],
    llm_client: tuple[Any, str, dict[str, Any]],
) -> tuple[bool, str]:
    client, model, extra_body = llm_client
    company_name = str(row.get("canonical_name") or "")
    source_url = str(row.get("source_url") or "")
    title = str(row.get("title") or "")
    text = str(row.get("summary_clean") or "").strip()
    if not text:
        return False, "empty_source_text"
    prompt = "\n".join(
        [
            "Decide whether this generic web source may be used to extract company products/services/scenarios.",
            "Return strict JSON only: {\"allow_product_extraction\": true|false, \"reason\": \"...\"}.",
            "",
            "Allow only when the text explicitly describes concrete products, named platforms, services, solutions, devices, or application scenarios provided by the target company.",
            "Reject when the text is only business registration, operating scope, legal/credit profile, patent/news headline, financing, investor, subsidiary establishment, strategic cooperation, government list, recruitment, generic company profile, or broad technical capability without a product/service offering.",
            "Reject if the product/service belongs to another company or attribution is ambiguous.",
            "",
            f"Company: {company_name}",
            f"Title: {title}",
            f"Source URL: {source_url}",
            "Source text:",
            text[:2200],
        ]
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict source-quality gate for company product "
                        "extraction. Output JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=300,
            extra_body=extra_body or {},
        )
    except Exception:
        return False, "llm_source_gate_failed"
    raw_text = (response.choices[0].message.content or "").strip()
    payload = _extract_json_object(raw_text)
    if not isinstance(payload, dict):
        return False, "llm_source_gate_parse_failed"
    reason = str(payload.get("reason") or "").strip() or "llm_source_gate_rejected"
    return bool(payload.get("allow_product_extraction") is True), reason


def _generic_web_allows_product_extraction(
    *,
    row: dict[str, Any],
    llm_client: tuple[Any, str, dict[str, Any]],
) -> bool:
    allowed, _reason = _generic_web_product_gate_result(row=row, llm_client=llm_client)
    return allowed


def _filter_source_candidates_with_llm(
    *,
    row: dict[str, Any],
    products: list[CompanyProductCandidate],
    scenarios: list[CompanyApplicationScenarioCandidate],
    llm_client: tuple[Any, str, dict[str, Any]],
) -> tuple[
    list[CompanyProductCandidate],
    list[CompanyApplicationScenarioCandidate],
    int,
    str | None,
]:
    if not products and not scenarios:
        return products, scenarios, 0, None
    client, model, extra_body = llm_client
    company_name = str(row.get("canonical_name") or "")
    source_url = str(row.get("source_url") or "")
    source_adapter = str(row.get("source_adapter") or "")
    title = str(row.get("title") or "")
    text = str(row.get("summary_clean") or "").strip()
    product_items = [
        {
            "product_name": product.product_name,
            "product_category": product.product_category,
            "evidence_span": product.evidence_span,
        }
        for product in products
    ]
    scenario_items = [
        {
            "scenario_name": scenario.scenario_name,
            "related_product_name": scenario.related_product_name,
            "evidence_span": scenario.evidence_span,
        }
        for scenario in scenarios
    ]
    prompt = "\n".join(
        [
            "Filter candidate products and scenarios extracted from a company source page.",
            "Return strict JSON only: {\"keep_products\": [\"...\"], \"keep_scenarios\": [\"...\"], \"reason\": \"...\"}.",
            "",
            "Keep a product only when the source text explicitly attributes that concrete product, named platform, device, service, solution, system, or productized offering to the target company.",
            "Reject products that belong to another company, appear in related articles, similar projects, investors, customer cases, platform recommendations, page navigation, SEO titles, company names, project names, brand-only names, investment/funding names, generic categories such as 智能硬件产品, broad capabilities, or evidence that only says the target is a company/provider/developer.",
            "Keep a scenario only when the source explicitly ties it to a kept product or to a concrete offering provided by the target company.",
            "",
            f"Company: {company_name}",
            f"Source adapter: {source_adapter}",
            f"Title: {title}",
            f"Source URL: {source_url}",
            "Product candidates:",
            json.dumps(product_items, ensure_ascii=False),
            "Scenario candidates:",
            json.dumps(scenario_items, ensure_ascii=False),
            "Source text:",
            text[:2200],
        ]
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict fact-attribution gate for company "
                        "product candidates. Output JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=500,
            extra_body=extra_body or {},
        )
    except Exception:
        return [], [], len(products) + len(scenarios), "llm_candidate_gate_failed"
    payload = _extract_json_object((response.choices[0].message.content or "").strip())
    if not isinstance(payload, dict):
        return [], [], len(products) + len(scenarios), "llm_candidate_gate_parse_failed"
    keep_products = {
        str(item).strip() for item in payload.get("keep_products") or [] if str(item).strip()
    }
    keep_scenarios = {
        str(item).strip() for item in payload.get("keep_scenarios") or [] if str(item).strip()
    }
    filtered_products = [
        product for product in products if product.product_name in keep_products
    ]
    filtered_scenarios = [
        scenario
        for scenario in scenarios
        if scenario.scenario_name in keep_scenarios
        and (
            not scenario.related_product_name
            or scenario.related_product_name in keep_products
        )
    ]
    rejected = (len(products) - len(filtered_products)) + (
        len(scenarios) - len(filtered_scenarios)
    )
    reason = None
    if rejected:
        reason = str(payload.get("reason") or "").strip() or "candidate_gate_rejected"
    return filtered_products, filtered_scenarios, rejected, reason


def _extract_json_object(raw_text: str) -> Any:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _extract_products_and_scenarios(
    *,
    row: dict[str, Any],
    llm_client: tuple[Any, str, dict[str, Any]] | None,
) -> tuple[
    list[CompanyProductCandidate],
    list[CompanyApplicationScenarioCandidate],
    bool,
    bool,
    bool,
    int,
    list[dict[str, Any]],
]:
    company_id = str(row["company_id"])
    company_name = str(row.get("canonical_name") or "")
    source_url = str(row.get("source_url") or "")
    title = str(row.get("title") or "")
    body_text = row.get("summary_clean")
    source_adapter = str(row.get("source_adapter") or "")
    requires_source_gate = _requires_llm_product_confirmation(source_adapter)
    requires_candidate_gate = _requires_llm_candidate_confirmation(source_adapter)
    if requires_source_gate:
        if llm_client is None:
            return [], [], False, True, False, 0, [
                _rejection_detail(
                    row,
                    gate="generic_product_source_gate",
                    reason="llm_client_unavailable",
                    rejected_count=1,
                )
            ]
        source_allowed, source_gate_reason = _generic_web_product_gate_result(
            row=row,
            llm_client=llm_client,
        )
        if not source_allowed:
            return [], [], False, False, True, 0, [
                _rejection_detail(
                    row,
                    gate="generic_product_source_gate",
                    reason=source_gate_reason,
                    rejected_count=1,
                )
            ]

    deterministic_products = extract_products_from_source_text(
        company_id=company_id,
        company_name=company_name,
        source_url=source_url,
        title=title,
        body_text=body_text,
    )
    deterministic_scenarios = extract_application_scenarios_from_source_text(
        company_id=company_id,
        company_name=company_name,
        source_url=source_url,
        title=title,
        body_text=body_text,
    )
    if llm_client is None:
        if requires_source_gate:
            return [], [], False, True, False, 0, [
                _rejection_detail(
                    row,
                    gate="generic_product_source_gate",
                    reason="llm_client_unavailable",
                    rejected_count=1,
                )
            ]
        return deterministic_products, deterministic_scenarios, False, False, False, 0, []

    if _deterministic_candidates_are_strong(
        deterministic_products, deterministic_scenarios
    ):
        if requires_candidate_gate:
            products, scenarios, rejected, reason = _filter_source_candidates_with_llm(
                row=row,
                products=deterministic_products,
                scenarios=deterministic_scenarios,
                llm_client=llm_client,
            )
            details = []
            if rejected:
                details.append(
                    _rejection_detail(
                        row,
                        gate="product_candidate_attribution_gate",
                        reason=reason or "candidate_gate_rejected",
                        rejected_count=rejected,
                    )
                )
            return products, scenarios, False, False, False, rejected, details
        return deterministic_products, deterministic_scenarios, False, False, False, 0, []

    client, model, extra_body = llm_client
    llm_products, llm_scenarios = extract_products_and_scenarios_with_llm_fallback(
        company_id=company_id,
        company_name=company_name,
        source_url=source_url,
        title=title,
        body_text=body_text,
        existing_products=[],
        existing_scenarios=[],
        llm_client=client,
        llm_model=model,
        extra_body=extra_body,
    )
    if llm_products or llm_scenarios:
        if requires_candidate_gate:
            products, scenarios, rejected, reason = _filter_source_candidates_with_llm(
                row=row,
                products=llm_products,
                scenarios=llm_scenarios,
                llm_client=llm_client,
            )
            details = []
            if rejected:
                details.append(
                    _rejection_detail(
                        row,
                        gate="product_candidate_attribution_gate",
                        reason=reason or "candidate_gate_rejected",
                        rejected_count=rejected,
                    )
                )
            return products, scenarios, True, False, False, rejected, details
        return llm_products, llm_scenarios, True, False, False, 0, []
    if requires_source_gate:
        return [], [], False, True, False, 0, []
    return deterministic_products, deterministic_scenarios, False, not (
        deterministic_products or deterministic_scenarios
    ), False, 0, []


def _deterministic_candidates_are_strong(
    products: list[CompanyProductCandidate],
    scenarios: list[CompanyApplicationScenarioCandidate],
) -> bool:
    if not products and scenarios:
        return True
    return any(_product_candidate_name_is_specific(product.product_name) for product in products)


def _product_candidate_name_is_specific(name: str) -> bool:
    text = str(name or "").strip()
    if not text:
        return False
    if text.isascii() and text.replace("-", "").replace("_", "").isalnum():
        return False
    product_markers = (
        "平台",
        "系统",
        "设备",
        "产品",
        "服务",
        "解决方案",
        "方案",
        "传感器",
        "芯片",
        "模组",
        "机器人",
        "相机",
        "工作站",
    )
    return any(marker in text for marker in product_markers)


def _process_source_row(
    *,
    row: dict[str, Any],
    llm_structured_extract: bool,
    llm_timeout_seconds: float | None,
    llm_retry_budget: int | None,
    thread_state: threading.local,
) -> dict[str, Any]:
    if not _is_supported_source_url(
        str(row.get("source_url") or ""),
        source_adapter=row.get("source_adapter"),
    ):
        return {
            "row": row,
            "products": [],
            "scenarios": [],
            "llm_used": False,
            "llm_failed": False,
            "product_gate_rejected": False,
            "candidate_gate_rejected": 0,
            "rejection_details": [],
            "unsupported_source_url": True,
        }
    llm_client = None
    if llm_structured_extract:
        llm_client = getattr(thread_state, "llm_client", None)
        if llm_client is None:
            try:
                if llm_timeout_seconds is None and llm_retry_budget is None:
                    llm_client = _open_llm_client()
                else:
                    llm_client = _open_llm_client(
                        timeout_seconds=llm_timeout_seconds,
                        retry_budget=llm_retry_budget,
                    )
            except Exception:
                llm_client = None
            thread_state.llm_client = llm_client
    (
        products,
        scenarios,
        llm_used,
        llm_failed,
        product_gate_rejected,
        candidate_gate_rejected,
        rejection_details,
    ) = _extract_products_and_scenarios(
        row=row,
        llm_client=llm_client,
    )
    return {
        "row": row,
        "products": products,
        "scenarios": scenarios,
        "llm_used": llm_used,
        "llm_failed": llm_failed,
        "product_gate_rejected": product_gate_rejected,
        "candidate_gate_rejected": candidate_gate_rejected,
        "rejection_details": rejection_details,
        "unsupported_source_url": False,
    }


def _process_source_rows(
    rows: list[dict[str, Any]],
    *,
    concurrency: int,
    llm_structured_extract: bool,
    llm_timeout_seconds: float | None,
    llm_retry_budget: int | None,
) -> list[dict[str, Any]]:
    max_workers = max(1, int(concurrency or 1))
    if max_workers <= 1 or len(rows) <= 1:
        state = threading.local()
        return [
            _process_source_row(
                row=row,
                llm_structured_extract=llm_structured_extract,
                llm_timeout_seconds=llm_timeout_seconds,
                llm_retry_budget=llm_retry_budget,
                thread_state=state,
            )
            for row in rows
        ]
    results: list[dict[str, Any] | None] = [None] * len(rows)
    state = threading.local()
    with ThreadPoolExecutor(max_workers=min(max_workers, len(rows))) as executor:
        futures = {
            executor.submit(
                _process_source_row,
                row=row,
                llm_structured_extract=llm_structured_extract,
                llm_timeout_seconds=llm_timeout_seconds,
                llm_retry_budget=llm_retry_budget,
                thread_state=state,
            ): index
            for index, row in enumerate(rows)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [result for result in results if result is not None]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1

    conn = _open_database_connection(dsn)
    sql, params = _build_source_news_select_sql(
        limit=args.limit,
        source_adapters=tuple(args.source_adapter),
        company_ids=tuple(args.company_id),
    )
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    report: dict[str, Any] = {
        "news_total": len(rows),
        "news_processed": 0,
        "products_extracted": 0,
        "products_inserted": 0,
        "products_with_target_customers": 0,
        "scenarios_extracted": 0,
        "scenarios_inserted": 0,
        "source_adapters": list(args.source_adapter),
        "enrichment_batch_id": args.enrichment_batch_id,
        "llm_structured_extract": args.llm_structured_extract,
        "llm_fallback_used": 0,
        "llm_fallback_failed": 0,
        "generic_web_product_gate_rejected": 0,
        "generic_web_candidate_gate_rejected": 0,
        "source_candidate_gate_rejected": 0,
        "rejected_candidate_reasons": {},
        "rejected_candidates": [],
        "source_adapter_counts": {},
        "dry_run": args.dry_run,
        "concurrency": max(1, int(args.concurrency or 1)),
        "llm_timeout_seconds": args.llm_timeout_seconds,
        "llm_retry_budget": args.llm_retry_budget,
        "items": [],
        "scenario_items": [],
    }
    company_stats: dict[str, dict[str, int]] = {
        company_id: _empty_company_stage_stats() for company_id in args.company_id
    }

    row_results = _process_source_rows(
        rows,
        concurrency=max(1, int(args.concurrency or 1)),
        llm_structured_extract=args.llm_structured_extract,
        llm_timeout_seconds=args.llm_timeout_seconds,
        llm_retry_budget=args.llm_retry_budget,
    )
    for row_result in row_results:
        row = row_result["row"]
        report["news_processed"] += 1
        bucket = _source_bucket(report, row.get("source_adapter"))
        bucket["news_processed"] += 1
        company_id = str(row.get("company_id") or "")
        stats = company_stats.setdefault(company_id, _empty_company_stage_stats())
        stats["source_rows_processed"] += 1
        if row_result.get("unsupported_source_url"):
            stats["unsupported_source_rows"] += 1
            continue
        products = row_result["products"]
        scenarios = row_result["scenarios"]
        llm_used = bool(row_result["llm_used"])
        llm_failed = bool(row_result["llm_failed"])
        product_gate_rejected = bool(row_result["product_gate_rejected"])
        candidate_gate_rejected = int(row_result["candidate_gate_rejected"] or 0)
        rejection_details = row_result["rejection_details"]
        _record_rejection_details(report, rejection_details)
        if llm_used:
            report["llm_fallback_used"] += 1
            stats["llm_fallback_used"] += 1
        if llm_failed:
            report["llm_fallback_failed"] += 1
            stats["llm_fallback_failed"] += 1
        if product_gate_rejected:
            report["generic_web_product_gate_rejected"] += 1
            bucket["product_gate_rejected"] += 1
            stats["product_gate_rejected"] += 1
        if candidate_gate_rejected:
            report["source_candidate_gate_rejected"] += candidate_gate_rejected
            bucket["candidate_gate_rejected"] += candidate_gate_rejected
            stats["candidate_gate_rejected"] += candidate_gate_rejected
            if str(row.get("source_adapter") or "") == "generic_web":
                report["generic_web_candidate_gate_rejected"] += candidate_gate_rejected
        products_with_target_customers = sum(
            1 for product in products if product.target_customers
        )
        report["products_extracted"] += len(products)
        report["products_with_target_customers"] += products_with_target_customers
        report["scenarios_extracted"] += len(scenarios)
        bucket["products_extracted"] += len(products)
        bucket["scenarios_extracted"] += len(scenarios)
        stats["product_count"] += len(products)
        stats["scenario_count"] += len(scenarios)
        stats["products_with_target_customers"] += products_with_target_customers
        report_items = report["items"]
        assert isinstance(report_items, list)
        report_items.extend(_product_business_fields_to_json(product) for product in products)
        scenario_items = report["scenario_items"]
        assert isinstance(scenario_items, list)
        scenario_items.extend(
            application_scenario_to_json(scenario) for scenario in scenarios
        )
        if args.dry_run:
            continue
        source_tier = str(row.get("source_adapter") or "")
        inserted = _insert_products(conn, products, source_tier=source_tier)
        scenario_inserted = _insert_application_scenarios(
            conn,
            scenarios,
            source_tier=source_tier,
        )
        conn.commit()
        report["products_inserted"] += inserted
        report["scenarios_inserted"] += scenario_inserted
        bucket["products_inserted"] += inserted
        bucket["scenarios_inserted"] += scenario_inserted

    _checkpoint_company_stages(
        conn,
        batch_id=args.enrichment_batch_id,
        stage=args.checkpoint_stage,
        company_stats=company_stats,
        dry_run=args.dry_run,
    )
    if args.enrichment_batch_id and args.checkpoint_stage:
        conn.commit()

    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
