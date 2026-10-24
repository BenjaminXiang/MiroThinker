"""Ordered web-search fallback for non-serving consumers.

The canonical-v2 chat lane composes Bocha + DeepSeek directly. This adapter is
for the professor enrichment path: try DeepSeek first (entity-accurate, domestic
billing), then Bocha (rich Chinese summaries), then Serper (legacy, only when a
key is still configured). A provider that errors or returns no organic results
falls through to the next one.
"""

from __future__ import annotations

import os
from typing import Any


def resolve_deepseek_search_key() -> str:
    """The DeepSeek key for search, independent of the chat model profile."""

    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    try:
        from src.data_agents.canonical_v2.managed_secrets import (
            ManagedSecretsStore,
            default_secrets_path,
        )

        return str(
            ManagedSecretsStore(path=default_secrets_path())
            .raw()
            .get("llm.api_key", "")
            or ""
        ).strip()
    except Exception:  # noqa: BLE001 - optional credential
        return ""


class FallbackWebSearchProvider:
    def __init__(self, *, providers: tuple[Any, ...]) -> None:
        if not providers:
            raise ValueError("at least one web-search provider is required")
        self._providers = providers
        self.api_key = next(
            (
                str(getattr(provider, "api_key", "") or "")
                for provider in providers
                if getattr(provider, "api_key", "")
            ),
            "",
        )

    def search(
        self, query: str, *, gl: str | None = None, hl: str | None = None
    ) -> dict[str, Any]:
        for provider in self._providers:
            try:
                payload = provider.search(query, gl=gl, hl=hl)
            except TypeError:
                try:
                    payload = provider.search(query)
                except Exception:  # noqa: BLE001 - fall through
                    continue
            except Exception:  # noqa: BLE001 - fall through
                continue
            if not isinstance(payload, dict):
                continue
            organic = payload.get("organic") or payload.get("results") or []
            if organic:
                return {"organic": organic}
        return {"organic": []}


__all__ = ["FallbackWebSearchProvider", "resolve_deepseek_search_key"]
