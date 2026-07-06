from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable

import requests


def _read_bocha_key_file() -> str:
    """Read .bocha_api_key from the repo root (fallback when BOCHA_API_KEY env is unset).
    Mirrors the .serper_api_key / .sglang_api_key file pattern (CLAUDE.md §5: secrets via
    env/key-file, never hardcoded or logged)."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / ".bocha_api_key"
        if candidate.is_file():
            try:
                value = candidate.read_text(encoding="utf-8").strip()
                if value:
                    return value
            except OSError:
                continue
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".bocha_api_key"
        if candidate.is_file():
            try:
                value = candidate.read_text(encoding="utf-8").strip()
                if value:
                    return value
            except OSError:
                continue
    return ""


class BochaSearchProvider:
    """Bocha (博查) web-search provider — China-native, AI-focused, returns a rich `summary`
    per result (not just snippets). Replaces Serper for content-rich web grounding.

    API: POST https://api.bochaai.com/v1/web-search
    Auth: Authorization: Bearer {key}; Content-Type: application/json
    Body: {query, freshness, summary, count}
    Response: {code, msg, data: {webPages: {value: [{name, url, snippet, summary, ...}]}}}
    """

    def __init__(
        self,
        *,
        endpoint: str = "https://api.bochaai.com/v1/web-search",
        api_key: str | None = None,
        freshness: str = "noLimit",
        count: int = 8,
        timeout: float = 30.0,
        session: requests.Session | Any | None = None,
        curl_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = (
            api_key or os.getenv("BOCHA_API_KEY", "").strip() or _read_bocha_key_file()
        ).strip()
        self.freshness = freshness
        self.count = count
        self.timeout = timeout
        self.session = session or requests.Session()
        self.curl_runner = curl_runner or subprocess.run
        self._disabled_reason: str | None = None
        if hasattr(self.session, "trust_env"):
            self.session.trust_env = False  # guard against proxy env pollution

    def build_payload(self, query: str) -> dict[str, Any]:
        return {
            "query": query,
            "freshness": self.freshness,
            "summary": True,  # request the rich per-result summary
            "count": self.count,
        }

    def build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize Bocha's {data: {webPages: {value: [...]}}} to the consumer-expected
        {organic: [{link, title, snippet, summary}]} shape (what _augment_with_web etc. read)."""
        data = payload.get("data") or {}
        web_pages = data.get("webPages") or {}
        values = web_pages.get("value") or []
        organic: list[dict[str, Any]] = []
        for item in values:
            organic.append(
                {
                    "link": item.get("url") or item.get("displayUrl") or "",
                    "url": item.get("url") or item.get("displayUrl") or "",
                    "title": item.get("name") or "",
                    "snippet": item.get("snippet") or "",
                    "summary": item.get("summary") or "",
                }
            )
        return {"organic": organic}

    def search(self, query: str, *, gl: str | None = None, hl: str | None = None) -> dict[str, Any]:
        """Search via Bocha. Best-effort: on failure returns {organic: []} (consumers fall
        through to local-only results — the add-web-augment graceful-degradation contract)."""
        if self._disabled_reason:
            return {"organic": []}
        if not self.api_key:
            self._disabled_reason = "missing bocha api key"
            return {"organic": []}
        try:
            response = self.session.post(
                self.endpoint,
                headers=self.build_headers(),
                json=self.build_payload(query),
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            # Graceful degradation: never propagate to the caller (add-web-augment contract).
            return {"organic": []}
        if str(payload.get("code", "")).strip() not in ("200", ""):
            return {"organic": []}
        return self._normalize(payload)
