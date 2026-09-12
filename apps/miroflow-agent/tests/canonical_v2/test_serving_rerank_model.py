"""Unit tests for the serving stage's relevance-model reranking."""

from __future__ import annotations

from typing import Any

import pytest

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving_module
from src.data_agents.canonical_v2.knowledge_read import (
    EvidenceItem,
    FusedCandidate,
    RerankRequest,
)
from src.data_agents.canonical_v2.rerank_client import (
    RemoteReranker,
    RerankUnavailable,
)

RELEASE_ID = "candidate-rerank-test"


def _candidate(
    *,
    token: str,
    lane: str,
    source_nature: str,
    snippet: str | None = None,
    raw_score: float = 1.0,
) -> FusedCandidate:
    local = source_nature == "local"
    evidence = EvidenceItem(
        evidence_id=f"evidence:rerank:{token}",
        object_id=f"object:rerank:{token}",
        domain="company",
        lane=lane,
        source_nature=source_nature,
        source_locator=(
            f"canonical-v2-isolated:{token}"
            if local
            else f"https://example.test/{token}"
        ),
        snippet=snippet if snippet is not None else token,
        score=raw_score,
    )
    return FusedCandidate(
        result_id=f"fused-result:{token}",
        canonical_id=(f"company:{token}" if local else None),
        display_name=token,
        domain="company",
        raw_candidate_ids=(f"raw-candidate:{token}",),
        evidence_ids=(evidence.evidence_id,),
        evidence=(evidence,),
        quality_flags=(),
        raw_score=raw_score,
        identity_kind=("canonical" if local else "web_only"),
        resolution_state=("resolved" if local else "unresolved"),
        origin_lane=lane,
        origin_attempt=1,
        adapter_versions=("test",),
        provider_versions=("serper-v1",),
    )


def _local(token: str, snippet: str | None = None) -> FusedCandidate:
    return _candidate(token=token, lane="lexical", source_nature="local", snippet=snippet)


def _web(token: str, snippet: str | None = None) -> FusedCandidate:
    return _candidate(
        token=token,
        lane="web",
        source_nature="current_web",
        snippet=snippet,
        raw_score=0.9,
    )


class _StubReranker:
    def __init__(
        self,
        scores: tuple[float, ...] | Exception,
        *,
        model_id: str = "stub-reranker-8b",
        max_documents: int = 128,
    ) -> None:
        self._scores = scores
        self.model_id = model_id
        self.max_documents = max_documents
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def score(self, query: str, documents: Any) -> tuple[float, ...]:
        self.calls.append((query, tuple(documents)))
        if isinstance(self._scores, Exception):
            raise self._scores
        return self._scores[: len(documents)]


def _install(monkeypatch: pytest.MonkeyPatch, reranker: Any) -> None:
    monkeypatch.setattr(serving_module, "configured_reranker", lambda: reranker)


def test_serving_rerank_document_carries_name_label_and_snippets() -> None:
    candidate = _local(
        "深圳市优必选科技股份有限公司",
        "人形 机器人\n 研发   与销售 ｜ 注册资本 5000 万元",
    )

    rendered = serving_module._serving_rerank_document(candidate)

    assert rendered.startswith("深圳市优必选科技股份有限公司（企业）：")
    assert "人形 机器人 研发 与销售" in rendered
    assert "\n" not in rendered


def test_model_reranking_orders_the_local_bucket_by_relevance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = (_local("A"), _local("B"))
    stub = _StubReranker((0.1, 0.9))
    _install(monkeypatch, stub)

    proposal = serving_module._serving_reranker(
        RerankRequest(
            release_id=RELEASE_ID,
            original_query="深圳有哪些做机器人的公司",
            eligible_candidates=candidates,
        )
    )

    assert proposal.ordered_result_ids == ("fused-result:B", "fused-result:A")
    assert proposal.model_id == "canonical-v2-serving-rerank-model:stub-reranker-8b"
    assert stub.calls[0][0] == "深圳有哪些做机器人的公司"


def test_model_reranking_keeps_the_local_web_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = (_local("A"), _local("B"), _web("C"), _web("D"))
    stub = _StubReranker((0.1, 0.9, 0.2, 0.8))
    _install(monkeypatch, stub)

    proposal = serving_module._serving_reranker(
        RerankRequest(
            release_id=RELEASE_ID,
            original_query="深圳有哪些做机器人的公司",
            eligible_candidates=candidates,
        )
    )

    assert proposal.ordered_result_ids == (
        "fused-result:B",
        "fused-result:D",
        "fused-result:A",
        "fused-result:C",
    )


def test_model_reranking_keeps_unscored_candidates_behind_scored_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = (_local("A"), _local("B"), _local("C"), _local("D"))
    stub = _StubReranker((0.1, 0.9), max_documents=2)
    _install(monkeypatch, stub)

    proposal = serving_module._serving_reranker(
        RerankRequest(
            release_id=RELEASE_ID,
            original_query="深圳有哪些做机器人的公司",
            eligible_candidates=candidates,
        )
    )

    assert proposal.ordered_result_ids == (
        "fused-result:B",
        "fused-result:A",
        "fused-result:C",
        "fused-result:D",
    )
    assert len(stub.calls[0][1]) == 2


def test_serving_reranker_falls_back_to_deterministic_order_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = (_local("A"), _local("B"), _web("C"), _web("D"))
    _install(monkeypatch, _StubReranker(RerankUnavailable("endpoint down")))
    request = RerankRequest(
        release_id=RELEASE_ID,
        original_query="深圳有哪些做机器人的公司",
        eligible_candidates=candidates,
    )

    proposal = serving_module._serving_reranker(request)

    deterministic = serving_module._deterministic_serving_rerank(request)
    assert proposal.ordered_result_ids == deterministic.ordered_result_ids
    assert proposal.model_id == "canonical-v2-deterministic-reranker-v1"


def test_serving_reranker_stays_deterministic_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = (_local("A"), _local("B"), _web("C"))
    _install(monkeypatch, None)
    request = RerankRequest(
        release_id=RELEASE_ID,
        original_query="深圳有哪些做机器人的公司",
        eligible_candidates=candidates,
    )

    proposal = serving_module._serving_reranker(request)

    assert proposal.ordered_result_ids == (
        serving_module._deterministic_serving_rerank(request).ordered_result_ids
    )
    assert proposal.model_id == "canonical-v2-deterministic-reranker-v1"


def test_remote_reranker_protocol_parses_real_endpoint_payload() -> None:
    payload = {
        "id": "rerank-test",
        "model": "qwen3-reranker-8b",
        "results": [
            {"index": 2, "relevance_score": 0.36},
            {"index": 0, "relevance_score": 0.30},
            {"index": 1, "relevance_score": 0.03},
        ],
    }

    def transport(url: str, body: dict[str, Any], key: str, timeout: float) -> Any:
        return payload

    reranker: RemoteReranker = RemoteReranker(
        base_url="http://100.64.0.27:18006",
        transport=transport,
    )

    assert reranker.score("q", ("a", "b", "c")) == (0.30, 0.03, 0.36)
