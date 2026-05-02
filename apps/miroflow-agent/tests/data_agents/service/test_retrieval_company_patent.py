from __future__ import annotations

from unittest.mock import MagicMock

from src.data_agents.providers.rerank import RerankResult
from src.data_agents.service.retrieval import Evidence, RetrievalService
from src.data_agents.storage.milvus_collections import (
    COMPANY_PROFILES_COLLECTION,
    PATENT_PROFILES_COLLECTION,
)


def _fake_embedding_client():
    client = MagicMock()
    client.embed_batch.return_value = [[0.1] * 4096]
    return client


def _fake_reranker():
    client = MagicMock()
    client.rerank.side_effect = lambda query, documents, top_n=None: [
        RerankResult(index=i, score=1.0 - i * 0.1, document=document)
        for i, document in enumerate(documents[: top_n or len(documents)])
    ]
    return client


def _milvus_search_result(rows: list[dict]):
    return [rows]


def _fake_milvus_with_domains(domain_results: dict[str, list[dict]]):
    client = MagicMock()

    def _search(*, collection_name, data, **kwargs):
        rows = domain_results.get(collection_name, [])
        return _milvus_search_result(rows)

    client.search.side_effect = _search
    return client


def _company_ann_row(company_id: str, score: float):
    return {
        "id": company_id,
        "entity": {
            "id": company_id,
            "name": "深圳示例科技有限公司",
            "industry": "机器人",
            "hq_city": "深圳",
            "description": "示例公司描述",
            "profile_summary": "示例公司聚焦机器人和智能制造。",
            "technology_route_summary": "围绕机器人感知与控制技术路线。",
        },
        "distance": score,
    }


def _patent_ann_row(patent_id: str, score: float):
    return {
        "id": patent_id,
        "entity": {
            "id": patent_id,
            "patent_number": "CN202610000001",
            "title": "一种机器人导航控制方法",
            "abstract": "本发明公开了一种机器人导航控制方法，提升复杂场景下的路径规划稳定性。",
            "technology_effect": "提升导航安全性。",
            "patent_type": "invention",
            "ipc_codes": '["G05D", "B64U"]',
        },
        "distance": score,
    }


def test_retrieve_company_returns_evidence():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {COMPANY_PROFILES_COLLECTION: [_company_ann_row("COMP-1", 0.91)]}
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve("机器人企业", domains=("company",))

    assert len(results) == 1
    assert isinstance(results[0], Evidence)
    assert results[0].object_type == "company"
    assert results[0].object_id == "COMP-1"
    assert results[0].snippet == "示例公司聚焦机器人和智能制造。"
    assert results[0].source_url is None


def test_retrieve_company_metadata_contains_industry_and_city():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {COMPANY_PROFILES_COLLECTION: [_company_ann_row("COMP-1", 0.91)]}
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve("机器人企业", domains=("company",))

    assert results[0].metadata["industry"] == "机器人"
    assert results[0].metadata["hq_city"] == "深圳"


def test_retrieve_patent_returns_evidence():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {PATENT_PROFILES_COLLECTION: [_patent_ann_row("PAT-1", 0.88)]}
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve("机器人导航专利", domains=("patent",))

    assert len(results) == 1
    assert isinstance(results[0], Evidence)
    assert results[0].object_type == "patent"
    assert results[0].object_id == "PAT-1"
    assert results[0].snippet.startswith("一种机器人导航控制方法\n")
    assert "路径规划稳定性" in results[0].snippet
    assert results[0].source_url is None


def test_retrieve_patent_metadata_contains_ipc():
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains(
            {PATENT_PROFILES_COLLECTION: [_patent_ann_row("PAT-1", 0.88)]}
        ),
        embedding_client=_fake_embedding_client(),
        reranker=_fake_reranker(),
    )

    results = svc.retrieve("机器人导航专利", domains=("patent",))

    assert results[0].metadata["ipc_codes"] == '["G05D", "B64U"]'
    assert results[0].metadata["patent_type"] == "invention"


def test_retrieve_unknown_domain_returns_empty():
    embed = _fake_embedding_client()
    svc = RetrievalService(
        pg_conn_factory=lambda: MagicMock(),
        milvus_client=_fake_milvus_with_domains({}),
        embedding_client=embed,
        reranker=_fake_reranker(),
    )

    assert svc.retrieve("query", domains=("not_a_real_domain",)) == []
    embed.embed_batch.assert_not_called()
