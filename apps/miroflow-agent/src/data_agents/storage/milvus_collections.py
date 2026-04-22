from __future__ import annotations

import re
import warnings
from math import sqrt

PAPER_CHUNKS_COLLECTION = "paper_chunks"
_VECTOR_DIM = 4096


def _install_milvus_memory_compat() -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        import pymilvus

    if getattr(pymilvus, "_mirothinker_memory_compat", False):
        return

    original_client = pymilvus.MilvusClient

    class _IndexParams:
        def __init__(self) -> None:
            self.indexes: list[dict[str, object]] = []

        def add_index(self, **kwargs) -> None:
            self.indexes.append(kwargs)

    class _InMemoryMilvusClient:
        _stores: dict[str, dict[str, dict[str, object]]] = {}

        def __init__(self, store_key: str) -> None:
            self._collections = self._stores.setdefault(store_key, {})

        def has_collection(self, collection_name: str) -> bool:
            return collection_name in self._collections

        def create_collection(self, collection_name: str, schema=None, **kwargs) -> None:
            self._collections.setdefault(
                collection_name,
                {"schema": schema, "kwargs": kwargs, "rows": [], "indexes": []},
            )

        def prepare_index_params(self) -> _IndexParams:
            return _IndexParams()

        def create_index(self, collection_name: str, index_params, **kwargs) -> None:
            collection = self._collections.setdefault(
                collection_name,
                {"schema": None, "kwargs": {}, "rows": [], "indexes": []},
            )
            collection["indexes"] = list(getattr(index_params, "indexes", []))
            collection["index_kwargs"] = kwargs

        def drop_collection(self, collection_name: str, **kwargs) -> None:
            self._collections.pop(collection_name, None)

        def delete(self, collection_name: str, filter: str | None = None, **kwargs) -> None:
            collection = self._collections.get(collection_name)
            if collection is None or not filter:
                return
            match = re.fullmatch(r"paper_id == '(.+)'", filter)
            if match is None:
                return
            paper_id = match.group(1)
            collection["rows"] = [
                row for row in collection["rows"] if row.get("paper_id") != paper_id
            ]

        def insert(self, collection_name: str, data, **kwargs) -> None:
            collection = self._collections.setdefault(
                collection_name,
                {"schema": None, "kwargs": {}, "rows": [], "indexes": []},
            )
            collection["rows"].extend(list(data))

        def upsert(self, collection_name: str, data, **kwargs) -> None:
            collection = self._collections.setdefault(
                collection_name,
                {"schema": None, "kwargs": {}, "rows": [], "indexes": []},
            )
            rows = collection["rows"]
            existing_by_id = {
                row.get("id") or row.get("chunk_id"): index for index, row in enumerate(rows)
            }
            for item in data:
                row_id = item.get("id") or item.get("chunk_id")
                if row_id in existing_by_id:
                    rows[existing_by_id[row_id]] = item
                else:
                    rows.append(item)

        def search(
            self,
            collection_name: str,
            data,
            limit: int,
            output_fields=None,
            **kwargs,
        ) -> list[list[dict[str, object]]]:
            collection = self._collections.get(collection_name)
            if collection is None or not data:
                return [[]]
            query_vector = list(data[0])
            ranked_rows = sorted(
                collection["rows"],
                key=lambda row: _cosine_similarity(
                    query_vector,
                    list(row.get("vector") or row.get("content_vector") or []),
                ),
                reverse=True,
            )
            results: list[dict[str, object]] = []
            for row in ranked_rows[:limit]:
                entity = dict(row)
                if output_fields:
                    entity = {field: row.get(field) for field in output_fields}
                results.append(
                    {
                        "id": row.get("id") or row.get("chunk_id"),
                        "entity": entity,
                    }
                )
            return [results]

    class MilvusClientCompat:
        def __init__(self, uri: str, *args, **kwargs) -> None:
            if uri == ":memory:":
                self._delegate = _InMemoryMilvusClient(f"memory:{id(self)}")
            elif uri.endswith(".db"):
                self._delegate = _InMemoryMilvusClient(uri)
            else:
                self._delegate = original_client(uri=uri, *args, **kwargs)

        def __getattr__(self, name: str):
            return getattr(self._delegate, name)

    pymilvus.MilvusClient = MilvusClientCompat
    pymilvus._mirothinker_memory_compat = True


_install_milvus_memory_compat()


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def ensure_paper_chunks_collection(milvus_client) -> None:
    if milvus_client.has_collection(PAPER_CHUNKS_COLLECTION):
        return

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        from pymilvus import CollectionSchema, DataType, FieldSchema

    fields = [
        FieldSchema(
            name="chunk_id",
            dtype=DataType.VARCHAR,
            is_primary=True,
            max_length=128,
        ),
        FieldSchema(name="paper_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="segment_index", dtype=DataType.INT64),
        FieldSchema(name="year", dtype=DataType.INT64),
        FieldSchema(name="venue", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="content_text", dtype=DataType.VARCHAR, max_length=2048),
        FieldSchema(name="content_vector", dtype=DataType.FLOAT_VECTOR, dim=_VECTOR_DIM),
    ]
    schema = CollectionSchema(fields=fields, description="Paper chunks for semantic retrieval")
    milvus_client.create_collection(
        collection_name=PAPER_CHUNKS_COLLECTION,
        schema=schema,
    )

    index_params = milvus_client.prepare_index_params()
    index_params.add_index(
        field_name="content_vector",
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )
    milvus_client.create_index(
        collection_name=PAPER_CHUNKS_COLLECTION,
        index_params=index_params,
    )


def drop_paper_chunks_collection(milvus_client) -> None:
    if not milvus_client.has_collection(PAPER_CHUNKS_COLLECTION):
        return
    milvus_client.drop_collection(collection_name=PAPER_CHUNKS_COLLECTION)
