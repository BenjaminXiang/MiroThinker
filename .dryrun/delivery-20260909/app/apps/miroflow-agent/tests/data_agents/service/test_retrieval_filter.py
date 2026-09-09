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


def _prof_evidence(prof_id: str) -> Any:
    from src.data_agents.service.retrieval import Evidence

    return Evidence(
        object_type="professor",
        object_id=prof_id,
        score=0.9,
        snippet="",
        source_url=None,
        metadata={"retrieval_source": "professor_vector"},
    )


def test_filter_admits_non_ready_professors_except_low_confidence() -> None:
    # Decouple retrievability from publication-completeness for professors:
    # ready/needs_review/needs_enrichment are retrievable; only low_confidence
    # (non-person-name / profile-blob) is excluded.
    cases = {
        "PROF-READY": {"quality_status": "ready"},
        "PROF-NEEDS-REVIEW": {"quality_status": "needs_review"},
        "PROF-NEEDS-ENRICHMENT": {"quality_status": "needs_enrichment"},
        "PROF-LOW-CONFIDENCE": {"quality_status": "low_confidence"},
    }
    from src.data_agents.service.retrieval import RetrievalService

    admitted = [
        pid
        for pid, info in cases.items()
        if RetrievalService._filter_ready_only(_prof_evidence(pid), info)
    ]
    assert admitted == ["PROF-READY", "PROF-NEEDS-REVIEW", "PROF-NEEDS-ENRICHMENT"]
    assert "PROF-LOW-CONFIDENCE" not in admitted


def test_ready_boost_prefers_ready_professor_on_near_tie() -> None:
    # The ready-boost multiplies a ready professor's rerank-fusion term by (1+boost),
    # so on a near-tie a `ready` profile outranks a `needs_review` profile (counteracts
    # loose matches from less-polish profiles admitted by the decouple).
    from src.data_agents.providers.rerank import RerankResult
    from src.data_agents.service.retrieval import Evidence, _hybrid_rrf_select

    def _prof(pid: str, quality: str) -> Any:
        return Evidence(
            object_type="professor",
            object_id=pid,
            score=0.5,
            snippet=f"snippet {pid}",
            source_url=None,
            metadata={"quality_status": quality, "retrieval_source": "professor_vector"},
        )

    candidates = [_prof("PROF-NEEDS-REVIEW", "needs_review"), _prof("PROF-READY", "ready")]
    # needs_review is ranked MORE relevant by the reranker (rank 1), ready rank 2 —
    # yet the ready-boost should still put ready first on this near-tie.
    reranked = [
        RerankResult(index=0, score=0.9, document="snippet PROF-NEEDS-REVIEW"),
        RerankResult(index=1, score=0.8, document="snippet PROF-READY"),
    ]
    results = _hybrid_rrf_select(
        "topic query", candidates, reranked, final_top_k=2
    )
    assert results[0].object_id == "PROF-READY"

