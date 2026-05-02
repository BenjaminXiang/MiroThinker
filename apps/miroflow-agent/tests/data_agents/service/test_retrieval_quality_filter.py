from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.data_agents.providers.rerank import RerankResult
from src.data_agents.service.retrieval import RetrievalService
from src.data_agents.storage.milvus_collections import (
    COMPANY_PROFILES_COLLECTION,
    PAPER_CHUNKS_COLLECTION,
    PATENT_PROFILES_COLLECTION,
)

_PROFESSOR_COLLECTION = "professor_profiles"
_COLLECTION_BY_DOMAIN = {
    "professor": _PROFESSOR_COLLECTION,
    "paper": PAPER_CHUNKS_COLLECTION,
    "company": COMPANY_PROFILES_COLLECTION,
    "patent": PATENT_PROFILES_COLLECTION,
}
_IDS_BY_DOMAIN = {
    "professor": ("PROF-READY", "PROF-REVIEW"),
    "paper": ("PAPER-READY", "PAPER-REVIEW"),
    "company": ("COMP-READY", "COMP-REVIEW"),
    "patent": ("PAT-READY", "PAT-REVIEW"),
}
_TABLE_BY_DOMAIN = {
    "professor": "professor",
    "paper": "paper",
    "company": "company",
    "patent": "patent",
}


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _QualityStatusConn:
    def __init__(self, statuses: dict[str, dict[str, str]]) -> None:
        self.statuses = statuses
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, params: tuple[Any, ...]) -> _FakeResult:
        sql = " ".join(query.split()).lower()
        self.calls.append((sql, params))
        for domain, table_name in _TABLE_BY_DOMAIN.items():
            if f"from {table_name}" in sql:
                return _FakeResult(
                    [
                        {"object_id": object_id, "quality_status": status}
                        for object_id, status in self.statuses[domain].items()
                        if object_id in params
                    ]
                )
        raise AssertionError(f"Unexpected quality_status SQL: {sql}")


def _fake_embedding_client() -> MagicMock:
    client = MagicMock()
    client.embed_batch.return_value = [[0.1] * 4096]
    return client


def _fake_reranker() -> MagicMock:
    client = MagicMock()
    client.rerank.side_effect = lambda query, documents, top_n=None: [
        RerankResult(index=index, score=1.0 - index * 0.1, document=document)
        for index, document in enumerate(documents[: top_n or len(documents)])
    ]
    return client


def _fake_milvus(domain: str) -> MagicMock:
    client = MagicMock()
    rows = [_ann_row(domain, object_id, 0.9 - index * 0.1) for index, object_id in enumerate(_IDS_BY_DOMAIN[domain])]

    def _search(*, collection_name: str, data: list[list[float]], **kwargs):
        del data
        assert "filter" not in kwargs
        assert "expr" not in kwargs
        if collection_name == _COLLECTION_BY_DOMAIN[domain]:
            return [rows]
        return [[]]

    client.search.side_effect = _search
    return client


def _ann_row(domain: str, object_id: str, score: float) -> dict[str, Any]:
    if domain == "professor":
        return {
            "id": object_id,
            "entity": {
                "id": object_id,
                "name": object_id,
                "institution": "Test University",
                "profile_summary": f"Profile summary for {object_id}",
            },
            "distance": score,
        }
    if domain == "paper":
        return {
            "id": f"{object_id}:abstract:0",
            "entity": {
                "chunk_id": f"{object_id}:abstract:0",
                "paper_id": object_id,
                "chunk_type": "abstract",
                "content_text": f"Paper chunk for {object_id}",
            },
            "distance": score,
        }
    if domain == "company":
        return {
            "id": object_id,
            "entity": {
                "id": object_id,
                "name": object_id,
                "profile_summary": f"Company profile for {object_id}",
            },
            "distance": score,
        }
    return {
        "id": object_id,
        "entity": {
            "id": object_id,
            "patent_number": object_id,
            "title": f"Patent {object_id}",
            "abstract": f"Patent abstract for {object_id}",
        },
        "distance": score,
    }


def _service(domain: str) -> RetrievalService:
    ready_id, review_id = _IDS_BY_DOMAIN[domain]
    statuses = {
        item: {
            ready_id if item == domain else _IDS_BY_DOMAIN[item][0]: "ready",
            review_id if item == domain else _IDS_BY_DOMAIN[item][1]: "needs_review",
        }
        for item in _IDS_BY_DOMAIN
    }
    return RetrievalService(
        pg_conn_factory=lambda: _QualityStatusConn(statuses),
        milvus_client=_fake_milvus(domain),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )


@pytest.mark.parametrize("domain", ["professor", "paper", "company", "patent"])
def test_default_quality_status_filter_keeps_only_ready(
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
) -> None:
    monkeypatch.delenv("FILTER_BY_QUALITY_STATUS", raising=False)

    results = _service(domain).retrieve("query", domains=(domain,), final_top_k=10)

    assert [result.object_id for result in results] == [_IDS_BY_DOMAIN[domain][0]]
    assert results[0].metadata["quality_status"] == "ready"


@pytest.mark.parametrize("domain", ["professor", "paper", "company", "patent"])
def test_quality_status_filter_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
) -> None:
    monkeypatch.setenv("FILTER_BY_QUALITY_STATUS", "0")

    results = _service(domain).retrieve("query", domains=(domain,), final_top_k=10)

    assert [result.object_id for result in results] == list(_IDS_BY_DOMAIN[domain])
    assert [result.metadata["quality_status"] for result in results] == [
        "ready",
        "needs_review",
    ]
