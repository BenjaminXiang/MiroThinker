"""LLM-backed professor profile structured-field extraction."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from bs4 import BeautifulSoup

from .llm_profiles import build_non_thinking_extra_body, resolve_professor_llm_settings


LLM_FIELD_EXTRACTION_SOURCE = "llm_extraction"
READY_CONFIDENCE_THRESHOLD = 0.75
MAX_PROFILE_TEXT_CHARS = 12000

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
_CONTACT_VALUE_RE = re.compile(
    r"@|https?://|(?:\+?\d[\d\s().-]{6,}\d)|电话|邮箱|电子邮箱|个人网站|"
    r"主页|website|email|phone|tel",
    re.IGNORECASE,
)

_FIELD_TO_FACT_TYPE = {
    "research_directions": "research_topic",
    "research_topic": "research_topic",
    "education": "education",
    "academic_position": "academic_position",
    "work_experience": "work_experience",
    "award": "award",
    "contact": "contact",
    "profile_summary": "profile_summary",
    "bio": "profile_summary",
}
_PERSISTABLE_FACT_TYPES = frozenset(
    {
        "research_topic",
        "education",
        "work_experience",
        "award",
        "academic_position",
        "contact",
    }
)
_BILINGUAL_REQUIRED_FACT_TYPES = frozenset(
    {
        "research_topic",
        "education",
        "work_experience",
        "award",
        "academic_position",
        "profile_summary",
    }
)


@dataclass(frozen=True, slots=True)
class ProfessorFieldExtractionInput:
    professor_id: str
    canonical_name: str
    institution: str
    page_text: str
    run_id: UUID | str | None
    canonical_name_en: str | None = None
    source_url: str | None = None

    def __post_init__(self) -> None:
        if self.run_id is None or not str(self.run_id).strip():
            raise ValueError("run_id is required for LLM field extraction")
        if not self.professor_id.strip():
            raise ValueError("professor_id is required")


@dataclass(frozen=True, slots=True)
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class LLMExtractedProfileFact:
    professor_id: str
    fact_type: str
    value_raw: str
    evidence_span: str
    confidence: float
    run_id: UUID | str
    source: str = LLM_FIELD_EXTRACTION_SOURCE
    value_original: str | None = None
    value_normalized: str | None = None
    field: str | None = None
    quality_status: str = "ready"

    @property
    def confidence_decimal(self) -> Decimal:
        return Decimal(str(self.confidence)).quantize(Decimal("0.01"))

    @property
    def is_persistable_fact(self) -> bool:
        return self.fact_type in _PERSISTABLE_FACT_TYPES


@dataclass(frozen=True, slots=True)
class LLMFieldExtractionResult:
    facts: tuple[LLMExtractedProfileFact, ...] = ()
    usage: LLMUsage = LLMUsage()
    error: str | None = None


def build_gemma4_llm_client() -> tuple[Any, str, dict[str, Any], dict[str, str]]:
    """Build the same OpenAI-compatible gemma4 client used by professor scans.

    The default OpenAI/httpx client intentionally keeps ``trust_env=True`` so
    the current shell's HTTPS/ALL proxy settings are honored.
    """
    from openai import OpenAI

    settings = resolve_professor_llm_settings("gemma4", include_profile=True)
    model = settings["local_llm_model"]
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        timeout=90.0,
        max_retries=0,
    )
    return client, model, build_non_thinking_extra_body(model), settings


def extract_llm_profile_fields(
    request: ProfessorFieldExtractionInput,
    *,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
) -> LLMFieldExtractionResult:
    page_text = normalize_profile_text(request.page_text)
    if not page_text:
        return LLMFieldExtractionResult(error="missing page_text")

    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract grounded professor profile facts. "
                        "Return strict JSON only."
                    ),
                },
                {"role": "user", "content": _build_prompt(request, page_text)},
            ],
            temperature=0.0,
            max_tokens=2400,
            extra_body=extra_body or {},
        )
    except Exception as exc:
        return LLMFieldExtractionResult(error=str(exc))

    try:
        payload = _parse_json_payload(response.choices[0].message.content)
        facts = tuple(
            fact
            for item in payload.get("facts", [])
            for fact in [_parse_fact_item(item, request=request, page_text=page_text)]
            if fact is not None
        )
    except Exception as exc:
        return LLMFieldExtractionResult(error=f"malformed output: {exc}")

    return LLMFieldExtractionResult(facts=facts, usage=_usage_from_response(response))


def normalize_profile_text(value: str | None) -> str:
    if not value:
        return ""
    text = value
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
    text = html.unescape(text)
    return _normalize_text(text)


def _build_prompt(request: ProfessorFieldExtractionInput, page_text: str) -> str:
    return f"""Extract structured professor profile fields from the provided page text.

Return strict JSON with this schema:
{{
  "facts": [
    {{
      "field": "research_directions | education | academic_position | work_experience | award | contact | profile_summary",
      "fact_type": "research_topic | education | academic_position | work_experience | award | contact | profile_summary",
      "original_value": "short exact value from the page",
      "bilingual_value": "English original (Chinese translation), Chinese original, or Chinese original (English gloss)",
      "evidence_span": "short exact supporting snippet copied from the page text",
      "confidence": 0.0
    }}
  ]
}}

Rules:
- Use one pass only: extract structured facts and translate English values to Chinese in bilingual_value.
- Preserve the original value inside bilingual_value. For English values, include Chinese in parentheses.
- Do not invent. Only emit a fact when evidence_span is copied from the page text.
- Omit absent fields. Do not synthesize education, position, award, work history, contact, or summary.
- Use contact only for explicit email/phone/homepage contact values.
- Keep profile_summary concise and grounded in the page.

Professor ID: {request.professor_id}
Canonical name: {request.canonical_name}
English name: {request.canonical_name_en or ""}
Institution: {request.institution}
Source URL: {request.source_url or ""}

Page text:
{page_text[:MAX_PROFILE_TEXT_CHARS]}
"""


def _parse_json_payload(text: object) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty response")
    body = text.strip()
    match = _JSON_FENCE_RE.search(body)
    if match:
        body = match.group(1).strip()
    else:
        start = body.find("{")
        end = body.rfind("}")
        if start >= 0 and end > start:
            body = body[start : end + 1]
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")
    facts = payload.get("facts")
    if not isinstance(facts, list):
        raise ValueError("facts must be a list")
    return payload


def _parse_fact_item(
    item: object,
    *,
    request: ProfessorFieldExtractionInput,
    page_text: str,
) -> LLMExtractedProfileFact | None:
    if not isinstance(item, dict):
        raise ValueError("fact item must be an object")

    field = _optional_text(item.get("field"))
    fact_type = _optional_text(item.get("fact_type"))
    fact_type = _FIELD_TO_FACT_TYPE.get(
        fact_type or "", _FIELD_TO_FACT_TYPE.get(field or "", "")
    )
    if not fact_type:
        return None

    confidence = item.get("confidence")
    if not isinstance(confidence, int | float):
        raise ValueError("confidence must be numeric")
    confidence_value = float(confidence)
    if not 0.0 <= confidence_value <= 1.0:
        raise ValueError("confidence must be between 0 and 1")

    evidence_span = _optional_text(item.get("evidence_span"))
    if evidence_span is None or not _contains_span(page_text, evidence_span):
        return None

    original_value = _optional_text(item.get("original_value")) or _optional_text(
        item.get("value_original")
    )
    value_raw = _optional_text(item.get("bilingual_value")) or _optional_text(
        item.get("value_raw")
    )
    if not value_raw:
        return None
    if original_value and not _contains_original(value_raw, original_value):
        return None
    if (
        original_value
        and fact_type in _BILINGUAL_REQUIRED_FACT_TYPES
        and _looks_english(original_value)
        and not _has_bilingual_translation(value_raw, original_value)
    ):
        return None
    if fact_type == "contact" and not _is_valid_contact_value(value_raw, evidence_span):
        return None

    quality_status = (
        "ready" if confidence_value >= READY_CONFIDENCE_THRESHOLD else "needs_review"
    )
    return LLMExtractedProfileFact(
        professor_id=request.professor_id,
        fact_type=fact_type,
        value_raw=value_raw,
        value_original=original_value,
        value_normalized=_optional_text(item.get("value_normalized")),
        evidence_span=evidence_span,
        confidence=confidence_value,
        run_id=request.run_id or "",
        field=field,
        quality_status=quality_status,
    )


def _usage_from_response(response: object) -> LLMUsage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return LLMUsage()
    return LLMUsage(
        prompt_tokens=_optional_int(getattr(usage, "prompt_tokens", None)),
        completion_tokens=_optional_int(getattr(usage, "completion_tokens", None)),
        total_tokens=_optional_int(getattr(usage, "total_tokens", None)),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("text fields must be strings or null")
    normalized = _normalize_text(value)
    return normalized or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.replace("\x00", "")).strip()


def _contains_span(page_text: str, span: str) -> bool:
    return _normalize_text(span) in page_text


def _contains_original(value_raw: str, original_value: str) -> bool:
    return (
        _normalize_text(original_value).casefold()
        in _normalize_text(value_raw).casefold()
    )


def _looks_english(value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized or _CJK_RE.search(normalized):
        return False
    return bool(_ASCII_LETTER_RE.search(normalized))


def _has_bilingual_translation(value_raw: str, original_value: str) -> bool:
    return _contains_original(value_raw, original_value) and bool(
        _CJK_RE.search(value_raw)
    )


def _is_valid_contact_value(value_raw: str, evidence_span: str) -> bool:
    return bool(_CONTACT_VALUE_RE.search(f"{value_raw} {evidence_span}"))


__all__ = [
    "LLM_FIELD_EXTRACTION_SOURCE",
    "LLMExtractedProfileFact",
    "LLMFieldExtractionResult",
    "LLMUsage",
    "ProfessorFieldExtractionInput",
    "build_gemma4_llm_client",
    "extract_llm_profile_fields",
    "normalize_profile_text",
]
