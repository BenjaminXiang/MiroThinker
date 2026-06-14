"""Pure chat context helpers shared by Wave 11 handlers."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

TARGET_DOMAINS = {"professor", "paper", "company", "patent"}
TARGET_DOMAIN_LABELS = {
    "professor": "教授",
    "paper": "论文",
    "company": "企业",
    "patent": "专利",
}

_NARROWING_PREFIX_RE = re.compile(r"^(其中|这些|上述|上面|里面|那里面|在这些中)\s*")


def looks_like_narrowing_query(query: str) -> bool:
    return bool(_NARROWING_PREFIX_RE.search(query))


def normalize_narrowing_topic(query: str, fallback: str = "") -> str:
    topic = fallback.strip() or _NARROWING_PREFIX_RE.sub("", query).strip()
    topic = re.sub(r"^(做|研究|属于|来自)\s*", "", topic).strip()
    topic = re.sub(r"(的|有哪些|有谁|是谁)$", "", topic).strip()
    return topic or query.strip()


def domain_id_key(domain: str) -> str:
    return {
        "professor": "professor_id",
        "paper": "paper_id",
        "company": "company_id",
        "patent": "patent_id",
    }[domain]


def result_ids_by_domain(
    structured_payload: dict[str, Any],
    citations: list[Any],
) -> dict[str, list[str]]:
    ids_by_domain: dict[str, list[str]] = {}

    def add(domain: str, value: Any) -> None:
        if domain not in TARGET_DOMAINS or not value:
            return
        value_str = str(value)
        ids_by_domain.setdefault(domain, [])
        if value_str not in ids_by_domain[domain]:
            ids_by_domain[domain].append(value_str)

    for domain in TARGET_DOMAINS:
        add(domain, structured_payload.get(domain_id_key(domain)))

    list_keys = {
        "professor": ("matched_professors", "candidates", "professors"),
        "paper": ("papers",),
        "company": ("companies",),
        "patent": ("patents",),
    }
    for domain, keys in list_keys.items():
        id_key = domain_id_key(domain)
        for key in keys:
            for item in structured_payload.get(key) or []:
                add(domain, item.get(id_key) or item.get("id"))

    for item in structured_payload.get("retrieval_evidence") or []:
        domain = item.get("type")
        if domain in TARGET_DOMAINS:
            add(str(domain), item.get(domain_id_key(str(domain))) or item.get("id"))

    for citation in citations:
        add(getattr(citation, "type", ""), getattr(citation, "id", ""))

    return ids_by_domain


def answer_narrowed_results(
    domain: str, topic: str, rows: list[dict], total: int
) -> str:
    label = TARGET_DOMAIN_LABELS.get(domain, "结果")
    if not rows:
        return f"在上轮 {total} 个{label}结果中，未筛选到与 {topic!r} 相关的条目。"
    lines = [
        f"在上轮 {total} 个{label}结果中，筛选到 {len(rows)} 个与 {topic!r} 相关的条目：",
        "",
    ]
    for row in rows[:10]:
        title = (
            row.get("canonical_name")
            or row.get("title")
            or row.get("title_clean")
            or row.get("patent_number")
            or row.get("id")
        )
        snippet = row.get("institution") or row.get("snippet") or row.get("industry") or ""
        suffix = f" — {snippet[:60]}" if snippet else ""
        lines.append(f"  • {title}{suffix}")
    return "\n".join(lines)


def infer_a_target_domain(query: str, name: str, classification: dict[str, str]) -> str:
    target_domain = classification.get("target_domain")
    if target_domain in TARGET_DOMAINS:
        return target_domain
    if re.search(r"\b(CN|US|EP|WO)\w+", name, re.IGNORECASE) or "专利" in query:
        return "patent"
    if "论文" in query or "paper" in query.casefold() or "文章" in query:
        return "paper"
    if "公司" in query or "企业" in query:
        return "company"
    return "professor"


def lookup_company(conn: Any, *, name: str) -> list[dict]:
    like = f"%{name}%"
    return conn.execute(
        """
        SELECT c.company_id, c.canonical_name, latest.industry,
               latest.business, latest.description, c.website,
               COALESCE(products.products_json, '[]'::jsonb) AS products,
               COALESCE(scenarios.application_scenarios_json, '[]'::jsonb) AS application_scenarios,
               COALESCE(recent_events.recent_events_json, '[]'::jsonb) AS recent_events,
               count(*) OVER ()::int AS total_count
          FROM company c
          LEFT JOIN LATERAL (
            SELECT cs.industry, cs.business, cs.description
              FROM company_snapshot cs
             WHERE cs.company_id = c.company_id
             ORDER BY cs.snapshot_created_at DESC NULLS LAST
             LIMIT 1
          ) latest ON true
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'name', cp.canonical_name,
                    'description', cp.short_description,
                    'source_url', cp.official_product_url,
                    'quality_status', cp.quality_status,
                    'confidence', cp.confidence,
                    'product_category', cp.product_category,
                    'target_customers', cp.target_customers,
                    'application_scenarios', cp.application_scenarios,
                    'technical_tags', cp.technical_tags
                )
                ORDER BY cp.confidence DESC NULLS LAST, cp.last_refreshed_at DESC NULLS LAST
            ) AS products_json
             FROM company_product cp
             WHERE cp.company_id = c.company_id
               AND cp.quality_status = 'ready'
          ) products ON true
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'scenario_id', cas.scenario_id,
                    'scenario_name', cas.scenario_name,
                    'scenario_category', cas.scenario_category,
                    'description', cas.description,
                    'target_customer', cas.target_customer,
                    'source_url', cas.source_url,
                    'quality_status', cas.quality_status,
                    'confidence', cas.confidence
                )
                ORDER BY cas.confidence DESC NULLS LAST, cas.last_refreshed_at DESC NULLS LAST
            ) AS application_scenarios_json
              FROM company_application_scenario cas
             WHERE cas.company_id = c.company_id
               AND cas.quality_status = 'ready'
          ) scenarios ON true
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'event_type', cse.event_type,
                    'event_date', cse.event_date,
                    'summary', cse.event_summary,
                    'confidence', cse.confidence,
                    'source_url', news.source_url,
                    'normalized', cse.event_subject_normalized
                )
                ORDER BY cse.event_date DESC, cse.created_at DESC NULLS LAST
            ) AS recent_events_json
              FROM (
                SELECT *
                  FROM company_signal_event cse
                 WHERE cse.company_id = c.company_id
                   AND cse.status = 'active'
                 ORDER BY cse.event_date DESC, cse.created_at DESC NULLS LAST
                 LIMIT 5
              ) cse
              LEFT JOIN company_news_item news ON news.news_id = cse.primary_news_id
          ) recent_events ON true
         WHERE c.identity_status != 'inactive'
           AND (
                c.canonical_name = %s
                OR jsonb_exists(COALESCE(c.aliases, '[]'::jsonb), %s)
                OR c.canonical_name ILIKE %s
           )
         ORDER BY c.canonical_name
         LIMIT 10
        """,
        (name, name, like),
    ).fetchall()


_PAPER_TITLE_PARTIAL_LOOKUP_KEY_MIN_CHARS = 32
_PAPER_TITLE_PARTIAL_LOOKUP_DISABLED = "__mirothinker_no_partial_title_match__"


def lookup_paper(conn: Any, *, title: str) -> list[dict]:
    like = f"%{title}%"
    title_key = _paper_title_lookup_key(title)
    partial_title_key_like = (
        f"%{title_key}%"
        if len(title_key) >= _PAPER_TITLE_PARTIAL_LOOKUP_KEY_MIN_CHARS
        else _PAPER_TITLE_PARTIAL_LOOKUP_DISABLED
    )
    return conn.execute(
        """
        SELECT paper_id, title_clean, year, venue, authors_display,
               abstract_clean, summary_zh, citation_count,
               count(*) OVER ()::int AS total_count
          FROM paper
         WHERE COALESCE(identity_status, 'unverified') != 'rejected'
           AND COALESCE(quality_status, 'needs_enrichment') != 'rejected'
           AND (
                paper_id = %s
                OR title_clean ILIKE %s
                OR doi = %s
                OR regexp_replace(lower(title_clean), '[^[:alnum:]]', '', 'g') = %s
                OR regexp_replace(lower(title_clean), '[^[:alnum:]]', '', 'g') LIKE %s
           )
         ORDER BY citation_count DESC NULLS LAST, year DESC NULLS LAST
         LIMIT 10
        """,
        (title, like, title, title_key, partial_title_key_like),
    ).fetchall()


def _paper_title_lookup_key(value: str) -> str:
    return "".join(char.casefold() for char in value if char.isalnum())


def lookup_patent(conn: Any, *, query: str) -> list[dict]:
    like = f"%{query}%"
    return conn.execute(
        """
        SELECT patent_id, patent_number, title_clean, applicants_raw,
               filing_date, grant_date, patent_type, abstract_clean,
               count(*) OVER ()::int AS total_count
          FROM patent
         WHERE COALESCE(status, '') != 'inactive'
           AND (patent_id = %s OR patent_number = %s OR patent_number ILIKE %s
                OR title_clean ILIKE %s)
         ORDER BY filing_date DESC NULLS LAST
         LIMIT 10
        """,
        (query, query, like, like),
    ).fetchall()


def answer_company_profile(company: dict) -> str:
    name = company.get("canonical_name") or "该企业"
    parts = [f"{name} 是深圳科创企业。"]
    if company.get("industry"):
        parts.append(f"行业方向：{company['industry']}。")
    if company.get("business"):
        parts.append(f"业务摘要：{company['business']}。")
    elif company.get("description"):
        parts.append(f"简介：{company['description']}。")
    products = _json_list(company.get("products"))
    if products:
        product_texts: list[str] = []
        for item in products[:3]:
            if not isinstance(item, dict):
                continue
            product_name = str(item.get("name") or item.get("canonical_name") or "").strip()
            description = str(
                item.get("description") or item.get("short_description") or ""
            ).strip()
            structured_parts = []
            product_category = str(item.get("product_category") or "").strip()
            if product_category:
                structured_parts.append(f"类别：{product_category}")
            target_customers = _string_list(item.get("target_customers"))
            if target_customers:
                structured_parts.append(f"目标客户：{'、'.join(target_customers)}")
            application_scenarios = _string_list(item.get("application_scenarios"))
            if application_scenarios:
                structured_parts.append(f"场景：{'、'.join(application_scenarios)}")
            technical_tags = _string_list(item.get("technical_tags"))
            if technical_tags:
                structured_parts.append(f"技术标签：{'、'.join(technical_tags)}")
            structured_suffix = (
                f"（{'；'.join(structured_parts)}）" if structured_parts else ""
            )
            if product_name and description:
                product_texts.append(f"{product_name}：{description}{structured_suffix}")
            elif product_name:
                product_texts.append(f"{product_name}{structured_suffix}")
        if product_texts:
            parts.append("产品/服务：" + _end_sentence("；".join(product_texts)))
    scenarios = _json_list(company.get("application_scenarios"))
    if scenarios:
        scenario_texts: list[str] = []
        for item in scenarios[:3]:
            if not isinstance(item, dict):
                continue
            scenario_name = str(item.get("scenario_name") or "").strip()
            target_customer = str(item.get("target_customer") or "").strip()
            description = str(item.get("description") or "").strip()
            text = " ".join(
                part for part in (scenario_name, target_customer, description) if part
            )
            if text:
                scenario_texts.append(text)
        if scenario_texts:
            parts.append("应用场景：" + _end_sentence("；".join(scenario_texts)))
    recent_events = _json_list(company.get("recent_events"))
    if recent_events:
        event_texts: list[str] = []
        for item in recent_events[:3]:
            if not isinstance(item, dict):
                continue
            event_date = str(item.get("event_date") or "").strip()
            event_type = str(item.get("event_type") or "").strip()
            summary = str(item.get("summary") or item.get("event_summary") or "").strip()
            if not summary:
                continue
            normalized_text = _event_normalized_text(item.get("normalized"))
            if normalized_text:
                summary = f"{summary} {normalized_text}"
            prefix = " ".join(part for part in (event_date, event_type) if part)
            event_texts.append(f"{prefix} {summary}".strip())
        if event_texts:
            parts.append("最近动态：" + _end_sentence("；".join(event_texts)))
    return " ".join(parts)


def _end_sentence(text: str) -> str:
    return text if text.endswith(("。", ".", "！", "!", "？", "?")) else f"{text}。"


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _event_normalized_text(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    parts: list[str] = []
    for key in ("round", "amount", "amount_raw", "amount_cny_wan"):
        text = str(value.get(key) or "").strip()
        if text:
            parts.append(text)
    parts.extend(_string_list(value.get("investors")))
    return " ".join(parts)


def answer_paper_profile(paper: dict) -> str:
    title = paper.get("title_clean") or paper.get("title") or paper.get("paper_id")
    year = paper.get("year") or "年份未知"
    venue = paper.get("venue") or "来源未知"
    parts = [f"{title} 是一篇 {year} 年发表于 {venue} 的论文。"]
    if authors := _compact_text(paper.get("authors_display")):
        parts.append(f"作者：{authors}。")
    if summary := _compact_text(paper.get("summary_zh") or paper.get("abstract_clean")):
        parts.append(f"摘要：{summary}")
    return "".join(parts)


def _compact_text(value: Any, *, max_chars: int = 700) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def answer_patent_profile(patent: dict) -> str:
    number = patent.get("patent_number") or patent.get("patent_id")
    title = patent.get("title_clean") or patent.get("title") or "标题未知"
    applicant = patent.get("applicants_raw") or "申请人未知"
    return f"{number} 是专利《{title}》，申请人为 {applicant}。"
