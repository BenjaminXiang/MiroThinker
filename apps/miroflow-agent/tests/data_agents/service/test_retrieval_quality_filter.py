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
    PROFESSOR_IDENTITY_PROFILES_COLLECTION,
)

_PROFESSOR_COLLECTION = PROFESSOR_IDENTITY_PROFILES_COLLECTION
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
    def __init__(
        self,
        statuses: dict[str, dict[str, str]],
        lifecycles: dict[str, str] | None = None,
    ) -> None:
        self.statuses = statuses
        self.lifecycles = lifecycles or {}
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, params: tuple[Any, ...]) -> _FakeResult:
        sql = " ".join(query.split()).lower()
        self.calls.append((sql, params))
        for domain, table_name in _TABLE_BY_DOMAIN.items():
            if f"from {table_name}" in sql:
                if domain == "professor" and "lifecycle_state" in sql:
                    return _FakeResult(
                        [
                            {
                                "object_id": object_id,
                                "quality_status": status,
                                "lifecycle_state": self.lifecycles.get(
                                    object_id, "active"
                                ),
                            }
                            for object_id, status in self.statuses[domain].items()
                            if object_id in params
                        ]
                    )
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

    query = "张三是谁" if domain == "professor" else "query"

    results = _service(domain).retrieve(query, domains=(domain,), final_top_k=10)

    ids = [result.object_id for result in results]
    ready_id, review_id = _IDS_BY_DOMAIN[domain]
    if domain == "professor":
        # Professor retrievability is decoupled from publication-completeness:
        # needs_review is admitted (only low_confidence is excluded). ready still
        # ranks first.
        assert set(ids) == {ready_id, review_id}
        assert ids[0] == ready_id
    else:
        assert ids == [ready_id]
        assert results[0].metadata["quality_status"] == "ready"


@pytest.mark.parametrize("domain", ["professor", "paper", "company", "patent"])
def test_quality_status_filter_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
) -> None:
    monkeypatch.setenv("FILTER_BY_QUALITY_STATUS", "0")

    query = "张三是谁" if domain == "professor" else "query"

    results = _service(domain).retrieve(query, domains=(domain,), final_top_k=10)

    assert [result.object_id for result in results] == list(_IDS_BY_DOMAIN[domain])
    assert [result.metadata["quality_status"] for result in results] == [
        "ready",
        "needs_review",
    ]


def test_professor_lifecycle_defaults_to_active_when_quality_filter_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILTER_BY_QUALITY_STATUS", "0")
    statuses = {
        domain: {
            _IDS_BY_DOMAIN[domain][0]: "ready",
            _IDS_BY_DOMAIN[domain][1]: "ready",
        }
        for domain in _IDS_BY_DOMAIN
    }
    lifecycles = {"PROF-READY": "active", "PROF-REVIEW": "archived"}
    service = RetrievalService(
        pg_conn_factory=lambda: _QualityStatusConn(statuses, lifecycles),
        milvus_client=_fake_milvus("professor"),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = service.retrieve(
        "张三是谁",
        domains=("professor",),
        final_top_k=10,
    )

    assert [result.object_id for result in results] == ["PROF-READY"]
    assert results[0].metadata["lifecycle_state"] == "active"


def test_professor_lifecycle_filter_can_request_archived_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILTER_BY_QUALITY_STATUS", "0")
    statuses = {
        domain: {
            _IDS_BY_DOMAIN[domain][0]: "ready",
            _IDS_BY_DOMAIN[domain][1]: "ready",
        }
        for domain in _IDS_BY_DOMAIN
    }
    lifecycles = {"PROF-READY": "active", "PROF-REVIEW": "archived"}
    service = RetrievalService(
        pg_conn_factory=lambda: _QualityStatusConn(statuses, lifecycles),
        milvus_client=_fake_milvus("professor"),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = service.retrieve(
        "张三是谁",
        domains=("professor",),
        filters={"lifecycle_state": "archived"},
        final_top_k=10,
    )

    assert [result.object_id for result in results] == ["PROF-REVIEW"]
    assert results[0].metadata["lifecycle_state"] == "archived"


def test_professor_lifecycle_filter_can_request_merged_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILTER_BY_QUALITY_STATUS", "0")
    statuses = {
        domain: {
            _IDS_BY_DOMAIN[domain][0]: "ready",
            _IDS_BY_DOMAIN[domain][1]: "ready",
        }
        for domain in _IDS_BY_DOMAIN
    }
    lifecycles = {
        "PROF-READY": "active",
        "PROF-REVIEW": "merged_to_other_school",
    }
    service = RetrievalService(
        pg_conn_factory=lambda: _QualityStatusConn(statuses, lifecycles),
        milvus_client=_fake_milvus("professor"),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = service.retrieve(
        "张三是谁",
        domains=("professor",),
        filters={"lifecycle_state": "merged_to_other_school"},
        final_top_k=10,
    )

    assert [result.object_id for result in results] == ["PROF-REVIEW"]
    assert results[0].metadata["lifecycle_state"] == "merged_to_other_school"


def test_quality_status_filter_argument_overrides_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FILTER_BY_QUALITY_STATUS", raising=False)

    results = _service("paper").retrieve(
        "query",
        domains=("paper",),
        final_top_k=10,
        filter_by_quality_status=False,
    )

    assert [result.object_id for result in results] == list(_IDS_BY_DOMAIN["paper"])
    assert [result.metadata["quality_status"] for result in results] == [
        "ready",
        "needs_review",
    ]


def test_rejected_candidates_are_never_returned_when_filter_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FILTER_BY_QUALITY_STATUS", "0")
    domain = "paper"
    ready_id, review_id = _IDS_BY_DOMAIN[domain]
    statuses = {
        item: {
            ready_id if item == domain else _IDS_BY_DOMAIN[item][0]: "ready",
            review_id if item == domain else _IDS_BY_DOMAIN[item][1]: "rejected",
        }
        for item in _IDS_BY_DOMAIN
    }
    service = RetrievalService(
        pg_conn_factory=lambda: _QualityStatusConn(statuses),
        milvus_client=_fake_milvus(domain),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = service.retrieve(
        "query",
        domains=(domain,),
        final_top_k=10,
        filter_by_quality_status=False,
    )

    assert [result.object_id for result in results] == [ready_id]
    assert all(result.metadata["quality_status"] != "rejected" for result in results)
