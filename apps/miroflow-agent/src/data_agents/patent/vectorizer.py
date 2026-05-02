# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Embedding vectorizer for patent profiles."""

from __future__ import annotations

import json
import logging
import warnings
from collections.abc import Mapping
from typing import Any

import httpx

from ..storage.milvus_collections import (
    PATENT_PROFILES_COLLECTION,
    ensure_patent_profiles_collection,
)

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_URL = "http://100.64.0.27:18005/v1"
_DEFAULT_MODEL = "Qwen/Qwen3-Embedding-8B"
_VECTOR_DIM = 4096


class EmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_EMBEDDING_URL,
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
        model: str = _DEFAULT_MODEL,
    ) -> list[list[float]]:
        if not texts:
            return []
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(trust_env=False, timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/embeddings",
                json={"input": texts, "model": model},
                headers=headers,
            )
        response.raise_for_status()
        data = response.json()
        results = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in results]


class PatentVectorizer:
    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient,
        milvus_uri: str,
        collection_name: str = PATENT_PROFILES_COLLECTION,
    ) -> None:
        self.embedding_client = embedding_client
        self.collection_name = collection_name
        self._milvus_client = _create_milvus_client(milvus_uri)

    def ensure_collection(self) -> None:
        ensure_patent_profiles_collection(self._milvus_client)

    def vectorize_and_upsert(self, patents: list[Mapping[str, Any]]) -> int:
        rows: list[Mapping[str, Any]] = []
        texts: list[str] = []
        for patent in patents:
            patent_id = str(patent.get("patent_id") or patent.get("id") or "")
            text = _compose_patent_text(patent)
            if not patent_id.strip() or not text.strip():
                continue
            rows.append(patent)
            texts.append(text[:3800])

        if not rows:
            return 0

        vectors = self.embedding_client.embed_batch(texts)
        payload = [
            _patent_row_to_payload(row, vector)
            for row, vector in zip(rows, vectors, strict=False)
        ]
        if not payload:
            return 0

        self._milvus_client.upsert(
            collection_name=self.collection_name,
            data=payload,
        )
        return len(payload)

    def search_by_profile(self, query: str, *, limit: int = 10) -> list[str]:
        query_vector = self.embedding_client.embed_batch([query])[0]
        results = self._milvus_client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            anns_field="profile_vector",
            limit=limit,
            output_fields=["id"],
        )
        return [str(row.get("id", "")) for row in (results[0] if results else [])]


def _compose_patent_text(row: Mapping[str, Any]) -> str:
    title = str(row.get("title_clean") or row.get("title") or "").strip()
    abstract = str(row.get("abstract_clean") or row.get("abstract") or "").strip()
    technology_effect = str(row.get("technology_effect") or "").strip()

    parts: list[str] = []
    if title:
        parts.append(title)
    if abstract:
        parts.append(abstract[:1800])
    elif technology_effect:
        parts.append(technology_effect[:1800])

    return "\n".join(parts)


def _serialize_ipc_codes(value: object) -> str:
    if value is None:
        return "[]"
    if isinstance(value, str):
        return value[:512]
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)[:512]
    return json.dumps(value, ensure_ascii=False)[:512]


def _patent_row_to_payload(
    row: Mapping[str, Any],
    vector: list[float],
) -> dict[str, object]:
    return {
        "id": str(row.get("patent_id") or row.get("id") or "")[:64],
        "patent_number": str(row.get("patent_number") or "")[:64],
        "title": str(row.get("title_clean") or row.get("title") or "")[:512],
        "abstract": str(row.get("abstract_clean") or row.get("abstract") or "")[
            :2048
        ],
        "technology_effect": str(row.get("technology_effect") or "")[:1024],
        "patent_type": str(row.get("patent_type") or "")[:32],
        "ipc_codes": _serialize_ipc_codes(row.get("ipc_codes")),
        "profile_vector": vector,
    }


def _create_milvus_client(uri: str) -> Any:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        from pymilvus import MilvusClient

        return MilvusClient(uri=uri)
