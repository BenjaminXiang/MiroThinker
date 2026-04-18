# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.10' — LLM-first author-id picker.

Replaces (or augments) the rule-based ``_select_exact_name_author`` logic
in ``paper.openalex``. Given a target professor and several OpenAlex
author candidates that share the name, the picker asks Gemma to decide
which candidate (if any) is the real target, using display names,
last-known institutions, topic tags, and high-level publication stats.

Precision-first: when the LLM is uncertain (confidence < 0.75), we
return ``None`` rather than a wrong ``author_id`` — same policy as
``identity_verifier``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from src.data_agents.professor.translation_spec import LLM_EXTRA_BODY

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class AuthorCandidate:
    """One candidate author record to show the picker.

    The shape is intentionally source-agnostic so the same prompt can be
    reused for OpenAlex, Semantic Scholar and Google Scholar candidates.
    """

    index: int
    author_id: str
    display_name: str
    display_name_alternatives: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    works_count: int | None = None
    cited_by_count: int | None = None
    h_index: int | None = None
    source: str = "openalex"


@dataclass(frozen=True)
class PickerDecision:
    """Outcome of the picker call."""

    accepted_author_id: str | None
    confidence: float
    reasoning: str
    considered_author_ids: list[str]
    error: str | None = None


class _LLMPickerOutput(BaseModel):
    chosen_index: int | None = Field(default=None)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


def _render_candidate(cand: AuthorCandidate) -> str:
    alt = (
        ", ".join(cand.display_name_alternatives[:5])
        if cand.display_name_alternatives
        else "—"
    )
    insts = ", ".join(cand.institutions[:3]) if cand.institutions else "未知"
    topics = ", ".join(cand.topics[:6]) if cand.topics else "—"
    stats_bits: list[str] = []
    if cand.works_count is not None:
        stats_bits.append(f"works={cand.works_count}")
    if cand.cited_by_count is not None:
        stats_bits.append(f"cites={cand.cited_by_count}")
    if cand.h_index is not None:
        stats_bits.append(f"h_index={cand.h_index}")
    stats = " · ".join(stats_bits) or "—"
    return (
        f"[{cand.index}] {cand.display_name}  ({cand.source})\n"
        f"      alt names : {alt}\n"
        f"      institutions: {insts}\n"
        f"      topics    : {topics}\n"
        f"      stats     : {stats}\n"
        f"      author_id : {cand.author_id}"
    )


def _build_prompt(
    *,
    target_name: str,
    target_institution: str,
    target_directions: list[str] | None,
    candidates: list[AuthorCandidate],
) -> str:
    directions_text = (
        "、".join(target_directions) if target_directions else "未知"
    )
    return (
        "## 任务\n"
        "给定一位目标教授，以及若干候选学术档案（同名学者）。判断哪一个档案是目标教授本人。\n\n"
        "## 目标教授\n"
        f"姓名: {target_name}\n"
        f"学校: {target_institution}\n"
        f"研究方向: {directions_text}\n\n"
        "## 候选档案（按编号）\n"
        f"{chr(10).join(_render_candidate(c) for c in candidates)}\n\n"
        "## 判断指引\n"
        "1. 机构匹配（last known institution 含目标学校或明确的旧职）→ 强证据\n"
        "2. 研究方向 / 主题与目标一致 → 强证据\n"
        "3. 候选机构全在其他国家/领域 → 可能是同名异人\n"
        "4. 宁缺毋滥：如果没有任何候选明显匹配，返回 chosen_index=null\n"
        "5. confidence 范围 0.0-1.0，0.75 以上才可信\n\n"
        "## 输出格式\n"
        "严格 JSON：\n"
        "```json\n"
        '{"chosen_index": 1, "confidence": 0.9, "reasoning": "..."}\n'
        "```\n"
        "若无匹配，chosen_index 返回 null。"
    )


def _parse(text: str) -> _LLMPickerOutput:
    match = _JSON_FENCE_RE.search(text)
    body = match.group(1).strip() if match else text.strip()
    start, end = body.find("{"), body.rfind("}")
    if start != -1 and end != -1 and end > start:
        body = body[start : end + 1]
    return _LLMPickerOutput.model_validate_json(body)


def pick_author_id(
    *,
    target_name: str,
    target_institution: str,
    target_directions: list[str] | None,
    candidates: list[AuthorCandidate],
    llm_client: Any,
    llm_model: str,
) -> PickerDecision:
    """Return the author_id the LLM believes belongs to the target.

    Returns ``accepted_author_id=None`` when:
      * The candidate list is empty.
      * The LLM confidence is below :data:`CONFIDENCE_THRESHOLD`.
      * The LLM explicitly declines (``chosen_index=None``).
      * The LLM call / JSON parse fails (fail-safe reject).
    """
    considered_ids = [c.author_id for c in candidates]
    if not candidates:
        return PickerDecision(
            accepted_author_id=None,
            confidence=0.0,
            reasoning="No candidates supplied.",
            considered_author_ids=[],
        )
    # Fast path: a single candidate that already has institution-name
    # overlap is almost certainly the target — skip the LLM to save calls.
    if len(candidates) == 1 and _institution_overlaps(
        candidates[0].institutions, target_institution
    ):
        only = candidates[0]
        return PickerDecision(
            accepted_author_id=only.author_id,
            confidence=0.9,
            reasoning="Single candidate with matching institution.",
            considered_author_ids=considered_ids,
        )

    prompt = _build_prompt(
        target_name=target_name,
        target_institution=target_institution,
        target_directions=target_directions,
        candidates=candidates,
    )
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是学术身份对齐助手。只输出符合要求的 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=512,
            extra_body=LLM_EXTRA_BODY,
        )
        text = response.choices[0].message.content
        parsed = _parse(text)
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.warning("author_id_picker parse failure: %s", exc)
        return PickerDecision(
            accepted_author_id=None,
            confidence=0.0,
            reasoning="LLM response did not parse.",
            considered_author_ids=considered_ids,
            error=str(exc),
        )
    except Exception as exc:  # pragma: no cover - LLM transport faults
        logger.warning("author_id_picker LLM call failed: %s", exc)
        return PickerDecision(
            accepted_author_id=None,
            confidence=0.0,
            reasoning="LLM call failed.",
            considered_author_ids=considered_ids,
            error=str(exc),
        )

    if parsed.chosen_index is None:
        return PickerDecision(
            accepted_author_id=None,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning or "LLM declined to pick a candidate.",
            considered_author_ids=considered_ids,
        )
    if parsed.confidence < CONFIDENCE_THRESHOLD:
        return PickerDecision(
            accepted_author_id=None,
            confidence=parsed.confidence,
            reasoning=(
                parsed.reasoning
                or f"LLM confidence {parsed.confidence:.2f} below threshold."
            ),
            considered_author_ids=considered_ids,
        )
    idx_lookup = {c.index: c for c in candidates}
    chosen = idx_lookup.get(parsed.chosen_index)
    if chosen is None:
        return PickerDecision(
            accepted_author_id=None,
            confidence=parsed.confidence,
            reasoning=f"LLM returned unknown index {parsed.chosen_index}.",
            considered_author_ids=considered_ids,
        )
    return PickerDecision(
        accepted_author_id=chosen.author_id,
        confidence=parsed.confidence,
        reasoning=parsed.reasoning or "LLM confirmed candidate.",
        considered_author_ids=considered_ids,
    )


def _institution_overlaps(
    candidate_institutions: list[str], target_institution: str
) -> bool:
    """Cheap substring test used for the single-candidate fast path."""
    if not target_institution or not candidate_institutions:
        return False
    target_lower = target_institution.lower().strip()
    if not target_lower:
        return False
    for inst in candidate_institutions:
        il = (inst or "").lower().strip()
        if not il:
            continue
        if target_lower in il or il in target_lower:
            return True
    return False
