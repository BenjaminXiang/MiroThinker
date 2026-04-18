# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.6 — batch identity gate for paper→professor attribution.

Same-name professors share author handles on OpenAlex/Semantic Scholar.
The original ``paper_collector`` matches author name + affiliation, but
it does not ask an LLM whether the candidate paper *really* belongs to
this specific professor. This module adds that check in batch form so
one prompt can evaluate up to ``BATCH_SIZE`` candidate papers at once,
keeping the LLM cost of verifying a full corpus bounded.

Precision-first: confidence < 0.8 forces rejection, same threshold as
``identity_verifier``. Fail-safe: LLM/JSON errors default to rejecting
the paper (never expand pollution).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .identity_verifier import CONFIDENCE_THRESHOLD, ProfessorContext
from .translation_spec import LLM_EXTRA_BODY

logger = logging.getLogger(__name__)

BATCH_SIZE = 15

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class PaperIdentityCandidate:
    """One paper presented to the gate for verification."""

    index: int
    title: str
    authors: list[str]
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None


class _PaperDecision(BaseModel):
    index: int
    is_same_person: bool
    confidence: float = Field(ge=0.0, le=1.0)
    topic_consistency: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning: str = ""


class _BatchDecision(BaseModel):
    decisions: list[_PaperDecision]


@dataclass(frozen=True, slots=True)
class PaperIdentityDecision:
    """Per-paper verdict returned by ``batch_verify_paper_identity``.

    ``topic_consistency`` is a 0-1 score indicating how well the paper's
    research topic aligns with the target professor's stated research
    directions. ``None`` when the LLM couldn't / didn't produce a score
    (e.g. parse error, missing field, or paper rejected outright).
    """

    index: int
    accepted: bool
    confidence: float
    reasoning: str
    topic_consistency: float | None = None
    error: str | None = None


def _render_candidates(candidates: list[PaperIdentityCandidate]) -> str:
    lines: list[str] = []
    for cand in candidates:
        author_text = ", ".join(cand.authors[:8])
        meta_bits = []
        if cand.year:
            meta_bits.append(str(cand.year))
        if cand.venue:
            meta_bits.append(cand.venue)
        meta_text = " · ".join(meta_bits)
        snippet = (cand.abstract or "").strip().replace("\n", " ")
        if snippet:
            snippet = snippet[:200]
        lines.append(
            f"[{cand.index}] title: {cand.title.strip()}\n"
            f"      authors: {author_text}\n"
            f"      meta: {meta_text or '—'}\n"
            f"      abstract: {snippet or '—'}"
        )
    return "\n".join(lines)


def _build_prompt(
    context: ProfessorContext, candidates: list[PaperIdentityCandidate]
) -> str:
    directions_text = (
        "、".join(context.research_directions)
        if context.research_directions
        else "未知"
    )
    return (
        "## 任务\n"
        "给定一位目标教授的身份信息，以及若干候选论文记录，判断每一篇论文是否由该教授本人撰写。\n\n"
        "## 目标教授\n"
        f"姓名: {context.name}\n"
        f"学校: {context.institution}\n"
        f"院系: {context.department or '未知'}\n"
        f"研究方向: {directions_text}\n\n"
        "## 候选论文（按 index 编号）\n"
        f"{_render_candidates(candidates)}\n\n"
        "## 判断指引\n"
        "1. 合作者名单中若能看到同一机构的同事 → 强匹配证据\n"
        "2. 期刊/会议领域与教授研究方向一致 → 中匹配证据\n"
        "3. 同名但领域不符、合作者全部来自不相关机构 → 可能是其他同名学者\n"
        "4. 信息不足难以判断 → 宁可拒绝 (confidence < 0.8)\n"
        "5. 对每篇论文独立给出决定，confidence 范围 0.0-1.0\n"
        "6. 同时估计 topic_consistency（0.0-1.0），表示论文主题与教授研究方向的贴合度：\n"
        "   1.0 = 完全吻合；0.7 = 主题相关但子方向不同；0.3 = 仅领域交集；0.0 = 完全无关\n\n"
        "## 输出格式\n"
        "仅输出 JSON，字段 decisions 是数组，按 index 升序：\n"
        "```json\n"
        "{\n"
        '  "decisions": [\n'
        '    {"index": 0, "is_same_person": true, "confidence": 0.92, "topic_consistency": 0.85, "reasoning": "..."},\n'
        "    ...\n"
        "  ]\n"
        "}\n"
        "```"
    )


def _parse(text: str) -> _BatchDecision:
    match = _JSON_FENCE_RE.search(text)
    body = match.group(1).strip() if match else text.strip()
    start, end = body.find("{"), body.rfind("}")
    if start != -1 and end != -1 and end > start:
        body = body[start : end + 1]
    return _BatchDecision.model_validate_json(body)


def _reject_all(
    candidates: list[PaperIdentityCandidate], *, reason: str, error: str | None = None
) -> list[PaperIdentityDecision]:
    return [
        PaperIdentityDecision(
            index=c.index,
            accepted=False,
            confidence=0.0,
            reasoning=reason,
            error=error,
        )
        for c in candidates
    ]


async def _verify_single_batch(
    *,
    context: ProfessorContext,
    candidates: list[PaperIdentityCandidate],
    llm_client: Any,
    llm_model: str,
) -> list[PaperIdentityDecision]:
    if not candidates:
        return []

    prompt = _build_prompt(context, candidates)
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是学术身份验证助手。只输出符合要求的 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
            extra_body=LLM_EXTRA_BODY,
        )
        text = response.choices[0].message.content
        parsed = _parse(text)
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.warning("paper_identity_gate parse failure: %s", exc)
        return _reject_all(
            candidates,
            reason="LLM response did not parse; defaulting to reject.",
            error=str(exc),
        )
    except Exception as exc:  # pragma: no cover - network / LLM faults
        logger.warning("paper_identity_gate LLM call failed: %s", exc)
        return _reject_all(
            candidates,
            reason="LLM call failed; defaulting to reject.",
            error=str(exc),
        )

    decisions_by_index: dict[int, _PaperDecision] = {
        d.index: d for d in parsed.decisions
    }
    out: list[PaperIdentityDecision] = []
    for cand in candidates:
        dec = decisions_by_index.get(cand.index)
        if dec is None:
            out.append(
                PaperIdentityDecision(
                    index=cand.index,
                    accepted=False,
                    confidence=0.0,
                    reasoning="LLM returned no decision for this paper.",
                )
            )
            continue
        accepted = dec.is_same_person and dec.confidence >= CONFIDENCE_THRESHOLD
        out.append(
            PaperIdentityDecision(
                index=cand.index,
                accepted=accepted,
                confidence=dec.confidence,
                reasoning=dec.reasoning,
                topic_consistency=dec.topic_consistency,
            )
        )
    return out


async def batch_verify_paper_identity(
    *,
    professor_context: ProfessorContext,
    candidates: list[PaperIdentityCandidate],
    llm_client: Any,
    llm_model: str,
    batch_size: int = BATCH_SIZE,
) -> list[PaperIdentityDecision]:
    """Run LLM identity verification on *candidates* in batches.

    Ordered output: one decision per input candidate, preserving order.
    """
    if not candidates:
        return []
    results: list[PaperIdentityDecision] = []
    for start in range(0, len(candidates), batch_size):
        chunk = candidates[start : start + batch_size]
        results.extend(
            await _verify_single_batch(
                context=professor_context,
                candidates=chunk,
                llm_client=llm_client,
                llm_model=llm_model,
            )
        )
    # Preserve input order even if LLM returns sorted differently
    by_index = {d.index: d for d in results}
    return [by_index[c.index] for c in candidates]
