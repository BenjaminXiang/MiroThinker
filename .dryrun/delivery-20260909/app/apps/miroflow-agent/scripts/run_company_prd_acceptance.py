#!/usr/bin/env python3
"""Company PRD acceptance closure utilities."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.professor.vectorizer import EmbeddingClient  # noqa: E402
from src.data_agents.providers.local_api_key import load_local_api_key  # noqa: E402
from src.data_agents.providers.rerank import RerankerClient  # noqa: E402
from src.data_agents.service.retrieval import RetrievalService  # noqa: E402

DEFAULT_DSN = "postgresql://miroflow:miroflow@localhost:15432/miroflow_real"
RUN_DIR = REPO_ROOT / ".agents" / "runs" / "company-prd-acceptance-closure"
HIGH_TRUST_SOURCE_TIERS = {"xlsx", "official", "official_site", "iyiou", "pitchhub_36kr"}

COMPANY_TOP5_QUERIES: list[dict[str, str]] = [
    {"query_id": "robotics-001", "category": "surgical_robot", "query": "深圳做手术机器人的公司"},
    {"query_id": "robotics-002", "category": "surgical_robot", "query": "腔镜手术机器人深圳厂商"},
    {"query_id": "robotics-003", "category": "surgical_robot", "query": "骨科机器人企业"},
    {"query_id": "robotics-004", "category": "surgical_robot", "query": "血管介入机器人公司"},
    {"query_id": "robotics-005", "category": "surgical_robot", "query": "医疗机器人导航定位公司"},
    {"query_id": "autonomous-001", "category": "autonomous_driving", "query": "自动驾驶感知公司"},
    {"query_id": "autonomous-002", "category": "autonomous_driving", "query": "L4 自动驾驶解决方案"},
    {"query_id": "autonomous-003", "category": "autonomous_driving", "query": "深圳车载激光雷达企业"},
    {"query_id": "autonomous-004", "category": "autonomous_driving", "query": "智能驾驶算法公司"},
    {"query_id": "autonomous-005", "category": "autonomous_driving", "query": "自动驾驶仿真测试平台"},
    {"query_id": "ai-chip-001", "category": "ai_chip", "query": "做 AI 芯片"},
    {"query_id": "ai-chip-002", "category": "ai_chip", "query": "边缘 AI 芯片企业"},
    {"query_id": "ai-chip-003", "category": "ai_chip", "query": "深圳算力芯片公司"},
    {"query_id": "ai-chip-004", "category": "ai_chip", "query": "人工智能处理器研发商"},
    {"query_id": "ai-chip-005", "category": "ai_chip", "query": "AI 加速芯片解决方案"},
    {"query_id": "llm-001", "category": "large_model", "query": "做大模型的公司"},
    {"query_id": "llm-002", "category": "large_model", "query": "企业级大模型应用平台"},
    {"query_id": "llm-003", "category": "large_model", "query": "医疗大模型公司"},
    {"query_id": "llm-004", "category": "large_model", "query": "多模态大模型企业"},
    {"query_id": "llm-005", "category": "large_model", "query": "AIGC 内容生成平台"},
    {"query_id": "quantum-001", "category": "quantum", "query": "量子计算公司"},
    {"query_id": "quantum-002", "category": "quantum", "query": "量子通信设备企业"},
    {"query_id": "quantum-003", "category": "quantum", "query": "量子测量传感公司"},
    {"query_id": "quantum-004", "category": "quantum", "query": "量子安全密码产品"},
    {"query_id": "quantum-005", "category": "quantum", "query": "深圳量子科技企业"},
    {"query_id": "industrial-software-001", "category": "industrial_software", "query": "工业软件公司"},
    {"query_id": "industrial-software-002", "category": "industrial_software", "query": "深圳 EDA 工具"},
    {"query_id": "industrial-software-003", "category": "industrial_software", "query": "MES 生产管理系统企业"},
    {"query_id": "industrial-software-004", "category": "industrial_software", "query": "工业仿真软件平台"},
    {"query_id": "industrial-software-005", "category": "industrial_software", "query": "智能制造工业互联网平台"},
    {"query_id": "biomed-001", "category": "biomed", "query": "做基因测序的公司"},
    {"query_id": "biomed-002", "category": "biomed", "query": "医疗 AI 影像诊断企业"},
    {"query_id": "biomed-003", "category": "biomed", "query": "创新药研发平台公司"},
    {"query_id": "biomed-004", "category": "biomed", "query": "多组学人工智能公司"},
    {"query_id": "biomed-005", "category": "biomed", "query": "体外诊断设备公司"},
    {"query_id": "energy-001", "category": "new_energy", "query": "做储能的公司"},
    {"query_id": "energy-002", "category": "new_energy", "query": "电池管理系统企业"},
    {"query_id": "energy-003", "category": "new_energy", "query": "新能源充电设备公司"},
    {"query_id": "energy-004", "category": "new_energy", "query": "光伏逆变器企业"},
    {"query_id": "energy-005", "category": "new_energy", "query": "氢能设备深圳公司"},
    {"query_id": "semiconductor-001", "category": "semiconductor", "query": "深圳半导体设备"},
    {"query_id": "semiconductor-002", "category": "semiconductor", "query": "光刻胶供应商"},
    {"query_id": "semiconductor-003", "category": "semiconductor", "query": "芯片封装测试企业"},
    {"query_id": "semiconductor-004", "category": "semiconductor", "query": "功率半导体器件公司"},
    {"query_id": "semiconductor-005", "category": "semiconductor", "query": "半导体材料企业"},
    {"query_id": "machine-tool-001", "category": "industrial_machine_tool", "query": "工业母机企业"},
    {"query_id": "machine-tool-002", "category": "industrial_machine_tool", "query": "深圳 CNC 机床"},
    {"query_id": "machine-tool-003", "category": "industrial_machine_tool", "query": "做激光切割机的"},
    {"query_id": "machine-tool-004", "category": "industrial_machine_tool", "query": "精密加工装备公司"},
    {"query_id": "machine-tool-005", "category": "industrial_machine_tool", "query": "数控系统解决方案"},
]

COMPANY_CANDIDATE_POOL_QUERIES: list[dict[str, Any]] = [
    {
        "query_id": "pilot-001",
        "category": "medical_robotics",
        "query": "深圳做手术机器人的公司",
        "terms": ["手术机器人", "腔镜机器人", "骨科机器人", "介入机器人", "手术导航", "医疗机器人"],
    },
    {
        "query_id": "pilot-002",
        "category": "lidar",
        "query": "深圳做车载激光雷达的公司",
        "terms": ["车载激光雷达", "激光雷达", "LiDAR", "DTOF", "智能驾驶感知", "自动驾驶感知"],
    },
    {
        "query_id": "pilot-003",
        "category": "optics",
        "query": "深圳做平面超透镜的公司",
        "terms": ["平面超透镜", "超透镜", "微纳结构", "平面光学", "光学透镜", "AR/VR"],
    },
    {
        "query_id": "pilot-004",
        "category": "medical_ai",
        "query": "深圳做心电 AI 诊断的公司",
        "terms": ["心电", "AI心电", "心电诊断", "心电筛查", "远程心电", "医疗AI诊断"],
    },
    {
        "query_id": "pilot-005",
        "category": "humanoid_robot",
        "query": "深圳做人形机器人的公司",
        "terms": ["人形机器人", "具身智能", "服务机器人", "工业机器人", "机器人本体", "伺服控制"],
    },
    {
        "query_id": "pilot-006",
        "category": "ai_chip",
        "query": "深圳做 AI 芯片和算力芯片的公司",
        "terms": ["AI芯片", "算力芯片", "人工智能芯片", "AI加速", "处理器", "ArmV9"],
    },
    {
        "query_id": "pilot-007",
        "category": "industrial_software",
        "query": "深圳做工业软件和 MES 系统的公司",
        "terms": ["工业软件", "MES", "生产管理系统", "工业互联网", "工业仿真", "智能制造"],
    },
    {
        "query_id": "pilot-008",
        "category": "ai_bioscience",
        "query": "深圳做多组学 AI 和生物科研大模型的公司",
        "terms": ["多组学", "AI for BioScience", "生物科研平台", "生物大模型", "GeneLLM", "医学诊断"],
    },
    {
        "query_id": "pilot-009",
        "category": "low_altitude",
        "query": "深圳做低空飞行器和无人机控制的公司",
        "terms": ["低空经济", "飞行器", "无人机", "飞行控制", "空中交通", "eVTOL"],
    },
    {
        "query_id": "pilot-010",
        "category": "quantum",
        "query": "深圳做量子计算或量子通信的公司",
        "terms": ["量子计算", "量子通信", "量子测量", "量子安全", "量子密码", "量子科技"],
    },
]


@dataclass(frozen=True, slots=True)
class SummaryCandidate:
    profile_summary: str | None
    technology_route_summary: str | None
    blocker: str | None = None


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _open_conn(dsn: str):
    return psycopg.connect(dsn, row_factory=dict_row)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _is_truthy_text(value: Any) -> bool:
    return bool(_clean(value))


def _company_material_row_sql(where: str = "", limit_sql: str = "") -> str:
    return f"""
    SELECT c.company_id,
           c.canonical_name,
           c.registered_name,
           c.website,
           c.hq_city,
           c.profile_summary,
           c.technology_route_summary,
           c.last_refreshed_at,
           c.updated_at,
           latest_snapshot.import_batch_id,
           latest_snapshot.source_row_number,
           latest_snapshot.project_name,
           latest_snapshot.industry,
           latest_snapshot.sub_industry,
           latest_snapshot.business,
           latest_snapshot.description,
           latest_snapshot.region,
           latest_snapshot.website_xlsx,
           latest_snapshot.team_raw,
           latest_snapshot.latest_funding_round,
           latest_snapshot.latest_funding_time_raw,
           latest_snapshot.latest_funding_amount_raw,
           latest_snapshot.latest_investors_raw,
           latest_snapshot.reported_patent_count,
           COALESCE(products.products_json, '[]'::jsonb) AS products_json,
           COALESCE(scenarios.scenarios_json, '[]'::jsonb) AS scenarios_json,
           COALESCE(events.events_json, '[]'::jsonb) AS events_json,
           COALESCE(news.news_json, '[]'::jsonb) AS news_json
      FROM company c
      LEFT JOIN LATERAL (
          SELECT *
            FROM company_snapshot cs
           WHERE cs.company_id = c.company_id
           ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
           LIMIT 1
      ) latest_snapshot ON true
      LEFT JOIN LATERAL (
          SELECT jsonb_agg(jsonb_build_object(
              'product_id', cp.product_id,
              'name', cp.canonical_name,
              'description', cp.short_description,
              'category', cp.product_category,
              'quality_status', cp.quality_status,
              'confidence', cp.confidence,
              'source_url', cp.official_product_url
          ) ORDER BY cp.quality_status = 'ready' DESC, cp.confidence DESC NULLS LAST) AS products_json
            FROM company_product cp
           WHERE cp.company_id = c.company_id
             AND cp.quality_status != 'rejected'
      ) products ON true
      LEFT JOIN LATERAL (
          SELECT jsonb_agg(jsonb_build_object(
              'scenario_id', cas.scenario_id,
              'name', cas.scenario_name,
              'category', cas.scenario_category,
              'description', cas.description,
              'target_customer', cas.target_customer,
              'quality_status', cas.quality_status,
              'confidence', cas.confidence,
              'source_url', cas.source_url
          ) ORDER BY cas.quality_status = 'ready' DESC, cas.confidence DESC NULLS LAST) AS scenarios_json
            FROM company_application_scenario cas
           WHERE cas.company_id = c.company_id
             AND cas.quality_status != 'rejected'
      ) scenarios ON true
      LEFT JOIN LATERAL (
          SELECT jsonb_agg(jsonb_build_object(
              'event_id', cse.event_id,
              'event_type', cse.event_type,
              'event_date', cse.event_date,
              'summary', cse.event_summary,
              'status', cse.status
          ) ORDER BY cse.event_date DESC NULLS LAST, cse.created_at DESC NULLS LAST) AS events_json
            FROM company_signal_event cse
           WHERE cse.company_id = c.company_id
             AND cse.status != 'deprecated'
      ) events ON true
      LEFT JOIN LATERAL (
          SELECT jsonb_agg(jsonb_build_object(
              'source_url', n.source_url,
              'source_type', COALESCE(n.source_adapter, n.source_domain),
              'source_tier', n.source_domain_tier,
              'fetched_at', n.fetched_at,
              'snippet', n.summary_clean,
              'confidence', n.confidence
          ) ORDER BY n.fetched_at DESC NULLS LAST) AS news_json
            FROM (
                SELECT *
                  FROM company_news_item n
                 WHERE n.company_id = c.company_id
                   AND n.is_company_confirmed = true
                 ORDER BY n.fetched_at DESC NULLS LAST
                 LIMIT 10
            ) n
      ) news ON true
     WHERE c.identity_status = 'resolved'
     {where}
     ORDER BY c.company_id
     {limit_sql}
    """


def build_summary_candidate(row: dict[str, Any]) -> SummaryCandidate:
    name = _clean(row.get("canonical_name") or row.get("registered_name"))
    industry = _clean(row.get("industry"))
    sub_industry = _clean(row.get("sub_industry"))
    business = _clean(row.get("business"))
    description = _clean(row.get("description"))
    city = _clean(row.get("hq_city") or row.get("region"))
    products = row.get("products_json") or []
    scenarios = row.get("scenarios_json") or []
    if isinstance(products, str):
        products = json.loads(products)
    if isinstance(scenarios, str):
        scenarios = json.loads(scenarios)
    product_names = [
        _clean(item.get("name"))
        for item in products
        if isinstance(item, dict) and _clean(item.get("name"))
    ][:3]
    scenario_names = [
        _clean(item.get("name"))
        for item in scenarios
        if isinstance(item, dict) and _clean(item.get("name"))
    ][:4]
    if not name or not any((description, business, industry, sub_industry, product_names)):
        return SummaryCandidate(None, None, "insufficient_trusted_material")

    industry_label = " / ".join(part for part in (industry, sub_industry) if part)
    profile_parts = [f"{name}是一家位于{city or '深圳'}的企业"]
    if industry_label:
        profile_parts.append(f"，所属方向为{industry_label}")
    if business:
        profile_parts.append(f"，主要定位为{business}")
    if description:
        profile_parts.append(f"。{description}")
    if product_names:
        profile_parts.append(f" 目前可识别的产品或服务包括：{'、'.join(product_names)}。")
    if row.get("reported_patent_count") is not None:
        profile_parts.append(f" XLSX 基线记录显示其相关专利数量为{row['reported_patent_count']}。")
    profile_summary = "".join(profile_parts).strip()

    tech_parts: list[str] = []
    if business:
        tech_parts.append(f"{name}的技术路线围绕{business}展开")
    elif sub_industry:
        tech_parts.append(f"{name}的技术路线围绕{sub_industry}展开")
    else:
        tech_parts.append(f"{name}的技术路线围绕{industry or '主营业务'}展开")
    if description:
        tech_parts.append(f"，核心材料显示其重点能力包括{description[:160]}")
    if product_names:
        tech_parts.append(f"；产品侧重点包括{'、'.join(product_names)}")
    if scenario_names:
        tech_parts.append(f"；应用场景包括{'、'.join(scenario_names)}")
    tech_parts.append("。")
    technology_route_summary = "".join(tech_parts).strip()
    return SummaryCandidate(profile_summary, technology_route_summary)


def run_audit(conn: Any, *, sample_limit: int) -> dict[str, Any]:
    counts = conn.execute(
        """
        SELECT count(*)::int AS resolved_companies,
               count(*) FILTER (WHERE COALESCE(profile_summary, '') = '')::int
                    AS missing_profile_summary,
               count(*) FILTER (WHERE COALESCE(technology_route_summary, '') = '')::int
                    AS missing_technology_route_summary,
               count(*) FILTER (WHERE quality_status = 'ready')::int AS ready_companies,
               count(*) FILTER (WHERE quality_status = 'needs_review')::int
                    AS needs_review_companies
          FROM company
         WHERE identity_status = 'resolved'
        """
    ).fetchone()
    business_counts = conn.execute(
        """
        SELECT
            (SELECT count(*)::int FROM company_product WHERE quality_status != 'rejected')
                AS product_rows,
            (SELECT count(DISTINCT company_id)::int FROM company_product
              WHERE quality_status != 'rejected') AS companies_with_products,
            (SELECT count(*)::int FROM company_application_scenario
              WHERE quality_status != 'rejected') AS scenario_rows,
            (SELECT count(DISTINCT company_id)::int FROM company_application_scenario
              WHERE quality_status != 'rejected') AS companies_with_scenarios,
            (SELECT count(*)::int FROM company_signal_event
              WHERE status != 'deprecated') AS signal_rows,
            (SELECT count(DISTINCT company_id)::int FROM company_signal_event
              WHERE status != 'deprecated') AS companies_with_signals,
            (SELECT count(*)::int FROM company_news_item) AS news_rows,
            (SELECT count(DISTINCT company_id)::int FROM company_news_item) AS companies_with_news
        """
    ).fetchone()
    review_counts = conn.execute(
        """
        SELECT 'product' AS table_name, quality_status AS status, count(*)::int AS row_count
          FROM company_product GROUP BY quality_status
        UNION ALL
        SELECT 'scenario' AS table_name, quality_status AS status, count(*)::int AS row_count
          FROM company_application_scenario GROUP BY quality_status
        UNION ALL
        SELECT 'signal' AS table_name, status, count(*)::int AS row_count
          FROM company_signal_event GROUP BY status
        ORDER BY table_name, status
        """
    ).fetchall()
    evidence_counts = conn.execute(
        """
        SELECT
            (SELECT count(*)::int FROM company_product cp
              WHERE cp.quality_status != 'rejected'
                AND NOT EXISTS (
                    SELECT 1 FROM company_product_evidence e
                    WHERE e.product_id = cp.product_id
                )) AS products_without_evidence,
            (SELECT count(*)::int FROM company_application_scenario cas
              WHERE cas.quality_status != 'rejected'
                AND NOT EXISTS (
                    SELECT 1 FROM company_application_scenario_evidence e
                    WHERE e.scenario_id = cas.scenario_id
                )) AS scenarios_without_evidence,
            (SELECT count(*)::int FROM company_signal_event cse
              WHERE cse.status != 'deprecated'
                AND cse.primary_news_id IS NULL
                AND COALESCE(cse.event_subject_normalized->>'source_url', '') = ''
            ) AS signal_events_without_source
        """
    ).fetchone()
    missing_rows = conn.execute(
        _company_material_row_sql(
            where=(
                "AND (COALESCE(c.profile_summary, '') = '' "
                "OR COALESCE(c.technology_route_summary, '') = '')"
            ),
            limit_sql="LIMIT %s",
        ),
        (sample_limit,),
    ).fetchall()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary_counts": dict(counts or {}),
        "business_counts": dict(business_counts or {}),
        "review_counts": [dict(row) for row in review_counts],
        "evidence_counts": dict(evidence_counts or {}),
        "missing_summary_samples": [
            {
                "company_id": row["company_id"],
                "canonical_name": row["canonical_name"],
                "industry": row.get("industry"),
                "business": row.get("business"),
                "description": row.get("description"),
                "candidate": _summary_candidate_payload(build_summary_candidate(row)),
            }
            for row in missing_rows
        ],
    }


def _summary_candidate_payload(candidate: SummaryCandidate) -> dict[str, str | None]:
    return {
        "profile_summary": candidate.profile_summary,
        "technology_route_summary": candidate.technology_route_summary,
        "blocker": candidate.blocker,
    }


def repair_summaries(conn: Any, *, apply: bool, limit: int | None) -> dict[str, Any]:
    limit_sql = "LIMIT %s" if limit is not None else ""
    params: tuple[Any, ...] = (limit,) if limit is not None else ()
    rows = conn.execute(
        _company_material_row_sql(
            where=(
                "AND (COALESCE(c.profile_summary, '') = '' "
                "OR COALESCE(c.technology_route_summary, '') = '')"
            ),
            limit_sql=limit_sql,
        ),
        params,
    ).fetchall()
    repaired: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in rows:
        candidate = build_summary_candidate(row)
        if candidate.blocker or not candidate.profile_summary or not candidate.technology_route_summary:
            blocked.append(
                {
                    "company_id": row["company_id"],
                    "canonical_name": row["canonical_name"],
                    "blocker": candidate.blocker or "empty_candidate",
                }
            )
            continue
        repaired.append(
            {
                "company_id": row["company_id"],
                "canonical_name": row["canonical_name"],
                "profile_summary": candidate.profile_summary,
                "technology_route_summary": candidate.technology_route_summary,
            }
        )
        if apply:
            conn.execute(
                """
                UPDATE company
                   SET profile_summary = %(profile_summary)s,
                       technology_route_summary = %(technology_route_summary)s,
                       updated_at = now()
                 WHERE company_id = %(company_id)s
                """,
                {
                    "company_id": row["company_id"],
                    "profile_summary": candidate.profile_summary,
                    "technology_route_summary": candidate.technology_route_summary,
                },
            )
    if apply:
        conn.commit()
    post = conn.execute(
        """
        SELECT count(*) FILTER (WHERE COALESCE(profile_summary, '') = '')::int
                 AS missing_profile_summary,
               count(*) FILTER (WHERE COALESCE(technology_route_summary, '') = '')::int
                 AS missing_technology_route_summary
          FROM company
         WHERE identity_status = 'resolved'
        """
    ).fetchone()
    return {
        "apply": apply,
        "selected": len(rows),
        "repaired_count": len(repaired),
        "blocked_count": len(blocked),
        "repaired": repaired,
        "blocked": blocked,
        "post_counts": dict(post or {}),
    }


def _open_milvus_client(uri: str):
    if uri.strip() != ":memory:":
        os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        from pymilvus import MilvusClient

    return MilvusClient(uri=uri)


class _FallbackReranker:
    def rerank(self, _query: str, docs: list[str], *, top_n: int):
        @dataclass(frozen=True, slots=True)
        class Result:
            index: int
            score: float

        return [Result(index=index, score=float(len(docs) - index)) for index in range(min(top_n, len(docs)))]


def _build_retrieval_service(dsn: str, *, allow_fallback_reranker: bool) -> RetrievalService:
    milvus_uri = os.environ.get("CHAT_MILVUS_URI") or os.environ.get("MILVUS_URI") or "./milvus.db"
    milvus_client = _open_milvus_client(milvus_uri)
    embedding_client = EmbeddingClient(api_key=load_local_api_key())
    if allow_fallback_reranker:
        reranker: Any = _FallbackReranker()
    else:
        reranker = RerankerClient(api_key=load_local_api_key())

    def _pg_conn_factory():
        return _open_conn(dsn)

    return RetrievalService(
        pg_conn_factory=_pg_conn_factory,
        milvus_client=milvus_client,
        embedding_client=embedding_client,
        reranker=reranker,
        cache=None,
    )


def _load_company_context(conn: Any, company_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not company_ids:
        return {}
    rows = conn.execute(
        _company_material_row_sql(where="AND c.company_id = ANY(%s::text[])"),
        (company_ids,),
    ).fetchall()
    return {str(row["company_id"]): dict(row) for row in rows}


def export_top5(
    conn: Any,
    *,
    dsn: str,
    output_csv: Path,
    allow_fallback_reranker: bool,
) -> dict[str, Any]:
    service = _build_retrieval_service(dsn, allow_fallback_reranker=allow_fallback_reranker)
    records: list[dict[str, Any]] = []
    for query_item in COMPANY_TOP5_QUERIES:
        results = service.retrieve(
            query_item["query"],
            domains=("company",),
            candidate_limit=30,
            final_top_k=5,
        )
        company_ids = [item.object_id for item in results]
        context_by_id = _load_company_context(conn, company_ids)
        for rank, item in enumerate(results[:5], start=1):
            ctx = context_by_id.get(item.object_id, {})
            records.append(
                {
                    "query_id": query_item["query_id"],
                    "category": query_item["category"],
                    "query": query_item["query"],
                    "rank": rank,
                    "company_id": item.object_id,
                    "company_name": item.metadata.get("name") or ctx.get("canonical_name"),
                    "score": item.score,
                    "industry": ctx.get("industry"),
                    "profile_summary": _clean(ctx.get("profile_summary"))[:500],
                    "technology_route_summary": _clean(ctx.get("technology_route_summary"))[:500],
                    "products": _compact_names(ctx.get("products_json"), "name"),
                    "application_scenarios": _compact_names(ctx.get("scenarios_json"), "name"),
                    "evidence_hints": _compact_source_hints(ctx.get("news_json")),
                    "human_label": "",
                    "human_notes": "",
                }
            )
        if not results:
            records.append(
                {
                    "query_id": query_item["query_id"],
                    "category": query_item["category"],
                    "query": query_item["query"],
                    "rank": "",
                    "company_id": "",
                    "company_name": "",
                    "score": "",
                    "industry": "",
                    "profile_summary": "",
                    "technology_route_summary": "",
                    "products": "",
                    "application_scenarios": "",
                    "evidence_hints": "",
                    "human_label": "",
                    "human_notes": "no_results",
                }
            )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(output_csv, records)
    return {
        "query_count": len(COMPANY_TOP5_QUERIES),
        "row_count": len(records),
        "queries_with_results": len({row["query_id"] for row in records if row.get("company_id")}),
        "output_csv": str(output_csv),
        "allow_fallback_reranker": allow_fallback_reranker,
    }


def _compact_names(value: Any, key: str) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return ""
    if not isinstance(value, list):
        return ""
    names = [_clean(item.get(key)) for item in value if isinstance(item, dict) and _clean(item.get(key))]
    return " | ".join(names[:5])


def _compact_source_hints(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return ""
    if not isinstance(value, list):
        return ""
    hints: list[str] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        source = _clean(item.get("source_type") or item.get("source_tier"))
        url = _clean(item.get("source_url"))
        if source or url:
            hints.append(f"{source}:{url}" if url else source)
    return " | ".join(hints)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def score_top5(label_csv: Path) -> dict[str, Any]:
    rows = list(csv.DictReader(label_csv.open("r", encoding="utf-8")))
    by_query: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_query.setdefault(row["query_id"], []).append(row)
    query_count = len(by_query)
    hit_queries = 0
    top1_hits = 0
    judged_results = 0
    hit_results = 0
    partial_results = 0
    unlabeled_results = 0
    failed_queries: list[dict[str, Any]] = []
    for query_id, query_rows in by_query.items():
        labels = [str(row.get("human_label") or "").strip().lower() for row in query_rows]
        hit = "hit" in labels
        if hit:
            hit_queries += 1
        else:
            failed_queries.append(
                {
                    "query_id": query_id,
                    "query": query_rows[0].get("query"),
                    "labels": labels,
                }
            )
        top1 = next((row for row in query_rows if str(row.get("rank")) == "1"), None)
        if top1 and str(top1.get("human_label") or "").strip().lower() == "hit":
            top1_hits += 1
        for label in labels:
            if not label:
                unlabeled_results += 1
                continue
            if label == "hit":
                hit_results += 1
                judged_results += 1
            elif label == "partial":
                partial_results += 1
                judged_results += 1
            elif label == "miss":
                judged_results += 1
    return {
        "label_csv": str(label_csv),
        "query_count": query_count,
        "hit_queries": hit_queries,
        "top5_hit_rate": hit_queries / query_count if query_count else None,
        "top5_prd_pass": (hit_queries / query_count) >= 0.85 if query_count else False,
        "top1_hits": top1_hits,
        "top1_hit_rate": top1_hits / query_count if query_count else None,
        "judged_results": judged_results,
        "hit_results": hit_results,
        "precision_at_5": hit_results / judged_results if judged_results else None,
        "partial_results": partial_results,
        "unlabeled_results": unlabeled_results,
        "failed_queries": failed_queries,
    }


def export_candidate_pool(
    conn: Any,
    *,
    dsn: str,
    output_csv: Path,
    query_limit: int,
    retrieval_top_k: int,
    lexical_limit: int,
    pool_limit: int,
    allow_fallback_reranker: bool,
) -> dict[str, Any]:
    queries = COMPANY_CANDIDATE_POOL_QUERIES[:query_limit]
    all_rows = conn.execute(_company_material_row_sql()).fetchall()
    context_by_id = {str(row["company_id"]): dict(row) for row in all_rows}
    service = _build_retrieval_service(dsn, allow_fallback_reranker=allow_fallback_reranker)
    records: list[dict[str, Any]] = []
    for query_item in queries:
        query = str(query_item["query"])
        terms = [str(term) for term in query_item.get("terms", []) if str(term).strip()]
        semantic_results = service.retrieve(
            query,
            domains=("company",),
            candidate_limit=max(50, retrieval_top_k * 3),
            final_top_k=retrieval_top_k,
        )
        candidates: dict[str, dict[str, Any]] = {}
        for rank, item in enumerate(semantic_results, start=1):
            candidate = candidates.setdefault(
                item.object_id,
                {
                    "company_id": item.object_id,
                    "retrieval_rank": rank,
                    "retrieval_score": item.score,
                    "candidate_sources": set(),
                    "lexical_score": 0,
                    "matched_terms": [],
                },
            )
            candidate["retrieval_rank"] = min(rank, int(candidate["retrieval_rank"]))
            candidate["retrieval_score"] = max(float(item.score), float(candidate["retrieval_score"]))
            candidate["candidate_sources"].add("semantic")

        for item in _rank_lexical_candidates(list(context_by_id.values()), terms, limit=lexical_limit):
            company_id = item["company_id"]
            candidate = candidates.setdefault(
                company_id,
                {
                    "company_id": company_id,
                    "retrieval_rank": None,
                    "retrieval_score": None,
                    "candidate_sources": set(),
                    "lexical_score": 0,
                    "matched_terms": [],
                },
            )
            candidate["candidate_sources"].add("lexical")
            candidate["lexical_score"] = max(int(candidate["lexical_score"]), int(item["lexical_score"]))
            candidate["matched_terms"] = sorted(
                set(candidate["matched_terms"]) | set(item["matched_terms"])
            )

        ordered = sorted(
            candidates.values(),
            key=lambda item: (
                item["retrieval_rank"] is None,
                item["retrieval_rank"] or 9999,
                -int(item["lexical_score"]),
                str(item["company_id"]),
            ),
        )[:pool_limit]
        for candidate_rank, item in enumerate(ordered, start=1):
            ctx = context_by_id.get(str(item["company_id"]), {})
            retrieval_rank = item["retrieval_rank"]
            in_top5 = retrieval_rank is not None and int(retrieval_rank) <= 5
            records.append(
                {
                    "query_id": query_item["query_id"],
                    "category": query_item["category"],
                    "query": query,
                    "query_terms": " | ".join(terms),
                    "candidate_rank": candidate_rank,
                    "retrieval_rank": retrieval_rank or "",
                    "in_retrieval_top5": "yes" if in_top5 else "no",
                    "candidate_sources": " | ".join(sorted(item["candidate_sources"])),
                    "company_id": item["company_id"],
                    "company_name": ctx.get("canonical_name") or "",
                    "retrieval_score": item["retrieval_score"] if item["retrieval_score"] is not None else "",
                    "lexical_score": item["lexical_score"],
                    "matched_terms": " | ".join(item["matched_terms"]),
                    "industry": ctx.get("industry"),
                    "business": ctx.get("business"),
                    "profile_summary": _clean(ctx.get("profile_summary"))[:700],
                    "technology_route_summary": _clean(ctx.get("technology_route_summary"))[:700],
                    "products": _compact_names(ctx.get("products_json"), "name"),
                    "application_scenarios": _compact_names(ctx.get("scenarios_json"), "name"),
                    "evidence_hints": _compact_source_hints(ctx.get("news_json")),
                    "system_candidate_reason": _candidate_reason(item),
                    "suggested_relevance_label": "",
                    "human_relevance_label": "",
                    "query_answerability": "",
                    "human_notes": "",
                }
            )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(output_csv, records)
    return {
        "query_count": len(queries),
        "row_count": len(records),
        "queries_with_candidates": len({row["query_id"] for row in records}),
        "output_csv": str(output_csv),
        "retrieval_top_k": retrieval_top_k,
        "lexical_limit": lexical_limit,
        "pool_limit": pool_limit,
        "allow_fallback_reranker": allow_fallback_reranker,
    }


def _candidate_reason(item: dict[str, Any]) -> str:
    parts: list[str] = []
    if item.get("retrieval_rank") is not None:
        parts.append(f"semantic_rank={item['retrieval_rank']}")
    if item.get("lexical_score"):
        terms = ", ".join(item.get("matched_terms") or [])
        parts.append(f"lexical_score={item['lexical_score']} matched_terms={terms}")
    return "; ".join(parts)


def _rank_lexical_candidates(
    rows: list[dict[str, Any]],
    terms: list[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    normalized_terms = [_clean(term).lower() for term in terms if _clean(term)]
    for row in rows:
        text = _candidate_search_text(row).lower()
        matched = [term for term in normalized_terms if term and term in text]
        if not matched:
            continue
        ranked.append(
            {
                "company_id": str(row["company_id"]),
                "lexical_score": len(matched),
                "matched_terms": matched,
            }
        )
    ranked.sort(
        key=lambda item: (-int(item["lexical_score"]), str(item["company_id"]))
    )
    return ranked[:limit]


def _candidate_search_text(row: dict[str, Any]) -> str:
    parts = [
        row.get("canonical_name"),
        row.get("registered_name"),
        row.get("industry"),
        row.get("sub_industry"),
        row.get("business"),
        row.get("description"),
        row.get("profile_summary"),
        row.get("technology_route_summary"),
        _compact_names(row.get("products_json"), "name"),
        _compact_names(row.get("scenarios_json"), "name"),
        _compact_names(row.get("scenarios_json"), "description"),
        _compact_names(row.get("events_json"), "summary"),
    ]
    return " ".join(_clean(part) for part in parts if _clean(part))


def score_candidate_pool(label_csv: Path) -> dict[str, Any]:
    rows = list(csv.DictReader(label_csv.open("r", encoding="utf-8")))
    by_query: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_query.setdefault(row["query_id"], []).append(row)
    answerable_queries = 0
    corpus_gap_queries = 0
    uncertain_queries = 0
    unlabeled_queries = 0
    top5_hit_queries = 0
    top1_hit_queries = 0
    candidate_pool_hit_queries = 0
    retrieval_missed_answerable_queries: list[dict[str, Any]] = []
    judged_top5_results = 0
    hit_top5_results = 0
    partial_top5_results = 0
    for query_id, query_rows in by_query.items():
        answerability = _query_answerability(query_rows)
        if answerability == "answerable":
            answerable_queries += 1
        elif answerability == "corpus_gap":
            corpus_gap_queries += 1
            continue
        elif answerability == "uncertain":
            uncertain_queries += 1
            continue
        else:
            unlabeled_queries += 1
            continue

        top5_rows = [
            row
            for row in query_rows
            if str(row.get("in_retrieval_top5") or "").strip().lower() == "yes"
            or _rank_int(row.get("retrieval_rank")) in {1, 2, 3, 4, 5}
        ]
        top5_labels = [_relevance_label(row) for row in top5_rows]
        all_labels = [_relevance_label(row) for row in query_rows]
        top5_hit = "hit" in top5_labels
        pool_hit = "hit" in all_labels
        if top5_hit:
            top5_hit_queries += 1
        if pool_hit:
            candidate_pool_hit_queries += 1
        if pool_hit and not top5_hit:
            retrieval_missed_answerable_queries.append(
                {
                    "query_id": query_id,
                    "query": query_rows[0].get("query"),
                    "top5_labels": top5_labels,
                }
            )
        top1 = next((row for row in query_rows if _rank_int(row.get("retrieval_rank")) == 1), None)
        if top1 and _relevance_label(top1) == "hit":
            top1_hit_queries += 1
        for label in top5_labels:
            if label in {"hit", "partial", "miss"}:
                judged_top5_results += 1
            if label == "hit":
                hit_top5_results += 1
            elif label == "partial":
                partial_top5_results += 1
    coverage_denominator = answerable_queries + corpus_gap_queries
    return {
        "label_csv": str(label_csv),
        "query_count": len(by_query),
        "answerable_queries": answerable_queries,
        "corpus_gap_queries": corpus_gap_queries,
        "uncertain_queries": uncertain_queries,
        "unlabeled_queries": unlabeled_queries,
        "corpus_coverage_rate": (
            answerable_queries / coverage_denominator if coverage_denominator else None
        ),
        "top5_hit_queries_on_answerable": top5_hit_queries,
        "top5_hit_rate_on_answerable": (
            top5_hit_queries / answerable_queries if answerable_queries else None
        ),
        "top1_hit_queries_on_answerable": top1_hit_queries,
        "top1_hit_rate_on_answerable": (
            top1_hit_queries / answerable_queries if answerable_queries else None
        ),
        "candidate_pool_hit_queries": candidate_pool_hit_queries,
        "judged_top5_results": judged_top5_results,
        "hit_top5_results": hit_top5_results,
        "precision_at_5_on_answerable": (
            hit_top5_results / judged_top5_results if judged_top5_results else None
        ),
        "partial_top5_results": partial_top5_results,
        "retrieval_missed_answerable_queries": retrieval_missed_answerable_queries,
        "pilot_top5_pass_if_representative": (
            top5_hit_queries / answerable_queries
        ) >= 0.85 if answerable_queries else False,
    }


def _query_answerability(query_rows: list[dict[str, str]]) -> str:
    values = [
        str(row.get("query_answerability") or "").strip().lower()
        for row in query_rows
        if str(row.get("query_answerability") or "").strip()
    ]
    if values:
        return values[0]
    labels = {_relevance_label(row) for row in query_rows}
    if labels & {"hit", "partial", "miss"}:
        return "answerable" if "hit" in labels else "uncertain"
    return "unlabeled"


def _relevance_label(row: dict[str, str]) -> str:
    return str(
        row.get("human_relevance_label")
        or row.get("human_label")
        or row.get("suggested_relevance_label")
        or ""
    ).strip().lower()


def _rank_int(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def export_duplicate_pairs(conn: Any, *, output_csv: Path, limit: int) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT c.company_id,
               c.canonical_name,
               c.registered_name,
               c.unified_credit_code,
               c.website,
               c.hq_city,
               latest_snapshot.industry,
               latest_snapshot.legal_representative,
               latest_snapshot.registered_address,
               latest_snapshot.description
          FROM company c
          LEFT JOIN LATERAL (
              SELECT *
                FROM company_snapshot cs
               WHERE cs.company_id = c.company_id
               ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
               LIMIT 1
          ) latest_snapshot ON true
         WHERE c.identity_status = 'resolved'
         ORDER BY c.canonical_name
        """
    ).fetchall()
    candidates = _build_duplicate_candidates([dict(row) for row in rows], limit=limit)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(output_csv, candidates)
    return {"candidate_count": len(candidates), "output_csv": str(output_csv)}


def _build_duplicate_candidates(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    sorted_rows = sorted(rows, key=lambda row: _clean(row.get("canonical_name")))
    for idx, left in enumerate(sorted_rows):
        if len(pairs) >= limit:
            break
        for right in sorted_rows[idx + 1 : idx + 35]:
            score = _duplicate_similarity(left, right)
            if score < 0.62 and len(pairs) < max(10, limit // 5):
                continue
            prediction = "duplicate" if score >= 0.92 else "not_duplicate"
            pairs.append(_pair_row(left, right, score, prediction))
            if len(pairs) >= limit:
                break
    if len(pairs) < limit:
        step = max(1, len(sorted_rows) // max(1, limit - len(pairs)))
        for idx in range(0, len(sorted_rows) - step, step):
            if len(pairs) >= limit:
                break
            left = sorted_rows[idx]
            right = sorted_rows[idx + step]
            pairs.append(_pair_row(left, right, _duplicate_similarity(left, right), "not_duplicate"))
    return pairs[:limit]


def _duplicate_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_credit = _clean(left.get("unified_credit_code"))
    right_credit = _clean(right.get("unified_credit_code"))
    if left_credit and right_credit and left_credit == right_credit:
        return 1.0
    left_name = _clean(left.get("canonical_name") or left.get("registered_name"))
    right_name = _clean(right.get("canonical_name") or right.get("registered_name"))
    name_score = SequenceMatcher(None, left_name, right_name).ratio()
    left_site = _clean(left.get("website")).lower().rstrip("/")
    right_site = _clean(right.get("website")).lower().rstrip("/")
    site_bonus = 0.12 if left_site and right_site and left_site == right_site else 0.0
    industry_bonus = (
        0.04
        if _clean(left.get("industry")) and _clean(left.get("industry")) == _clean(right.get("industry"))
        else 0.0
    )
    return min(1.0, name_score + site_bonus + industry_bonus)


def _pair_row(
    left: dict[str, Any],
    right: dict[str, Any],
    score: float,
    prediction: str,
) -> dict[str, Any]:
    return {
        "left_company_id": left.get("company_id"),
        "left_name": left.get("canonical_name"),
        "left_registered_name": left.get("registered_name"),
        "left_credit_code": left.get("unified_credit_code"),
        "left_website": left.get("website"),
        "left_legal_representative": left.get("legal_representative"),
        "left_address": left.get("registered_address"),
        "left_industry": left.get("industry"),
        "left_description": _clean(left.get("description"))[:240],
        "right_company_id": right.get("company_id"),
        "right_name": right.get("canonical_name"),
        "right_registered_name": right.get("registered_name"),
        "right_credit_code": right.get("unified_credit_code"),
        "right_website": right.get("website"),
        "right_legal_representative": right.get("legal_representative"),
        "right_address": right.get("registered_address"),
        "right_industry": right.get("industry"),
        "right_description": _clean(right.get("description"))[:240],
        "system_similarity": f"{score:.4f}",
        "system_prediction": prediction,
        "human_label": "",
        "human_notes": "",
    }


def score_duplicate_pairs(label_csv: Path) -> dict[str, Any]:
    rows = list(csv.DictReader(label_csv.open("r", encoding="utf-8")))
    usable = [row for row in rows if str(row.get("human_label") or "").strip().lower() in {"duplicate", "not_duplicate"}]
    tp = fp = tn = fn = 0
    for row in usable:
        predicted = str(row.get("system_prediction") or "").strip().lower()
        actual = str(row.get("human_label") or "").strip().lower()
        if predicted == "duplicate" and actual == "duplicate":
            tp += 1
        elif predicted == "duplicate" and actual == "not_duplicate":
            fp += 1
        elif predicted == "not_duplicate" and actual == "not_duplicate":
            tn += 1
        elif predicted == "not_duplicate" and actual == "duplicate":
            fn += 1
    total = len(usable)
    accuracy = (tp + tn) / total if total else None
    return {
        "label_csv": str(label_csv),
        "total_rows": len(rows),
        "labeled_rows": total,
        "uncertain_or_unlabeled_rows": len(rows) - total,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "accuracy": accuracy,
        "dedup_prd_pass": accuracy >= 0.95 if accuracy is not None else False,
    }


def run_evidence_audit(conn: Any, *, sample_limit: int) -> dict[str, Any]:
    rows = conn.execute(
        """
        WITH product_sample AS (
            SELECT c.company_id,
                   c.canonical_name,
                   'product' AS fact_type,
                   cp.product_id AS fact_id,
                   cp.canonical_name AS fact_name,
                   cp.quality_status,
                   cp.official_product_url AS source_url,
                   EXISTS (
                       SELECT 1 FROM company_product_evidence e
                       WHERE e.product_id = cp.product_id
                   ) AS has_evidence
              FROM company c
              JOIN company_product cp ON cp.company_id = c.company_id
             WHERE c.identity_status = 'resolved'
               AND cp.quality_status != 'rejected'
             ORDER BY cp.last_refreshed_at DESC NULLS LAST
             LIMIT %(sample_limit)s
        ),
        scenario_sample AS (
            SELECT c.company_id,
                   c.canonical_name,
                   'scenario' AS fact_type,
                   cas.scenario_id AS fact_id,
                   cas.scenario_name AS fact_name,
                   cas.quality_status,
                   cas.source_url,
                   EXISTS (
                       SELECT 1 FROM company_application_scenario_evidence e
                       WHERE e.scenario_id = cas.scenario_id
                   ) AS has_evidence
              FROM company c
              JOIN company_application_scenario cas ON cas.company_id = c.company_id
             WHERE c.identity_status = 'resolved'
               AND cas.quality_status != 'rejected'
             ORDER BY cas.last_refreshed_at DESC NULLS LAST
             LIMIT %(sample_limit)s
        ),
        signal_sample AS (
            SELECT c.company_id,
                   c.canonical_name,
                   'signal' AS fact_type,
                   cse.event_id::text AS fact_id,
                   cse.event_summary AS fact_name,
                   cse.status AS quality_status,
                   COALESCE(
                       news.source_url,
                       cse.event_subject_normalized->>'source_url',
                       CASE
                           WHEN latest_snapshot.source_row_number IS NOT NULL
                           THEN 'xlsx://company/' || c.company_id || '/row/' || latest_snapshot.source_row_number::text
                       END
                   ) AS source_url,
                   (cse.primary_news_id IS NOT NULL
                    OR COALESCE(cse.event_subject_normalized->>'source_url', '') != ''
                    OR latest_snapshot.import_batch_id IS NOT NULL
                    OR latest_snapshot.source_row_number IS NOT NULL) AS has_evidence
              FROM company c
              JOIN company_signal_event cse ON cse.company_id = c.company_id
              LEFT JOIN company_news_item news ON news.news_id = cse.primary_news_id
              LEFT JOIN LATERAL (
                  SELECT cs.import_batch_id, cs.source_row_number
                    FROM company_snapshot cs
                   WHERE cs.company_id = c.company_id
                   ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
                   LIMIT 1
              ) latest_snapshot ON true
             WHERE c.identity_status = 'resolved'
               AND cse.status != 'deprecated'
             ORDER BY cse.event_date DESC NULLS LAST
             LIMIT %(sample_limit)s
        )
        SELECT * FROM product_sample
        UNION ALL SELECT * FROM scenario_sample
        UNION ALL SELECT * FROM signal_sample
        ORDER BY fact_type, company_id, fact_id
        """,
        {"sample_limit": sample_limit},
    ).fetchall()
    failures = [
        dict(row)
        for row in rows
        if not bool(row.get("has_evidence")) and not _clean(row.get("source_url"))
    ]
    return {
        "sample_limit_per_type": sample_limit,
        "sampled_rows": len(rows),
        "failure_count": len(failures),
        "failures": failures,
        "samples": [dict(row) for row in rows],
    }


def run_refresh_dry_run(conn: Any, *, explicit_ids: list[str], stale_days: int, limit: int | None) -> dict[str, Any]:
    reasons: list[str] = []
    params: dict[str, Any] = {"stale_days": stale_days}
    conditions: list[str] = ["c.identity_status = 'resolved'"]
    if explicit_ids:
        conditions.append("c.company_id = ANY(%(explicit_ids)s::text[])")
        params["explicit_ids"] = explicit_ids
        reasons.append("explicit_company_ids")
    else:
        conditions.append(
            """
            (
                COALESCE(c.profile_summary, '') = ''
                OR COALESCE(c.technology_route_summary, '') = ''
                OR c.last_refreshed_at IS NULL
                OR c.last_refreshed_at < now() - (%(stale_days)s::text || ' days')::interval
            )
            """
        )
        reasons.append("missing_or_stale_company_fields")
    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT %(limit)s"
        params["limit"] = limit
    rows = conn.execute(
        f"""
        SELECT c.company_id,
               c.canonical_name,
               c.last_refreshed_at,
               COALESCE(c.profile_summary, '') = '' AS missing_profile_summary,
               COALESCE(c.technology_route_summary, '') = '' AS missing_technology_route_summary
          FROM company c
         WHERE {' AND '.join(conditions)}
         ORDER BY c.last_refreshed_at NULLS FIRST, c.company_id
         {limit_sql}
        """,
        params,
    ).fetchall()
    return {
        "dry_run": True,
        "selection_reasons": reasons,
        "stale_days": stale_days,
        "selected_count": len(rows),
        "selected_company_ids": [row["company_id"] for row in rows],
        "sample": [dict(row) for row in rows[:20]],
        "enabled_stages": [
            "baseline_readiness",
            "xlsx_team_synthesis",
            "official_site_capture",
            "yiou_pitchhub_capture",
            "generic_source_judgment",
            "multi_source_synthesis",
            "touched_vector_refresh",
        ],
        "writes": {"business_fact_tables": 0, "vectors": 0},
    }


def source_fact_is_default_visible(
    *,
    quality_status: str,
    confidence: float | Decimal | None,
    source_tiers: list[str],
) -> bool:
    if quality_status == "ready":
        return True
    if quality_status != "needs_review":
        return False
    normalized_tiers = {tier.strip().lower() for tier in source_tiers if tier}
    if not normalized_tiers & HIGH_TRUST_SOURCE_TIERS:
        return False
    if confidence is None:
        return True
    return Decimal(str(confidence)) >= Decimal("0.60")


def run_review_policy_sample(conn: Any, *, sample_limit: int) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT cp.company_id,
               c.canonical_name AS company_name,
               'product' AS fact_type,
               cp.product_id AS fact_id,
               cp.canonical_name AS fact_name,
               cp.quality_status,
               cp.confidence,
               COALESCE(array_agg(DISTINCT e.source_tier)
                        FILTER (WHERE e.source_tier IS NOT NULL), ARRAY[]::text[]) AS source_tiers
          FROM company_product cp
          JOIN company c ON c.company_id = cp.company_id
          LEFT JOIN company_product_evidence e ON e.product_id = cp.product_id
         WHERE cp.quality_status != 'rejected'
         GROUP BY cp.company_id, c.canonical_name, cp.product_id
        UNION ALL
        SELECT cas.company_id,
               c.canonical_name AS company_name,
               'scenario' AS fact_type,
               cas.scenario_id AS fact_id,
               cas.scenario_name AS fact_name,
               cas.quality_status,
               cas.confidence,
               COALESCE(array_agg(DISTINCT e.source_tier)
                        FILTER (WHERE e.source_tier IS NOT NULL), ARRAY[]::text[]) AS source_tiers
          FROM company_application_scenario cas
          JOIN company c ON c.company_id = cas.company_id
          LEFT JOIN company_application_scenario_evidence e ON e.scenario_id = cas.scenario_id
         WHERE cas.quality_status != 'rejected'
         GROUP BY cas.company_id, c.canonical_name, cas.scenario_id
         ORDER BY quality_status, confidence DESC NULLS LAST
         LIMIT %(sample_limit)s
        """,
        {"sample_limit": sample_limit},
    ).fetchall()
    sample = []
    visible_count = 0
    for row in rows:
        visible = source_fact_is_default_visible(
            quality_status=str(row["quality_status"]),
            confidence=row.get("confidence"),
            source_tiers=list(row.get("source_tiers") or []),
        )
        visible_count += int(visible)
        item = dict(row)
        item["default_visible_by_policy"] = visible
        sample.append(item)
    return {
        "sampled_rows": len(sample),
        "default_visible_count": visible_count,
        "review_gated_count": len(sample) - visible_count,
        "sample": sample,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Company PRD acceptance closure utilities.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--output-dir", type=Path, default=RUN_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--sample-limit", type=int, default=20)

    repair_parser = sub.add_parser("repair-summaries")
    repair_parser.add_argument("--apply", action="store_true")
    repair_parser.add_argument("--confirm-real-db", action="store_true")
    repair_parser.add_argument("--limit", type=int, default=None)

    top5_parser = sub.add_parser("export-top5")
    top5_parser.add_argument("--output-csv", type=Path, default=None)
    top5_parser.add_argument("--allow-fallback-reranker", action="store_true")

    score_top5_parser = sub.add_parser("score-top5")
    score_top5_parser.add_argument("--label-csv", type=Path, required=True)

    pool_parser = sub.add_parser("export-candidate-pool")
    pool_parser.add_argument("--output-csv", type=Path, default=None)
    pool_parser.add_argument("--query-limit", type=int, default=10)
    pool_parser.add_argument("--retrieval-top-k", type=int, default=20)
    pool_parser.add_argument("--lexical-limit", type=int, default=30)
    pool_parser.add_argument("--pool-limit", type=int, default=25)
    pool_parser.add_argument("--allow-fallback-reranker", action="store_true")

    score_pool_parser = sub.add_parser("score-candidate-pool")
    score_pool_parser.add_argument("--label-csv", type=Path, required=True)

    dedup_parser = sub.add_parser("export-dedup-pairs")
    dedup_parser.add_argument("--output-csv", type=Path, default=None)
    dedup_parser.add_argument("--limit", type=int, default=120)

    score_dedup_parser = sub.add_parser("score-dedup-pairs")
    score_dedup_parser.add_argument("--label-csv", type=Path, required=True)

    evidence_parser = sub.add_parser("evidence-audit")
    evidence_parser.add_argument("--sample-limit", type=int, default=20)

    refresh_parser = sub.add_parser("refresh-dry-run")
    refresh_parser.add_argument("--company-id", action="append", default=[])
    refresh_parser.add_argument("--stale-days", type=int, default=30)
    refresh_parser.add_argument("--limit", type=int, default=100)

    policy_parser = sub.add_parser("review-policy-sample")
    policy_parser.add_argument("--sample-limit", type=int, default=100)

    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "repair-summaries" and args.apply:
        if "miroflow_real" in args.database_url and not args.confirm_real_db:
            print("ERROR: --confirm-real-db is required when applying to miroflow_real", file=sys.stderr)
            return 2

    with _open_conn(args.database_url) as conn:
        if args.command == "audit":
            payload = run_audit(conn, sample_limit=args.sample_limit)
            path = args.output_dir / "company_prd_audit.json"
        elif args.command == "repair-summaries":
            payload = repair_summaries(conn, apply=args.apply, limit=args.limit)
            path = args.output_dir / ("company_summary_repair_apply.json" if args.apply else "company_summary_repair_dry_run.json")
        elif args.command == "export-top5":
            csv_path = args.output_csv or args.output_dir / "company_top5_eval_unlabeled.csv"
            payload = export_top5(
                conn,
                dsn=args.database_url,
                output_csv=csv_path,
                allow_fallback_reranker=args.allow_fallback_reranker,
            )
            path = args.output_dir / "company_top5_eval_export.json"
        elif args.command == "score-top5":
            payload = score_top5(args.label_csv)
            path = args.output_dir / "company_top5_eval_score.json"
        elif args.command == "export-candidate-pool":
            csv_path = args.output_csv or args.output_dir / "company_candidate_pool_10_unlabeled.csv"
            payload = export_candidate_pool(
                conn,
                dsn=args.database_url,
                output_csv=csv_path,
                query_limit=args.query_limit,
                retrieval_top_k=args.retrieval_top_k,
                lexical_limit=args.lexical_limit,
                pool_limit=args.pool_limit,
                allow_fallback_reranker=args.allow_fallback_reranker,
            )
            path = args.output_dir / "company_candidate_pool_10_export.json"
        elif args.command == "score-candidate-pool":
            payload = score_candidate_pool(args.label_csv)
            path = args.output_dir / "company_candidate_pool_10_score.json"
        elif args.command == "export-dedup-pairs":
            csv_path = args.output_csv or args.output_dir / "company_dedup_pairs_unlabeled.csv"
            payload = export_duplicate_pairs(conn, output_csv=csv_path, limit=args.limit)
            path = args.output_dir / "company_dedup_pair_export.json"
        elif args.command == "score-dedup-pairs":
            payload = score_duplicate_pairs(args.label_csv)
            path = args.output_dir / "company_dedup_pair_score.json"
        elif args.command == "evidence-audit":
            payload = run_evidence_audit(conn, sample_limit=args.sample_limit)
            path = args.output_dir / "company_evidence_audit.json"
        elif args.command == "refresh-dry-run":
            payload = run_refresh_dry_run(
                conn,
                explicit_ids=args.company_id,
                stale_days=args.stale_days,
                limit=args.limit,
            )
            path = args.output_dir / "company_refresh_dry_run.json"
        elif args.command == "review-policy-sample":
            payload = run_review_policy_sample(conn, sample_limit=args.sample_limit)
            path = args.output_dir / "company_review_policy_sample.json"
        else:
            raise AssertionError(args.command)

    _write_json(path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
    print(f"\nReport saved to: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
