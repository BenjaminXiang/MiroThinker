# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Identity verification for web search results.

Determines whether a web page describes the same professor as our target,
using LLM-based verification with confidence scoring.
Precision-first: confidence >= 0.8 required, false negatives preferred.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from .translation_spec import LLM_EXTRA_BODY

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

# Minimum confidence to accept identity match
CONFIDENCE_THRESHOLD = 0.8


@dataclass(frozen=True)
class ProfessorContext:
    """Known anchor fields for identity verification."""

    name: str
    institution: str
    department: str | None = None
    email: str | None = None
    research_directions: list[str] | None = None


class _VerificationOutput(BaseModel):
    """Schema for LLM identity verification output."""

    is_same_person: bool
    confidence: float
    matching_signals: list[str] = []
    conflicting_signals: list[str] = []
    reasoning: str = ""


@dataclass(frozen=True)
class IdentityVerification:
    """Result of identity verification."""

    is_same_person: bool
    confidence: float
    matching_signals: list[str]
    conflicting_signals: list[str]
    reasoning: str
    error: str | None = None


def _build_verification_prompt(
    ctx: ProfessorContext,
    page_url: str,
    page_content: str,
) -> str:
    """Build LLM prompt for identity verification."""
    directions_text = "、".join(ctx.research_directions) if ctx.research_directions else "未知"

    schema = json.dumps(
        _VerificationOutput.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )

    return f"""## 任务目标
判断以下网页内容是否描述了同一位教授。

## 目标教授信息
姓名: {ctx.name}
学校: {ctx.institution}
院系: {ctx.department or "未知"}
邮箱: {ctx.email or "未知"}
研究方向: {directions_text}

## 待验证网页
URL: {page_url}
内容（截取）:
{page_content[:3000]}

## 判断指引
1. 重点匹配：姓名 + 学校/机构 + 研究方向
2. 同名同姓但不同学校/不同领域 → 不是同一人
3. 如果教授曾转校，需要有明确证据（如"曾任职于..."）
4. 如果页面内容模糊或信息不足，宁可判断为不是同一人（精确优先于召回）
5. confidence 范围 0.0-1.0，0.8 以上才算确认

## 输出格式
严格按以下 JSON Schema 输出:
{schema}"""


async def verify_identity(
    *,
    professor_context: ProfessorContext,
    page_url: str,
    page_content: str,
    llm_client: Any,
    llm_model: str,
) -> IdentityVerification:
    """Verify if a web page describes the same professor.

    Returns IdentityVerification with is_same_person=False if confidence < 0.8,
    regardless of LLM output.
    """
    # Short-circuit for empty content
    if not page_content or not page_content.strip():
        return IdentityVerification(
            is_same_person=False,
            confidence=0.0,
            matching_signals=[],
            conflicting_signals=["empty_content"],
            reasoning="Page content is empty.",
        )

    prompt = _build_verification_prompt(professor_context, page_url, page_content)

    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个身份验证助手。请严格按JSON格式输出。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
            extra_body=LLM_EXTRA_BODY,
        )
        text = response.choices[0].message.content
        output = _parse_verification_output(text)
    except (ValidationError, json.JSONDecodeError) as e:
        logger.warning("Identity verification JSON parse failed for %s: %s", page_url, e)
        return IdentityVerification(
            is_same_person=False,
            confidence=0.0,
            matching_signals=[],
            conflicting_signals=[],
            reasoning="",
            error=str(e),
        )
    except Exception as e:
        logger.warning("Identity verification failed for %s: %s", page_url, e)
        return IdentityVerification(
            is_same_person=False,
            confidence=0.0,
            matching_signals=[],
            conflicting_signals=[],
            reasoning="",
            error=str(e),
        )

    # Hard rule: confidence < 0.8 → force is_same_person=False
    is_same = output.is_same_person and output.confidence >= CONFIDENCE_THRESHOLD

    return IdentityVerification(
        is_same_person=is_same,
        confidence=output.confidence,
        matching_signals=output.matching_signals,
        conflicting_signals=output.conflicting_signals,
        reasoning=output.reasoning,
    )


def _parse_verification_output(text: str) -> _VerificationOutput:
    """Parse LLM response to _VerificationOutput."""
    match = _JSON_FENCE_RE.search(text)
    content = match.group(1).strip() if match else text.strip()

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        content = content[start : end + 1]

    return _VerificationOutput.model_validate_json(content)
