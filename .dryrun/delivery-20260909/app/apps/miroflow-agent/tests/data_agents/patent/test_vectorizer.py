from __future__ import annotations

from unittest.mock import MagicMock

from src.data_agents.patent import vectorizer as vectorizer_module
from src.data_agents.patent.vectorizer import (
    PatentVectorizer,
    _compose_patent_text,
    _VECTOR_DIM,
)
from src.data_agents.storage.milvus_collections import PATENT_PROFILES_COLLECTION


class _FakeMilvusClient:
    def __init__(self) -> None:
        self.upsert_calls: list[dict] = []

    def has_collection(self, collection_name: str) -> bool:
        return True

    def upsert(self, *, collection_name: str, data: list[dict]) -> None:
        self.upsert_calls.append(
            {"collection_name": collection_name, "data": list(data)}
        )


def _embedding_client() -> MagicMock:
    client = MagicMock()
    client.embed_batch.side_effect = (
        lambda texts, **_: [[0.2] * _VECTOR_DIM for _ in texts]
    )
    return client


def _patent_row(**overrides) -> dict:
    defaults = {
        "patent_id": "PAT-001",
        "patent_number": "CN123",
        "title_clean": "Autonomous obstacle avoidance",
        "abstract_clean": "A method for drone navigation.",
        "technology_effect": "Improves navigation safety.",
        "patent_type": "invention",
        "ipc_codes": ["G05D", "B64U"],
    }
    defaults.update(overrides)
    return defaults


def test_compose_patent_text_uses_title_and_abstract():
    text = _compose_patent_text(_patent_row())

    assert text.splitlines() == [
        "Autonomous obstacle avoidance",
        "A method for drone navigation.",
    ]


def test_compose_patent_text_falls_back_to_technology_effect():
    text = _compose_patent_text(
        _patent_row(abstract_clean="", technology_effect="x" * 2000)
    )

    assert text.splitlines()[0] == "Autonomous obstacle avoidance"
    assert len(text.splitlines()[-1]) == 1800


def test_vectorize_and_upsert_serializes_ipc_codes(monkeypatch):
    milvus = _FakeMilvusClient()
    monkeypatch.setattr(
        vectorizer_module,
        "_create_milvus_client",
        lambda uri: milvus,
    )
    embed = _embedding_client()
    vectorizer = PatentVectorizer(embedding_client=embed, milvus_uri="test.db")

    count = vectorizer.vectorize_and_upsert([_patent_row()])

    assert count == 1
    payload = milvus.upsert_calls[0]["data"][0]
    assert milvus.upsert_calls[0]["collection_name"] == PATENT_PROFILES_COLLECTION
    assert payload["id"] == "PAT-001"
    assert payload["ipc_codes"] == '["G05D", "B64U"]'
    assert payload["profile_vector"] == [0.2] * _VECTOR_DIM


def test_vectorize_and_upsert_skips_rows_without_semantic_text(monkeypatch):
    milvus = _FakeMilvusClient()
    monkeypatch.setattr(
        vectorizer_module,
        "_create_milvus_client",
        lambda uri: milvus,
    )
    embed = _embedding_client()
    vectorizer = PatentVectorizer(embedding_client=embed, milvus_uri="test.db")

    count = vectorizer.vectorize_and_upsert(
        [_patent_row(title_clean="", abstract_clean="", technology_effect="")]
    )

    assert count == 0
    embed.embed_batch.assert_not_called()
    assert milvus.upsert_calls == []


def test_ensure_collection_is_idempotent():
    vectorizer = PatentVectorizer(
        embedding_client=_embedding_client(),
        milvus_uri=":memory:",
    )

    vectorizer.ensure_collection()
    vectorizer.ensure_collection()

    assert vectorizer._milvus_client.has_collection(PATENT_PROFILES_COLLECTION)
