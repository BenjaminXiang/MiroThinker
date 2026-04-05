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
from .models import EducationEntry, EnrichedProfessorProfile, WorkEntry

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

    return AgentOutputModel.model_validate_json(content)


def _merge_agent_output(
    profile: EnrichedProfessorProfile,
    output: AgentOutputModel,
) -> EnrichedProfessorProfile:
    """Merge agent output into profile, not overwriting existing non-empty fields."""
    updates: dict[str, Any] = {}

    if output.education_structured and not profile.education_structured:
        updates["education_structured"] = output.education_structured
    if output.work_experience and not profile.work_experience:
        updates["work_experience"] = output.work_experience
    if output.awards and not profile.awards:
        updates["awards"] = output.awards
    if output.academic_positions and not profile.academic_positions:
        updates["academic_positions"] = output.academic_positions
    if output.projects and not profile.projects:
        updates["projects"] = output.projects
    if output.company_roles and not profile.company_roles:
        updates["company_roles"] = output.company_roles
    if output.patent_ids and not profile.patent_ids:
        updates["patent_ids"] = output.patent_ids
    if output.department and not profile.department:
        updates["department"] = output.department
    if output.title and not profile.title:
        updates["title"] = output.title

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
