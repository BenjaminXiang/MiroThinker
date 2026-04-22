"""M6 Unit 1 — profile summary reinforcement from paper full text.

Pure function core. Takes a professor record + list of paper contexts
(title + abstract + intro from M2.3 paper_full_text table) and calls a
Gemma4-compatible LLM to synthesize an enriched profile_summary.

Caller owns:
- LLM client construction (via resolve_professor_llm_settings)
- Paper-context SQL join (via professor_paper_link + paper_full_text)
- Writing result back to professor.profile_summary

This module is stateless and I/O-free except for the injected LLM call.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_MIN_SUMMARY_LENGTH = 100
_MAX_SUMMARY_LENGTH = 800
_DEFAULT_MAX_PAPERS = 5
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_MAX_TOKENS = 600
_DEFAULT_MIN_REINFORCE_LENGTH = 50

_MARKDOWN_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class PaperContext:
    """One paper's textual context used to build the reinforcement prompt."""

    title: str
    abstract: str | None
    intro: str | None
    year: int | None
    venue: str | None


@dataclass(frozen=True, slots=True)
class ReinforcementResult:
    """Result of one reinforcement synthesis call."""

    summary: str
    source_paper_count: int
    error: str | None


def summary_reinforcement_needed(
    profile_summary: str | None,
    *,
    min_length: int = _DEFAULT_MIN_REINFORCE_LENGTH,
) -> bool:
    """Return True if the profile_summary is missing, empty, or below min_length."""
    if profile_summary is None:
        return True
    stripped = profile_summary.strip()
    return len(stripped) < min_length


_SYSTEM_PROMPT = (
    "你是深圳科创信息检索平台的教授画像合成助手。"
    "根据提供的教授基本信息和论文摘要，合成一段 200-500 字的中文画像，描述该教授的研究方向、"
    "代表性成果和学术特长。规则：\n"
    "(1) 只使用提供的内容，不要编造任何未出现的事实。\n"
    "(2) 中文，连贯叙述，不要列 bullet。\n"
    "(3) 不要加任何 Markdown 标记（如 **、##、代码块围栏）。\n"
    "(4) 长度 200-500 字为宜。"
)


def _build_user_prompt(
    *,
    prof_name: str,
    institution: str,
    research_directions: list[str],
    bio: str | None,
    paper_contexts: list[PaperContext],
) -> str:
    parts: list[str] = []
    parts.append(f"## 教授基本信息\n姓名：{prof_name}\n机构：{institution}")
    if research_directions:
        parts.append("研究方向：" + "、".join(research_directions))
    if bio and bio.strip():
        parts.append("官网简介：" + bio.strip())
    if paper_contexts:
        parts.append("\n## 代表性论文")
        for idx, paper in enumerate(paper_contexts, start=1):
            line = f"[{idx}] {paper.title}"
            meta_bits: list[str] = []
            if paper.year:
                meta_bits.append(str(paper.year))
            if paper.venue:
                meta_bits.append(paper.venue)
            if meta_bits:
                line += f" ({' / '.join(meta_bits)})"
            parts.append(line)
            if paper.abstract and paper.abstract.strip():
                parts.append(f"  摘要：{paper.abstract.strip()[:500]}")
            if paper.intro and paper.intro.strip():
                parts.append(f"  引言摘录：{paper.intro.strip()[:500]}")
    else:
        parts.append(
            "\n## 论文信息\n本教授暂无已收录的论文全文。仅基于基本信息合成。"
        )
    parts.append("\n现在请合成画像：")
    return "\n".join(parts)


def _strip_markdown_fences(text: str) -> str:
    cleaned = _MARKDOWN_FENCE_RE.sub("", text)
    return cleaned.strip()


def generate_reinforced_profile_summary(
    *,
    prof_name: str,
    institution: str,
    research_directions: list[str],
    bio: str | None,
    paper_contexts: list[PaperContext],
    llm_client: Any,
    llm_model: str,
    max_papers: int = _DEFAULT_MAX_PAPERS,
    extra_body: dict[str, Any] | None = None,
) -> ReinforcementResult:
    """Synthesize an enriched profile_summary via LLM.

    Never raises on LLM failure — returns ReinforcementResult with empty
    summary + error string set. Caller decides whether to retry or skip.
    """
    capped = list(paper_contexts[:max_papers])
    source_count = len(capped)

    user_prompt = _build_user_prompt(
        prof_name=prof_name,
        institution=institution,
        research_directions=list(research_directions or []),
        bio=bio,
        paper_contexts=capped,
    )

    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=_DEFAULT_TEMPERATURE,
            max_tokens=_DEFAULT_MAX_TOKENS,
            extra_body=extra_body or {},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM call failed for prof %s: %s", prof_name, exc)
        return ReinforcementResult(
            summary="",
            source_paper_count=source_count,
            error=str(exc),
        )

    try:
        raw_text = (response.choices[0].message.content or "").strip()
    except (AttributeError, IndexError, TypeError) as exc:
        logger.warning("Malformed LLM response for prof %s: %s", prof_name, exc)
        return ReinforcementResult(
            summary="",
            source_paper_count=source_count,
            error=f"malformed_response: {exc}",
        )

    cleaned = _strip_markdown_fences(raw_text)

    if len(cleaned) < _MIN_SUMMARY_LENGTH:
        logger.info(
            "Rejecting short summary for prof %s (len=%d)", prof_name, len(cleaned)
        )
        return ReinforcementResult(
            summary="",
            source_paper_count=source_count,
            error=f"too_short: {len(cleaned)}",
        )

    capped_text = cleaned[:_MAX_SUMMARY_LENGTH]
    return ReinforcementResult(
        summary=capped_text,
        source_paper_count=source_count,
        error=None,
    )
