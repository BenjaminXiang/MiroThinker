# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Verify professor-company associations from web search results.

Uses LLM to confirm whether a professor is truly associated with a company,
then produces a CompanyLink for cross-domain writing.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from .cross_domain import CompanyLink
from .models import EnrichedProfessorProfile
from .translation_spec import LLM_EXTRA_BODY
from .web_search_enrichment import CompanyMention

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
CONFIDENCE_THRESHOLD = 0.8


class _VerificationOutput(BaseModel):
    """Schema for LLM company association verification."""

    is_associated: bool
    confidence: float
    role: str = ""
    reasoning: str = ""


@dataclass(frozen=True)
class CompanyLinkResult:
    """Result of verified company link."""

    company_link: CompanyLink
    verification_confidence: float


def _build_verification_prompt(
    professor: EnrichedProfessorProfile,
    mention: CompanyMention,
    evidence_text: str = "",
) -> str:
    """Build LLM prompt for company association verification."""
    schema = json.dumps(
        _VerificationOutput.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )

    evidence_section = ""
    if evidence_text:
        evidence_section = f"""
## 证据页面内容
{evidence_text[:2000]}
"""

    return f"""## 任务目标
判断以下教授是否与该企业存在关联。

## 教授信息
姓名: {professor.name}
学校: {professor.institution}
院系: {professor.department or "未知"}
研究方向: {"、".join(professor.research_directions[:3]) if professor.research_directions else "未知"}

## 企业信息
企业名称: {mention.company_name}
角色（线索）: {mention.role}
证据来源: {mention.evidence_url}
{evidence_section}
## 判断指引
1. 确认该教授是否真的与该企业存在关联（创始人、首席科学家、顾问、董事等）
2. 如果只是同名不同人，判断为不关联
3. confidence 范围 0.0-1.0，0.8 以上才算确认
4. 如果关联存在，明确角色
5. 重点参考证据页面内容进行判断

## 输出格式
{schema}"""


async def verify_company_link(
    *,
    professor: EnrichedProfessorProfile,
    company_mention: CompanyMention,
    llm_client: Any,
    llm_model: str,
    evidence_text: str = "",
) -> CompanyLinkResult | None:
    """Verify a company association and return CompanyLink if confirmed."""
    prompt = _build_verification_prompt(professor, company_mention, evidence_text)

    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": "你是一个企业关联验证助手。请严格按JSON格式输出。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
            extra_body=LLM_EXTRA_BODY,
        )
        text = response.choices[0].message.content

        match = _JSON_FENCE_RE.search(text)
        content = match.group(1).strip() if match else text.strip()
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            content = content[start : end + 1]

        output = _VerificationOutput.model_validate_json(content)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning("Company link verification failed for %s: %s", company_mention.company_name, e)
        return None

    if not output.is_associated or output.confidence < CONFIDENCE_THRESHOLD:
        return None

    link = CompanyLink(
        company_id=None,  # Backfilled by cross_domain_linker
        company_name=company_mention.company_name,
        role=output.role or company_mention.role,
        evidence_url=company_mention.evidence_url,
        source="web_search",
    )

    return CompanyLinkResult(
        company_link=link,
        verification_confidence=output.confidence,
    )
