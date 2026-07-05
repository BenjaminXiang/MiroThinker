from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from src.data_agents.providers.rerank import RerankResult
from src.data_agents.service.retrieval import RetrievalService


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _PaperQualityConn:
    def __init__(self, status_rows: dict[str, dict[str, Any]]) -> None:
        self.status_rows = status_rows
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, params: tuple[Any, ...]) -> _FakeResult:
        sql = " ".join(query.split()).lower()
        self.calls.append((sql, params))
        if "regexp_replace(lower(coalesce(title_clean" in sql:
            return _FakeResult([])
        if "from paper" in sql and "quality_status" in sql:
            return _FakeResult(
                [
                    {
                        "object_id": paper_id,
                        "quality_status": row["quality_status"],
                        "paper_has_rich_text": row["paper_has_rich_text"],
                    }
                    for paper_id, row in self.status_rows.items()
                    if paper_id in params
                ]
            )
        return _FakeResult([])


def _paper_ann_row(paper_id: str) -> dict[str, Any]:
    return {
        "id": f"{paper_id}:abstract:0",
        "entity": {
            "chunk_id": f"{paper_id}:abstract:0",
            "paper_id": paper_id,
            "chunk_type": "abstract",
            "segment_index": 0,
            "year": 2024,
            "venue": "TestConf",
            "content_text": f"Chunk content for {paper_id}",
        },
        "distance": 0.9,
    }


def test_vector_filter_admits_only_ready_and_partial_rich_text_papers() -> None:
    status_rows = {
        "PAPER-READY": {
            "quality_status": "ready",
            "paper_has_rich_text": False,
        },
        "PAPER-PARTIAL-RICH": {
            "quality_status": "partial",
            "paper_has_rich_text": True,
        },
        "PAPER-PARTIAL-TITLE-ONLY": {
            "quality_status": "partial",
            "paper_has_rich_text": False,
        },
        "PAPER-NEEDS-ENRICHMENT": {
            "quality_status": "needs_enrichment",
            "paper_has_rich_text": True,
        },
    }
    conn = _PaperQualityConn(status_rows)
    milvus = MagicMock()
    milvus.search.return_value = [[_paper_ann_row(paper_id) for paper_id in status_rows]]
    embed = MagicMock()
    embed.embed_batch.return_value = [[0.1] * 4096]
    reranker = MagicMock()
    reranker.rerank.side_effect = lambda _query, documents, top_n=None: [
        RerankResult(index=index, score=1.0 - index * 0.1, document=document)
        for index, document in enumerate(documents[: top_n or len(documents)])
    ]
    service = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=milvus,
        embedding_client=embed,
        reranker=reranker,
    )

    results = service.retrieve(
        "rich partial topic query",
        domains=("paper",),
        final_top_k=10,
        filter_by_quality_status=True,
    )

    assert [result.object_id for result in results] == [
        "PAPER-READY",
        "PAPER-PARTIAL-RICH",
    ]
    assert results[1].metadata["quality_status"] == "partial"
    assert results[1].metadata["paper_has_rich_text"] is True

