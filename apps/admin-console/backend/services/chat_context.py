"""Pure chat context helpers shared by Wave 11 handlers."""

from __future__ import annotations

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
               count(*) OVER ()::int AS total_count
          FROM company c
          LEFT JOIN LATERAL (
            SELECT cs.industry, cs.business, cs.description
              FROM company_snapshot cs
             WHERE cs.company_id = c.company_id
             ORDER BY cs.snapshot_created_at DESC NULLS LAST
             LIMIT 1
          ) latest ON true
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


def lookup_paper(conn: Any, *, title: str) -> list[dict]:
    like = f"%{title}%"
    return conn.execute(
        """
        SELECT paper_id, title_clean, year, venue, abstract_clean, citation_count,
               count(*) OVER ()::int AS total_count
          FROM paper
         WHERE paper_id = %s OR title_clean ILIKE %s OR doi = %s
         ORDER BY citation_count DESC NULLS LAST, year DESC NULLS LAST
         LIMIT 10
        """,
        (title, like, title),
    ).fetchall()


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
    return " ".join(parts)


def answer_paper_profile(paper: dict) -> str:
    title = paper.get("title_clean") or paper.get("title") or paper.get("paper_id")
    year = paper.get("year") or "年份未知"
    venue = paper.get("venue") or "来源未知"
    return f"{title} 是一篇 {year} 年发表于 {venue} 的论文。"


def answer_patent_profile(patent: dict) -> str:
    number = patent.get("patent_number") or patent.get("patent_id")
    title = patent.get("title_clean") or patent.get("title") or "标题未知"
    applicant = patent.get("applicants_raw") or "申请人未知"
    return f"{number} 是专利《{title}》，申请人为 {applicant}。"
