from __future__ import annotations

import logging
from datetime import date
from typing import Any

import requests

from .base import NewsRecord, parse_news_payload

logger = logging.getLogger(__name__)


class CNStockConnector:
    """CNStock-backed company news connector."""

    def __init__(
        self,
        api_token: str,
        *,
        endpoint: str = "https://www.cnstock.com/api/news/search",
        session: Any | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_token = api_token.strip()
        self.endpoint = endpoint
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def fetch(self, company_unified_credit_code: str, since: date) -> list[NewsRecord]:
        if not self.api_token:
            logger.info("Skipping CNStock fetch: CNSTOCK_TOKEN is not set")
            return []

        params = {
            "keyword": company_unified_credit_code,
            "since": since.isoformat(),
            "token": self.api_token,
        }
        try:
            response = self.session.get(
                self.endpoint, params=params, timeout=self.timeout_seconds
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "CNStock fetch failed for %s: %s", company_unified_credit_code, exc
            )
            return []
        return parse_news_payload(body, company_id=company_unified_credit_code)
