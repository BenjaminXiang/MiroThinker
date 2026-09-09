from __future__ import annotations

import os
import re
from typing import Any, Literal

from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings


PatentSummaryMethod = Literal["llm", "fallback_template"]

_MIN_LLM_SUMMARY_LENGTH = 50
_MAX_LLM_SUMMARY_LENGTH = 300
_WHITESPACE_RE = re.compile(r"\s+")
_MARKDOWN_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", re.MULTILINE)
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_MAX_TOKENS = 500

_SYSTEM_PROMPT = (
    "你是专利技术摘要助手。根据给定专利字段，输出一段 150-300 字中文摘要，"
    "覆盖问题背景、核心方法、技术效果。只输出单段正文，不要 Markdown、标题或列表。"
)


def generate_patent_summary_text(
    record: Any,
    *,
    llm_client: Any,
) -> tuple[str, PatentSummaryMethod]:
    """Generate a patent summary with an OpenAI-compatible client.

    The caller injects the client, while this helper resolves the project LLM
    profile for the model and request options. Any invalid output or LLM failure
    falls back to the deterministic template.
    """
    fallback = build_fallback_summary_text(record)
    if llm_client is None:
        return fallback, "fallback_template"
    try:
        settings = resolve_professor_llm_settings("gemma4", include_profile=True)
        _clear_https_proxy_env()
        response = llm_client.chat.completions.create(
            model=settings["local_llm_model"],
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(record)},
            ],
            temperature=_DEFAULT_TEMPERATURE,
            max_tokens=_DEFAULT_MAX_TOKENS,
        )
        text = _normalize_output(response.choices[0].message.content or "")
    except Exception:  # noqa: BLE001 - fallback is the intended runtime behavior
        return fallback, "fallback_template"

    if len(text) < _MIN_LLM_SUMMARY_LENGTH:
        return fallback, "fallback_template"
    if len(text) > _MAX_LLM_SUMMARY_LENGTH:
        text = text[:_MAX_LLM_SUMMARY_LENGTH].rstrip() + "…"
    return text, "llm"


def build_fallback_summary_text(record: Any) -> str:
    title = _field(record, "title_clean", "title")
    abstract = _field(record, "abstract_clean", "abstract")
    technology_effect = _technology_effect(record)
    patent_type = _field(record, "patent_type")

    parts = [f"该专利围绕“{title}”展开。"] if title else ["该专利围绕相关技术方案展开。"]
    if abstract:
        parts.append(abstract)
    if technology_effect:
        parts.append(f"技术效果重点是{technology_effect}。")
    if patent_type:
        parts.append(f"当前记录的专利类型为{patent_type}。")
    return _join_and_trim(parts, limit=280)


def _build_user_prompt(record: Any) -> str:
    applicants = _field_list(record, "applicants_parsed", "applicants")
    lines = [
        f"标题：{_field(record, 'title_clean', 'title') or '未填写'}",
        f"申请人：{'；'.join(applicants) if applicants else '未填写'}",
        f"摘要：{_field(record, 'abstract_clean', 'abstract') or '未填写'}",
        f"技术效果：{_technology_effect(record) or '未填写'}",
    ]
    return "\n".join(lines)


def _field(record: Any, *names: str) -> str | None:
    for name in names:
        value = getattr(record, name, None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _field_list(record: Any, *names: str) -> list[str]:
    for name in names:
        value = getattr(record, name, None)
        if value is None:
            continue
        if isinstance(value, str):
            values = [value]
        else:
            values = list(value)
        tokens = [str(item).strip() for item in values if str(item).strip()]
        if tokens:
            return tokens
    return []


def _technology_effect(record: Any) -> str | None:
    direct = _field(record, "technology_effect", "technology_effect_sentence")
    if direct:
        return direct
    phrases = _field_list(record, "technology_effect_phrases")
    if phrases:
        return "、".join(phrases)
    return None


def _normalize_output(text: str) -> str:
    cleaned = _MARKDOWN_FENCE_RE.sub("", text).strip()
    cleaned = cleaned.strip().strip('"').strip("'")
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _join_and_trim(parts: list[str], *, limit: int) -> str:
    text = "".join(part for part in parts if part)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip("，。；; ") + "。"


def _clear_https_proxy_env() -> None:
    for key in ("https_proxy", "HTTPS_PROXY"):
        os.environ.pop(key, None)
