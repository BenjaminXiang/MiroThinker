from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import Any
from urllib.parse import urlparse

import requests

from .base import NewsRecord

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.deepseek.com/v1/tools/search"
_NOISE_DOMAINS = (
    "baike.baidu.com",
    "tianyancha.com",
    "qcc.com",
    "qichacha.com",
    "aiqicha.baidu.com",
    "168report.com",
    "hengceresearch.cn",
    "zhaopin.com",
    "zhipin.com",
    "liepin.com",
    "51job.com",
    "docin.com",
    "wenku.baidu.com",
)
_NOISE_TITLE_WORDS = (
    "股价",
    "行情",
    "收盘",
    "涨",
    "跌",
    "招聘",
    "招标",
    "年报",
    "百科",
    "企查查",
    "天眼查",
    "研究报告",
    "行业报告",
    "市场规模",
    "职位",
    "工资",
)
_NEWS_PATH_MARKERS = (
    "news",
    "article",
    "expo",
    "press",
    "media",
    "finance",
    "content",
    "story",
    "detail",
)


def _as_utc_date(value: date) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(timezone.utc).date()
    return value


def _core_name(name: str) -> str:
    core = name.strip()
    for prefix in (
        "深圳市",
        "深圳",
        "广州市",
        "广州",
        "广东省",
        "广东",
        "北京市",
        "北京",
        "上海市",
        "上海",
    ):
        if core.startswith(prefix):
            core = core[len(prefix) :]
            break
    for suffix in ("股份有限公司", "有限责任公司", "有限公司", "公司"):
        if core.endswith(suffix):
            core = core[: -len(suffix)]
            break
    return core.strip()


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_noise(host: str, title: str) -> bool:
    if any(domain in host for domain in _NOISE_DOMAINS):
        return True
    return any(word in title for word in _NOISE_TITLE_WORDS)


def _is_news_like(host: str, path: str) -> bool:
    text = f"{host}{path}".lower()
    return any(marker in text for marker in _NEWS_PATH_MARKERS)


def _matches_name(name: str, core: str, text: str) -> bool:
    lowered = text.lower()
    if name.lower() in lowered:
        return True
    return len(core) >= 2 and core.lower() in lowered


class DeepSeekNewsConnector:
    """DeepSeek Search news connector.

    DeepSeek's Search API (``POST /v1/tools/search``) returns structured results
    with title/url/summary/date/authority/rerank_score. It is a web-search index,
    not a news-only feed, so the connector filters encyclopedias, company
    registries, reports and stock-quote pages, then requires a company-name match
    and (when a date is absent) a news-like URL.
    """

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = _ENDPOINT,
        timeout_seconds: float = 20.0,
        result_cap: int = 10,
        min_authority: int = 2,
        query_tail: str = "最新新闻 动态 -招聘 -招标",
        session: Any | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.result_cap = result_cap
        self.min_authority = min_authority
        self.query_tail = query_tail
        self.session = session or requests.Session()
        if hasattr(self.session, "trust_env"):
            self.session.trust_env = False

    def fetch(self, company_name: str, since: date) -> list[NewsRecord]:
        if not self.api_key:
            logger.info("Skipping DeepSeek fetch: DEEPSEEK_API_KEY not set")
            return []

        query = f"{company_name} {self.query_tail}".strip()[:128]
        ori_question = f"{company_name} 最近有什么新闻"[:128]
        try:
            response = self.session.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "count": self.result_cap,
                    "ori_question": ori_question,
                    "need_content": False,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - connector boundary
            logger.warning("DeepSeek search failed for %s: %s", company_name, exc)
            return []

        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []

        core = _core_name(company_name)
        since_start = datetime.combine(
            _as_utc_date(since), time.min, tzinfo=timezone.utc
        )
        now = datetime.now(timezone.utc)
        records: list[NewsRecord] = []
        seen_urls: set[str] = set()
        for item in results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url:
                continue
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            host = parsed.netloc.lower()
            if _is_noise(host, title):
                continue
            try:
                authority = int(item.get("authority"))
            except (TypeError, ValueError):
                authority = -1
            if authority < self.min_authority:
                continue
            published_at = _parse_date(item.get("date"))
            if published_at is not None:
                if published_at < since_start or published_at > now + timedelta(days=2):
                    continue
            elif not _is_news_like(host, parsed.path):
                continue
            summary = str(item.get("summary") or item.get("snippet") or "").strip()
            text = f"{title} {summary}"
            if not _matches_name(company_name, core, text):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            records.append(
                NewsRecord(
                    company_id=company_name,
                    source_url=url,
                    title=title,
                    summary=summary or None,
                    published_at=published_at,
                    raw_text=None,
                    source_adapter="deepseek-search",
                    extraction_diagnostics={
                        "authority": authority,
                        "rerank_score": item.get("rerank_score"),
                        "site_name": item.get("site_name"),
                        "query": query,
                    },
                )
            )
            if len(records) >= self.result_cap:
                break
        return records
