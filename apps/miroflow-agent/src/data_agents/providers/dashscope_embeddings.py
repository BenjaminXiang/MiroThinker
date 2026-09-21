# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""DashScope-native text-embedding client (Alibaba's own shape, not OpenAI's).

DashScope's native embeddings route is not the OpenAI one: the request carries
``input: {texts: [...]}`` and the answer arrives under
``output.embeddings[].{text_index, embedding}``. The v2 candidate serving model
(``qwen3.7-text-embedding-flash`` on the MaaS gateway) is addressed only through
this shape, so the build/serving embedding authority needs a second HTTP client
beside the OpenAI-compatible one.

Transport failures are normalized here exactly as
``company.vectorizer.EmbeddingClient`` does for the OpenAI shape — a provider
that is *unreachable* becomes ``TimeoutError``/``ConnectionError``, the builtins
the lane-level fail-open hook understands. An *answer we cannot use* (a wrong
``text_index`` set, an empty vector) stays a validation failure and fails
closed.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

#: Appended to the bundle's ``base_url``. The bundle records the versioned
#: prefix (``https://maas.qianwenaiapi.com/api/v1``), the way the OpenAI bundle
#: records ``.../v1`` and the client appends ``/embeddings``.
_TEXT_EMBEDDINGS_PATH = "/services/embeddings/text-embedding/text-embedding"


class DashScopeTextEmbeddingClient:
    """One DashScope-native ``text-embedding`` call per ``embed_batch``."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def embed_batch(
        self,
        texts: list[str],
        *,
        model: str,
    ) -> list[list[float]]:
        """Embed ``texts`` in one call, returning vectors in input order.

        ``dimension`` is deliberately not sent: the candidate model answers 1024
        dimensions by default and rejects an unsupported ``dimension`` with HTTP
        400 (measured 2026-09-21), so the declared dimension is enforced on the
        response instead — a silent dimension change then fails closed rather
        than mixing vector spaces.
        """

        if not texts:
            return []
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client(trust_env=False, timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}{_TEXT_EMBEDDINGS_PATH}",
                    json={"model": model, "input": {"texts": texts}},
                    headers=headers,
                )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"embedding endpoint {self.base_url} did not answer in time"
            ) from exc
        except (httpx.HTTPError, OSError) as exc:
            raise ConnectionError(
                f"embedding endpoint {self.base_url} is unreachable"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ConnectionError(
                f"embedding endpoint {self.base_url} answered with a non-JSON body"
            ) from exc
        return _ordered_embeddings(data, expected=len(texts))


def _ordered_embeddings(document: Any, *, expected: int) -> list[list[float]]:
    """Read ``output.embeddings`` and restore input order through ``text_index``.

    DashScope does not promise the answer order, so every row is placed back at
    the index it names; a set that is not exactly ``0..n-1`` is a validation
    failure, never a silent misalignment of text and vector.
    """

    output = document.get("output") if isinstance(document, dict) else None
    rows = output.get("embeddings") if isinstance(output, dict) else None
    if not isinstance(rows, list) or len(rows) != expected:
        raise ValueError("embedding provider returned a different row count")
    ordered: dict[int, list[float]] = {}
    for row in rows:
        text_index = row.get("text_index") if isinstance(row, dict) else None
        if not isinstance(text_index, int) or isinstance(text_index, bool):
            raise ValueError("embedding provider returned a malformed embedding row")
        if text_index in ordered or not 0 <= text_index < expected:
            raise ValueError(
                "embedding provider returned a non-permutation text_index set"
            )
        embedding = row.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise ValueError("embedding provider returned an empty embedding")
        ordered[text_index] = embedding
    return [ordered[index] for index in range(expected)]


__all__ = ["DashScopeTextEmbeddingClient"]
