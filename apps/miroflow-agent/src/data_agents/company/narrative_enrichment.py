"""Company profile and technology-route narrative synthesis.

Pure LLM wrapper for W10-4. The caller owns database reads, retries across
companies, checkpointing, and persistence.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_PROFILE_MIN_LENGTH = 200
_PROFILE_MAX_LENGTH = 300
_TECH_ROUTE_MIN_LENGTH = 300
_TECH_ROUTE_MAX_LENGTH = 500
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_MAX_TOKENS = 1200

_MARKDOWN_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class NarrativeResult:
    profile_summary: str
    technology_route_summary: str
    error: str | None


_SYSTEM_PROMPT = (
    "你是深圳科创平台的企业画像合成助手。根据提供的企业基本信息（行业、所在城市、原始介绍），"
    "合成两段中文文本：\n"
    "1. profile_summary（200-300字）：企业画像，包含主营业务、行业定位、创立背景。\n"
    "2. technology_route_summary（300-500字）：技术路线、核心产品、研发方向、行业地位。\n"
    "规则：\n"
    "- 只使用提供的内容，不要编造未出现的事实。\n"
    "- 中文，连贯叙述，不要 bullet。\n"
    "- 不要 Markdown 标记。\n"
    "- 输出严格 JSON：{\"profile_summary\":\"...\", \"technology_route_summary\":\"...\"}"
)


def build_user_prompt(
    *,
    company_name: str,
    industry: str | None,
    hq_city: str | None,
    description: str | None,
) -> str:
    return "\n".join(
        [
            "## 企业基本信息",
            f"公司名称：{company_name or '未填写'}",
            f"行业：{industry or '行业未填写'}",
            f"所在城市：{hq_city or '城市未填写'}",
            "原始介绍：",
            (description or "").strip(),
            "",
            "请严格输出 JSON，不要输出 Markdown 或解释文字。",
        ]
    )


def _strip_markdown_fences(text: str) -> str:
    return _MARKDOWN_FENCE_RE.sub("", text).strip()


def _normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = _strip_markdown_fences(text)
    text = text.strip().strip('"').strip("'")
    return _WHITESPACE_RE.sub(" ", text).strip()


def _call_llm(
    *,
    llm_client: Any,
    llm_model: str,
    system_prompt: str,
    user_prompt: str,
    extra_body: dict[str, Any] | None,
) -> str:
    response = llm_client.chat.completions.create(
        model=llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=_DEFAULT_TEMPERATURE,
        max_tokens=_DEFAULT_MAX_TOKENS,
        extra_body=extra_body or {},
    )
    return (response.choices[0].message.content or "").strip()


def _extract_json_payload(raw_text: str) -> tuple[dict[str, Any] | None, str | None]:
    cleaned = _strip_markdown_fences(raw_text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, "json_not_found"

    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error: {exc}"
    if not isinstance(payload, dict):
        return None, "json_not_object"
    missing = [
        key
        for key in ("profile_summary", "technology_route_summary")
        if key not in payload
    ]
    if missing:
        return None, "json_missing_keys: " + ",".join(missing)
    return payload, None


def _validate_field(
    label: str,
    text: str,
    *,
    min_length: int,
    max_length: int,
) -> str | None:
    length = len(text)
    if length < min_length:
        return f"{label}_too_short: {length}"
    if length > max_length:
        return f"{label}_too_long: {length}"
    return None


def _validate_payload(
    *,
    profile_summary: str,
    technology_route_summary: str,
) -> str | None:
    profile_error = _validate_field(
        "profile_summary",
        profile_summary,
        min_length=_PROFILE_MIN_LENGTH,
        max_length=_PROFILE_MAX_LENGTH,
    )
    if profile_error:
        return profile_error
    return _validate_field(
        "technology_route_summary",
        technology_route_summary,
        min_length=_TECH_ROUTE_MIN_LENGTH,
        max_length=_TECH_ROUTE_MAX_LENGTH,
    )


def _split_prompt(
    *,
    field_name: str,
    company_name: str,
    industry: str | None,
    hq_city: str | None,
    description: str | None,
) -> tuple[str, str]:
    if field_name == "profile_summary":
        requirement = "生成 200-300 字中文企业画像，包含主营业务、行业定位、创立背景。"
    else:
        requirement = "生成 300-500 字中文技术路线摘要，包含技术路线、核心产品、研发方向、行业地位。"
    system_prompt = (
        "你是深圳科创平台的企业画像合成助手。只使用提供的信息，不编造事实；"
        "中文连贯叙述，不要 bullet，不要 Markdown。"
    )
    user_prompt = "\n".join(
        [
            requirement,
            f"公司名称：{company_name or '未填写'}",
            f"行业：{industry or '行业未填写'}",
            f"所在城市：{hq_city or '城市未填写'}",
            "原始介绍：",
            (description or "").strip(),
            "",
            "只输出正文文本，不要输出 JSON。",
        ]
    )
    return system_prompt, user_prompt


def _generate_split_fields(
    *,
    company_name: str,
    industry: str | None,
    hq_city: str | None,
    description: str | None,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None,
    original_error: str,
) -> NarrativeResult:
    try:
        profile_system, profile_prompt = _split_prompt(
            field_name="profile_summary",
            company_name=company_name,
            industry=industry,
            hq_city=hq_city,
            description=description,
        )
        profile_summary = _normalize_text(
            _call_llm(
                llm_client=llm_client,
                llm_model=llm_model,
                system_prompt=profile_system,
                user_prompt=profile_prompt,
                extra_body=extra_body,
            )
        )
        tech_system, tech_prompt = _split_prompt(
            field_name="technology_route_summary",
            company_name=company_name,
            industry=industry,
            hq_city=hq_city,
            description=description,
        )
        technology_route_summary = _normalize_text(
            _call_llm(
                llm_client=llm_client,
                llm_model=llm_model,
                system_prompt=tech_system,
                user_prompt=tech_prompt,
                extra_body=extra_body,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Split narrative fallback failed for company %s: %s", company_name, exc)
        return NarrativeResult(
            profile_summary="",
            technology_route_summary="",
            error=f"{original_error}; split_fallback_failed: {exc}",
        )

    validation_error = _validate_payload(
        profile_summary=profile_summary,
        technology_route_summary=technology_route_summary,
    )
    if validation_error:
        return NarrativeResult(
            profile_summary="",
            technology_route_summary="",
            error=f"{original_error}; split_fallback_invalid: {validation_error}",
        )
    return NarrativeResult(
        profile_summary=profile_summary,
        technology_route_summary=technology_route_summary,
        error=None,
    )


def generate_company_narrative(
    *,
    company_name: str,
    industry: str | None,
    hq_city: str | None,
    description: str | None,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
) -> NarrativeResult:
    """Generate profile_summary and technology_route_summary for one company.

    Returns empty fields with an error string on LLM, parsing, or validation
    failure. JSON parse/key failures fall back to two single-field prompts.
    """
    if len((description or "").strip()) < 30:
        return NarrativeResult(
            profile_summary="",
            technology_route_summary="",
            error="short_input",
        )

    user_prompt = build_user_prompt(
        company_name=company_name,
        industry=industry,
        hq_city=hq_city,
        description=description,
    )
    last_error: str | None = None
    for attempt in range(2):
        retry_suffix = ""
        if attempt:
            retry_suffix = (
                "\n\n上次输出不符合长度或格式要求。请重新输出严格 JSON，"
                "profile_summary 必须 200-300 字，technology_route_summary 必须 300-500 字。"
            )
        try:
            raw_text = _call_llm(
                llm_client=llm_client,
                llm_model=llm_model,
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt + retry_suffix,
                extra_body=extra_body,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Narrative LLM call failed for company %s: %s", company_name, exc)
            return NarrativeResult(
                profile_summary="",
                technology_route_summary="",
                error=str(exc),
            )

        payload, parse_error = _extract_json_payload(raw_text)
        if parse_error or payload is None:
            last_error = parse_error or "json_parse_failed"
            logger.info(
                "Narrative JSON parse failed for company %s: %s; using split fallback",
                company_name,
                last_error,
            )
            return _generate_split_fields(
                company_name=company_name,
                industry=industry,
                hq_city=hq_city,
                description=description,
                llm_client=llm_client,
                llm_model=llm_model,
                extra_body=extra_body,
                original_error=last_error,
            )

        profile_summary = _normalize_text(payload.get("profile_summary"))
        technology_route_summary = _normalize_text(
            payload.get("technology_route_summary")
        )
        validation_error = _validate_payload(
            profile_summary=profile_summary,
            technology_route_summary=technology_route_summary,
        )
        if validation_error is None:
            return NarrativeResult(
                profile_summary=profile_summary,
                technology_route_summary=technology_route_summary,
                error=None,
            )
        last_error = validation_error

    return NarrativeResult(
        profile_summary="",
        technology_route_summary="",
        error=last_error,
    )
