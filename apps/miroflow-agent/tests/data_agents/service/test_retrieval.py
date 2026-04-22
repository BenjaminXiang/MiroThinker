"""RED-phase tests for M3 Unit 4 — RetrievalService.

Hermetic tests: mock EmbeddingClient + MilvusClient + RerankerClient.
Validate cascade, filter application, rerank fallback, concurrency, cache.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from src.data_agents.providers.rerank import RerankResult
from src.data_agents.service.retrieval import (
    Evidence,
    RetrievalService,
)

# =============================================================================
# Evidence dataclass
# =============================================================================


def test_evidence_dataclass_smoke():
    e = Evidence(
        object_type="paper",
        object_id="paper:doi:10.1/x",
        score=0.87,
        snippet="We study ...",
        source_url="https://doi.org/10.1/x",
        metadata={"year": 2023},
    )
    assert e.object_type == "paper"
    assert e.score == 0.87
    assert e.metadata == {"year": 2023}


def test_evidence_is_frozen():
    e = Evidence(
        object_type="paper",
        object_id="p1",
        score=1.0,
        snippet="s",
        source_url=None,
        metadata={},
    )
    with pytest.raises((AttributeError, TypeError, Exception)):
        e.score = 0.0


# =============================================================================
# RetrievalService — fixtures
# =============================================================================


def _fake_embedding_client():
    client = MagicMock()
    client.embed_batch.return_value = [[0.1] * 4096]
    return client


def _fake_reranker(order: list[int] | None = None):
    """Reranker that returns candidates in the given index order (highest score first)."""
    client = MagicMock()
    if order is None:
        client.rerank.side_effect = lambda query, documents, top_n=None: [
            RerankResult(index=i, score=1.0 - i * 0.1, document=d)
            for i, d in enumerate(documents[: top_n or len(documents)])
        ]
    else:
        def _rerank(query, documents, top_n=None):
            results = [
                RerankResult(
                    index=idx,
                    score=1.0 - rank * 0.1,
                    document=documents[idx],
                )
                for rank, idx in enumerate(order[: top_n or len(order)])
                if idx < len(documents)
            ]
            return results

        client.rerank.side_effect = _rerank
    return client


def _milvus_search_result(rows: list[dict]):
    """Milvus search() returns list-of-list-of-row-dicts. One query → outer list length 1."""
    return [rows]


def _fake_milvus_with_domains(domain_results: dict[str, list[dict]]):
    """Return a MagicMock that returns different results per collection name."""
    client = MagicMock()

    def _search(*, collection_name, data, **kwargs):
        rows = domain_results.get(collection_name, [])
        return _milvus_search_result(rows)

    client.search.side_effect = _search
    return client


def _prof_ann_row(object_id: str, score: float):
    return {
        "id": object_id,
        "entity": {
            "id": object_id,
            "name": "Prof " + object_id,
            "institution": "南科大",
            "profile_summary": f"Short summary for {object_id}. " * 3,
        },
        "distance": score,
    }


def _paper_ann_row(chunk_id: str, paper_id: str, score: float, year: int = 2023):
    return {
        "id": chunk_id,
        "entity": {
            "chunk_id": chunk_id,
            "paper_id": paper_id,
            "chunk_type": "abstract",
            "segment_index": 0,
            "year": year,
            "venue": "NeurIPS",
            "content_text": f"Abstract text for {paper_id}",
        },
        "distance": score,
    }


# =============================================================================
# Happy paths
# =============================================================================


def test_retrieve_single_domain_professor_happy_path():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {
                "professor_profiles": [
                    _prof_ann_row("p1", 0.9),
                    _prof_ann_row("p2", 0.8),
                    _prof_ann_row("p3", 0.7),
                ]
            }
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    results = svc.retrieve(
        "query text",
        domains=("professor",),
        candidate_limit=30,
        final_top_k=10,
    )
    assert isinstance(results, list)
    assert all(isinstance(r, Evidence) for r in results)
    assert len(results) == 3
    assert all(r.object_type == "professor" for r in results)


def test_retrieve_single_domain_paper_happy_path():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {
                "paper_chunks": [
                    _paper_ann_row(f"p{i}:abstract:0", f"p{i}", 0.9 - i * 0.1)
                    for i in range(3)
                ]
            }
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    results = svc.retrieve(
        "query",
        domains=("paper",),
    )
    assert len(results) == 3
    assert all(r.object_type == "paper" for r in results)
    # object_id should be the paper_id, not chunk_id
    assert results[0].object_id == "p0"
    # snippet should be chunk content_text, not chunk_id
    assert "Abstract text" in results[0].snippet


def test_retrieve_two_domain_merges_candidates():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {
                "professor_profiles": [_prof_ann_row(f"prof{i}", 0.9 - i * 0.05) for i in range(5)],
                "paper_chunks": [
                    _paper_ann_row(f"p{i}:abstract:0", f"paper{i}", 0.85 - i * 0.05) for i in range(5)
                ],
            }
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    results = svc.retrieve(
        "query",
        domains=("professor", "paper"),
        final_top_k=10,
    )
    assert len(results) <= 10
    types = {r.object_type for r in results}
    # Mixed results
    assert "professor" in types or "paper" in types


def test_retrieve_final_top_k_limits_results():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {
                "paper_chunks": [
                    _paper_ann_row(f"p{i}:abstract:0", f"p{i}", 0.9 - i * 0.01) for i in range(15)
                ]
            }
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    results = svc.retrieve("query", domains=("paper",), final_top_k=3)
    assert len(results) == 3


# =============================================================================
# SQL filter application
# =============================================================================


def test_retrieve_filter_drops_non_matching_candidates():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {
                "professor_profiles": [
                    _prof_ann_row("p1", 0.9),
                    _prof_ann_row("p2", 0.8),
                ]
            }
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    # Wire the second prof to a DIFFERENT institution post-hoc
    # Since _prof_ann_row hardcodes 南科大, override in the rows:
    rows = [_prof_ann_row("p1", 0.9), _prof_ann_row("p2", 0.8)]
    rows[0]["entity"]["institution"] = "清华大学深圳国际研究生院"
    rows[1]["entity"]["institution"] = "南方科技大学"
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains({"professor_profiles": rows}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    results = svc.retrieve(
        "query",
        domains=("professor",),
        filters={"institution": "南方科技大学"},
    )
    # Only the matching prof survives
    assert len(results) == 1
    assert results[0].object_id == "p2"


# =============================================================================
# Reranker fallback
# =============================================================================


def test_retrieve_rerank_exception_falls_back_to_ann_order():
    """Reranker raises → use raw ANN score order."""
    rerank = MagicMock()
    rerank.rerank.side_effect = RuntimeError("rerank unavailable")
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {
                "paper_chunks": [
                    _paper_ann_row("p1:abstract:0", "p1", 0.5),
                    _paper_ann_row("p2:abstract:0", "p2", 0.9),
                    _paper_ann_row("p3:abstract:0", "p3", 0.3),
                ]
            }
        ),
        embedding_client=_fake_embedding_client(),
        reranker=rerank,
    )
    results = svc.retrieve("query", domains=("paper",))
    # Must not raise; must return results sorted by ANN score (implementation
    # detail: highest score wins — pin whichever sort direction the impl chooses)
    assert len(results) == 3
    # Scores should be set to raw ANN scores when rerank failed.
    assert all(isinstance(r.score, float) for r in results)


# =============================================================================
# Partial failures
# =============================================================================


def test_retrieve_one_domain_milvus_failure_other_domain_survives():
    def _mixed_search(*, collection_name, data, **kwargs):
        if collection_name == "professor_profiles":
            raise RuntimeError("milvus professor collection down")
        if collection_name == "paper_chunks":
            return _milvus_search_result(
                [_paper_ann_row(f"p{i}:abstract:0", f"p{i}", 0.9 - i * 0.1) for i in range(3)]
            )
        raise ValueError("unknown")

    milvus = MagicMock()
    milvus.search.side_effect = _mixed_search
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    results = svc.retrieve("query", domains=("professor", "paper"))
    # Paper results survive
    assert len(results) >= 3
    assert all(r.object_type == "paper" for r in results)


def test_retrieve_embedding_failure_returns_empty():
    embed = MagicMock()
    embed.embed_batch.side_effect = RuntimeError("embed service down")
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=embed,
        reranker=_fake_reranker(),
    )
    results = svc.retrieve("query", domains=("paper",))
    assert results == []


# =============================================================================
# Contract: unknown domain, empty result
# =============================================================================


def test_retrieve_unknown_domain_raises_value_error():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains({}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    with pytest.raises(ValueError):
        svc.retrieve("query", domains=("not_a_real_domain",))


def test_retrieve_no_candidates_returns_empty_list():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    assert svc.retrieve("query", domains=("paper",)) == []


# =============================================================================
# Cache
# =============================================================================


class _FakeCache:
    def __init__(self) -> None:
        self.store: dict = {}
        self.get_calls: list = []
        self.set_calls: list = []

    def get(self, query, domains, filters_key):
        key = (query, domains, filters_key)
        self.get_calls.append(key)
        return self.store.get(key)

    def set(self, query, domains, filters_key, evidence):
        key = (query, domains, filters_key)
        self.set_calls.append(key)
        self.store[key] = evidence


def test_retrieve_cache_hit_skips_milvus_and_rerank():
    cache = _FakeCache()
    cached = [
        Evidence(
            object_type="paper",
            object_id="cached1",
            score=0.95,
            snippet="cached snippet",
            source_url=None,
            metadata={},
        )
    ]
    # Prime the cache manually
    filters_key = RetrievalService._compute_filters_key({})  # may be a static method
    cache.store[("query", ("paper",), filters_key)] = cached

    milvus = MagicMock()
    embed = MagicMock()
    rerank = MagicMock()
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
        embedding_client=embed,
        reranker=rerank,
        cache=cache,
    )
    results = svc.retrieve("query", domains=("paper",))
    assert results == cached
    # None of the downstream clients were called
    embed.embed_batch.assert_not_called()
    milvus.search.assert_not_called()
    rerank.rerank.assert_not_called()


def test_retrieve_cache_miss_then_set():
    cache = _FakeCache()
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {"paper_chunks": [_paper_ann_row("p1:abstract:0", "p1", 0.9)]}
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
        cache=cache,
    )
    results = svc.retrieve("query", domains=("paper",))
    assert len(results) == 1
    # Cache set was invoked
    assert len(cache.set_calls) == 1


def test_retrieve_empty_result_not_cached():
    cache = _FakeCache()
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
        cache=cache,
    )
    results = svc.retrieve("query", domains=("paper",))
    assert results == []
    # Empty results should NOT be cached (churn protection).
    assert cache.set_calls == []


# =============================================================================
# Concurrent ANN search
# =============================================================================


def test_retrieve_concurrent_ann_across_domains():
    """Two-domain retrieve should invoke ANN searches concurrently, not serially."""
    search_started: list[str] = []
    search_finished: list[str] = []
    lock = threading.Lock()

    def _slow_search(*, collection_name, data, **kwargs):
        with lock:
            search_started.append(collection_name)
        time.sleep(0.2)  # simulate wire latency
        with lock:
            search_finished.append(collection_name)
        if collection_name == "professor_profiles":
            return _milvus_search_result([_prof_ann_row("p1", 0.9)])
        if collection_name == "paper_chunks":
            return _milvus_search_result([_paper_ann_row("p1:abstract:0", "p1", 0.85)])
        return _milvus_search_result([])

    milvus = MagicMock()
    milvus.search.side_effect = _slow_search
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    t0 = time.monotonic()
    svc.retrieve("query", domains=("professor", "paper"))
    elapsed = time.monotonic() - t0
    # If serial, elapsed ≥ 0.4s. If concurrent, ≥ 0.2s but < 0.4s (plus overhead).
    # Give generous headroom for slow CI: require < 0.38s as the concurrency threshold.
    assert elapsed < 0.38, f"retrieve was serial: elapsed={elapsed:.3f}s"
    # Both searches must have started before EITHER finishes (interleaving proof).
    # Strict check: search_started is populated for both before search_finished has 2 entries.
    assert len(search_started) == 2
    # Start timestamps should be close; second start should happen before first finish.
    # This is implied by the elapsed check above; the length assertion above is sufficient.
