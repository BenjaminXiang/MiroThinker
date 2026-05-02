from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.data_agents.professor import vectorizer as vectorizer_module
from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.vectorizer import ProfessorVectorizer, _VECTOR_DIM


class _FakeMilvusClient:
    def __init__(self) -> None:
        self.upsert_calls: list[dict] = []

    def has_collection(self, collection_name: str) -> bool:
        return True

    def upsert(self, *, collection_name: str, data: list[dict]) -> None:
        self.upsert_calls.append(
            {"collection_name": collection_name, "data": list(data)}
        )


def _profile(**overrides) -> EnrichedProfessorProfile:
    defaults = {
        "name": "张三",
        "institution": "南方科技大学",
        "department": "计算机系",
        "title": "教授",
        "research_directions": ["大语言模型", "RLHF"],
        "profile_summary": "张三教授专注于大语言模型研究",
        "profile_url": "https://example.com/prof",
        "roster_source": "https://example.com/roster",
        "extraction_status": "structured",
    }
    defaults.update(overrides)
    return EnrichedProfessorProfile(**defaults)


def _embedding_client() -> MagicMock:
    client = MagicMock()
    client.embed_batch.side_effect = (
        lambda texts: [[0.1] * _VECTOR_DIM for _ in texts]
    )
    return client


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        (
            {"h_index": 15, "citation_count": 708, "paper_count": 70},
            {"h_index": 15, "citation_count": 708, "paper_count": 70},
        ),
        (
            {"h_index": None, "citation_count": None, "paper_count": None},
            {"h_index": None, "citation_count": None, "paper_count": None},
        ),
    ],
)
def test_vectorize_and_upsert_carries_academic_metrics(
    monkeypatch: pytest.MonkeyPatch,
    metrics: dict[str, int | None],
    expected: dict[str, int | None],
) -> None:
    milvus = _FakeMilvusClient()
    monkeypatch.setattr(
        vectorizer_module,
        "_create_milvus_client",
        lambda uri: milvus,
    )
    vectorizer = ProfessorVectorizer(
        embedding_client=_embedding_client(),
        milvus_uri="test.db",
    )

    count = vectorizer.vectorize_and_upsert(
        [("PROF-001", _profile(**metrics), "ready")]
    )

    assert count == 1
    payload = milvus.upsert_calls[0]["data"][0]
    assert {
        "h_index": payload["h_index"],
        "citation_count": payload["citation_count"],
        "paper_count": payload["paper_count"],
    } == expected
