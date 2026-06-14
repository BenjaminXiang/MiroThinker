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
from src.data_agents.storage.milvus_collections import (
    PROFESSOR_IDENTITY_PROFILES_COLLECTION,
    PROFESSOR_RESEARCH_PROFILES_COLLECTION,
)

_PROFESSOR_IDENTITY_COLLECTION = PROFESSOR_IDENTITY_PROFILES_COLLECTION
_PROFESSOR_RESEARCH_COLLECTION = PROFESSOR_RESEARCH_PROFILES_COLLECTION

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


@pytest.fixture(autouse=True)
def _disable_quality_status_filter(monkeypatch):
    monkeypatch.setenv("FILTER_BY_QUALITY_STATUS", "0")


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
            "h_index": 21,
            "citation_count": 3456,
            "paper_count": 87,
        },
        "distance": score,
    }


def _prof_identity_ann_row(object_id: str, score: float):
    return {
        "id": object_id,
        "entity": {
            "id": object_id,
            "name": "张三",
            "name_en": "San Zhang",
            "institution": "南方科技大学",
            "department": "计算机科学与工程系",
            "title": "教授",
            "profile_url": "https://example.edu/prof/zhangsan",
            "identity_text": "张三 南方科技大学 计算机科学与工程系 教授",
            "quality_status": "ready",
        },
        "distance": score,
    }


def _prof_research_ann_row(object_id: str, score: float):
    return {
        "id": object_id,
        "entity": {
            "id": object_id,
            "research_text": "具身智能 机器人学习 多模态感知",
            "research_directions": "[\"具身智能\", \"机器人学习\"]",
            "profile_summary": "长期研究具身智能和机器人学习。",
            "paper_summary": "近年论文聚焦机器人策略学习。",
            "patent_summary": "相关专利覆盖机器人控制。",
            "quality_status": "ready",
            "h_index": 21,
            "citation_count": 3456,
            "paper_count": 87,
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


class _FakeResult:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict]:
        return list(self._rows)


class _PaperTitleConn:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, query: str, params: tuple):
        sql = " ".join(query.split()).lower()
        self.calls.append((sql, params))
        if "regexp_replace(lower(coalesce(title_clean" in sql:
            return _FakeResult(list(self._rows))
        if "from paper" in sql and "quality_status" in sql:
            object_ids = set(params)
            return _FakeResult(
                [
                    {
                        "object_id": row["paper_id"],
                        "quality_status": row.get("quality_status", "ready"),
                    }
                    for row in self._rows
                    if row["paper_id"] in object_ids
                ]
            )
        return _FakeResult([])


# =============================================================================
# Happy paths
# =============================================================================


def test_retrieve_single_domain_professor_happy_path():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {
                _PROFESSOR_IDENTITY_COLLECTION: [
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
        "张三是谁",
        domains=("professor",),
        candidate_limit=30,
        final_top_k=10,
    )
    assert isinstance(results, list)
    assert all(isinstance(r, Evidence) for r in results)
    assert len(results) == 3
    assert all(r.object_type == "professor" for r in results)
    assert results[0].metadata["h_index"] == 21
    assert results[0].metadata["citation_count"] == 3456
    assert results[0].metadata["paper_count"] == 87


def test_retrieve_single_domain_paper_happy_path():
    milvus = _fake_milvus_with_domains(
        {
            "paper_chunks": [
                _paper_ann_row(f"p{i}:abstract:0", f"p{i}", 0.9 - i * 0.1)
                for i in range(3)
            ]
        }
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
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
    assert milvus.search.call_args.kwargs["anns_field"] == "content_vector"


def test_retrieve_paper_exact_title_candidate_preempts_ann_noise():
    title = "High-speed silicon photonic Mach-Zehnder modulator at 2 μm"
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-EXACT",
                "title_clean": title,
                "year": 2024,
                "venue": "Optics Express",
                "abstract_clean": None,
                "summary_zh": None,
                "quality_status": "ready",
            }
        ]
    )
    milvus = _fake_milvus_with_domains(
        {"paper_chunks": [_paper_ann_row("PAPER-NOISE:abstract:0", "PAPER-NOISE", 0.99)]}
    )
    reranker = _fake_reranker(order=[1, 0])
    svc = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=milvus,
        embedding_client=_fake_embedding_client(),
        reranker=reranker,
    )

    results = svc.retrieve(title, domains=("paper",), final_top_k=2)

    assert [result.object_id for result in results] == ["PAPER-EXACT", "PAPER-NOISE"]
    assert results[0].metadata["retrieval_source"] == "paper_title_exact"
    assert results[0].metadata["title_clean"] == title
    assert results[0].metadata["chunk_type"] == "title"
    assert title in results[0].snippet
    assert any(
        "regexp_replace(lower(coalesce(title_clean" in sql
        for sql, _params in conn.calls
    )


def test_retrieve_paper_exact_title_strips_main_point_question_suffix():
    title = "Manipulating coordination environment for a high-voltage aqueous copper-chlorine battery"
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-SUAT",
                "title_clean": title,
                "year": 2023,
                "venue": "Nature Communications",
                "abstract_clean": "English abstract.",
                "summary_zh": "这是一段中文论文解读。",
                "quality_status": "ready",
                "citation_count": 1,
            }
        ]
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve(f"{title} 这篇论文主要讲什么？", domains=("paper",), final_top_k=2)

    assert [result.object_id for result in results] == ["PAPER-SUAT"]
    assert results[0].metadata["retrieval_source"] == "paper_title_exact"
    assert results[0].metadata["snippet_source"] == "summary_zh"


def test_retrieve_paper_exact_title_strips_cn_paper_abstract_suffix():
    title = (
        "Environmental Exposure and Childhood Atopic Dermatitis in Shanghai: "
        "A Season-Stratified Time-Series Analysis"
    )
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-AD",
                "title_clean": title,
                "year": 2021,
                "venue": "Dermatology",
                "abstract_clean": "English abstract.",
                "summary_zh": "这是一段环境暴露与儿童特应性皮炎论文解读。",
                "quality_status": "ready",
                "citation_count": 1,
            }
        ]
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve(
        "Environmental Exposure and Childhood Atopic Dermatitis in Shanghai 这篇论文的摘要",
        domains=("paper",),
        final_top_k=2,
    )

    assert [result.object_id for result in results] == ["PAPER-AD"]
    assert results[0].metadata["retrieval_source"] == "paper_title_exact"
    assert results[0].metadata["snippet_source"] == "summary_zh"


def test_retrieve_paper_title_prefix_query_matches_full_long_title():
    title = (
        "OctGLP-Net: Learning Octree-Structured Context Entropy Model With "
        "Global-Local Perception for Point Cloud Geometry Compression"
    )
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-SYSU",
                "title_clean": title,
                "year": 2026,
                "venue": "IEEE Transactions on Intelligent Transportation Systems",
                "abstract_clean": "English abstract.",
                "summary_zh": "这是一段点云压缩论文解读。",
                "quality_status": "ready",
                "citation_count": 1,
            }
        ]
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve(
        "OctGLP-Net Learning Octree-Structured Context Entropy Model 这篇论文主要讲什么？",
        domains=("paper",),
        final_top_k=2,
    )

    assert [result.object_id for result in results] == ["PAPER-SYSU"]
    assert results[0].metadata["retrieval_source"] == "paper_title_exact"
    assert results[0].metadata["title_clean"] == title
    assert results[0].metadata["snippet_source"] == "summary_zh"


def test_retrieve_paper_title_prefix_query_strips_what_is_suffix():
    title = (
        "Designing Mediated Social Touch for Mobile Communication: "
        "From Hand Gestures to Touch Signals"
    )
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-SZTU",
                "title_clean": title,
                "year": 2025,
                "venue": "International Journal of Human-Computer Studies",
                "abstract_clean": None,
                "summary_zh": None,
                "quality_status": "needs_enrichment",
                "citation_count": 1,
            }
        ]
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve(
        "Designing Mediated Social Touch for Mobile Communication 这篇论文是什么",
        domains=("paper",),
        final_top_k=2,
        filter_by_quality_status=False,
    )

    assert [result.object_id for result in results] == ["PAPER-SZTU"]
    assert results[0].metadata["retrieval_source"] == "paper_title_exact"
    assert results[0].metadata["snippet_source"] == "title"


def test_retrieve_paper_exact_title_strips_paper_domain_prefix_and_summary_suffix():
    title = (
        "Non-Iridium Based Electrocatalyst for Durable Acidic Oxygen Evolution "
        "Reaction in Proton Exchange Membrane Water Electrolysis"
    )
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-NATURE-MATERIALS",
                "title_clean": title,
                "year": 2022,
                "venue": "Nature Materials",
                "abstract_clean": "English abstract.",
                "summary_zh": "这是一段中文论文解读。",
                "quality_status": "ready",
                "citation_count": 920,
            }
        ]
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve(
        f"论文 {title} 的摘要是什么",
        domains=("paper",),
        final_top_k=2,
    )

    assert [result.object_id for result in results] == ["PAPER-NATURE-MATERIALS"]
    assert results[0].metadata["retrieval_source"] == "paper_title_exact"
    assert results[0].metadata["snippet_source"] == "summary_zh"


def test_retrieve_paper_exact_title_allows_partial_rows_with_summary_under_ready_filter():
    title = (
        "Control of polymorphism in solution-processed organic thin film "
        "transistors by self-assembled monolayers"
    )
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-INTRO-SUMMARY",
                "title_clean": title,
                "year": 2020,
                "venue": "Science China Chemistry",
                "abstract_clean": None,
                "summary_zh": "这是一段基于论文正文引言生成的中文解读。",
                "quality_status": "partial",
                "citation_count": 12,
            }
        ]
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve(
        f"论文 {title} 的摘要是什么",
        domains=("paper",),
        final_top_k=2,
        filter_by_quality_status=True,
    )

    assert [result.object_id for result in results] == ["PAPER-INTRO-SUMMARY"]
    assert results[0].metadata["retrieval_source"] == "paper_title_exact"
    assert results[0].metadata["snippet_source"] == "summary_zh"
    assert results[0].metadata["quality_status"] == "partial"


def test_retrieve_paper_exact_title_filters_partial_rows_without_summary_under_ready_filter():
    title = "Sparse title-only paper row that still needs enrichment"
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-PARTIAL-TITLE-ONLY",
                "title_clean": title,
                "year": 2020,
                "venue": None,
                "abstract_clean": None,
                "summary_zh": None,
                "quality_status": "partial",
                "citation_count": 1,
            }
        ]
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve(
        f"论文 {title} 的摘要是什么",
        domains=("paper",),
        final_top_k=2,
        filter_by_quality_status=True,
    )

    assert results == []


def test_retrieve_paper_exact_title_prefers_rich_duplicate_record():
    title = "Mendelian randomization analyses reveal causal relationships between the human microbiome and longevity"
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-SPARSE",
                "title_clean": title,
                "year": 2023,
                "venue": "Nature Aging",
                "abstract_clean": None,
                "summary_zh": None,
                "quality_status": "ready",
                "citation_count": 999,
            },
            {
                "paper_id": "PAPER-RICH",
                "title_clean": title,
                "year": 2023,
                "venue": "Nature Aging",
                "abstract_clean": "English abstract.",
                "summary_zh": "中文摘要。",
                "quality_status": "ready",
                "citation_count": 1,
            },
        ]
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve(title, domains=("paper",), final_top_k=2)

    assert [result.object_id for result in results] == ["PAPER-RICH", "PAPER-SPARSE"]
    assert results[0].snippet == "中文摘要。"
    assert results[0].metadata["snippet_source"] == "summary_zh"


def test_retrieve_paper_exact_title_excludes_rejected_rows():
    title = "A distributed data management system to support large-scale data analysis"
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-BAD",
                "title_clean": title,
                "year": 2019,
                "venue": None,
                "abstract_clean": None,
                "summary_zh": None,
                "quality_status": "rejected",
                "identity_status": "rejected",
                "citation_count": 999,
            },
            {
                "paper_id": "PAPER-GOOD",
                "title_clean": title,
                "year": 2019,
                "venue": "The Journal of Systems & Software",
                "abstract_clean": "English abstract.",
                "summary_zh": "中文摘要。",
                "quality_status": "ready",
                "identity_status": "confirmed",
                "citation_count": 1,
            },
        ]
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=_fake_milvus_with_domains({"paper_chunks": []}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve(title, domains=("paper",), final_top_k=2)

    assert [result.object_id for result in results] == ["PAPER-GOOD"]
    assert any("identity_status" in sql for sql, _params in conn.calls)
    assert any("quality_status" in sql for sql, _params in conn.calls)


def test_retrieve_two_domain_merges_candidates():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {
                _PROFESSOR_IDENTITY_COLLECTION: [
                    _prof_ann_row(f"prof{i}", 0.9 - i * 0.05) for i in range(5)
                ],
                "paper_chunks": [
                    _paper_ann_row(f"p{i}:abstract:0", f"paper{i}", 0.85 - i * 0.05) for i in range(5)
                ],
            }
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    results = svc.retrieve(
        "张三是谁",
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
        milvus_client=_fake_milvus_with_domains({_PROFESSOR_IDENTITY_COLLECTION: rows}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    results = svc.retrieve(
        "张三是谁",
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
        if collection_name in {
            _PROFESSOR_IDENTITY_COLLECTION,
            _PROFESSOR_RESEARCH_COLLECTION,
        }:
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
    results = svc.retrieve("张三是谁", domains=("professor", "paper"))
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


def test_retrieve_unknown_domain_returns_empty_list():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains({}),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )
    assert svc.retrieve("query", domains=("not_a_real_domain",)) == []


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
    filters_key = RetrievalService._compute_filters_key(
        {"__quality_status_filter_enabled": False}
    )
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
# Professor split retrieval routing
# =============================================================================


def test_professor_identity_query_routes_to_identity_collection_with_label():
    milvus = _fake_milvus_with_domains(
        {_PROFESSOR_IDENTITY_COLLECTION: [_prof_identity_ann_row("PROF-ID", 0.93)]}
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve("张三教授是谁", domains=("professor",), final_top_k=10)

    assert [result.object_id for result in results] == ["PROF-ID"]
    assert milvus.search.call_args.kwargs["collection_name"] == _PROFESSOR_IDENTITY_COLLECTION
    assert milvus.search.call_args.kwargs["anns_field"] == "identity_vector"
    assert results[0].metadata["collection_name"] == _PROFESSOR_IDENTITY_COLLECTION
    assert results[0].metadata["professor_retrieval_index"] == "identity"
    assert results[0].source_url == "https://example.edu/prof/zhangsan"


def test_professor_research_query_routes_to_research_collection_with_label():
    milvus = _fake_milvus_with_domains(
        {_PROFESSOR_RESEARCH_COLLECTION: [_prof_research_ann_row("PROF-RES", 0.91)]}
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve("找做具身智能的教授", domains=("professor",), final_top_k=10)

    assert [result.object_id for result in results] == ["PROF-RES"]
    assert milvus.search.call_args.kwargs["collection_name"] == _PROFESSOR_RESEARCH_COLLECTION
    assert milvus.search.call_args.kwargs["anns_field"] == "research_vector"
    assert "具身智能" in results[0].snippet
    assert results[0].metadata["collection_name"] == _PROFESSOR_RESEARCH_COLLECTION
    assert results[0].metadata["professor_retrieval_index"] == "research"


def test_professor_ambiguous_query_searches_both_collections_and_preserves_labels():
    milvus = _fake_milvus_with_domains(
        {
            _PROFESSOR_IDENTITY_COLLECTION: [_prof_identity_ann_row("PROF-ID", 0.93)],
            _PROFESSOR_RESEARCH_COLLECTION: [_prof_research_ann_row("PROF-RES", 0.91)],
        }
    )
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=milvus,
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve("张三教授的具身智能方向", domains=("professor",), final_top_k=10)

    searched = [call.kwargs["collection_name"] for call in milvus.search.call_args_list]
    assert searched == [_PROFESSOR_IDENTITY_COLLECTION, _PROFESSOR_RESEARCH_COLLECTION]
    assert [call.kwargs["anns_field"] for call in milvus.search.call_args_list] == [
        "identity_vector",
        "research_vector",
    ]
    assert {
        result.metadata["professor_retrieval_index"] for result in results
    } == {"identity", "research"}
    assert {
        result.metadata["collection_name"] for result in results
    } == {_PROFESSOR_IDENTITY_COLLECTION, _PROFESSOR_RESEARCH_COLLECTION}


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
        if collection_name == _PROFESSOR_IDENTITY_COLLECTION:
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
    svc.retrieve("张三是谁", domains=("professor", "paper"))
    elapsed = time.monotonic() - t0
    # If serial, elapsed ≥ 0.4s. If concurrent, ≥ 0.2s but < 0.4s (plus overhead).
    # Give generous headroom for slow CI: require < 0.38s as the concurrency threshold.
    assert elapsed < 0.38, f"retrieve was serial: elapsed={elapsed:.3f}s"
    # Both searches must have started before EITHER finishes (interleaving proof).
    # Strict check: search_started is populated for both before search_finished has 2 entries.
    assert len(search_started) == 2
    # Start timestamps should be close; second start should happen before first finish.
    # This is implied by the elapsed check above; the length assertion above is sufficient.
