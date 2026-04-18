# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Stage 2c — Per-professor agent enrichment for remaining fields.

Uses a single LLM call with structured output to fill education,
work experience, company roles, patents, and other fields not covered
by regex pre-extract or paper collection.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from .cross_domain import CompanyLink, PatentLink
from .homepage_crawler import _sanitize_title
from .models import EducationEntry, EnrichedProfessorProfile, WorkEntry
from .translation_spec import LLM_EXTRA_BODY, TRANSLATION_GUIDELINES

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True)
class AgentEnrichmentResult:
    profile: EnrichedProfessorProfile
    enrichment_source: str  # "agent_local" | "agent_online"
    llm_calls: int
    tool_calls: int


class AgentOutputModel(BaseModel):
    """Schema for agent structured output — only gap fields."""

    education_structured: list[EducationEntry] = []
    work_experience: list[WorkEntry] = []
    awards: list[str] = []
    academic_positions: list[str] = []
    projects: list[str] = []
    company_roles: list[CompanyLink] = []
    patent_ids: list[PatentLink] = []
    department: str | None = None
    title: str | None = None


def build_agent_prompt(
    profile: EnrichedProfessorProfile,
    missing_fields: list[str],
    html_text: str,
) -> str:
    """Build structured prompt for agent enrichment."""
    directions_text = "、".join(profile.research_directions) if profile.research_directions else "暂无"
    papers_text = "\n".join(
        f"  - {p.title} ({p.year}, {p.venue}, 引用{p.citation_count})"
        for p in profile.top_papers[:5]
    ) or "暂无"

    gap_list = "\n".join(f"- {field}" for field in missing_fields)

    schema = json.dumps(
        AgentOutputModel.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )

    truncated_html = html_text[:4000] if html_text else "（无官网页面内容）"

    return f"""## 任务目标
你是一个教授信息采集助手。以下教授的身份信息和学术画像已通过官网和论文采集获得，
请补全剩余缺失字段。

## 已有信息
姓名: {profile.name}
学校: {profile.institution}
院系: {profile.department or "未知"}
职称: {profile.title or "未知"}
研究方向: {directions_text}
h-index: {profile.h_index or "未知"} | 总引用: {profile.citation_count or "未知"}
代表论文:
{papers_text}
官网页面 URL: {profile.profile_url}

## 待补全字段
{gap_list}

## 官网页面原文
{truncated_html}

## 工作指引
1. 首先从官网页面原文中提取教育经历、工作经历、奖项等信息
2. 不能编造信息。没有证据的字段留空（空数组或null）
3. 教育经历请包含学校、学位、专业、起止年份
4. 工作经历请包含机构、职位、起止年份
5. 企业关联请包含企业名称和角色

{TRANSLATION_GUIDELINES}

## 输出格式
严格按以下 JSON Schema 输出，不要包含任何其他文字:
{schema}"""


def _parse_agent_output(text: str) -> AgentOutputModel:
    """Parse LLM response to AgentOutputModel."""
    match = _JSON_FENCE_RE.search(text)
    content = match.group(1).strip() if match else text.strip()

    # Find JSON object
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        content = content[start : end + 1]

    data = json.loads(content)
    data["education_structured"] = _filter_education_entries(
        data.get("education_structured", [])
    )
    data["work_experience"] = _filter_work_entries(
        data.get("work_experience", [])
    )
    data["company_roles"] = _filter_company_roles(
        data.get("company_roles", [])
    )
    return AgentOutputModel.model_validate(data)


def _filter_education_entries(entries: object) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    filtered: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        school = item.get("school") or item.get("institution")
        if not school:
            continue
        normalized = dict(item)
        normalized["school"] = school
        filtered.append(normalized)
    return filtered


def _filter_work_entries(entries: object) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    filtered: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        organization = item.get("organization") or item.get("institution")
        if not organization:
            continue
        normalized = dict(item)
        normalized["organization"] = organization
        filtered.append(normalized)
    return filtered


def _filter_company_roles(entries: object) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    filtered: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        company_name = item.get("company_name") or item.get("name")
        role = item.get("role")
        source = item.get("source")
        if not isinstance(company_name, str) or not company_name.strip():
            continue
        if not isinstance(role, str) or not role.strip():
            continue
        if not isinstance(source, str) or not source.strip():
            continue
        normalized = dict(item)
        normalized["company_name"] = company_name.strip()
        normalized["role"] = role.strip()
        normalized["source"] = source.strip()
        filtered.append(normalized)
    return filtered


def _merge_string_list(existing: list[str], new: list[str]) -> list[str] | None:
    """Merge two string lists, deduplicating by lowercase value. Returns None if no change."""
    if not new:
        return None
    seen = {s.lower() for s in existing}
    merged = list(existing)
    for s in new:
        if s.lower() not in seen:
            seen.add(s.lower())
            merged.append(s)
    return merged if len(merged) > len(existing) else None


def _merge_agent_output(
    profile: EnrichedProfessorProfile,
    output: AgentOutputModel,
) -> EnrichedProfessorProfile:
    """Merge agent output into profile, additively merging list fields."""
    updates: dict[str, Any] = {}

    if output.education_structured:
        if not profile.education_structured:
            updates["education_structured"] = output.education_structured
        else:
            # Dedupe by (institution, degree) key
            existing_keys = {
                (
                    e.school.lower() if getattr(e, "school", None) else "",
                    e.degree.lower() if getattr(e, "degree", None) else "",
                )
                for e in profile.education_structured
            }
            merged = list(profile.education_structured)
            for e in output.education_structured:
                key = (
                    e.school.lower() if getattr(e, "school", None) else "",
                    e.degree.lower() if getattr(e, "degree", None) else "",
                )
                if key not in existing_keys:
                    existing_keys.add(key)
                    merged.append(e)
            if len(merged) > len(profile.education_structured):
                updates["education_structured"] = merged

    if output.work_experience:
        if not profile.work_experience:
            updates["work_experience"] = output.work_experience
        else:
            existing_keys = {
                (
                    w.organization.lower() if getattr(w, "organization", None) else "",
                    w.role.lower() if getattr(w, "role", None) else "",
                )
                for w in profile.work_experience
            }
            merged = list(profile.work_experience)
            for w in output.work_experience:
                key = (
                    w.organization.lower() if getattr(w, "organization", None) else "",
                    w.role.lower() if getattr(w, "role", None) else "",
                )
                if key not in existing_keys:
                    existing_keys.add(key)
                    merged.append(w)
            if len(merged) > len(profile.work_experience):
                updates["work_experience"] = merged

    awards_merged = _merge_string_list(profile.awards, output.awards)
    if awards_merged is not None:
        updates["awards"] = awards_merged

    positions_merged = _merge_string_list(profile.academic_positions, output.academic_positions)
    if positions_merged is not None:
        updates["academic_positions"] = positions_merged

    projects_merged = _merge_string_list(profile.projects, output.projects)
    if projects_merged is not None:
        updates["projects"] = projects_merged

    if output.company_roles and not profile.company_roles:
        updates["company_roles"] = output.company_roles
    if output.patent_ids and not profile.patent_ids:
        updates["patent_ids"] = output.patent_ids
    if output.department and not profile.department:
        updates["department"] = output.department
    if output.title and not profile.title:
        sanitized_title = _sanitize_title(output.title)
        if sanitized_title:
            updates["title"] = sanitized_title

    if updates:
        return profile.model_copy(update=updates)
    return profile


async def run_agent_enrichment(
    *,
    profile: EnrichedProfessorProfile,
    missing_fields: list[str],
    html_text: str,
    local_llm_client: Any,
    local_llm_model: str,
    online_llm_client: Any | None = None,
    online_llm_model: str = "qwen3.6-plus",
    web_search: Any | None = None,
    fetch_html: Any | None = None,
    timeout: float = 300.0,
) -> AgentEnrichmentResult:
    """Run agent enrichment with LLM tiering."""
    prompt = build_agent_prompt(profile, missing_fields, html_text)
    llm_calls = 0

    # Tier 1: Local LLM
    try:
        response = local_llm_client.chat.completions.create(
            model=local_llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个教授信息采集助手。请严格按JSON格式输出。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
            extra_body=LLM_EXTRA_BODY,
        )
        llm_calls += 1
        text = response.choices[0].message.content
        output = _parse_agent_output(text)
        enriched = _merge_agent_output(profile, output)
        return AgentEnrichmentResult(
            profile=enriched.model_copy(update={"enrichment_source": "agent_local"}),
            enrichment_source="agent_local",
            llm_calls=llm_calls,
            tool_calls=0,
        )
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("Local LLM agent enrichment failed: %s", e)

    # Tier 2: Online LLM (DashScope)
    if online_llm_client:
        try:
            response = online_llm_client.chat.completions.create(
                model=online_llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个教授信息采集助手。请严格按JSON格式输出。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            llm_calls += 1
            text = response.choices[0].message.content
            output = _parse_agent_output(text)
            enriched = _merge_agent_output(profile, output)
            return AgentEnrichmentResult(
                profile=enriched.model_copy(update={"enrichment_source": "agent_online"}),
                enrichment_source="agent_online",
                llm_calls=llm_calls,
                tool_calls=0,
            )
        except (ValidationError, json.JSONDecodeError, Exception) as e:
            logger.warning("Online LLM agent enrichment failed: %s", e)

    # Both tiers failed — return original profile
    return AgentEnrichmentResult(
        profile=profile,
        enrichment_source="agent_failed",
        llm_calls=llm_calls,
        tool_calls=0,
    )
