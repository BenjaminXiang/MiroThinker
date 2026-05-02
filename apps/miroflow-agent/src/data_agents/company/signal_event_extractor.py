from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .entity_dedup import build_signal_event_dedup_key, normalize_name

logger = logging.getLogger(__name__)

COMPANY_SIGNAL_EVENT_TYPES: tuple[str, ...] = (
    "funding",
    "product_launch",
    "partnership",
    "policy",
    "hiring",
    "order",
    "patent_grant",
    "award",
    "expansion",
    "executive_change",
)

_EVENT_TYPE_ALIASES: dict[str, str] = {
    "funding": "funding",
    "financing": "funding",
    "融资": "funding",
    "投资": "funding",
    "ipo": "funding",
    "上市": "funding",
    "挂牌": "funding",
    "新三板": "funding",
    "product_launch": "product_launch",
    "product": "product_launch",
    "产品发布": "product_launch",
    "新品发布": "product_launch",
    "发布": "product_launch",
    "partnership": "partnership",
    "合作": "partnership",
    "战略合作": "partnership",
    "并购": "partnership",
    "收购": "partnership",
    "合并": "partnership",
    "policy": "policy",
    "政策": "policy",
    "监管": "policy",
    "hiring": "hiring",
    "招聘": "hiring",
    "招募": "hiring",
    "order": "order",
    "订单": "order",
    "中标": "order",
    "采购": "order",
    "patent_grant": "patent_grant",
    "专利授权": "patent_grant",
    "专利": "patent_grant",
    "award": "award",
    "获奖": "award",
    "奖项": "award",
    "荣誉": "award",
    "expansion": "expansion",
    "扩张": "expansion",
    "投产": "expansion",
    "落地": "expansion",
    "executive_change": "executive_change",
    "高管变动": "executive_change",
    "任命": "executive_change",
    "离任": "executive_change",
}

_MARKDOWN_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", re.MULTILINE)
_DEFAULT_TEMPERATURE = 0.1
_DEFAULT_MAX_TOKENS = 1200


@dataclass(frozen=True, slots=True)
class SignalEventExtraction:
    company_id: str
    primary_news_id: str | None
    event_type: str
    event_date: date
    event_subject_normalized: dict[str, Any]
    event_summary: str
    confidence: Decimal
    corroborating_news_ids: tuple[str, ...]
    dedup_key: str


@dataclass(frozen=True, slots=True)
class SignalExtractionResult:
    events: tuple[SignalEventExtraction, ...]
    error: str | None = None


_SYSTEM_PROMPT = (
    "你是深圳科创数据平台的企业新闻事件抽取器。只从给定新闻中抽取对企业画像有用的明确信号事件。"
    "允许的 event_type 只能是：funding, product_launch, partnership, policy, hiring, order, "
    "patent_grant, award, expansion, executive_change。"
    '如果新闻没有明确事件，输出 {"events": []}。'
    "输出严格 JSON，不要 Markdown。"
)


def build_signal_event_prompt(
    *,
    company_name: str,
    title: str,
    summary: str | None,
    raw_text: str | None,
    published_at: datetime | date | str | None,
) -> str:
    published_text = _format_context_date(published_at)
    content = (raw_text or summary or "").strip()
    return "\n".join(
        [
            "## 企业",
            company_name or "未填写",
            "",
            "## 新闻",
            f"标题：{title.strip()}",
            f"发布时间：{published_text or '未知'}",
            "正文/摘要：",
            content[:4000],
            "",
            "## 输出 JSON schema",
            (
                '{"events":[{"event_type":"funding|product_launch|partnership|policy|'
                'hiring|order|patent_grant|award|expansion|executive_change",'
                '"event_date":"YYYY-MM-DD","event_summary":"中文一句话",'
                '"confidence":0.0,"subject":{"amount":"可选","counterparty":"可选"}}]}'
            ),
            "不要抽取传闻、预测、泛泛介绍或缺少日期的弱信号。",
        ]
    )


def extract_signal_events_from_news(
    *,
    company_id: str,
    company_name: str,
    news_id: str | None,
    title: str,
    summary: str | None,
    raw_text: str | None,
    published_at: datetime | date | str | None,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
) -> SignalExtractionResult:
    if not (title or summary or raw_text):
        return SignalExtractionResult(events=(), error="empty_news_input")

    prompt = build_signal_event_prompt(
        company_name=company_name,
        title=title,
        summary=summary,
        raw_text=raw_text,
        published_at=published_at,
    )
    last_error: str | None = None
    for attempt in range(2):
        retry_suffix = ""
        if attempt:
            retry_suffix = (
                '\n\n上次输出无法解析。请只输出严格 JSON 对象，形如 {"events": []}。'
            )
        try:
            raw_response = _call_llm(
                llm_client=llm_client,
                llm_model=llm_model,
                user_prompt=prompt + retry_suffix,
                extra_body=extra_body,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Signal extraction LLM call failed for news %s: %s", news_id, exc
            )
            return SignalExtractionResult(events=(), error=str(exc))

        payload, parse_error = _extract_json_payload(raw_response)
        if parse_error:
            last_error = parse_error
            continue

        events, validation_error = _coerce_events(
            payload,
            company_id=company_id,
            company_name=company_name,
            news_id=news_id,
            title=title,
            published_at=published_at,
        )
        if validation_error:
            last_error = validation_error
            continue
        return SignalExtractionResult(events=tuple(events), error=None)

    return SignalExtractionResult(events=(), error=last_error or "unknown_parse_error")


def _call_llm(
    *,
    llm_client: Any,
    llm_model: str,
    user_prompt: str,
    extra_body: dict[str, Any] | None,
) -> str:
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
    return (response.choices[0].message.content or "").strip()


def _extract_json_payload(raw_text: str) -> tuple[Any, str | None]:
    cleaned = _MARKDOWN_FENCE_RE.sub("", raw_text).strip()
    if not cleaned:
        return None, "empty_llm_response"

    start_candidates = [
        index for index in (cleaned.find("{"), cleaned.find("[")) if index >= 0
    ]
    if not start_candidates:
        return None, "json_not_found"
    start = min(start_candidates)
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if end <= start:
        return None, "json_not_found"

    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error: {exc}"
    return payload, None


def _coerce_events(
    payload: Any,
    *,
    company_id: str,
    company_name: str,
    news_id: str | None,
    title: str,
    published_at: datetime | date | str | None,
) -> tuple[list[SignalEventExtraction], str | None]:
    rows = _event_rows(payload)
    if rows is None:
        return [], "json_events_not_list"

    events: list[SignalEventExtraction] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        event_type = _coerce_event_type(row.get("event_type") or row.get("type"))
        if event_type is None:
            logger.debug("Skipping unsupported company signal event type: %s", row)
            continue
        event_date = _parse_event_date(
            row.get("event_date") or row.get("date"), published_at
        )
        if event_date is None:
            logger.debug("Skipping company signal event without usable date: %s", row)
            continue
        summary = _normalize_text(
            row.get("event_summary") or row.get("summary") or row.get("description")
        )
        if not summary:
            logger.debug("Skipping company signal event without summary: %s", row)
            continue
        subject = row.get("subject") if isinstance(row.get("subject"), dict) else {}
        normalized_subject = {
            "company_name": normalize_name(company_name),
            "source_title": title.strip(),
            **{str(key): value for key, value in subject.items()},
        }
        dedup_key = build_signal_event_dedup_key(
            company_id=company_id,
            event_type=event_type,
            event_date=event_date,
        )
        events.append(
            SignalEventExtraction(
                company_id=company_id,
                primary_news_id=news_id,
                event_type=event_type,
                event_date=event_date,
                event_subject_normalized=normalized_subject,
                event_summary=summary,
                confidence=_coerce_confidence(row.get("confidence")),
                corroborating_news_ids=(news_id,) if news_id else (),
                dedup_key=dedup_key,
            )
        )
    return events, None


def _event_rows(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return events
        if payload.get("event_type") or payload.get("type"):
            return [payload]
    return None


def _coerce_event_type(value: Any) -> str | None:
    text = _normalize_text(value).lower()
    if not text:
        return None
    if text in COMPANY_SIGNAL_EVENT_TYPES:
        return text
    return _EVENT_TYPE_ALIASES.get(text)


def _parse_event_date(
    value: Any, fallback: datetime | date | str | None
) -> date | None:
    parsed = _parse_date(value)
    if parsed is not None:
        return parsed
    return _parse_date(fallback)


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _format_context_date(value: datetime | date | str | None) -> str | None:
    parsed = _parse_date(value)
    if parsed is not None:
        return parsed.isoformat()
    if value is None:
        return None
    return str(value).strip() or None


def _coerce_confidence(value: Any) -> Decimal:
    try:
        confidence = Decimal(str(value if value is not None else "0.7"))
    except (InvalidOperation, ValueError):
        confidence = Decimal("0.7")
    if confidence > 1:
        confidence = confidence / Decimal("100")
    confidence = max(Decimal("0.0"), min(Decimal("1.0"), confidence))
    return confidence.quantize(Decimal("0.01"))


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = _MARKDOWN_FENCE_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
