"""Pure chat context helpers shared by Wave 11 handlers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
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


@dataclass(frozen=True)
class SetReferent:
    domain: str | None
    surface: str


@dataclass(frozen=True)
class ChipPredicate:
    kind: str
    domain: str
    param: dict[str, Any]


_SET_REFERENT_DOMAIN_WORDS = {
    "professor": ("教授", "老师", "学者"),
    "company": ("公司", "企业"),
    "paper": ("论文", "文章"),
    "patent": ("专利",),
}
_SET_REFERENT_PREFIXES = ("上面这些", "上述", "这些")
_BARE_SET_REFERENTS = ("上面这些", "他们", "这些", "上述")


def looks_like_narrowing_query(query: str) -> bool:
    return bool(_NARROWING_PREFIX_RE.search(query))


def detect_set_referent(query: str) -> SetReferent | None:
    text = query.strip()
    if not text:
        return None

    for prefix in _SET_REFERENT_PREFIXES:
        for domain, words in _SET_REFERENT_DOMAIN_WORDS.items():
            for word in words:
                surface = f"{prefix}{word}"
                if surface in text:
                    return SetReferent(domain=domain, surface=surface)

    # Bare referents anchor the query start; mid-sentence 他们/这些 is
    # intra-sentence coreference (…厂商，他们…), not a cross-turn set reference.
    for surface in _BARE_SET_REFERENTS:
        if text.startswith(surface):
            return SetReferent(domain=None, surface=surface)
    return None


def detect_set_operation(query: str, source_domain: str) -> tuple[str, str | None]:
    text = query.strip()
    if not text:
        return ("narrow", None)

    referenced_domains = {
        domain
        for domain, words in _SET_REFERENT_DOMAIN_WORDS.items()
        if domain != source_domain and any(word in text for word in words)
    }
    if len(referenced_domains) == 1:
        return ("traverse", next(iter(referenced_domains)))
    return ("narrow", None)


_INVALID_REGION_TOKENS = {
    "这些",
    "上述",
    "上面",
    "其中",
    "哪些",
    "那里",
    "这里",
}
_CN_SMALL_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _parse_small_year_count(value: str) -> int | None:
    value = value.strip()
    if value.isdigit():
        return int(value)
    if value in _CN_SMALL_NUMBERS:
        return _CN_SMALL_NUMBERS[value]
    if len(value) == 2 and value.startswith("十"):
        suffix = _CN_SMALL_NUMBERS.get(value[1])
        return 10 + suffix if suffix else None
    if len(value) == 2 and value.endswith("十"):
        prefix = _CN_SMALL_NUMBERS.get(value[0])
        return prefix * 10 if prefix else None
    return None


def _detect_region_city(text: str) -> str | None:
    if any(token in text for token in ("在深圳", "总部深圳", "总部在深圳", "深圳的")):
        return "深圳"
    patterns = (
        r"总部(?:在)?(?P<city>[\u4e00-\u9fff]{2,6})(?:市)?(?:的|$|[，,。？?\s])",
        r"(?:位于|在)(?P<city>[\u4e00-\u9fff]{2,6})(?:市)?(?:的|$|[，,。？?\s])",
    )
    for pattern in patterns:
        if match := re.search(pattern, text):
            city = match.group("city").strip()
            city = city.removesuffix("市")
            if city and city not in _INVALID_REGION_TOKENS and not city.endswith(("中", "里")):
                return city
    return None


def _detect_recency_param(text: str) -> dict[str, Any] | None:
    if match := re.search(r"(?P<year>20\d{2})\s*年", text):
        return {"mode": "year", "year": int(match.group("year"))}
    if "近一年" in text:
        return {"mode": "recent_years", "years": 1}
    if match := re.search(r"近\s*(?P<count>[0-9一二两三四五六七八九十]{1,3})\s*年", text):
        count = _parse_small_year_count(match.group("count"))
        if count is not None and count > 0:
            return {"mode": "recent_years", "years": count}
    return None


def detect_chip_predicate(query: str, domain: str) -> ChipPredicate | None:
    """Detect closed-table narrowing predicates that should not use retrieval."""
    if domain not in TARGET_DOMAINS:
        return None
    text = query.strip()
    if not text:
        return None

    if domain in {"professor", "company"}:
        city = _detect_region_city(text)
        if city:
            return ChipPredicate(kind="region", domain=domain, param={"city": city})

    if domain in {"paper", "patent"}:
        recency = _detect_recency_param(text)
        if recency:
            return ChipPredicate(kind="recency", domain=domain, param=recency)

    if domain == "patent" and "授权" in text:
        return ChipPredicate(
            kind="grant_status",
            domain=domain,
            param={"status": "granted"},
        )

    if domain == "patent" and re.search(r"申请人(是|为|类型)?.*(企业|公司)", text):
        return ChipPredicate(
            kind="applicant_type",
            domain=domain,
            param={"type": "企业"},
        )

    return None


def _row_label(domain: str, row: Mapping[str, Any]) -> str:
    if domain in {"professor", "company"}:
        label = row.get("canonical_name") or row.get("name") or row.get("title")
    elif domain == "paper":
        label = row.get("title") or row.get("title_clean")
    else:
        label = row.get("patent_number") or row.get("title") or row.get("title_clean")
    return str(label or row.get(domain_id_key(domain)) or row.get("id") or "未知")


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _extract_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return int(value.year)
    if isinstance(value, int):
        return value
    text = str(value)
    if match := re.search(r"(19|20)\d{2}", text):
        return int(match.group(0))
    return None


def _recency_cutoff_and_phrase(param: Mapping[str, Any]) -> tuple[int | None, str]:
    if param.get("mode") == "year":
        year = int(param.get("year") or 0)
        return (year or None), f"{year}年"
    if param.get("mode") == "recent_years":
        years = int(param.get("years") or 0)
        if years <= 0:
            return None, "近年"
        cutoff = date.today().year - years + 1
        return cutoff, f"近{years}年"
    return None, "近年"


def _evaluate_region_professor(
    row: Mapping[str, Any],
    *,
    city: str,
    label: str,
) -> tuple[bool | None, str]:
    institution = str(row.get("institution") or "").strip()
    if not institution:
        return None, f"{label} - 机构信息缺失 -> 信息缺失"
    if city in institution:
        return True, f"{label} - {institution} -> 在{city}"
    return False, f"{label} - {institution} -> 不在{city}"


def _evaluate_region_company(
    row: Mapping[str, Any],
    *,
    city: str,
    label: str,
) -> tuple[bool | None, str]:
    for field in ("hq_city", "region", "registered_address", "hq_district"):
        value = str(row.get(field) or "").strip()
        if not value:
            continue
        if city in value:
            return True, f"{label} - {field}={value} -> 在{city}"
        return False, f"{label} - {field}={value} -> 不在{city}"

    if city == "深圳" and row.get("is_shenzhen") is True:
        return True, f"{label} - is_shenzhen=True -> 在深圳"

    name_values = (
        str(row.get("canonical_name") or "").strip(),
        str(row.get("registered_name") or "").strip(),
    )
    if city == "深圳":
        for name in name_values:
            if name.startswith(("深圳市", "深圳")):
                return True, f"{label} - 名称前缀={name} -> 在深圳"

    return None, f"{label} - 地区信息缺失 -> 信息缺失"


def _evaluate_recency(
    domain: str,
    row: Mapping[str, Any],
    predicate: ChipPredicate,
    *,
    label: str,
) -> tuple[bool | None, str]:
    field = "year" if domain == "paper" else "filing_date"
    year = _extract_year(row.get(field))
    cutoff, phrase = _recency_cutoff_and_phrase(predicate.param)
    missing = "年份信息缺失" if domain == "paper" else "申请年份信息缺失"
    if year is None or cutoff is None:
        return None, f"{label} - {missing} -> 信息缺失"
    if year >= cutoff:
        return True, f"{label} - {field}={year} -> {phrase}"
    return False, f"{label} - {field}={year} -> 不满足{phrase}"


def _evaluate_patent_grant_status(
    row: Mapping[str, Any],
    *,
    label: str,
) -> tuple[bool | None, str]:
    grant_date = row.get("grant_date")
    if not _is_blank(grant_date):
        return True, f"{label} - grant_date={grant_date} -> 已授权"
    legal_status = str(row.get("legal_status") or "").strip().casefold()
    if legal_status and ("授权" in legal_status or "granted" in legal_status):
        return True, f"{label} - legal_status={row.get('legal_status')} -> 已授权"
    filing_date = row.get("filing_date")
    if not _is_blank(filing_date):
        return False, f"{label} - filing_date={filing_date} -> 未见授权日"
    return None, f"{label} - 授权/申请日期信息缺失 -> 信息缺失"


def _evaluate_patent_applicant_type(
    row: Mapping[str, Any],
    *,
    label: str,
) -> tuple[bool | None, str]:
    applicants = str(row.get("applicants_raw") or "").strip()
    if not applicants:
        return None, f"{label} - 申请人信息缺失 -> 信息缺失"
    if any(token in applicants for token in ("企业", "公司", "有限公司")):
        return True, f"{label} - applicants_raw={applicants} -> 企业申请人"
    return False, f"{label} - applicants_raw={applicants} -> 非企业申请人"


def evaluate_chip_predicate(
    domain: str,
    member_row: Mapping[str, Any],
    predicate: ChipPredicate,
) -> tuple[bool | None, str]:
    label = _row_label(domain, member_row)
    if predicate.domain != domain:
        return None, f"{label} - 谓词不适用于{TARGET_DOMAIN_LABELS.get(domain, domain)} -> 信息缺失"

    if predicate.kind == "region":
        city = str(predicate.param.get("city") or "深圳")
        if domain == "professor":
            return _evaluate_region_professor(member_row, city=city, label=label)
        if domain == "company":
            return _evaluate_region_company(member_row, city=city, label=label)
        return None, f"{label} - 地区谓词不适用于{TARGET_DOMAIN_LABELS.get(domain, domain)} -> 信息缺失"

    if predicate.kind == "recency" and domain in {"paper", "patent"}:
        return _evaluate_recency(domain, member_row, predicate, label=label)

    if predicate.kind == "grant_status" and domain == "patent":
        return _evaluate_patent_grant_status(member_row, label=label)

    if predicate.kind == "applicant_type" and domain == "patent":
        return _evaluate_patent_applicant_type(member_row, label=label)

    return None, f"{label} - 谓词不适用于{TARGET_DOMAIN_LABELS.get(domain, domain)} -> 信息缺失"


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


def _normalize_company_name(name: str) -> str:
    """Strip region prefix + legal suffix -> short matchable core.

    '深圳法本信息科技有限公司' -> '法本信息'; '深圳市普渡科技股份有限公司' -> '普渡'.
    """
    import re

    s = re.sub(r"^(深圳|北京|上海|广州|杭州|南京|武汉|成都|西安|苏州|东莞|深圳市|北京市|上海市)[市]?", "", name.strip())
    prev = None
    suffix_re = re.compile(r"(股份有限公司|有限公司|责任公司|科技|集团|控股|公司|技术|有限)$")
    while prev != s:
        prev = s
        s = suffix_re.sub("", s).strip()
    return s or name


def lookup_company(conn: Any, *, name: str) -> list[dict]:
    core = _normalize_company_name(name)
    like = f"%{core}%"
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
                OR c.registered_name = %s
                OR jsonb_exists(COALESCE(c.aliases, '[]'::jsonb), %s)
                OR c.canonical_name ILIKE %s
                OR c.registered_name ILIKE %s
                OR c.canonical_name ILIKE %s
           )
         ORDER BY c.canonical_name
         LIMIT 10
        """,
        (name, name, name, like, like, f"%{name}%"),
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
