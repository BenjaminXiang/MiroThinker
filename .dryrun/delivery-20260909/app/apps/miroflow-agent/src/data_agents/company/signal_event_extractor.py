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
    status: str = "active"


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
    source_adapter: str | None = None,
    source_url: str | None = None,
) -> str:
    published_text = _format_context_date(published_at)
    content = (raw_text or summary or "").strip()
    source_context = ""
    if source_adapter or source_url:
        source_context = "\n".join(
            [
                "",
                "## source profile context",
                f"source_adapter：{source_adapter or 'unknown'}",
                f"source_url：{source_url or 'unknown'}",
                "这可能是企业画像/项目页，不一定是新闻稿；可以从其中明确标注日期的融资历史、产品发布、合作、奖项、扩张和高管/团队变动中抽取事件。",
                "不要把页面抓取时间或当前日期当作事件日期；正文没有对应年月/日期证据时不要抽取事件。",
            ]
        )
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
            source_context,
            "",
            "## 输出 JSON schema",
            (
                '{"events":[{"event_type":"funding|product_launch|partnership|policy|'
                'hiring|order|patent_grant|award|expansion|executive_change",'
                '"event_date":"YYYY-MM-DD","event_summary":"中文一句话",'
                '"confidence":0.0,"subject":{"amount":"可选","counterparty":"可选"}}]}'
            ),
            "融资事件的 subject 应尽量使用 round, amount, investors, review_reason 或 requires_review 字段；只能填写正文明确出现的融资轮次、金额和投资方。",
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
    source_adapter: str | None = None,
    source_url: str | None = None,
    baseline_latest_funding_round: str | None = None,
    baseline_latest_funding_date: date | datetime | str | None = None,
) -> SignalExtractionResult:
    if not (title or summary or raw_text):
        return SignalExtractionResult(events=(), error="empty_news_input")

    prompt = build_signal_event_prompt(
        company_name=company_name,
        title=title,
        summary=summary,
        raw_text=raw_text,
        published_at=published_at,
        source_adapter=source_adapter,
        source_url=source_url,
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
            source_text=raw_text or summary,
            published_at=published_at,
            require_source_date_evidence=_requires_source_profile_date_evidence(
                source_adapter=source_adapter,
                source_url=source_url,
            ),
            source_adapter=source_adapter,
            source_url=source_url,
            baseline_latest_funding_round=baseline_latest_funding_round,
            baseline_latest_funding_date=baseline_latest_funding_date,
        )
        if validation_error:
            last_error = validation_error
            continue
        return SignalExtractionResult(events=tuple(events), error=None)

    return SignalExtractionResult(events=(), error=last_error or "unknown_parse_error")


def _requires_source_profile_date_evidence(
    *, source_adapter: str | None, source_url: str | None
) -> bool:
    if source_adapter not in {"iyiou", "pitchhub_36kr"}:
        return False
    url = source_url or ""
    if "data.iyiou.com/news/" in url:
        return False
    return True


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
    source_text: str | None,
    published_at: datetime | date | str | None,
    require_source_date_evidence: bool = False,
    source_adapter: str | None = None,
    source_url: str | None = None,
    baseline_latest_funding_round: str | None = None,
    baseline_latest_funding_date: date | datetime | str | None = None,
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
        if require_source_date_evidence and not _date_supported_by_source_text(
            event_date,
            source_text,
        ):
            logger.debug(
                "Skipping source-profile signal event without source date evidence: %s",
                row,
            )
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
        event_status = "active"
        if event_type == "funding":
            funding_subject, event_status = _normalize_funding_subject(
                subject=subject,
                event_date=event_date,
                event_summary=summary,
                source_adapter=source_adapter,
                source_url=source_url,
                baseline_latest_funding_round=baseline_latest_funding_round,
                baseline_latest_funding_date=baseline_latest_funding_date,
            )
            normalized_subject.update(funding_subject)
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
                status=event_status,
            )
        )
    return events, None


def _normalize_funding_subject(
    *,
    subject: dict[str, Any],
    event_date: date,
    event_summary: str,
    source_adapter: str | None,
    source_url: str | None,
    baseline_latest_funding_round: str | None,
    baseline_latest_funding_date: date | datetime | str | None,
) -> tuple[dict[str, Any], str]:
    financing_round = _first_text(
        subject,
        "financing_round",
        "funding_round",
        "round",
        "轮次",
        "融资轮次",
    )
    amount_raw = _first_text(
        subject,
        "amount",
        "amount_raw",
        "funding_amount",
        "融资金额",
        "金额",
    )
    investors_raw = _first_text(
        subject,
        "investors",
        "investor",
        "counterparty",
        "投资方",
        "投资机构",
    )
    investors = _coerce_investors(
        subject.get("investors")
        or subject.get("investor")
        or subject.get("counterparty")
        or subject.get("投资方")
        or subject.get("投资机构")
    )
    baseline_date = _parse_date(baseline_latest_funding_date)
    baseline_round = _normalize_text(baseline_latest_funding_round)
    review_reason = _first_text(
        subject,
        "review_reason",
        "conflict_reason",
        "uncertain_reason",
        "审核原因",
    )

    freshness = "no_xlsx_baseline"
    if baseline_date is not None:
        if event_date > baseline_date:
            freshness = "newer_than_xlsx_baseline"
        elif event_date < baseline_date:
            freshness = "older_than_xlsx_baseline"
        else:
            freshness = "same_date_as_xlsx_baseline"
            if (
                not review_reason
                and financing_round
                and baseline_round
                and _normalize_funding_round(financing_round)
                != _normalize_funding_round(baseline_round)
            ):
                review_reason = "conflicts_with_xlsx_baseline"

    normalized: dict[str, Any] = {
        "financing_summary": event_summary,
        "funding_freshness": freshness,
    }
    if financing_round:
        normalized["financing_round"] = financing_round
    if amount_raw:
        normalized["amount_raw"] = amount_raw
        amount_cny_wan = _amount_cny_wan(amount_raw)
        if amount_cny_wan is not None:
            normalized["amount_cny_wan"] = amount_cny_wan
    if investors_raw:
        normalized["investors_raw"] = investors_raw
    if investors:
        normalized["investors"] = investors
    if source_url:
        normalized["source_url"] = source_url
    if source_adapter:
        normalized["source_adapter"] = source_adapter
    if baseline_round or baseline_date is not None:
        normalized["xlsx_baseline"] = {
            "round": baseline_round or None,
            "date": baseline_date.isoformat() if baseline_date else None,
        }

    requires_review = _truthy(subject.get("requires_review")) or bool(review_reason)
    if review_reason:
        normalized["review_reason"] = review_reason
    return normalized, "needs_review" if requires_review else "active"


def _first_text(subject: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = subject.get(key)
        if isinstance(value, (list, tuple)):
            text = "、".join(_normalize_text(item) for item in value if _normalize_text(item))
        else:
            text = _normalize_text(value)
        if text:
            return text
    return None


def _coerce_investors(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        candidates = value
    else:
        candidates = re.split(r"[,，、;；/|和及与]+", str(value))
    investors: list[str] = []
    for item in candidates:
        text = _normalize_text(item)
        if text and text not in investors:
            investors.append(text)
    return investors


def _amount_cny_wan(value: str) -> str | None:
    text = _normalize_text(value).replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(亿元|亿|万元|万|元)", text)
    if match is None:
        return None
    amount = Decimal(match.group(1))
    unit = match.group(2)
    if unit in {"亿元", "亿"}:
        amount *= Decimal("10000")
    elif unit == "元":
        amount /= Decimal("10000")
    quantized = amount.quantize(Decimal("0.01")) if amount % 1 else amount
    return format(quantized.normalize(), "f")


def _normalize_funding_round(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().casefold() in {"1", "true", "yes", "y", "是", "需审核"}


def _date_supported_by_source_text(event_date: date, source_text: str | None) -> bool:
    text = source_text or ""
    if not text:
        return False
    day_markers = (
        event_date.isoformat(),
        f"{event_date.year:04d}年{event_date.month}月{event_date.day}日",
        f"{event_date.year:04d}年{event_date.month:02d}月{event_date.day:02d}日",
    )
    if any(marker in text for marker in day_markers):
        return True
    if event_date.day != 1:
        return False
    month_markers = (
        f"{event_date.year:04d}-{event_date.month:02d}",
        f"{event_date.year:04d}年{event_date.month}月",
        f"{event_date.year:04d}年{event_date.month:02d}月",
    )
    return any(marker in text for marker in month_markers)


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
