#!/usr/bin/env python3
"""Generate XLSX-baseline narratives and structure team_raw for companies."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
from pathlib import Path
import sys
import threading
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
import httpx
import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.data_agents.company.narrative_enrichment import (  # noqa: E402
    NarrativeResult,
    generate_company_narrative,
)
from src.data_agents.company.enrichment_batch import mark_company_stage_complete  # noqa: E402
from src.data_agents.company.llm_routing import resolve_company_llm_task_settings  # noqa: E402
from src.data_agents.company.provider_rate_limit import wrap_openai_client  # noqa: E402
from src.data_agents.company.source_material import CompanySourceMaterial  # noqa: E402
from src.data_agents.company.source_product_extractor import (  # noqa: E402
    persist_synthesized_products_and_scenarios,
    synthesize_products_and_scenarios_from_xlsx,
)
from src.data_agents.company.team_parser import structure_team_raw_with_llm  # noqa: E402
from src.data_agents.company.team_persistence import (  # noqa: E402
    persist_structured_team_members,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)

logger = logging.getLogger("run_company_xlsx_team_synthesis")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synthesize company narrative and structured team facts from XLSX baseline.",
    )
    parser.add_argument("--company-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--enrichment-batch-id", default=None)
    parser.add_argument(
        "--include-source-materials",
        action="store_true",
        help="Include accepted products, scenarios, news, and signal events when synthesizing narratives.",
    )
    parser.add_argument(
        "--skip-team",
        action="store_true",
        help="Only synthesize narratives; do not re-run team_raw structuring.",
    )
    parser.add_argument(
        "--skip-narrative",
        action="store_true",
        help="Only structure team_raw; do not generate profile or technology narratives.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Per-process worker concurrency for company-level LLM work.",
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
        help="Optional company_enrichment stage name to checkpoint after each company.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _open_llm_client(
    task_type: str,
    *,
    timeout_seconds: float | None = None,
    retry_budget: int | None = None,
):
    from openai import OpenAI

    settings = resolve_company_llm_task_settings(
        task_type,
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


def _llm_task_type_for_args(*, include_source_materials: bool, skip_narrative: bool) -> str:
    if include_source_materials and not skip_narrative:
        return "multi_source_profile_synthesis"
    return "trusted_xlsx_structuring"


def _build_select_sql(
    *,
    company_ids: tuple[str, ...],
    limit: int | None,
    include_source_materials: bool = False,
) -> tuple[str, tuple[Any, ...]]:
    conditions = ["c.identity_status = 'resolved'"]
    params: list[Any] = []
    if company_ids:
        placeholders = ", ".join(["%s"] * len(company_ids))
        conditions.append(f"c.company_id IN ({placeholders})")
        params.extend(company_ids)
    select_extras = ""
    joins = ""
    if include_source_materials:
        select_extras = (
            ", COALESCE(products.products_json, '[]'::jsonb) AS products_json"
            ", COALESCE(source_materials.source_materials_json, '[]'::jsonb) AS source_materials_json"
        )
        joins = (
            "  LEFT JOIN LATERAL ("
            "       SELECT jsonb_agg("
            "                  jsonb_build_object("
            "                      'name', ranked.canonical_name,"
            "                      'description', ranked.short_description,"
            "                      'product_category', ranked.product_category,"
            "                      'target_customers', ranked.target_customers,"
            "                      'application_scenarios', ranked.application_scenarios,"
            "                      'technical_tags', ranked.technical_tags,"
            "                      'source_url', ranked.official_product_url,"
            "                      'quality_status', ranked.quality_status,"
            "                      'confidence', ranked.confidence,"
            "                      'source_tier', ranked.source_tier"
            "                  )"
            "                  ORDER BY ranked.priority, ranked.confidence DESC NULLS LAST,"
            "                           ranked.last_refreshed_at DESC NULLS LAST"
            "              ) AS products_json"
            "         FROM ("
            "              SELECT cp.canonical_name, cp.short_description, cp.product_category,"
            "                     cp.target_customers, cp.application_scenarios, cp.technical_tags,"
            "                     cp.official_product_url, cp.quality_status, cp.confidence,"
            "                     cp.last_refreshed_at,"
            "                     CASE WHEN cp.quality_status = 'ready' THEN 0 ELSE 1 END AS priority,"
            "                     ("
            "                         SELECT e.source_tier"
            "                           FROM company_product_evidence e"
            "                          WHERE e.product_id = cp.product_id"
            "                          ORDER BY CASE e.source_tier"
            "                                   WHEN 'xlsx' THEN 0"
            "                                   WHEN 'official_site' THEN 1"
            "                                   WHEN 'official' THEN 1"
            "                                   WHEN 'pitchhub_36kr' THEN 2"
            "                                   WHEN 'iyiou' THEN 2"
            "                                   WHEN 'generic_web' THEN 3"
            "                                   ELSE 9 END,"
            "                                   e.created_at DESC NULLS LAST"
            "                          LIMIT 1"
            "                     ) AS source_tier"
            "                FROM company_product cp"
            "               WHERE cp.company_id = c.company_id"
            "                 AND cp.quality_status = 'ready'"
            "               ORDER BY priority, cp.confidence DESC NULLS LAST,"
            "                        cp.last_refreshed_at DESC NULLS LAST"
            "               LIMIT 16"
            "         ) ranked"
            "  ) products ON true"
            "  LEFT JOIN LATERAL ("
            "       SELECT jsonb_agg("
            "                  jsonb_build_object("
            "                      'source_tier', material.source_tier,"
            "                      'url', material.url,"
            "                      'title', material.title,"
            "                      'captured_text', material.captured_text,"
            "                      'trust_reason', material.trust_reason"
            "                  )"
            "                  ORDER BY material.priority, material.captured_at DESC NULLS LAST"
            "              ) AS source_materials_json"
            "         FROM ("
            "              SELECT *"
            "                FROM ("
            "              SELECT 0 AS priority, s.last_refreshed_at AS captured_at,"
            "                     'structured_scenario'::text AS source_tier,"
            "                     s.source_url AS url,"
            "                     s.scenario_name AS title,"
            "                     concat_ws('；', s.description, s.target_customer, s.scenario_category) AS captured_text,"
            "                     'ready scenario linked to the company'::text AS trust_reason"
            "                FROM company_application_scenario s"
            "               WHERE s.company_id = c.company_id"
            "                 AND s.quality_status = 'ready'"
            "              UNION ALL"
            "              SELECT CASE n.source_adapter"
            "                         WHEN 'pitchhub_36kr' THEN 1"
            "                         WHEN 'iyiou' THEN 1"
            "                         WHEN 'generic_web' THEN 3"
            "                         ELSE 5 END AS priority,"
            "                     n.fetched_at AS captured_at,"
            "                     COALESCE(n.source_adapter, n.source_domain_tier) AS source_tier,"
            "                     n.source_url AS url,"
            "                     n.title,"
            "                     n.summary_clean AS captured_text,"
            "                     COALESCE(n.extraction_diagnostics->>'trust_reason',"
            "                              CASE WHEN n.is_company_confirmed THEN 'company identity confirmed' END) AS trust_reason"
            "                FROM company_news_item n"
            "               WHERE n.company_id = c.company_id"
            "                 AND n.summary_clean IS NOT NULL"
            "                 AND n.summary_clean <> ''"
            "                 AND n.source_adapter IN ('iyiou', 'pitchhub_36kr', 'generic_web')"
            "                 AND n.is_company_confirmed = true"
            "              UNION ALL"
            "              SELECT 2 AS priority,"
            "                     e.created_at AS captured_at,"
            "                     COALESCE(n.source_adapter, 'structured_signal') AS source_tier,"
            "                     n.source_url AS url,"
            "                     concat_ws(' / ', e.event_type, e.event_date::text) AS title,"
            "                     concat_ws('；', e.event_summary, e.event_subject_normalized::text) AS captured_text,"
            "                     'structured company signal event'::text AS trust_reason"
            "                FROM company_signal_event e"
            "                LEFT JOIN company_news_item n ON n.news_id = e.primary_news_id"
            "               WHERE e.company_id = c.company_id"
            "                 AND e.status IN ('active', 'needs_review')"
            "                ) material_candidates"
            "               WHERE material_candidates.captured_text IS NOT NULL"
            "                 AND material_candidates.captured_text <> ''"
            "               ORDER BY material_candidates.priority,"
            "                        material_candidates.captured_at DESC NULLS LAST"
            "               LIMIT 24"
            "         ) material"
            "  ) source_materials ON true"
        )
    sql = (
        "SELECT c.company_id, c.canonical_name, c.hq_city, "
        "       latest.snapshot_id, latest.project_name, latest.industry, latest.description, "
        "       latest.business, latest.product_intro, latest.product_features, "
        f"       latest.application_scenarios_raw, latest.team_raw{select_extras} "
        "  FROM company c "
        "  JOIN LATERAL ("
        "       SELECT cs.snapshot_id, cs.project_name, cs.industry, cs.description, "
        "              cs.business, cs.team_raw, "
        "              cs.raw_row_jsonb->>'product_intro' AS product_intro, "
        "              cs.raw_row_jsonb->>'product_features' AS product_features, "
        "              cs.raw_row_jsonb->>'application_scenarios_raw' AS application_scenarios_raw "
        "         FROM company_snapshot cs "
        "        WHERE cs.company_id = c.company_id "
        "        ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC "
        "        LIMIT 1"
        f"  ) latest ON true {joins} "
        f" WHERE {' AND '.join(conditions)} "
        " ORDER BY c.company_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _json_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _persist_narrative(
    conn: Any,
    *,
    company_id: str,
    result: NarrativeResult,
    run_id: UUID | str,
) -> None:
    conn.execute(
        """
        UPDATE company
           SET profile_summary = %(profile_summary)s,
               technology_route_summary = %(technology_route_summary)s,
               run_id = %(run_id)s,
               updated_at = now()
         WHERE company_id = %(company_id)s
        """,
        {
            "company_id": company_id,
            "profile_summary": result.profile_summary,
            "technology_route_summary": result.technology_route_summary,
            "run_id": run_id,
        },
    )


def _xlsx_product_source_material(row: dict[str, Any]) -> CompanySourceMaterial:
    company_id = str(row["company_id"])
    source_text_parts = [
        ("行业", row.get("industry")),
        ("简介", row.get("description")),
        ("业务", row.get("business")),
        ("产品简介", row.get("product_intro")),
        ("产品特点", row.get("product_features")),
        ("应用场景", row.get("application_scenarios_raw")),
        ("团队", row.get("team_raw")),
    ]
    captured_text = "\n".join(
        f"{label}: {str(value).strip()}"
        for label, value in source_text_parts
        if str(value or "").strip()
    )
    return CompanySourceMaterial(
        source_id=f"xlsx:{company_id}",
        source_tier="xlsx",
        url=f"xlsx://company/{company_id}",
        title=f"XLSX trusted baseline - {row.get('canonical_name') or company_id}",
        captured_text=captured_text,
        captured_at=None,
        trust_reason="trusted_xlsx_baseline",
    )


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _join_unique(values: list[str], *, limit: int = 8) -> str:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return "、".join(result)


def _trusted_xlsx_fallback_narrative(
    row: dict[str, Any],
    *,
    products: list[Any],
    scenarios: list[Any],
    original_error: str | None,
) -> NarrativeResult | None:
    """Build a factual narrative when the LLM refuses sparse trusted XLSX facts.

    The fallback is intentionally conservative: it only restates imported XLSX
    fields and already-structured product/scenario candidates. It should keep
    mandatory release fields non-empty without inventing financing, team, or
    customer facts for sparse rows.
    """
    company_name = _clean_text(row.get("canonical_name"))
    project_name = _clean_text(row.get("project_name"))
    industry = _clean_text(row.get("industry"))
    hq_city = _clean_text(row.get("hq_city"))
    description = _clean_text(row.get("description"))
    business = _clean_text(row.get("business"))
    product_intro = _clean_text(row.get("product_intro"))
    product_features = _clean_text(row.get("product_features"))
    application_scenarios_raw = _clean_text(row.get("application_scenarios_raw"))
    product_names = _join_unique(
        [
            _clean_text(getattr(product, "product_name", ""))
            for product in products
        ]
    )
    product_descriptions = _join_unique(
        [
            _clean_text(getattr(product, "short_description", ""))
            for product in products
        ],
        limit=4,
    )
    product_categories = _join_unique(
        [
            _clean_text(getattr(product, "product_category", ""))
            for product in products
        ]
    )
    technical_tags = _join_unique(
        [
            str(tag)
            for product in products
            for tag in getattr(product, "technical_tags", ()) or ()
        ]
    )
    scenario_names = _join_unique(
        [
            _clean_text(getattr(scenario, "scenario_name", ""))
            for scenario in scenarios
        ]
    )
    target_customers = _join_unique(
        [
            str(customer)
            for product in products
            for customer in getattr(product, "target_customers", ()) or ()
        ]
        + [
            _clean_text(getattr(scenario, "target_customer", ""))
            for scenario in scenarios
        ]
    )
    application_scenarios = _join_unique(
        [
            str(scenario)
            for product in products
            for scenario in getattr(product, "application_scenarios", ()) or ()
        ]
        + [scenario_names, application_scenarios_raw]
    )

    factual_parts = [
        company_name,
        project_name,
        industry,
        hq_city,
        description,
        business,
        product_intro,
        product_features,
        application_scenarios_raw,
        product_names,
        product_descriptions,
        product_categories,
        technical_tags,
        target_customers,
        application_scenarios,
    ]
    if sum(len(part) for part in factual_parts if part) < 12:
        return None

    subject = company_name or project_name or "该企业"
    intro_parts = [f"根据导入 XLSX 可信基线，{subject}"]
    if project_name and project_name != subject:
        intro_parts.append(f"项目或品牌名称为{project_name}")
    if hq_city:
        intro_parts.append(f"所在城市为{hq_city}")
    if industry:
        intro_parts.append(f"行业归类为{industry}")
    if business:
        intro_parts.append(f"业务定位为{business}")
    elif description:
        intro_parts.append(f"表格简介显示其业务为{description}")
    profile_sentences = ["，".join(intro_parts) + "。"]
    if description and description != business:
        profile_sentences.append(f"表格中的公司简介为：{description}。")
    if product_intro:
        profile_sentences.append(f"产品简介显示：{product_intro}。")
    if product_features:
        profile_sentences.append(f"产品特点包括：{product_features}。")
    if product_names or product_descriptions:
        profile_sentences.append(
            "已结构化出的产品或服务包括"
            f"{product_names or product_descriptions}。"
        )
    if target_customers:
        profile_sentences.append(f"现有材料中可确认的目标客户包括{target_customers}。")
    if application_scenarios:
        profile_sentences.append(f"可确认的应用场景包括{application_scenarios}。")
    profile_sentences.append(
        "当前简介只基于可信 XLSX 字段和已通过归属判断的结构化事实生成；"
        "未在材料中出现的融资、团队、客户案例或经营数据不会被补写，后续可由官网、36Kr、亿欧或通用网页材料继续增强。"
    )

    technology_sentences = []
    if technical_tags:
        technology_sentences.append(f"技术路线方面，现有材料显示其技术标签包括{technical_tags}。")
    elif product_categories:
        technology_sentences.append(f"技术路线方面，现有材料显示其产品类别集中在{product_categories}。")
    elif business:
        technology_sentences.append(f"技术路线方面，现有材料显示其围绕{business}展开。")
    else:
        technology_sentences.append(
            f"技术路线方面，当前材料仅能确认{subject}的基础业务定位。"
        )
    if product_names:
        technology_sentences.append(f"核心产品或服务名称包括{product_names}。")
    if product_descriptions:
        technology_sentences.append(f"产品描述显示：{product_descriptions}。")
    if product_features:
        technology_sentences.append(f"产品能力或特点包括：{product_features}。")
    if application_scenarios:
        technology_sentences.append(f"技术和产品主要服务于{application_scenarios}等场景。")
    technology_sentences.append(
        "由于当前没有更多通过身份确认的外部来源，技术路线摘要保持保守表述，"
        "只保留 XLSX 与结构化产品字段中已经出现的事实，并等待后续外部来源补强。"
    )

    return NarrativeResult(
        profile_summary="".join(profile_sentences),
        technology_route_summary="".join(technology_sentences),
        error=None,
        blockers=(
            "trusted_xlsx_fallback",
            *(("original_error:" + original_error,) if original_error else ()),
        ),
    )


def _process_company(
    *,
    conn: Any,
    row: dict[str, Any],
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any],
    dry_run: bool,
    run_id: UUID | str,
    product_llm_client: Any | None = None,
    product_llm_model: str | None = None,
    product_extra_body: dict[str, Any] | None = None,
    include_source_materials: bool = False,
    skip_team: bool = False,
    skip_narrative: bool = False,
) -> dict[str, Any]:
    company_id = str(row["company_id"])
    products = _json_list(row.get("products_json")) if include_source_materials else None
    source_materials = (
        _json_list(row.get("source_materials_json"))
        if include_source_materials
        else None
    )
    if skip_narrative:
        result = NarrativeResult(
            profile_summary="",
            technology_route_summary="",
            error=None,
        )
    else:
        result = generate_company_narrative(
            company_name=str(row.get("canonical_name") or ""),
            industry=row.get("industry"),
            hq_city=row.get("hq_city"),
            description=row.get("description"),
            business=row.get("business"),
            products=products,
            source_materials=source_materials,
            llm_client=llm_client,
            llm_model=llm_model,
            extra_body=extra_body,
        )
    members = []
    if not skip_team:
        members = structure_team_raw_with_llm(
            row.get("team_raw"),
            company_name=str(row.get("canonical_name") or ""),
            llm_client=llm_client,
            llm_model=llm_model,
            extra_body=extra_body,
        )

    team_members_written = 0
    if members and row.get("snapshot_id") is not None:
        if dry_run:
            team_members_written = len(members)
        else:
            team_members_written = persist_structured_team_members(
                conn,
                company_id=company_id,
                snapshot_id=row["snapshot_id"],
                members=members,
            )
    xlsx_products = []
    xlsx_scenarios = []
    products_written = 0
    scenarios_written = 0
    product_diagnostics: dict[str, Any] = {}
    xlsx_products, xlsx_scenarios = synthesize_products_and_scenarios_from_xlsx(
        company_id=company_id,
        company_name=str(row.get("canonical_name") or ""),
        project_name=str(row.get("project_name") or row.get("canonical_name") or ""),
        industry=row.get("industry"),
        description=row.get("description"),
        business=row.get("business"),
        product_intro=row.get("product_intro"),
        product_features=row.get("product_features"),
        application_scenarios_raw=row.get("application_scenarios_raw"),
        team_raw=row.get("team_raw"),
        llm_client=product_llm_client or llm_client,
        llm_model=product_llm_model or llm_model,
        extra_body=product_extra_body or extra_body,
        diagnostics=product_diagnostics,
    )
    if xlsx_products or xlsx_scenarios:
        if dry_run:
            products_written = len(xlsx_products)
            scenarios_written = len(xlsx_scenarios)
        else:
            write_report = persist_synthesized_products_and_scenarios(
                conn=conn,
                products=xlsx_products,
                scenarios=xlsx_scenarios,
                source_materials=[_xlsx_product_source_material(row)],
                extractor_version=(
                    "post_collection_xlsx_product_synthesis.v1"
                    if include_source_materials
                    else "xlsx_product_synthesis.v1"
                ),
            )
            products_written = int(write_report.get("products_inserted") or 0)
            scenarios_written = int(write_report.get("scenarios_inserted") or 0)
    narratives_written = 0
    narratives_rejected = 0
    narrative_fallback_used = False
    original_narrative_error = result.error
    final_result = result
    if skip_narrative:
        pass
    elif result.error is not None:
        fallback = _trusted_xlsx_fallback_narrative(
            row,
            products=xlsx_products,
            scenarios=xlsx_scenarios,
            original_error=result.error,
        )
        if fallback is not None:
            final_result = fallback
            narrative_fallback_used = True
            narratives_written = 1
            if not dry_run:
                _persist_narrative(
                    conn,
                    company_id=company_id,
                    result=final_result,
                    run_id=run_id,
                )
        else:
            narratives_rejected = 1
    else:
        narratives_written = 1
        if not dry_run:
            _persist_narrative(
                conn,
                company_id=company_id,
                result=final_result,
                run_id=run_id,
            )
    return {
        "company_id": company_id,
        "narratives_written": narratives_written,
        "narratives_rejected": narratives_rejected,
        "narrative_fallback_used": narrative_fallback_used,
        "original_narrative_error": original_narrative_error,
        "team_members_written": team_members_written,
        "team_members_extracted": len(members),
        "products_synthesized": len(xlsx_products),
        "products_with_target_customers": sum(
            1 for product in xlsx_products if product.target_customers
        ),
        "scenarios_synthesized": len(xlsx_scenarios),
        "products_written": products_written,
        "scenarios_written": scenarios_written,
        "product_synthesis_diagnostics": product_diagnostics,
        "product_synthesis_error": product_diagnostics.get("llm_fallback_error"),
        "narrative_skipped": skip_narrative,
        "error": None if narrative_fallback_used else result.error,
    }


def _checkpoint_company_stage(
    conn: Any,
    *,
    batch_id: str | None,
    stage: str | None,
    company_report: dict[str, Any],
    dry_run: bool,
) -> None:
    if not batch_id or not stage:
        return
    company_id = str(company_report.get("company_id") or "")
    if not company_id:
        return
    counters = {
        "product_count": int(company_report.get("products_written") or 0),
        "scenario_count": int(company_report.get("scenarios_written") or 0),
    }
    details = {
        "produced_facts": {
            "products": int(company_report.get("products_synthesized") or 0),
            "scenarios": int(company_report.get("scenarios_synthesized") or 0),
            "narratives": int(company_report.get("narratives_written") or 0),
            "narrative_fallbacks": (
                1 if company_report.get("narrative_fallback_used") else 0
            ),
            "team_members": int(company_report.get("team_members_extracted") or 0),
        },
        "rejected_facts": {
            "narratives_rejected": int(
                company_report.get("narratives_rejected") or 0
            ),
            "original_narrative_error": company_report.get(
                "original_narrative_error"
            ),
            "companies_with_errors": 1 if company_report.get("error") else 0,
            "product_synthesis_errors": (
                1 if company_report.get("product_synthesis_error") else 0
            ),
        },
        "persistence_outcome": {
            "dry_run": dry_run,
            "status": "failed" if company_report.get("error") else "succeeded",
        },
    }
    product_diagnostics = company_report.get("product_synthesis_diagnostics")
    if isinstance(product_diagnostics, dict) and product_diagnostics:
        details["product_synthesis_diagnostics"] = {
            str(key): value for key, value in product_diagnostics.items()
        }
    mark_company_stage_complete(
        conn,
        batch_id=batch_id,
        company_id=company_id,
        stage=stage,
        counters=counters,
        details=details,
        miss_reason="llm_rejected" if company_report.get("error") else None,
        status="failed" if company_report.get("error") else "partial",
        last_error=company_report.get("error") or None,
    )


def _run_company_worker(
    *,
    dsn: str,
    row: dict[str, Any],
    llm_task_type: str,
    dry_run: bool,
    run_id: UUID | str,
    include_source_materials: bool,
    skip_team: bool,
    skip_narrative: bool,
    enrichment_batch_id: str | None,
    checkpoint_stage: str | None,
    llm_timeout_seconds: float | None,
    llm_retry_budget: int | None,
    thread_state: threading.local,
) -> dict[str, Any]:
    conn = _open_database_connection(dsn)
    try:
        llm_bundle = getattr(thread_state, "llm_bundle", None)
        if llm_bundle is None:
            llm_bundle = _open_llm_client(
                llm_task_type,
                timeout_seconds=llm_timeout_seconds,
                retry_budget=llm_retry_budget,
            )
            thread_state.llm_bundle = llm_bundle
        llm_client, llm_model, extra_body = llm_bundle
        if llm_task_type == "generic_product_admission":
            product_llm_bundle = llm_bundle
        else:
            product_llm_bundle = getattr(thread_state, "product_llm_bundle", None)
            if product_llm_bundle is None:
                product_llm_bundle = _open_llm_client(
                    "generic_product_admission",
                    timeout_seconds=llm_timeout_seconds,
                    retry_budget=llm_retry_budget,
                )
                thread_state.product_llm_bundle = product_llm_bundle
        product_llm_client, product_llm_model, product_extra_body = product_llm_bundle
        company_report = _process_company(
            conn=conn,
            row=row,
            llm_client=llm_client,
            llm_model=llm_model,
            extra_body=extra_body,
            product_llm_client=product_llm_client,
            product_llm_model=product_llm_model,
            product_extra_body=product_extra_body,
            dry_run=dry_run,
            run_id=run_id,
            include_source_materials=include_source_materials,
            skip_team=skip_team,
            skip_narrative=skip_narrative,
        )
        _checkpoint_company_stage(
            conn,
            batch_id=enrichment_batch_id,
            stage=checkpoint_stage,
            company_report=company_report,
            dry_run=dry_run,
        )
        if not dry_run:
            conn.commit()
        elif enrichment_batch_id and checkpoint_stage:
            conn.commit()
        return company_report
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        company_report = {
            "company_id": str(row.get("company_id") or ""),
            "narratives_written": 0,
            "narratives_rejected": 0,
            "narrative_fallback_used": False,
            "original_narrative_error": None,
            "team_members_extracted": 0,
            "team_members_written": 0,
            "products_synthesized": 0,
            "products_with_target_customers": 0,
            "scenarios_synthesized": 0,
            "products_written": 0,
            "scenarios_written": 0,
            "product_synthesis_diagnostics": {},
            "product_synthesis_error": None,
            "error": str(exc),
        }
        try:
            _checkpoint_company_stage(
                conn,
                batch_id=enrichment_batch_id,
                stage=checkpoint_stage,
                company_report=company_report,
                dry_run=dry_run,
            )
            conn.commit()
        except Exception:
            conn.rollback()
        return company_report
    finally:
        conn.close()


def _process_rows(
    *,
    dsn: str,
    rows: list[dict[str, Any]],
    concurrency: int,
    llm_task_type: str,
    dry_run: bool,
    run_id: UUID | str,
    include_source_materials: bool,
    skip_team: bool,
    skip_narrative: bool,
    enrichment_batch_id: str | None,
    checkpoint_stage: str | None,
    llm_timeout_seconds: float | None,
    llm_retry_budget: int | None,
) -> list[dict[str, Any]]:
    max_workers = max(1, int(concurrency or 1))
    if max_workers <= 1 or len(rows) <= 1:
        state = threading.local()
        return [
            _run_company_worker(
                dsn=dsn,
                row=row,
                llm_task_type=llm_task_type,
                dry_run=dry_run,
                run_id=run_id,
                include_source_materials=include_source_materials,
                skip_team=skip_team,
                skip_narrative=skip_narrative,
                enrichment_batch_id=enrichment_batch_id,
                checkpoint_stage=checkpoint_stage,
                llm_timeout_seconds=llm_timeout_seconds,
                llm_retry_budget=llm_retry_budget,
                thread_state=state,
            )
            for row in rows
        ]
    reports: list[dict[str, Any] | None] = [None] * len(rows)
    thread_state = threading.local()
    with ThreadPoolExecutor(max_workers=min(max_workers, len(rows))) as executor:
        futures = {
            executor.submit(
                _run_company_worker,
                dsn=dsn,
                row=row,
                llm_task_type=llm_task_type,
                dry_run=dry_run,
                run_id=run_id,
                include_source_materials=include_source_materials,
                skip_team=skip_team,
                skip_narrative=skip_narrative,
                enrichment_batch_id=enrichment_batch_id,
                checkpoint_stage=checkpoint_stage,
                llm_timeout_seconds=llm_timeout_seconds,
                llm_retry_budget=llm_retry_budget,
                thread_state=thread_state,
            ): index
            for index, row in enumerate(rows)
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
            "task": "company_xlsx_team_synthesis",
            "company_ids": list(args.company_id),
            "limit": args.limit,
            "dry_run": args.dry_run,
            "enrichment_batch_id": args.enrichment_batch_id,
            "include_source_materials": args.include_source_materials,
            "skip_team": args.skip_team,
            "skip_narrative": args.skip_narrative,
            "concurrency": args.concurrency,
            "llm_timeout_seconds": args.llm_timeout_seconds,
            "llm_retry_budget": args.llm_retry_budget,
            "checkpoint_stage": args.checkpoint_stage,
            "product_llm_task_type": "generic_product_admission",
        },
        triggered_by="run_company_xlsx_team_synthesis",
    )
    conn.commit()
    try:
        llm_task_type = _llm_task_type_for_args(
            include_source_materials=args.include_source_materials,
            skip_narrative=args.skip_narrative,
        )
        sql, params = _build_select_sql(
            company_ids=tuple(args.company_id),
            limit=args.limit,
            include_source_materials=args.include_source_materials,
        )
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        report: dict[str, Any] = {
            "run_id": str(run_id),
            "companies_total": len(rows),
            "companies_processed": 0,
            "narratives_written": 0,
            "narratives_rejected": 0,
            "narrative_fallbacks": 0,
            "team_members_extracted": 0,
            "team_members_written": 0,
            "products_synthesized": 0,
            "products_with_target_customers": 0,
            "scenarios_synthesized": 0,
            "products_written": 0,
            "scenarios_written": 0,
            "product_synthesis_failures": 0,
            "companies_with_errors": 0,
            "dry_run": args.dry_run,
            "concurrency": max(1, int(args.concurrency or 1)),
            "llm_timeout_seconds": args.llm_timeout_seconds,
            "llm_retry_budget": args.llm_retry_budget,
            "llm_task_type": llm_task_type,
            "product_llm_task_type": "generic_product_admission",
            "company_reports": [],
        }
        company_reports = _process_rows(
            dsn=dsn,
            rows=rows,
            concurrency=max(1, int(args.concurrency or 1)),
            llm_task_type=llm_task_type,
            dry_run=args.dry_run,
            run_id=run_id,
            include_source_materials=args.include_source_materials,
            skip_team=args.skip_team,
            skip_narrative=args.skip_narrative,
            enrichment_batch_id=args.enrichment_batch_id,
            checkpoint_stage=args.checkpoint_stage,
            llm_timeout_seconds=args.llm_timeout_seconds,
            llm_retry_budget=args.llm_retry_budget,
        )
        for company_report in company_reports:
            if company_report.get("error"):
                logger.warning(
                    "XLSX/team synthesis failed for %s: %s",
                    company_report.get("company_id"),
                    company_report.get("error"),
                )
                report["companies_with_errors"] += 1
            report["companies_processed"] += 1
            for key in (
                "narratives_written",
                "narratives_rejected",
                "team_members_extracted",
                "team_members_written",
                "products_synthesized",
                "products_with_target_customers",
                "scenarios_synthesized",
                "products_written",
                "scenarios_written",
            ):
                report[key] += int(company_report.get(key) or 0)
            if company_report.get("narrative_fallback_used"):
                report["narrative_fallbacks"] += 1
            if company_report.get("product_synthesis_error"):
                report["product_synthesis_failures"] += 1
            report["company_reports"].append(company_report)
        close_pipeline_run(
            conn,
            run_id,
            status="partial" if report["companies_with_errors"] else "succeeded",
            items_processed=report["companies_processed"],
            items_failed=report["companies_with_errors"],
        )
        conn.commit()
        print(json.dumps(report, ensure_ascii=False))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
