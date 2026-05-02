"""LLM-backed English abstract to Chinese summary translation."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.data_agents.professor.summary_generator import BOILERPLATE_KEYWORDS

logger = logging.getLogger(__name__)

_MIN_SUMMARY_ZH_LENGTH = 150
_MAX_SUMMARY_ZH_LENGTH = 500
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_MAX_TOKENS = 700
_MARKDOWN_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"\s+")

_SYSTEM_PROMPT = (
    "你是科技论文中文摘要助手。给定英文学术论文摘要，输出 200-400 字"
    "中文 paraphrase（不直译，提炼核心方法 + 结果 + 应用领域）。\n"
    "规则：\n"
    "- 保持事实准确，不增不减\n"
    "- 中文流畅，避免直译欧化句式\n"
    "- 使用领域术语\n"
    "- 不要 Markdown / bullet\n"
    "- 直接输出中文摘要文本"
)


def translate_abstract_to_zh(
    text: str | None,
    *,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
    max_retries: int = 1,
) -> str | None:
    """Translate an English abstract into a validated Chinese summary.

    Empty inputs and already-Chinese abstracts are skipped by returning None.
    LLM failures or invalid outputs also return None; callers own checkpointing.
    """
    source_text = (text or "").strip()
    if not source_text:
        return None
    if _zh_char_ratio(source_text) > 0.6:
        return None

    last_error: str | None = None
    for attempt in range(max_retries + 1):
        retry_suffix = ""
        if attempt:
            retry_suffix = (
                "\n\n上次输出不符合要求。请重新输出 200-400 字中文摘要，"
                "不要 Markdown，不要 bullet，不要解释。"
            )
        try:
            response = llm_client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": "英文摘要：\n" + source_text + retry_suffix,
                    },
                ],
                temperature=_DEFAULT_TEMPERATURE,
                max_tokens=_DEFAULT_MAX_TOKENS,
                extra_body=extra_body or {},
            )
            raw_text = (response.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Abstract translation LLM call failed: %s", exc)
            return None

        summary = _normalize_output(raw_text)
        validation_error = _validate_summary_zh(summary)
        if validation_error is None:
            return summary
        last_error = validation_error

    logger.info("Rejected translated abstract: %s", last_error)
    return None


def _normalize_output(text: str) -> str:
    cleaned = _MARKDOWN_FENCE_RE.sub("", text).strip()
    cleaned = cleaned.strip().strip('"').strip("'")
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _validate_summary_zh(summary: str) -> str | None:
    length = len(summary)
    if length < _MIN_SUMMARY_ZH_LENGTH:
        return f"too_short: {length}"
    if length > _MAX_SUMMARY_ZH_LENGTH:
        return f"too_long: {length}"
    if any(keyword in summary for keyword in BOILERPLATE_KEYWORDS):
        return "boilerplate"
    return None


def _zh_char_ratio(text: str) -> float:
    stripped = text.strip()
    if not stripped:
        return 0.0
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", stripped))
    return cjk_count / max(1, len(stripped))
