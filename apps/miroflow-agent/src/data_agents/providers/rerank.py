from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from .local_api_key import load_local_api_key

logger = logging.getLogger(__name__)

_DEFAULT_RERANK_URL = "http://100.64.0.27:18006/v1"
_DEFAULT_MODEL = "qwen3-reranker-8b"
_DEFAULT_TIMEOUT = 60.0


@dataclass(frozen=True, slots=True)
class RerankResult:
    index: int
    score: float
    document: str


class RerankerClient:
    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_RERANK_URL,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        timeout: float = _DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = load_local_api_key() if api_key is None else api_key
        self.model = model
        self.timeout = timeout
        self._owns_http = client is None
        self._http = client or httpx.Client(timeout=timeout, trust_env=False)

    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
    ) -> list[RerankResult]:
        if not documents:
            return []
        if not self.api_key:
            raise RuntimeError(
                "RerankerClient: no API key. Set API_KEY env or .sglang_api_key file."
            )

        effective_top_n = (
            len(documents) if top_n is None else min(top_n, len(documents))
        )
        response = self._http.post(
            f"{self.base_url}/rerank",
            json={
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": effective_top_n,
            },
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()

        results: list[RerankResult] = []
        raw_results = response.json()["results"]
        for item in raw_results:
            index = item["index"]
            document = item.get("document")
            if isinstance(document, dict):
                text = document.get("text") or documents[index]
            elif isinstance(document, str):
                text = document
            else:
                text = documents[index]
            results.append(
                RerankResult(
                    index=index,
                    score=item["relevance_score"],
                    document=text,
                )
            )

        if any(
            results[position].score > results[position - 1].score
            for position in range(1, len(results))
        ):
            logger.warning(
                "Reranker server returned results out of descending score order."
            )

        return results

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> RerankerClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
