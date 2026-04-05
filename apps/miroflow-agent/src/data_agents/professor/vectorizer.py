# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Real embedding vectorizer for professor profiles.

Uses Qwen3-Embedding-8B (4096-dim) instead of hash-based embeddings.
Creates a professor-specific Milvus collection with dual vectors:
- profile_vector: for general semantic search on profile_summary
- direction_vector: for research direction precision search
"""
from __future__ import annotations

import json
import logging
import warnings
from typing import Any

import httpx

from .models import EnrichedProfessorProfile

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_URL = "http://172.18.41.222:18005/v1"
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
        response = httpx.post(
            f"{self.base_url}/embeddings",
            json={"input": texts, "model": model},
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        results = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in results]


class ProfessorVectorizer:
    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient,
        milvus_uri: str,
        collection_name: str = "professor_profiles",
    ) -> None:
        self.embedding_client = embedding_client
        self.collection_name = collection_name
        self._milvus_client = _create_milvus_client(milvus_uri)

    def ensure_collection(self) -> None:
        if self._milvus_client.has_collection(self.collection_name):
            return
        from pymilvus import CollectionSchema, DataType, FieldSchema

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="institution", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="department", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="research_directions", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="profile_summary", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="evaluation_summary", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="quality_status", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="profile_vector", dtype=DataType.FLOAT_VECTOR, dim=_VECTOR_DIM),
            FieldSchema(name="direction_vector", dtype=DataType.FLOAT_VECTOR, dim=_VECTOR_DIM),
        ]
        schema = CollectionSchema(fields=fields, description="Professor profiles with dual vectors")
        self._milvus_client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
        )
        index_params = self._milvus_client.prepare_index_params()
        index_params.add_index(
            field_name="profile_vector",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        index_params.add_index(
            field_name="direction_vector",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        self._milvus_client.create_index(
            collection_name=self.collection_name,
            index_params=index_params,
        )

    def vectorize_and_upsert(
        self,
        professors: list[tuple[str, EnrichedProfessorProfile, str]],
    ) -> int:
        if not professors:
            return 0

        profile_texts = [p.profile_summary for _, p, _ in professors]
        direction_texts = [
            "，".join(p.research_directions) if p.research_directions else p.profile_summary
            for _, p, _ in professors
        ]

        profile_vectors = self.embedding_client.embed_batch(profile_texts)
        direction_vectors = self.embedding_client.embed_batch(direction_texts)

        data = []
        for i, (prof_id, profile, quality_status) in enumerate(professors):
            data.append({
                "id": prof_id,
                "name": profile.name,
                "institution": profile.institution,
                "department": profile.department or "",
                "title": profile.title or "",
                "research_directions": json.dumps(
                    profile.research_directions, ensure_ascii=False
                ),
                "profile_summary": profile.profile_summary,
                "evaluation_summary": profile.evaluation_summary,
                "quality_status": quality_status,
                "profile_vector": profile_vectors[i],
                "direction_vector": direction_vectors[i],
            })

        self._milvus_client.upsert(
            collection_name=self.collection_name,
            data=data,
        )
        return len(data)

    def search_by_profile(
        self,
        query: str,
        *,
        limit: int = 10,
        institution: str | None = None,
    ) -> list[str]:
        return self._search(
            query=query,
            vector_field="profile_vector",
            limit=limit,
            institution=institution,
        )

    def search_by_direction(
        self,
        query: str,
        *,
        limit: int = 10,
        institution: str | None = None,
    ) -> list[str]:
        return self._search(
            query=query,
            vector_field="direction_vector",
            limit=limit,
            institution=institution,
        )

    def _search(
        self,
        *,
        query: str,
        vector_field: str,
        limit: int,
        institution: str | None,
    ) -> list[str]:
        query_vector = self.embedding_client.embed_batch([query])[0]
        filter_expr = f'institution == "{institution}"' if institution else ""
        results = self._milvus_client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            anns_field=vector_field,
            limit=limit,
            filter=filter_expr if filter_expr else None,
            output_fields=["id"],
        )
        return [str(row.get("id", "")) for row in (results[0] if results else [])]


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
