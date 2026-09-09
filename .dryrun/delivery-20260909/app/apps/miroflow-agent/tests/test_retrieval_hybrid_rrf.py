"""Unit tests for the hybrid-retrieval lexical + RRF helpers (deterministic layer)."""
from __future__ import annotations

from src.data_agents.service.retrieval import (
    Evidence,
    _hybrid_rrf_select,
    _lexical_coverage,
    _lexical_terms,
)


def _ev(oid: str, snippet: str) -> Evidence:
    return Evidence(
        object_type="company",
        object_id=oid,
        score=0.0,
        snippet=snippet,
        source_url=None,
        metadata={},
    )


class _RR:
    def __init__(self, index: int, score: float) -> None:
        self.index = index
        self.score = score


def test_lexical_terms_cjk_bigrams_and_latin() -> None:
    terms = _lexical_terms("普渡科技 PUDU 做配送机器人")
    assert "普渡" in terms and "渡科" in terms and "配送" in terms
    assert "pudu" in terms  # latin token lowercased


def test_lexical_coverage_query_overlap() -> None:
    q = _lexical_terms("酒店送餐机器人")
    assert _lexical_coverage(q, "普渡配送清洁机器人酒店餐饮") > 0.0
    assert _lexical_coverage(q, "完全不相关的文本") == 0.0
    assert _lexical_coverage(set(), "anything") == 0.0


def test_hybrid_rrf_keeps_high_rerank_and_includes_high_lexical() -> None:
    # A: rerank #1 but low lexical overlap (a robot trading platform).
    # B: rerank #2 but high lexical overlap (the query's market leader).
    cands = [
        _ev("A", "中铧机器人（深圳）是一家机器人交易平台运营商。"),
        _ev("B", "普渡科技专注于配送机器人，服务于酒店、餐饮等场景。"),
    ]
    reranked = [_RR(0, 0.54), _RR(1, 0.39)]  # reranker prefers A
    res = _hybrid_rrf_select("酒店送餐机器人供应商", cands, reranked, final_top_k=2)
    ids = [r.object_id for r in res]
    assert ids == ["A", "B"] or ids == ["B", "A"]  # both kept (top_k=2)
    assert "B" in ids


def test_hybrid_rrf_promotes_good_in_both_over_one_dimensional() -> None:
    # RRF rewards candidates good in BOTH dimensions. A is rerank #1 but lexical #3
    # (a trading platform). B is rerank #2 but lexical #1 (the keyword market leader).
    # B (good in both) should outrank A (strong in one dimension only).
    cands = [
        _ev("A", "中铧（深圳）电子商务是一家综合在线交易平台运营商。"),
        _ev("B", "普渡科技配送清洁机器人，服务于酒店、餐饮等场景。"),
        _ev("C", "某机器人零部件加工厂，主营机械配件。"),
    ]
    reranked = [_RR(0, 0.54), _RR(1, 0.42), _RR(2, 0.30)]
    res = _hybrid_rrf_select("酒店送餐机器人供应商", cands, reranked, final_top_k=3)
    assert res[0].object_id == "B"  # good-in-both wins over one-dimensional


def test_hybrid_rrf_respects_final_top_k() -> None:
    cands = [_ev(f"C{i}", f"company {i} 机器人") for i in range(8)]
    reranked = [_RR(i, 1.0 / (i + 1)) for i in range(8)]
    res = _hybrid_rrf_select("机器人", cands, reranked, final_top_k=3)
    assert len(res) == 3
