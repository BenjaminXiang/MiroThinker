from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import requests

from .base import NewsRecord

logger = logging.getLogger(__name__)

_QUERY_TAIL = "(融资 OR 发布 OR 收购 OR 上市 OR 任命 OR 中标) -招聘 -招标公告"


class SerperNewsConnector:
    """Serper.dev news search connector for company news ingest."""

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = "https://google.serper.dev/news",
        session: Any | None = None,
        timeout_seconds: float = 15.0,
        result_cap: int = 10,
    ) -> None:
        self.api_key = api_key.strip()
        self.endpoint = endpoint
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.result_cap = result_cap

    def fetch(self, company_canonical_name: str, since: date) -> list[NewsRecord]:
        if not self.api_key:
            logger.info("Skipping Serper fetch: SERPER_API_KEY not set")
            return []

        query = _build_query(company_canonical_name)
        payload = {
            "q": query,
            "tbs": f"qdr:{_qdr_for_since(since)}",
            "num": self.result_cap,
            "hl": "zh-cn",
            "gl": "cn",
        }
        try:
            response = self.session.post(
                self.endpoint,
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Serper fetch failed for %s: %s", company_canonical_name, exc)
            return []

        news_items = body.get("news") if isinstance(body, dict) else None
        if not isinstance(news_items, list):
            return []

        since_start = datetime.combine(_as_utc_date(since), time.min, tzinfo=timezone.utc)
        fetched_at = datetime.now(timezone.utc)
        seen_urls: set[str] = set()
        records: list[NewsRecord] = []
        for item in news_items:
            if not isinstance(item, dict):
                continue
            record = _record_from_serper_item(
                item,
                company_id=company_canonical_name,
                fetched_at=fetched_at,
            )
            if record is None:
                continue
            if record.published_at is not None and record.published_at < since_start:
                continue
            if record.source_url in seen_urls:
                continue
            seen_urls.add(record.source_url)
            records.append(record)
        return records


def _build_query(company_canonical_name: str) -> str:
    return f"{company_canonical_name.strip()} {_QUERY_TAIL}".strip()


def _qdr_for_since(since: date) -> str:
    days = (datetime.now(timezone.utc).date() - _as_utc_date(since)).days
    if days <= 1:
        return "d"
    if days <= 7:
        return "w"
    if days <= 30:
        return "m"
    return "y"


def _as_utc_date(value: date) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(timezone.utc).date()
    return value


def _record_from_serper_item(
    item: dict[str, Any],
    *,
    company_id: str,
    fetched_at: datetime,
) -> NewsRecord | None:
    title = _clean_text(item.get("title"))
    source_url = _clean_text(item.get("link"))
    if not title or not source_url:
        logger.debug("Skipping Serper news row without title/link: %s", item)
        return None

    snippet = _clean_text(item.get("snippet"))
    published_at = _parse_serper_date(_clean_text(item.get("date")) or "") or fetched_at
    return NewsRecord(
        company_id=company_id,
        source_url=source_url,
        title=title,
        summary=snippet,
        published_at=published_at,
        raw_text=snippet,
    )


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_serper_date(text: str) -> datetime | None:
    """Best-effort parse Serper's published-at hint to UTC datetime.

    Handles English relative hints, common Chinese relative hints, ISO 8601,
    and English month-name dates. Returns None if unparseable.
    """
    normalized = (text or "").strip()
    if not normalized:
        return None

    now = datetime.now(timezone.utc)
    lowered = normalized.casefold()
    relative = _parse_relative_date(lowered, now=now)
    if relative is not None:
        return relative

    chinese_relative = _parse_chinese_relative_date(normalized, now=now)
    if chinese_relative is not None:
        return chinese_relative

    iso = normalized.replace("Z", "+00:00")
    try:
        return _ensure_utc(datetime.fromisoformat(iso))
    except ValueError:
        pass

    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    for fmt in ("%Y年%m月%d日", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            parsed = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc)

    return None


def _parse_relative_date(text: str, *, now: datetime) -> datetime | None:
    text = text.replace("an ", "1 ", 1).replace("a ", "1 ", 1)
    relative_patterns = (
        (r"^(\d+)\s*(?:minute|minutes|min|mins)\s+ago$", "minutes"),
        (r"^(\d+)\s*(?:hour|hours|hr|hrs)\s+ago$", "hours"),
        (r"^(\d+)\s*(?:day|days)\s+ago$", "days"),
        (r"^(\d+)\s*(?:week|weeks)\s+ago$", "weeks"),
    )
    for pattern, unit in relative_patterns:
        match = re.fullmatch(pattern, text)
        if not match:
            continue
        count = int(match.group(1))
        if unit == "weeks":
            return now - timedelta(weeks=count)
        return now - timedelta(**{unit: count})
    if text in {"just now", "now"}:
        return now
    if text == "yesterday":
        return now - timedelta(days=1)
    if text == "today":
        return now
    return None


def _parse_chinese_relative_date(text: str, *, now: datetime) -> datetime | None:
    chinese_patterns = (
        (r"^(\d+)\s*分钟前$", "minutes"),
        (r"^(\d+)\s*小时前$", "hours"),
        (r"^(\d+)\s*天前$", "days"),
        (r"^(\d+)\s*周前$", "weeks"),
    )
    for pattern, unit in chinese_patterns:
        match = re.fullmatch(pattern, text)
        if not match:
            continue
        count = int(match.group(1))
        if unit == "weeks":
            return now - timedelta(weeks=count)
        return now - timedelta(**{unit: count})

    if text in {"刚刚", "今天"}:
        return now
    if text == "昨天":
        return now - timedelta(days=1)
    if text == "前天":
        return now - timedelta(days=2)
    for prefix, days_ago in (("今天", 0), ("昨天", 1), ("前天", 2)):
        if not text.startswith(prefix):
            continue
        parsed_time = _parse_chinese_clock(text.removeprefix(prefix).strip())
        if parsed_time is None:
            return now - timedelta(days=days_ago)
        parsed_date = (now - timedelta(days=days_ago)).date()
        return datetime.combine(parsed_date, parsed_time, tzinfo=timezone.utc)
    return None


def _parse_chinese_clock(text: str) -> time | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour=hour, minute=minute)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
