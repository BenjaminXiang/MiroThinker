from __future__ import annotations

import logging
from datetime import date
from typing import Any

import requests

from .base import NewsRecord, parse_news_payload

logger = logging.getLogger(__name__)


class TushareConnector:
    """Tushare-backed company news connector.

    The connector keeps the external API surface isolated so tests can mock the
    HTTP session and production scripts can skip cleanly when no token exists.
    """

    def __init__(
        self,
        api_token: str,
        *,
        endpoint: str = "https://api.tushare.pro",
        session: Any | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_token = api_token.strip()
        self.endpoint = endpoint
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def fetch(self, company_unified_credit_code: str, since: date) -> list[NewsRecord]:
        if not self.api_token:
            logger.info("Skipping Tushare fetch: TUSHARE_TOKEN is not set")
            return []

        payload = {
            "api_name": "news",
            "token": self.api_token,
            "params": {
                "credit_code": company_unified_credit_code,
                "start_date": since.strftime("%Y%m%d"),
            },
            "fields": "datetime,title,content,url",
        }
        try:
            response = self.session.post(
                self.endpoint, json=payload, timeout=self.timeout_seconds
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Tushare fetch failed for %s: %s", company_unified_credit_code, exc
            )
            return []

        if isinstance(body, dict) and body.get("code") not in (None, 0):
            logger.warning(
                "Tushare returned code=%s for %s: %s",
                body.get("code"),
                company_unified_credit_code,
                body.get("msg"),
            )
            return []
        return parse_news_payload(body, company_id=company_unified_credit_code)
