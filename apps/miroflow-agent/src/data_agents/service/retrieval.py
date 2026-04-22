from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from ..storage.milvus_collections import PAPER_CHUNKS_COLLECTION

logger = logging.getLogger(__name__)

_VALID_DOMAINS = {"professor", "paper"}
_PROFESSOR_COLLECTION = "professor_profiles"
_PROFESSOR_OUTPUT_FIELDS = [
    "id",
    "name",
    "institution",
    "department",
    "profile_summary",
    "homepage_url",
]
_PAPER_OUTPUT_FIELDS = [
    "chunk_id",
    "paper_id",
    "chunk_type",
    "segment_index",
    "year",
    "venue",
    "content_text",
]


@dataclass(frozen=True, slots=True)
class Evidence:
    object_type: str
    object_id: str
    score: float
    snippet: str
    source_url: str | None
    metadata: dict


class RetrievalCache(Protocol):
    def get(
        self,
        query: str,
        domains: tuple[str, ...],
        filters_key: str,
    ) -> list[Evidence] | None: ...

    def set(
        self,
        query: str,
        domains: tuple[str, ...],
        filters_key: str,
        evidence: list[Evidence],
    ) -> None: ...


class RetrievalService:
    def __init__(
        self,
        *,
        pg_conn_factory,
        milvus_client,
        embedding_client,
        reranker,
        cache: RetrievalCache | None = None,
    ) -> None:
        self._pg_conn_factory = pg_conn_factory
        self._milvus_client = milvus_client
        self._embedding_client = embedding_client
        self._reranker = reranker
        self._cache = cache

    @staticmethod
    def _compute_filters_key(filters: dict | None) -> str:
        items = sorted((filters or {}).items(), key=lambda item: item[0])
        payload = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def retrieve(
        self,
        query: str,
        *,
        domains: tuple[str, ...],
        filters: dict | None = None,
        candidate_limit: int = 30,
        final_top_k: int = 10,
    ) -> list[Evidence]:
        for domain in domains:
            if domain not in _VALID_DOMAINS:
                raise ValueError(f"Unsupported retrieval domain: {domain}")

        filters_key = self._compute_filters_key(filters)
        if self._cache is not None:
            cached = self._cache.get(query, domains, filters_key)
            if cached is not None:
                return cached

        if not domains:
            return []

        try:
            vectors = self._embedding_client.embed_batch([query])
        except Exception as exc:
            logger.warning("Embedding failed for retrieval query %r: %s", query, exc)
            return []

        with ThreadPoolExecutor(max_workers=len(domains)) as executor:
            futures: list[tuple[str, Future[list[dict]]]] = []
            for domain in domains:
                futures.append(
                    (
                        domain,
                        executor.submit(
                            self._search_domain,
                            domain=domain,
                            vectors=vectors,
                            candidate_limit=candidate_limit,
                        ),
                    )
                )

            raw_rows_by_domain: list[tuple[str, list[dict]]] = []
            for domain, future in futures:
                try:
                    raw_rows_by_domain.append((domain, future.result()))
                except Exception as exc:
                    logger.warning("Retrieval search failed for domain %s: %s", domain, exc)

        candidates: list[Evidence] = []
        for domain, rows in raw_rows_by_domain:
            for row in rows:
                evidence = self._row_to_evidence(domain, row)
                if evidence is not None:
                    candidates.append(evidence)

        if filters:
            candidates = self._apply_filters(candidates, filters)

        if not candidates:
            return []

        try:
            reranked = self._reranker.rerank(
                query,
                [candidate.snippet for candidate in candidates],
                top_n=final_top_k,
            )
        except Exception as exc:
            logger.warning("Rerank failed for retrieval query %r: %s", query, exc)
            results = sorted(
                candidates,
                key=lambda candidate: candidate.metadata.get("ann_score", candidate.score),
                reverse=True,
            )[:final_top_k]
        else:
            results = []
            for item in reranked:
                if item.index < 0 or item.index >= len(candidates):
                    logger.warning("Reranker returned out-of-range index %s", item.index)
                    continue
                candidate = candidates[item.index]
                results.append(
                    Evidence(
                        object_type=candidate.object_type,
                        object_id=candidate.object_id,
                        score=item.score,
                        snippet=candidate.snippet,
                        source_url=candidate.source_url,
                        metadata=candidate.metadata,
                    )
                )

        if self._cache is not None and results:
            self._cache.set(query, domains, filters_key, results)

        return results

    def _search_domain(
        self,
        *,
        domain: str,
        vectors: list[list[float]],
        candidate_limit: int,
    ) -> list[dict]:
        collection_name, output_fields = self._domain_search_config(domain)
        try:
            response = self._milvus_client.search(
                collection_name=collection_name,
                data=vectors,
                limit=candidate_limit,
                output_fields=output_fields,
            )
        except Exception as exc:
            logger.warning("Milvus search failed for domain %s: %s", domain, exc)
            return []

        if not response:
            return []
        first_query_rows = response[0]
        if not isinstance(first_query_rows, list):
            return []
        return first_query_rows

    def _row_to_evidence(self, domain: str, row: dict) -> Evidence | None:
        entity = dict(row.get("entity") or {})
        raw_score = float(row.get("distance", 0.0))

        if domain == "professor":
            object_id = str(entity.get("id") or row.get("id") or "")
            profile_summary = str(entity.get("profile_summary") or "")
            name = str(entity.get("name") or "")
            metadata = dict(entity)
            return Evidence(
                object_type="professor",
                object_id=object_id,
                score=raw_score,
                snippet=profile_summary[:500] or name,
                source_url=entity.get("homepage_url"),
                metadata=metadata,
            )

        if domain == "paper":
            object_id = str(entity.get("paper_id") or "")
            metadata = {
                "year": entity.get("year"),
                "venue": entity.get("venue"),
                "chunk_type": entity.get("chunk_type"),
                "chunk_id": entity.get("chunk_id") or row.get("id"),
                "ann_score": raw_score,
            }
            return Evidence(
                object_type="paper",
                object_id=object_id,
                score=raw_score,
                snippet=str(entity.get("content_text") or ""),
                source_url=None,
                metadata=metadata,
            )

        return None

    def _domain_search_config(self, domain: str) -> tuple[str, list[str]]:
        if domain == "professor":
            return _PROFESSOR_COLLECTION, _PROFESSOR_OUTPUT_FIELDS
        return PAPER_CHUNKS_COLLECTION, _PAPER_OUTPUT_FIELDS

    def _apply_filters(
        self,
        candidates: list[Evidence],
        filters: dict,
    ) -> list[Evidence]:
        filtered = candidates
        for key, value in filters.items():
            filtered = [
                candidate
                for candidate in filtered
                if candidate.metadata.get(key) == value
            ]
        return filtered
