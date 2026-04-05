from __future__ import annotations

import os
from typing import Any

import requests


class WebSearchProvider:
    def __init__(
        self,
        *,
        endpoint: str = "https://google.serper.dev/search",
        api_key: str | None = None,
        gl: str = "cn",
        hl: str = "zh-cn",
        timeout: float = 30.0,
        session: requests.Session | Any | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key or os.getenv("SERPER_API_KEY", "").strip()
        self.gl = gl
        self.hl = hl
        self.timeout = timeout
        self.session = session or requests.Session()

    def build_payload(
        self,
        query: str,
        *,
        gl: str | None = None,
        hl: str | None = None,
    ) -> dict[str, str]:
        return {
            "q": query,
            "gl": gl or self.gl,
            "hl": hl or self.hl,
        }

    def build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-KEY": self.api_key,
        }

    def search(self, query: str, *, gl: str | None = None, hl: str | None = None) -> dict[str, Any]:
        response = self.session.post(
            self.endpoint,
            json=self.build_payload(query, gl=gl, hl=hl),
            headers=self.build_headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
