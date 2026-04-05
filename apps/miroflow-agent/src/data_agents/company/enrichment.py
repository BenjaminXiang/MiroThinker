from __future__ import annotations

from dataclasses import dataclass
import re

from src.data_agents.contracts import CompanyKeyPerson

from .models import CompanyImportRecord


_PERSON_SPLIT_RE = re.compile(r"[\n；;]+")


@dataclass(frozen=True, slots=True)
class CompanySummaries:
    profile_summary: str
    evaluation_summary: str
    technology_route_summary: str


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.replace("\u3000", " ").split()).strip()
    return normalized or None


def extract_key_personnel(record: CompanyImportRecord) -> list[CompanyKeyPerson]:
    team_raw = record.team_raw
    if not team_raw:
        return []

    people: list[CompanyKeyPerson] = []
    seen: set[tuple[str, str]] = set()
    for chunk in _PERSON_SPLIT_RE.split(team_raw):
        text = normalize_text(chunk)
        if not text:
            continue
        name = _extract_segment(text, "，职务：")
        role = _extract_between(text, "职务：", "，介绍：")
        if not name or not role:
            continue
        key = (name, role)
        if key in seen:
            continue
        seen.add(key)
        people.append(CompanyKeyPerson(name=name, role=role))
    return people


def build_rule_based_summaries(record: CompanyImportRecord) -> CompanySummaries:
    company_name = record.name
    industry = normalize_text(record.industry) or "科技产业"
    business = normalize_text(record.business)
    description = normalize_text(record.description)
    sub_industry = normalize_text(record.sub_industry)
    investor_text = "、".join(record.investors[:3]) if record.investors else None

    profile_parts = [f"{company_name}是一家聚焦{industry}的企业。"]
    if sub_industry:
        profile_parts.append(f"细分方向覆盖{sub_industry}。")
    if business:
        profile_parts.append(f"当前业务定位为{business}。")
    if description:
        profile_parts.append(description)
    profile_summary = _join_and_trim(profile_parts, limit=220)

    evaluation_parts = [f"{company_name}当前已形成基础企业画像。"]
    if record.patent_count is not None:
        evaluation_parts.append(f"公开专利数量记录为{record.patent_count}件。")
    if record.financing_events:
        evaluation_parts.append(
            f"已记录{len(record.financing_events)}次融资事件。"
        )
    if investor_text:
        evaluation_parts.append(f"主要投资方包括{investor_text}。")
    evaluation_parts.append("现阶段评价以导出数据中的客观字段为主，不做主观排序。")
    evaluation_summary = _join_and_trim(evaluation_parts, limit=150)

    technology_parts = [f"{company_name}的技术路线围绕{industry}展开。"]
    if sub_industry:
        technology_parts.append(f"当前重点落在{sub_industry}。")
    if business:
        technology_parts.append(f"业务场景集中在{business}。")
    if description:
        technology_parts.append(description)
    technology_route_summary = _join_and_trim(technology_parts, limit=180)

    return CompanySummaries(
        profile_summary=profile_summary,
        evaluation_summary=evaluation_summary,
        technology_route_summary=technology_route_summary,
    )


def _extract_segment(text: str, marker: str) -> str | None:
    if marker not in text:
        return None
    return normalize_text(text.split(marker, 1)[0])


def _extract_between(text: str, start_marker: str, end_marker: str) -> str | None:
    if start_marker not in text:
        return None
    remainder = text.split(start_marker, 1)[1]
    if end_marker in remainder:
        remainder = remainder.split(end_marker, 1)[0]
    return normalize_text(remainder)


def _join_and_trim(parts: list[str], *, limit: int) -> str:
    text = "".join(part for part in parts if part)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip("，。；; ") + "。"
