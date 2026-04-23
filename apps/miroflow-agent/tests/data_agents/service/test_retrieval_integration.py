"""M3 Unit 5 (deferred) — integration test for RetrievalService against Milvus-Lite.

Uses MilvusClient(uri=":memory:") with deterministic synthetic vectors so we
exercise the real Milvus ANN + filter + rerank plumbing without calling the
live Qwen3-Embedding-8B service.

This complements the 16 mocked unit tests in test_retrieval.py by proving
the schema + insert + search + metadata-round-trip compose correctly.
"""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock

from src.data_agents.providers.rerank import RerankResult
from src.data_agents.service.retrieval import Evidence, RetrievalService
from src.data_agents.storage.milvus_collections import (
    PAPER_CHUNKS_COLLECTION,
    ensure_paper_chunks_collection,
)


def _milvus_client():
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        from pymilvus import MilvusClient

        return MilvusClient(uri=":memory:")


def _chunk(
    chunk_id: str,
    paper_id: str,
    vector: list[float],
    *,
    year: int = 2023,
    venue: str = "NeurIPS",
    content_text: str = "Content text",
    chunk_type: str = "abstract",
    segment_index: int = 0,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "paper_id": paper_id,
        "chunk_type": chunk_type,
        "segment_index": segment_index,
        "year": year,
        "venue": venue,
        "content_text": content_text,
        "content_vector": vector,
    }


def _unit_vector_4096(component: int, value: float = 1.0) -> list[float]:
    """Sparse unit-ish vector with all zeros except one component set.

    Guarantees cosine distance between two such vectors is 1.0 if different
    components, 0.0 if same component — deterministic for test assertions.
    """
    vec = [0.0] * 4096
    vec[component % 4096] = value
    return vec


def test_retrieve_roundtrip_against_milvus_lite_returns_closest_chunk():
    """End-to-end: insert 3 known-distance chunks, query with vector closest
    to one, assert Evidence list has that chunk's paper_id as top_1."""
    milvus = _milvus_client()
    ensure_paper_chunks_collection(milvus)

    # Three chunks with distinct sparse vectors.
    chunks = [
        _chunk("c1", "paper_1", _unit_vector_4096(0), content_text="Chunk A"),
        _chunk("c2", "paper_2", _unit_vector_4096(1000), content_text="Chunk B"),
        _chunk("c3", "paper_3", _unit_vector_4096(2000), content_text="Chunk C"),
    ]
    milvus.insert(collection_name=PAPER_CHUNKS_COLLECTION, data=chunks)

    # Query vector identical to chunk c2's → cosine similarity 1.0.
    target_vector = _unit_vector_4096(1000)
    embed = MagicMock()
    embed.embed_batch.return_value = [target_vector]

    # Reranker returns the order Milvus gave us (identity).
    rerank = MagicMock()
    rerank.rerank.side_effect = lambda query, docs, top_n=None: [
        RerankResult(index=i, score=1.0 - i * 0.1, document=d)
        for i, d in enumerate(docs[: top_n or len(docs)])
    ]

    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
        embedding_client=embed,
        reranker=rerank,
    )
    results = svc.retrieve(
        "query",
        domains=("paper",),
        candidate_limit=10,
        final_top_k=3,
    )
    assert len(results) >= 1
    assert all(isinstance(r, Evidence) for r in results)
    # Top result should be paper_2 (the chunk whose vector exactly matches).
    assert results[0].object_id == "paper_2"
    # Chunk content_text was preserved as snippet.
    assert "Chunk B" in results[0].snippet


def test_retrieve_filter_respected_against_real_milvus():
    """Same roundtrip but with filters={'year': 2024} — only matching chunks pass."""
    milvus = _milvus_client()
    ensure_paper_chunks_collection(milvus)

    chunks = [
        _chunk("c_old", "paper_old", _unit_vector_4096(0), year=2020),
        _chunk("c_match", "paper_match", _unit_vector_4096(0, 0.99), year=2024),
        _chunk("c_newer", "paper_newer", _unit_vector_4096(0, 0.98), year=2024),
    ]
    milvus.insert(collection_name=PAPER_CHUNKS_COLLECTION, data=chunks)

    embed = MagicMock()
    embed.embed_batch.return_value = [_unit_vector_4096(0)]
    rerank = MagicMock()
    rerank.rerank.side_effect = lambda query, docs, top_n=None: [
        RerankResult(index=i, score=1.0 - i * 0.1, document=d)
        for i, d in enumerate(docs[: top_n or len(docs)])
    ]

    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
        embedding_client=embed,
        reranker=rerank,
    )
    results = svc.retrieve(
        "query",
        domains=("paper",),
        filters={"year": 2024},
        final_top_k=5,
    )
    # year=2020 paper should be filtered out.
    paper_ids = {r.object_id for r in results}
    assert "paper_old" not in paper_ids
    assert paper_ids.issubset({"paper_match", "paper_newer"})


def test_retrieve_empty_collection_returns_empty():
    """Freshly-ensured collection with zero rows → retrieve returns []."""
    milvus = _milvus_client()
    ensure_paper_chunks_collection(milvus)

    embed = MagicMock()
    embed.embed_batch.return_value = [_unit_vector_4096(0)]
    rerank = MagicMock()

    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
        embedding_client=embed,
        reranker=rerank,
    )
    results = svc.retrieve("query", domains=("paper",))
    assert results == []
    # Rerank never called on empty candidates.
    rerank.rerank.assert_not_called()


def test_ensure_then_drop_then_retrieve_empty_on_missing():
    """After drop_paper_chunks_collection, retrieve still graceful (empty result)."""
    from src.data_agents.storage.milvus_collections import drop_paper_chunks_collection

    milvus = _milvus_client()
    ensure_paper_chunks_collection(milvus)
    # Insert then drop.
    milvus.insert(
        collection_name=PAPER_CHUNKS_COLLECTION,
        data=[_chunk("c", "p", _unit_vector_4096(0))],
    )
    drop_paper_chunks_collection(milvus)

    embed = MagicMock()
    embed.embed_batch.return_value = [_unit_vector_4096(0)]
    rerank = MagicMock()

    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
        embedding_client=embed,
        reranker=rerank,
    )
    # Should not raise — RetrievalService catches Milvus errors and returns [].
    results = svc.retrieve("query", domains=("paper",))
    assert isinstance(results, list)
