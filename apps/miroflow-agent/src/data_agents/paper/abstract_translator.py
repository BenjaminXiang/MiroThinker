"""LLM-backed paper abstract to Chinese summary generation.

Two-stage rejection (per OpenSpec change ``prof-paper-patent-from-page-flow``
spec Requirement "summary_zh generation" + design.md §11):

1. ``translate_abstract_to_zh`` produces a 200-400 字 paraphrase and
   rejects obvious failure modes via a regex catalog
   (``BOILERPLATE_KEYWORDS``) — cheap, catches known patterns.
2. ``judge_summary_boilerplate`` is a second, deliberately separate
   LLM call that classifies a candidate summary as informative vs.
   topic-agnostic boilerplate. Use it on summaries that survive the
   regex filter; callers MUST set ``summary_zh=NULL`` and recompute a
   non-terminal retryable ``quality_status`` when the judge returns
   ``True``.

The judge fails open: on LLM transport / parse errors it returns
``False`` so a transient outage doesn't silently null out every newly
generated summary.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.data_agents.professor.summary_generator import BOILERPLATE_KEYWORDS

logger = logging.getLogger(__name__)

_MIN_SUMMARY_ZH_LENGTH = 100
_MAX_SUMMARY_ZH_LENGTH = 800
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_MAX_TOKENS = 700
_MARKDOWN_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"\s+")

_JUDGE_DEFAULT_TEMPERATURE = 0.0
_JUDGE_DEFAULT_MAX_TOKENS = 50
_JUDGE_BOILERPLATE_VERDICT = "BOILERPLATE"
_JUDGE_INFORMATIVE_VERDICT = "INFORMATIVE"
_GENERIC_BOILERPLATE_RE = re.compile(
    r"(?:"
    r"研究了(?:一个)?重要问题|"
    r"提出了(?:一种|一个)?新方法|"
    r"实验证明(?:了)?(?:该方法)?(?:的)?有效性|"
    r"具有重要(?:理论|现实|应用)?(?:意义|价值)|"
    r"取得了(?:较好|良好|显著)效果"
    r")"
)

_JUDGE_SYSTEM_PROMPT = (
    "你是中文学术摘要质量判别器。判断给定的论文摘要是否为「无信息量的模板"
    "化套话」(boilerplate)。\n"
    "判别规则：\n"
    "- 若摘要明确描述具体方法、具体数据/实验、具体结果或具体应用领域，"
    "判为 INFORMATIVE。\n"
    "- 若摘要全部使用「本文研究了一个重要问题」「提出了一种新方法」"
    "「实验证明了有效性」等只能套在任意论文上的通用句式，判为 BOILERPLATE。\n"
    "- 长度短并不等于 boilerplate；真正的判别标准是「换一篇论文还能照抄」。\n"
    "- 单行输出，仅输出 BOILERPLATE 或 INFORMATIVE，不要其它字符。"
)

_SYSTEM_PROMPT = (
    "你是科技论文中文摘要助手。给定英文或中文学术论文摘要，输出 200-400 字"
    "中文 paraphrase（英文需翻译并提炼，中文需改写并提炼核心方法 + 结果 + 应用领域）。\n"
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
    """Translate or summarize a paper abstract into a validated Chinese summary.

    Empty inputs are skipped by returning None. English abstracts are translated and
    condensed; Chinese abstracts are condensed/paraphrased into the same summary
    contract. LLM failures or invalid outputs also return None; callers own
    checkpointing.
    """
    source_text = (text or "").strip()
    if not source_text:
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
                        "content": "论文摘要：\n" + source_text + retry_suffix,
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


def judge_summary_boilerplate(
    summary: str | None,
    *,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
) -> bool:
    """Return True iff the LLM judge classifies ``summary`` as boilerplate.

    The LLM judge is advisory rather than a hard gate. Return True only
    when the judge says BOILERPLATE and the summary also has local
    low-information signals.

    Fails open: empty / whitespace inputs return False (nothing to
    judge; the prior translation step already returned None for those);
    LLM transport or parse errors also return False so a transient
    outage doesn't mass-reject. Callers can re-run the judge on the
    next cron pass for borderline cases.
    """
    candidate = (summary or "").strip()
    if not candidate:
        return False

    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": "\u5019\u9009\u6458\u8981\uff1a\n" + candidate},
            ],
            temperature=_JUDGE_DEFAULT_TEMPERATURE,
            max_tokens=_JUDGE_DEFAULT_MAX_TOKENS,
            extra_body=extra_body or {},
        )
        raw_text = (response.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Boilerplate judge LLM call failed: %s", exc)
        return False

    verdict = _parse_judge_verdict(raw_text)
    return (
        verdict == _JUDGE_BOILERPLATE_VERDICT
        and _looks_topic_agnostic_summary(candidate)
    )


def _looks_topic_agnostic_summary(summary: str) -> bool:
    text = summary.strip()
    if not text:
        return False
    if any(keyword in text for keyword in BOILERPLATE_KEYWORDS):
        return True
    generic_hits = len(_GENERIC_BOILERPLATE_RE.findall(text))
    if generic_hits >= 2:
        return True
    return len(text) < _MIN_SUMMARY_ZH_LENGTH and generic_hits >= 1


def _parse_judge_verdict(text: str) -> str:
    """Extract BOILERPLATE / INFORMATIVE token from the judge's reply.

    The prompt asks for a single token, but LLMs sometimes return
    quoted, punctuated, or explained variants. We scan verdict tokens in
    order and ignore explicitly negated tokens such as ``not
    BOILERPLATE``. This keeps the gate weak: reject only on an
    affirmative boilerplate verdict.
    """
    if not isinstance(text, str):
        return _JUDGE_INFORMATIVE_VERDICT
    upper = text.upper()
    token_re = re.compile(
        rf"\b({_JUDGE_BOILERPLATE_VERDICT}|{_JUDGE_INFORMATIVE_VERDICT})\b"
    )
    for match in token_re.finditer(upper):
        if _is_negated_verdict(upper, match.start()):
            continue
        return match.group(1)
    return _JUDGE_INFORMATIVE_VERDICT  # default: informative on parse miss


def _is_negated_verdict(text: str, token_start: int) -> bool:
    prefix = text[max(0, token_start - 16) : token_start]
    return bool(re.search(r"\b(?:NOT|NON|NO)\s+$", prefix))
