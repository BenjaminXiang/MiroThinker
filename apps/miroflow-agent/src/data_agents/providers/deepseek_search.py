"""DeepSeek Search API client for the canonical-v2 web lane.

DeepSeek's ``POST /v1/tools/search`` returns a ranked ``results`` list with
title / url / summary / authority. It is the second web-lane leg on the
customer site: Bocha keeps the Chinese-web summary recall, DeepSeek supplies
the entity-accurate retrieval that Bocha misses for person names.

Error contract matches :class:`BochaSearchProvider`: transport/HTTP failures
raise ``RuntimeError`` so the lane's breaker and trace can classify them; a
successful empty result is ``{"organic": []}``.
"""

from __future__ import annotations

import os
from typing import Any

import requests


class DeepSeekSearchProvider:
    """Search via DeepSeek's tool-search endpoint."""

    def __init__(
        self,
        *,
        endpoint: str = "https://api.deepseek.com/v1/tools/search",
        api_key: str | None = None,
        count: int = 10,
        timeout: float = 8.0,
        session: requests.Session | Any | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = (api_key or os.getenv("DEEPSEEK_API_KEY", "")).strip()
        self.count = count
        self.timeout = timeout
        self.session = session or requests.Session()
        if hasattr(self.session, "trust_env"):
            self.session.trust_env = False

    def build_payload(self, query: str) -> dict[str, Any]:
        return {
            "query": query,
            "count": self.count,
            "need_content": False,
        }

    def build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        results = payload.get("results") if isinstance(payload, dict) else None
        organic: list[dict[str, Any]] = []
        if not isinstance(results, list):
            return {"organic": organic}
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            if not url or not title:
                continue
            snippet = str(item.get("summary") or item.get("snippet") or "").strip()
            organic.append(
                {
                    "link": url,
                    "url": url,
                    "title": title,
                    "snippet": snippet,
                    "summary": snippet,
                }
            )
        return {"organic": organic}

    def search(
        self, query: str, *, gl: str | None = None, hl: str | None = None
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("DeepSeek search error: missing api key")
        try:
            response = self.session.post(
                self.endpoint,
                headers=self.build_headers(),
                json=self.build_payload(query),
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - provider boundary
            raise RuntimeError(f"DeepSeek search transport error: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("DeepSeek search error: response is not an object")
        return self._normalize(payload)


__all__ = ["DeepSeekSearchProvider"]
