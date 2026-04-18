# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.17 — sync identity gate for canonical_name ↔ canonical_name_en.

Precision-first: the LLM must explicitly accept the candidate English name
with confidence >= 0.8. Any parse fault or upstream LLM error defaults to
rejecting the candidate so the pipeline never expands polluted data.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .translation_spec import LLM_EXTRA_BODY

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.8
BATCH_SIZE = 20
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class NameIdentityCandidate:
    canonical_name: str
    candidate_name_en: str
    source_url: str | None = None


class _LLMDecision(BaseModel):
    is_same_person: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


@dataclass(frozen=True, slots=True)
class NameIdentityDecision:
    accepted: bool
    confidence: float
    reasoning: str
    error: str | None = None


_PROMPT_TEMPLATE = """你是一位中英姓名核对专家。我会给你一位中国教授的中文姓名和一个候选英文姓名，
判断该英文姓名是否是这位教授本人的英文形式（本人选用的英文名、标准汉语拼音、
粤语拼音 Jyutping、威妥玛拼音 Wade-Giles，都视为合法；姓名顺序可以是东方式或
西方式）。

接受标准（examples, two-shot）：
- (熊会元, Huiyuan Xiong) → is_same_person=true, confidence=0.95
  reason: 标准汉语拼音，"Xiong Huiyuan" 的西方姓后写法
- (夏树涛, Shu-Tao Xia) → is_same_person=true, confidence=0.92
  reason: 连字符拼音
- (谢霆锋, Nicholas Tse) → is_same_person=true, confidence=0.90
  reason: Tse = 谢的粤语拼音；Nicholas 为本人英文名

拒绝标准（examples, three-shot）：
- (张成萍, Thomas Hardy) → is_same_person=false, confidence=0.05
  reason: Thomas Hardy 与 张成萍 无音近、无语义关联，像是页面上另一个人的名字
- (廖庆敏, Senior Member) → is_same_person=false, confidence=0.02
  reason: "Senior Member" 不是人名，是 IEEE 会员级别
- (张春香, Laser Technol) → is_same_person=false, confidence=0.02
  reason: "Laser Technol" 是期刊名缩写，不是人名

输出 JSON（不要 markdown fence）：
{
  "is_same_person": boolean,
  "confidence": float 0-1,
  "reasoning": "<= 60 字的简短理由"
}

现在判断：
- 中文姓名: {canonical_name}
- 候选英文姓名: {candidate_name_en}
"""


def _build_prompt(candidate: NameIdentityCandidate) -> str:
    return (
        _PROMPT_TEMPLATE.replace("{canonical_name}", candidate.canonical_name)
        .replace("{candidate_name_en}", candidate.candidate_name_en)
    )


def _parse_decision(text: str) -> _LLMDecision:
    body = text.strip()
    match = _JSON_FENCE_RE.search(body)
    if match:
        body = match.group(1).strip()
    payload = json.loads(body)
    return _LLMDecision.model_validate(payload)


def verify_name_identity(
    candidate: NameIdentityCandidate,
    *,
    llm_client: Any,
    llm_model: str,
) -> NameIdentityDecision:
    prompt = _build_prompt(candidate)
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是姓名身份验证助手。只输出符合要求的 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=512,
            extra_body=LLM_EXTRA_BODY,
        )
        text = response.choices[0].message.content
        parsed = _parse_decision(text)
    except (ValidationError, TypeError, json.JSONDecodeError) as exc:
        logger.warning("name_identity_gate parse failure: %s", exc)
        return NameIdentityDecision(
            accepted=False,
            confidence=0.0,
            reasoning="LLM response did not parse; defaulting to reject.",
            error="parse",
        )
    except Exception as exc:  # pragma: no cover - network / LLM faults
        logger.warning("name_identity_gate LLM call failed: %s", exc)
        return NameIdentityDecision(
            accepted=False,
            confidence=0.0,
            reasoning="LLM call failed; defaulting to reject.",
            error="llm_exception",
        )

    accepted = parsed.is_same_person and parsed.confidence >= CONFIDENCE_THRESHOLD
    return NameIdentityDecision(
        accepted=accepted,
        confidence=parsed.confidence,
        reasoning=parsed.reasoning,
    )


def batch_verify_name_identity(
    candidates: list[NameIdentityCandidate],
    *,
    llm_client: Any,
    llm_model: str,
    batch_size: int = BATCH_SIZE,
) -> list[NameIdentityDecision]:
    if not candidates:
        return []

    results: list[NameIdentityDecision] = []
    for start in range(0, len(candidates), batch_size):
        chunk = candidates[start : start + batch_size]
        for candidate in chunk:
            results.append(
                verify_name_identity(
                    candidate,
                    llm_client=llm_client,
                    llm_model=llm_model,
                )
            )
    return results
