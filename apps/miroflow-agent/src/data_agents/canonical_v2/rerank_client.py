"""Remote relevance reranker for the serving selection stage.

The serving rerank stage orders the eligible fused candidates with a
deterministic local/current-Web bucket policy. This module adds an optional
relevance model on top of that policy: candidate documents (display name plus
evidence text) are scored by an OpenAI-compatible ``/v1/rerank`` endpoint
(vLLM serving ``qwen3-reranker-8b``), and the returned scores reorder the
candidates inside each policy bucket.

The adapter is fail-open by construction: an unconfigured endpoint, transport
error, timeout, or malformed response raises :class:`RerankUnavailable` and the
caller keeps the deterministic ordering. Logs carry endpoint, model, document
count, and elapsed time only — never the query text, the candidate text, or the
credential.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache
import json
import logging
import math
import os
from pathlib import Path
from time import monotonic
from typing import Any
import urllib.error
import urllib.request

_LOGGER = logging.getLogger(__name__)

ENV_BASE_URL = "CANONICAL_V2_RERANK_BASE_URL"
ENV_MODEL = "CANONICAL_V2_RERANK_MODEL"
ENV_API_KEY = "CANONICAL_V2_RERANK_API_KEY"
ENV_API_KEY_FILE = "CANONICAL_V2_RERANK_API_KEY_FILE"
ENV_TIMEOUT_SECONDS = "CANONICAL_V2_RERANK_TIMEOUT_SECONDS"
ENV_MAX_DOCUMENTS = "CANONICAL_V2_RERANK_MAX_DOCUMENTS"
ENV_DEBUG = "CANONICAL_V2_RERANK_DEBUG"

DEFAULT_MODEL = "qwen3-reranker-8b"
DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_MAX_DOCUMENTS = 128

_RERANK_PATH = "/v1/rerank"


class RerankUnavailable(RuntimeError):
    """The relevance model could not produce a complete score vector."""


def _post_json(
    url: str,
    payload: dict[str, Any],
    api_key: str,
    timeout_seconds: float,
) -> Any:
    """POST one JSON body and return the decoded response (test seam)."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
    return json.loads(body)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        _LOGGER.warning("%s is not a number; using %s", name, default)
        return default
    if not math.isfinite(value) or value <= 0:
        _LOGGER.warning("%s must be positive and finite; using %s", name, default)
        return default
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        _LOGGER.warning("%s is not an integer; using %s", name, default)
        return default
    if value <= 0:
        _LOGGER.warning("%s must be positive; using %s", name, default)
        return default
    return value


def _resolve_api_key() -> str:
    """Read the endpoint credential from env or an approved key file."""
    inline = os.environ.get(ENV_API_KEY)
    if inline and inline.strip():
        return inline.strip()
    key_file = os.environ.get(ENV_API_KEY_FILE)
    if key_file and key_file.strip():
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            _LOGGER.warning("rerank key file is unreadable: %s", type(exc).__name__)
            return ""
    return ""


class RemoteReranker:
    """Score candidate documents against one query with a relevance model."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str = DEFAULT_MODEL,
        api_key: str = "",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_documents: int = DEFAULT_MAX_DOCUMENTS,
        debug: bool = False,
        transport: Any = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_documents = max_documents
        self._debug = debug
        self._transport = transport if transport is not None else _post_json

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def max_documents(self) -> int:
        return self._max_documents

    @property
    def endpoint(self) -> str:
        return f"{self._base_url}{_RERANK_PATH}"

    def score(self, query: str, documents: Sequence[str]) -> tuple[float, ...]:
        """Return one relevance score per document, aligned by position.

        Raises :class:`RerankUnavailable` on any transport, protocol, or
        completeness failure so the caller can keep its deterministic order.
        """
        if not documents:
            return ()
        if len(documents) > self._max_documents:
            raise RerankUnavailable(
                f"document count {len(documents)} exceeds the {self._max_documents} cap"
            )
        payload = {
            "model": self._model,
            "query": query,
            "documents": list(documents),
            "top_n": len(documents),
        }
        started = monotonic()
        try:
            response = self._transport(
                self.endpoint,
                payload,
                self._api_key,
                self._timeout_seconds,
            )
        except RerankUnavailable:
            raise
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise RerankUnavailable(f"rerank request failed: {type(exc).__name__}") from exc
        elapsed_ms = (monotonic() - started) * 1000
        scores = self._parse_scores(response, len(documents))
        if self._debug:
            _LOGGER.info(
                "[rerank] endpoint=%s model=%s documents=%d elapsed_ms=%.0f",
                self.endpoint,
                self._model,
                len(documents),
                elapsed_ms,
            )
        return scores

    def _parse_scores(self, response: Any, expected: int) -> tuple[float, ...]:
        if not isinstance(response, Mapping):
            raise RerankUnavailable("rerank response is not an object")
        results = response.get("results")
        if not isinstance(results, list) or not results:
            raise RerankUnavailable("rerank response carries no results")
        scores: list[float | None] = [None] * expected
        for item in results:
            if not isinstance(item, Mapping):
                raise RerankUnavailable("rerank result is not an object")
            index = item.get("index")
            value = item.get("relevance_score")
            if not isinstance(index, int) or isinstance(index, bool):
                raise RerankUnavailable("rerank result lacks an integer index")
            if not 0 <= index < expected:
                raise RerankUnavailable("rerank result index is out of range")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RerankUnavailable("rerank result lacks a numeric score")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise RerankUnavailable("rerank result score is not finite")
            if scores[index] is not None:
                raise RerankUnavailable("rerank response repeats a document index")
            scores[index] = numeric
        if any(score is None for score in scores):
            raise RerankUnavailable("rerank response is missing document scores")
        return tuple(score for score in scores if score is not None)


@lru_cache(maxsize=1)
def configured_reranker() -> RemoteReranker | None:
    """Return the process-wide reranker for the current env, or None."""
    base_url = (os.environ.get(ENV_BASE_URL) or "").strip()
    if not base_url:
        return None
    return RemoteReranker(
        base_url=base_url,
        model=(os.environ.get(ENV_MODEL) or "").strip() or DEFAULT_MODEL,
        api_key=_resolve_api_key(),
        timeout_seconds=_env_float(ENV_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS),
        max_documents=_env_int(ENV_MAX_DOCUMENTS, DEFAULT_MAX_DOCUMENTS),
        debug=(os.environ.get(ENV_DEBUG) or "").strip() not in {"", "0", "false"},
    )


__all__ = [
    "DEFAULT_MAX_DOCUMENTS",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "ENV_API_KEY",
    "ENV_API_KEY_FILE",
    "ENV_BASE_URL",
    "ENV_DEBUG",
    "ENV_MAX_DOCUMENTS",
    "ENV_MODEL",
    "ENV_TIMEOUT_SECONDS",
    "RemoteReranker",
    "RerankUnavailable",
    "configured_reranker",
]
