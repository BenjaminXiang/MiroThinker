from __future__ import annotations

from dataclasses import dataclass
import re

from src.data_agents.contracts import (
    CompanyKeyPerson,
    CompanyWorkExperience,
    EducationExperience,
)

from .models import CompanyImportRecord


_PERSON_SPLIT_RE = re.compile(r"[\n；;]+")


@dataclass(frozen=True, slots=True)
class CompanySummaries:
    profile_summary: str
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
        description = _extract_after(text, "，介绍：")
        key = (name, role)
        if key in seen:
            continue
        seen.add(key)
        people.append(
            CompanyKeyPerson(
                name=name,
                role=role,
                description=description,
                education_structured=_extract_education_hints(description),
                work_experience=_extract_work_hints(description),
            )
        )
    return people


def build_rule_based_summaries(record: CompanyImportRecord) -> CompanySummaries:
    company_name = record.name
    industry = normalize_text(record.industry) or "科技产业"
    business = normalize_text(record.business)
    description = normalize_text(record.description)
    sub_industry = normalize_text(record.sub_industry)

    profile_parts = [f"{company_name}是一家聚焦{industry}的企业。"]
    if sub_industry:
        profile_parts.append(f"细分方向覆盖{sub_industry}。")
    if business:
        profile_parts.append(f"当前业务定位为{business}。")
    if description:
        profile_parts.append(description)
    profile_summary = _join_and_trim(profile_parts, limit=220)

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


def _extract_after(text: str, marker: str) -> str | None:
    if marker not in text:
        return None
    return normalize_text(text.split(marker, 1)[1])


_SCHOOL_HINT_RE = re.compile(
    r"(?P<degree>博士|硕士|本科|学士|MBA|EMBA|PhD|Master|Bachelor)?"
    r"(?:毕业于|就读于|获|取得|来自)"
    r"(?P<school>[\u4e00-\u9fa5A-Za-z\s·.&-]{2,40}?(?:大学|学院|University|College|Institute))",
    re.IGNORECASE,
)
_WORK_HINT_RE = re.compile(
    r"(?:曾任|曾就职于|任职于|就职于)"
    r"(?P<body>[^，。；;]{2,50})",
)
_ROLE_SUFFIXES = (
    "算法负责人",
    "技术负责人",
    "产品负责人",
    "研发负责人",
    "负责人",
    "总监",
    "经理",
    "工程师",
    "科学家",
    "研究员",
    "合伙人",
    "CEO",
    "CTO",
    "CFO",
    "COO",
    "VP",
)


def _extract_education_hints(description: str | None) -> list[EducationExperience]:
    if not description:
        return []
    results: list[EducationExperience] = []
    seen: set[tuple[str, str | None]] = set()
    for match in _SCHOOL_HINT_RE.finditer(description):
        school = normalize_text(match.group("school"))
        if not school:
            continue
        degree = normalize_text(match.group("degree"))
        key = (school, degree)
        if key in seen:
            continue
        seen.add(key)
        results.append(EducationExperience(school=school, degree=degree))
    return results


def _extract_work_hints(description: str | None) -> list[CompanyWorkExperience]:
    if not description:
        return []
    results: list[CompanyWorkExperience] = []
    seen: set[str] = set()
    for match in _WORK_HINT_RE.finditer(description):
        body = normalize_text(match.group("body"))
        if not body:
            continue
        raw_description = f"曾任{body}"
        if raw_description in seen:
            continue
        seen.add(raw_description)
        organization, role = _split_work_body(body)
        results.append(
            CompanyWorkExperience(
                description=raw_description,
                organization=organization,
                role=role,
            )
        )
    return results


def _split_work_body(body: str) -> tuple[str | None, str | None]:
    for suffix in _ROLE_SUFFIXES:
        if body.endswith(suffix) and len(body) > len(suffix):
            return normalize_text(body[: -len(suffix)]), suffix
    return None, body


def _join_and_trim(parts: list[str], *, limit: int) -> str:
    text = "".join(part for part in parts if part)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip("，。；; ") + "。"
