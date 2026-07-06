from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src.data_agents.providers.bocha_search import BochaSearchProvider
from src.data_agents.providers.web_search import WebSearchProvider

logger = logging.getLogger(__name__)


class CompositeWebSearchProvider:
    """Dual web-search provider: runs Bocha + Serper concurrently, merges + deduplicates by URL.

    Bocha provides rich Chinese `summary` per result (content depth for knowledge QA);
    Serper provides Google-backed results (brand/entity coverage that Bocha's Baidu index misses).
    Both run concurrently (ThreadPoolExecutor, ~2-3s wall-clock = max of the two, within the 6s SLO).
    Graceful: if one provider fails, the other's results are returned unchanged.
    """

    def __init__(
        self,
        *,
        bocha: BochaSearchProvider | None = None,
        serper: WebSearchProvider | None = None,
    ) -> None:
        self._bocha = bocha or BochaSearchProvider()
        self._serper = serper or WebSearchProvider()
        # api_key is truthy if EITHER provider has a key (the _get_web_search_provider_or_none gate)
        self.api_key = (self._bocha.api_key or self._serper.api_key).strip()

    @staticmethod
    def _safe_search(provider: Any, query: str) -> list[dict[str, Any]]:
        """Run one provider's search; return [] on any failure (graceful degradation)."""
        try:
            result = provider.search(query)
            if isinstance(result, dict):
                return result.get("organic") or result.get("results") or []
            return []
        except Exception as exc:  # noqa: BLE001 - best-effort web search
            logger.warning("Web search provider %s failed for %r: %s", type(provider).__name__, query, exc)
            return []

    def search(self, query: str, *, gl: str | None = None, hl: str | None = None) -> dict[str, Any]:
        """Run both providers concurrently, merge + dedup by URL. Returns {organic: [...]}."""
        with ThreadPoolExecutor(max_workers=2) as executor:
            bocha_future = executor.submit(self._safe_search, self._bocha, query)
            serper_future = executor.submit(self._safe_search, self._serper, query)
            bocha_results = bocha_future.result()
            serper_results = serper_future.result()

        merged = self._merge_dedup(bocha_results, serper_results)
        return {"organic": merged}

    @staticmethod
    def _merge_dedup(
        bocha_results: list[dict[str, Any]],
        serper_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge two result lists, deduplicating by URL. Prefers Bocha (richer summaries)
        for duplicates; appends Serper-only results after."""
        seen_urls: set[str] = set()
        merged: list[dict[str, Any]] = []

        # Bocha first (richer summaries — keep these for dup URLs)
        for item in bocha_results:
            url = (item.get("link") or item.get("url") or "").lower().strip().rstrip("/")
            if url:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
            merged.append(item)

        # Serper results not already seen (Google-backed entity coverage)
        for item in serper_results:
            url = (item.get("link") or item.get("url") or "").lower().strip().rstrip("/")
            if url:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
            merged.append(item)

        return merged
