from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from .quality_gate import (
    ProfessorCanonicalState,
    ProfessorQualityEvaluation,
    evaluate_professor_quality,
)

MODEL_QUALITY_GATE_REPORTED_BY = "professor_model_quality_gate"
MODEL_QUALITY_GATE_STAGE = "data_quality_flag"
MODEL_QUALITY_GATE_ACTOR = "professor-model-quality-gate"
MODEL_READY_CONFIDENCE_THRESHOLD = 0.75

ModelQualityFinalStatus = Literal["ready", "needs_review", "needs_enrichment", "low_confidence"]

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ModelQualityGateDecision:
    publishable: bool
    confidence: float
    reason_codes: tuple[str, ...]
    rationale: str
    raw_response_hash: str
    prompt_hash: str
    usage: dict[str, int | None]


@dataclass(frozen=True, slots=True)
class ModelQualityGateResult:
    professor_id: str
    base_quality_status: str
    final_quality_status: ModelQualityFinalStatus
    model_called: bool
    decision: ModelQualityGateDecision | None = None
    skip_reason: str | None = None

    @property
    def ready_for_publish(self) -> bool:
        return self.final_quality_status == "ready"


def evaluate_model_quality_gate(
    state: ProfessorCanonicalState,
    *,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
    confidence_threshold: float = MODEL_READY_CONFIDENCE_THRESHOLD,
) -> ModelQualityGateResult:
    """Run model publishability review only after deterministic quality passes."""

    base = evaluate_professor_quality(state)
    if base.quality_status != "ready":
        return ModelQualityGateResult(
            professor_id=state.professor_id,
            base_quality_status=base.quality_status,
            final_quality_status=base.quality_status,
            model_called=False,
            skip_reason=f"base_gate_{base.quality_status}",
        )

    messages = build_model_quality_gate_messages(state, base)
    prompt_hash = _hash_text(json.dumps(messages, ensure_ascii=False, sort_keys=True))
    create_kwargs: dict[str, Any] = {
        "model": llm_model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 700,
    }
    if extra_body:
        create_kwargs["extra_body"] = extra_body
    response = llm_client.chat.completions.create(**create_kwargs)
    raw_text = _response_text(response)
    payload = _parse_json_object(raw_text)
    decision = _decision_from_payload(
        payload,
        prompt_hash=prompt_hash,
        raw_text=raw_text,
        usage=_usage_metadata(response),
    )
    final_status: ModelQualityFinalStatus = (
        "ready"
        if decision.publishable and decision.confidence >= confidence_threshold
        else "needs_review"
    )
    return ModelQualityGateResult(
        professor_id=state.professor_id,
        base_quality_status=base.quality_status,
        final_quality_status=final_status,
        model_called=True,
        decision=decision,
    )


def build_model_quality_gate_messages(
    state: ProfessorCanonicalState,
    base_evaluation: ProfessorQualityEvaluation,
) -> list[dict[str, str]]:
    profile = _profile_payload(state, base_evaluation)
    return [
        {
            "role": "system",
            "content": (
                "你是高校教师画像发布质量门。只基于输入数据判断这条教师画像能否发布使用。"
                "不要补充外部事实。只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                "判断标准：publishable=true 仅当姓名是人名、院校/院系/职称无明显矛盾、"
                "中文简介符合 200-300 字且不是英文主导/模板话术/空泛堆砌、研究方向不是人名或无意义缩写、"
                "官方来源或原始文本足以支撑核心身份与研究信息。若证据不足、摘要过薄、明显重复、"
                "英文未翻译或字段疑似误抽，则 publishable=false。\n"
                "输出严格 JSON："
                '{"publishable": true|false, "confidence": 0.0-1.0, '
                '"reason_codes": ["..."], "rationale": "一句中文理由"}\n'
                "待审画像 JSON：\n"
                f"{json.dumps(profile, ensure_ascii=False, default=str)}"
            ),
        },
    ]


def _profile_payload(
    state: ProfessorCanonicalState,
    base_evaluation: ProfessorQualityEvaluation,
) -> dict[str, Any]:
    current_affiliations = [
        {
            "institution": item.institution,
            "department": item.department,
            "title": item.title,
            "is_primary": item.is_primary,
            "is_current": item.is_current,
        }
        for item in state.affiliations
        if item.is_current
    ]
    facts = [
        {
            "fact_type": fact.fact_type,
            "value_raw": fact.value_raw,
            "status": fact.status,
        }
        for fact in state.facts
        if fact.status == "active" and (fact.value_raw or "").strip()
    ][:80]
    external_issues = [
        {
            "stage": issue.stage,
            "reported_by": issue.reported_by,
            "description": issue.description,
        }
        for issue in state.open_issues
        if not issue.resolved
    ][:30]
    return {
        "professor_id": state.professor_id,
        "canonical_name": state.canonical_name,
        "aliases": list(state.aliases),
        "identity_status": state.identity_status,
        "lifecycle_state": state.lifecycle_state,
        "profile_summary": state.profile_summary,
        "paper_summary": state.paper_summary,
        "primary_official_profile_page_id": str(state.primary_official_profile_page_id or ""),
        "source_pages": [
            {"url": page.url, "is_official_source": page.is_official_source}
            for page in state.source_pages[:10]
        ],
        "current_affiliations": current_affiliations,
        "facts": facts,
        "has_verified_paper_signal": state.has_verified_paper_signal,
        "has_research_overview_zh": state.has_research_overview_zh,
        "base_quality_status": base_evaluation.quality_status,
        "base_reasons": [reason.rule_id for reason in base_evaluation.reasons],
        "open_issues_sample": external_issues,
        "official_raw_text_excerpt": (state.profile_raw_text or "")[:3000],
    }


def _decision_from_payload(
    payload: Any,
    *,
    prompt_hash: str,
    raw_text: str,
    usage: dict[str, int | None],
) -> ModelQualityGateDecision:
    if not isinstance(payload, dict):
        return ModelQualityGateDecision(
            publishable=False,
            confidence=0.0,
            reason_codes=("malformed_model_response",),
            rationale="模型未返回可解析 JSON。",
            raw_response_hash=_hash_text(raw_text),
            prompt_hash=prompt_hash,
            usage=usage,
        )
    publishable = bool(payload.get("publishable") is True)
    confidence = _coerce_confidence(payload.get("confidence"))
    raw_reasons = payload.get("reason_codes")
    if isinstance(raw_reasons, list):
        reason_codes = tuple(str(item).strip() for item in raw_reasons if str(item).strip())
    else:
        reason_codes = ()
    rationale = str(payload.get("rationale") or "").strip()[:300]
    if not rationale:
        reason_codes = (*reason_codes, "missing_rationale")
        publishable = False
    return ModelQualityGateDecision(
        publishable=publishable,
        confidence=confidence,
        reason_codes=reason_codes,
        rationale=rationale,
        raw_response_hash=_hash_text(raw_text),
        prompt_hash=prompt_hash,
        usage=usage,
    )


def _parse_json_object(raw_text: str) -> Any:
    cleaned = raw_text.strip()
    fence = _JSON_FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return str(getattr(message, "content", "") or "").strip()


def _usage_metadata(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
