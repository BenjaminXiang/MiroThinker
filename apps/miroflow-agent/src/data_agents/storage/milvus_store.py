from __future__ import annotations

import hashlib
import json
import math
import re
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message="pkg_resources is deprecated as an API.*",
        category=UserWarning,
        module="milvus_lite",
    )
    from pymilvus import MilvusClient

from src.data_agents.contracts import ReleasedObject

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{1,}|[\u3400-\u4DBF\u4E00-\u9FFF]")


class MilvusVectorStore:
    def __init__(
        self,
        *,
        uri: str,
        collection_name: str,
        dimension: int = 64,
    ) -> None:
        self.client = _create_milvus_client(uri)
        self.collection_name = collection_name
        self.dimension = dimension
        if not self.client.has_collection(collection_name):
            self.client.create_collection(
                collection_name=collection_name,
                dimension=dimension,
                primary_field_name="id",
                vector_field_name="vector",
                id_type="string",
                max_length=128,
                metric_type="COSINE",
            )

    def upsert_released_objects(self, objects: list[ReleasedObject]) -> None:
        if not objects:
            return
        self.client.upsert(
            collection_name=self.collection_name,
            data=[
                {
                    "id": item.id,
                    "vector": _embed_text(_vector_text(item), self.dimension),
                    "object_type": item.object_type,
                    "text": _vector_text(item),
                }
                for item in objects
            ],
        )

    def search_domain(self, domain: str, query: str, limit: int = 10) -> list[str]:
        query_vector = _embed_text(query, self.dimension)
        rows = self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            limit=max(limit * 4, limit),
            output_fields=["object_type"],
        )
        result_ids: list[str] = []
        for row in rows[0] if rows else []:
            if row.get("entity", {}).get("object_type") != domain:
                continue
            result_ids.append(str(row.get("id")))
            if len(result_ids) >= limit:
                break
        return result_ids


def _vector_text(item: ReleasedObject) -> str:
    return " ".join(
        [
            item.display_name,
            json.dumps(item.core_facts, ensure_ascii=False),
            json.dumps(item.summary_fields, ensure_ascii=False),
        ]
    )


def _create_milvus_client(uri: str) -> MilvusClient:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        return MilvusClient(uri=uri)


def _embed_text(text: str, dimension: int) -> list[float]:
    vector = [0.0] * dimension
    for token in _TOKEN_RE.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
