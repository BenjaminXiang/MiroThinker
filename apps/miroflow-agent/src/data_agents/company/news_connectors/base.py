from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NewsRecord:
    company_id: str
    source_url: str
    title: str
    summary: str | None
    published_at: datetime | None
    raw_text: str | None


class NewsConnector(Protocol):
    def fetch(
        self, company_unified_credit_code: str, since: date
    ) -> list[NewsRecord]: ...


def parse_news_payload(payload: Any, *, company_id: str) -> list[NewsRecord]:
    """Normalize common Chinese finance-news API response shapes."""
    records: list[NewsRecord] = []
    for row in _iter_payload_rows(payload):
        mapping = _row_to_mapping(row)
        if not mapping:
            continue
        record = _record_from_mapping(mapping, company_id=company_id)
        if record is not None:
            records.append(record)
    return records


def _iter_payload_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    data = payload.get("data")
    if isinstance(data, dict):
        fields = data.get("fields")
        items = data.get("items")
        if isinstance(fields, list) and isinstance(items, list):
            return [
                dict(zip([str(field) for field in fields], item, strict=False))
                for item in items
                if isinstance(item, list | tuple)
            ]
        for key in ("items", "news", "articles", "rows", "result", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    for key in ("items", "news", "articles", "rows", "result", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _row_to_mapping(row: Any) -> dict[str, Any] | None:
    if isinstance(row, dict):
        return row
    if isinstance(row, list | tuple):
        keys = ("published_at", "title", "summary", "raw_text", "source_url")
        return dict(zip(keys, row, strict=False))
    return None


def _record_from_mapping(
    mapping: dict[str, Any], *, company_id: str
) -> NewsRecord | None:
    source_url = _first_text(
        mapping,
        "source_url",
        "url",
        "link",
        "article_url",
        "content_url",
    )
    title = _first_text(mapping, "title", "headline", "name")
    if not source_url or not title:
        logger.debug("Skipping news row without source_url/title: %s", mapping)
        return None

    summary = _first_text(mapping, "summary", "desc", "description", "abstract")
    raw_text = _first_text(mapping, "raw_text", "content", "body", "text")
    return NewsRecord(
        company_id=company_id,
        source_url=source_url,
        title=title,
        summary=summary or raw_text,
        published_at=_parse_datetime(
            _first_present(
                mapping,
                "published_at",
                "publish_time",
                "pub_time",
                "datetime",
                "time",
                "date",
            )
        ),
        raw_text=raw_text or summary,
    )


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _first_text(mapping: dict[str, Any], *keys: str) -> str | None:
    value = _first_present(mapping, *keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            parsed_date = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)

    normalized = text.replace("Z", "+00:00")
    try:
        return _ensure_aware(datetime.fromisoformat(normalized))
    except ValueError:
        logger.debug("Could not parse news published_at=%r", value)
        return None


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
