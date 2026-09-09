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

from .profile_summary_contract import (
    PROFILE_SUMMARY_MAX_CHARS,
    PROFILE_SUMMARY_MIN_CHARS,
    PROFILE_SUMMARY_PROMPT_CONTRACT,
    profile_summary_contract_violations,
)

logger = logging.getLogger(__name__)

_MIN_SUMMARY_LENGTH = PROFILE_SUMMARY_MIN_CHARS
_MAX_SUMMARY_LENGTH = PROFILE_SUMMARY_MAX_CHARS
_DEFAULT_MAX_PAPERS = 5
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_MAX_TOKENS = 600
_DEFAULT_COMPRESSION_MAX_TOKENS = 360
_DEFAULT_STRICT_COMPRESSION_MAX_TOKENS = 320
_DEFAULT_MIN_REINFORCE_LENGTH = PROFILE_SUMMARY_MIN_CHARS
_DEFAULT_MAX_ATTEMPTS = 2
_DEFAULT_COMPRESSION_ATTEMPTS = 2

_MARKDOWN_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class PaperContext:
    """One paper's textual context used to build the reinforcement prompt.

    Callers should pass paper.summary_zh as abstract when present, falling
    back to paper.abstract_clean or paper_full_text.abstract.
    """

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
    "根据提供的教授基本信息和论文摘要，合成一段 200-300 字的中文画像，描述该教授的研究方向、"
    f"代表性成果和学术特长。合同：{PROFILE_SUMMARY_PROMPT_CONTRACT}\n规则：\n"
    "(1) 只使用提供的内容，不要编造任何未出现的事实。\n"
    "(2) 中文，连贯叙述，不要列 bullet。\n"
    "(3) 不要加任何 Markdown 标记（如 **、##、代码块围栏）。\n"
    "(4) 严格 200-300 字。\n"
    "(5) 不要提及资料缺失、平台收录状态、暂无论文全文或仅基于基本信息。"
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
            "\n## 论文信息\n未提供代表性论文上下文。请只使用上方教授基本信息和官网简介；"
            "不要提及资料缺失、平台收录状态或论文全文缺失。"
        )
    parts.append("\n现在请合成画像：")
    return "\n".join(parts)


def _strip_markdown_fences(text: str) -> str:
    cleaned = _MARKDOWN_FENCE_RE.sub("", text)
    return cleaned.strip()


def _build_retry_prompt(*, user_prompt: str, reason: str) -> str:
    return (
        f"{user_prompt}\n\n"
        "上次输出违反摘要合同，不能写入数据库。"
        f"违反项：{reason}。请重新生成，必须严格满足 200-300 字中文摘要，"
        "不要输出英文主导内容，不要补充未提供的事实，"
        "不要提及资料缺失、平台收录状态或论文全文缺失。"
    )


def _build_compression_prompt(
    *, user_prompt: str, reason: str, compression_attempt: int
) -> str:
    if compression_attempt > 1:
        return (
            f"{user_prompt}\n\n"
            "上次压缩后仍然过长，不能写入数据库。"
            f"违反项：{reason}。请执行极限压缩：只输出 220-250 个中文字符，"
            "最多 4 个短句。删除英文括号、论文清单、项目清单、奖项细节和泛泛评价；"
            "只保留姓名、机构、身份、1-2 个最核心研究方向和 1 个最有证据的成果。"
            "不得编造未提供事实，不得提及资料缺失、平台收录状态或论文全文缺失。"
            "直接输出一段中文正文，绝对不要超过 300 字。"
        )
    return (
        f"{user_prompt}\n\n"
        "上次输出仍然过长，不能写入数据库。"
        f"违反项：{reason}。请执行压缩改写：只保留姓名、机构、研究方向、"
        "代表成果或履历中最有证据的要点，压缩为 220-260 个中文字符。"
        "必须是一段中文连贯叙述，不要列 bullet，不要输出英文主导内容，"
        "不要补充未提供的事实，不要提及资料缺失、平台收录状态或论文全文缺失。"
        "最终输出绝对不要超过 300 字。"
    )


def _summary_validation_error(text: str) -> str | None:
    violations = profile_summary_contract_violations(text)
    if not violations:
        return None
    return "profile_summary_contract: " + ",".join(violations)


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
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    compression_attempts: int = _DEFAULT_COMPRESSION_ATTEMPTS,
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

    current_user_prompt = user_prompt
    last_error: str | None = None
    attempts = max(1, int(max_attempts))

    for attempt in range(attempts):
        try:
            response = llm_client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": current_user_prompt},
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
        validation_error = _summary_validation_error(cleaned)
        if validation_error is None:
            return ReinforcementResult(
                summary=cleaned,
                source_paper_count=source_count,
                error=None,
            )

        last_error = validation_error
        logger.info(
            "Rejecting profile_summary contract violation for prof %s: %s",
            prof_name,
            validation_error,
        )
        if attempt < attempts - 1:
            current_user_prompt = _build_retry_prompt(
                user_prompt=user_prompt,
                reason=validation_error,
            )

    if last_error and "profile_summary_too_long" in last_error:
        for compression_index in range(max(0, int(compression_attempts))):
            compression_prompt = _build_compression_prompt(
                user_prompt=user_prompt,
                reason=last_error,
                compression_attempt=compression_index + 1,
            )
            max_tokens = (
                _DEFAULT_COMPRESSION_MAX_TOKENS
                if compression_index == 0
                else _DEFAULT_STRICT_COMPRESSION_MAX_TOKENS
            )
            try:
                response = llm_client.chat.completions.create(
                    model=llm_model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": compression_prompt},
                    ],
                    temperature=_DEFAULT_TEMPERATURE,
                    max_tokens=max_tokens,
                    extra_body=extra_body or {},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "LLM compression call failed for prof %s: %s", prof_name, exc
                )
                return ReinforcementResult(
                    summary="",
                    source_paper_count=source_count,
                    error=str(exc),
                )

            try:
                raw_text = (response.choices[0].message.content or "").strip()
            except (AttributeError, IndexError, TypeError) as exc:
                logger.warning(
                    "Malformed LLM compression response for prof %s: %s",
                    prof_name,
                    exc,
                )
                return ReinforcementResult(
                    summary="",
                    source_paper_count=source_count,
                    error=f"malformed_response: {exc}",
                )

            cleaned = _strip_markdown_fences(raw_text)
            validation_error = _summary_validation_error(cleaned)
            if validation_error is None:
                return ReinforcementResult(
                    summary=cleaned,
                    source_paper_count=source_count,
                    error=None,
                )
            last_error = validation_error
            logger.info(
                "Rejecting compressed profile_summary contract violation for prof %s: %s",
                prof_name,
                validation_error,
            )

    return ReinforcementResult(
        summary="",
        source_paper_count=source_count,
        error=last_error,
    )
