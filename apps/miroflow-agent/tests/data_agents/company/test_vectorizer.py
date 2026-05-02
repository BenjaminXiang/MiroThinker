from __future__ import annotations

from unittest.mock import MagicMock

from src.data_agents.company import vectorizer as vectorizer_module
from src.data_agents.company.vectorizer import (
    CompanyVectorizer,
    _compose_company_text,
    _VECTOR_DIM,
)
from src.data_agents.storage.milvus_collections import COMPANY_PROFILES_COLLECTION


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
        lambda texts, **_: [[0.1] * _VECTOR_DIM for _ in texts]
    )
    return client


def _company_row(**overrides) -> dict:
    defaults = {
        "company_id": "COMP-001",
        "canonical_name": "Example Robotics",
        "industry": "AI",
        "hq_city": "Shenzhen",
        "description": "Builds autonomy systems for drones.",
        "profile_summary": "Robotics company focused on embodied AI.",
        "technology_route_summary": "Uses multimodal perception and planning.",
    }
    defaults.update(overrides)
    return defaults


def test_compose_company_text_prefers_narrative_fields():
    text = _compose_company_text(_company_row())

    assert text.splitlines()[0] == "Example Robotics，AI，Shenzhen"
    assert "embodied AI" in text
    assert "multimodal perception" in text
    assert "drones" not in text


def test_compose_company_text_falls_back_to_description_and_truncates():
    text = _compose_company_text(
        _company_row(
            profile_summary=None,
            technology_route_summary=None,
            description="x" * 2000,
        )
    )

    assert text.endswith("x" * 1800)
    assert len(text.splitlines()[-1]) == 1800


def test_vectorize_and_upsert_writes_single_profile_vector(monkeypatch):
    milvus = _FakeMilvusClient()
    monkeypatch.setattr(
        vectorizer_module,
        "_create_milvus_client",
        lambda uri: milvus,
    )
    embed = _embedding_client()
    vectorizer = CompanyVectorizer(embedding_client=embed, milvus_uri="test.db")

    count = vectorizer.vectorize_and_upsert([_company_row()])

    assert count == 1
    assert embed.embed_batch.call_count == 1
    payload = milvus.upsert_calls[0]["data"][0]
    assert milvus.upsert_calls[0]["collection_name"] == COMPANY_PROFILES_COLLECTION
    assert payload["id"] == "COMP-001"
    assert payload["name"] == "Example Robotics"
    assert payload["profile_vector"] == [0.1] * _VECTOR_DIM


def test_vectorize_and_upsert_skips_rows_without_name(monkeypatch):
    milvus = _FakeMilvusClient()
    monkeypatch.setattr(
        vectorizer_module,
        "_create_milvus_client",
        lambda uri: milvus,
    )
    embed = _embedding_client()
    vectorizer = CompanyVectorizer(embedding_client=embed, milvus_uri="test.db")

    count = vectorizer.vectorize_and_upsert([_company_row(canonical_name="")])

    assert count == 0
    embed.embed_batch.assert_not_called()
    assert milvus.upsert_calls == []


def test_ensure_collection_is_idempotent():
    vectorizer = CompanyVectorizer(
        embedding_client=_embedding_client(),
        milvus_uri=":memory:",
    )

    vectorizer.ensure_collection()
    vectorizer.ensure_collection()

    assert vectorizer._milvus_client.has_collection(COMPANY_PROFILES_COLLECTION)
