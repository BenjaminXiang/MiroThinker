from __future__ import annotations

from unittest.mock import MagicMock

from src.data_agents.company import vectorizer as vectorizer_module
from src.data_agents.company.vectorizer import (
    CompanyVectorizer,
    _compose_company_text,
    _VECTOR_DIM,
)
from src.data_agents.storage.milvus_collections import COMPANY_PROFILES_COLLECTION


class _FakeMilvusClient:
    def __init__(self) -> None:
        self.upsert_calls: list[dict] = []

    def has_collection(self, collection_name: str) -> bool:
        return True

    def upsert(self, *, collection_name: str, data: list[dict]) -> None:
        self.upsert_calls.append(
            {"collection_name": collection_name, "data": list(data)}
        )


def _embedding_client() -> MagicMock:
    client = MagicMock()
    client.embed_batch.side_effect = (
        lambda texts, **_: [[0.1] * _VECTOR_DIM for _ in texts]
    )
    return client


def _company_row(**overrides) -> dict:
    defaults = {
        "company_id": "COMP-001",
        "canonical_name": "Example Robotics",
        "industry": "AI",
        "hq_city": "Shenzhen",
        "description": "Builds autonomy systems for drones.",
        "profile_summary": "Robotics company focused on embodied AI.",
        "technology_route_summary": "Uses multimodal perception and planning.",
    }
    defaults.update(overrides)
    return defaults


def test_compose_company_text_prefers_narrative_fields():
    text = _compose_company_text(_company_row())

    assert text.splitlines()[0] == "Example Robotics，AI，Shenzhen"
    assert "embodied AI" in text
    assert "multimodal perception" in text
    assert "drones" not in text


def test_compose_company_text_falls_back_to_description_and_truncates():
    text = _compose_company_text(
        _company_row(
            profile_summary=None,
            technology_route_summary=None,
            description="x" * 2000,
        )
    )

    assert text.endswith("x" * 1800)
    assert len(text.splitlines()[-1]) == 1800


def test_compose_company_text_includes_products_and_recent_events():
    text = _compose_company_text(
        _company_row(
            products_json=[
                {
                    "name": "旭宏医疗",
                    "description": "AI心电智能筛查服务。",
                    "product_category": "心电诊断系统",
                    "target_customers": ["医院/临床机构"],
                    "application_scenarios": ["远程心电诊断"],
                    "technical_tags": ["AI自动诊断"],
                }
            ],
            application_scenarios_json=[
                {
                    "scenario_name": "远程心电诊断",
                    "scenario_category": "医疗诊断",
                    "target_customer": "医院/临床机构",
                    "description": "支持临床远程心电诊断及监护。",
                }
            ],
            recent_events_json=[
                {
                    "event_type": "funding",
                    "event_date": "2026-05-01",
                    "summary": "旭宏医疗完成天使轮融资。",
                }
            ],
        )
    )

    assert "产品/服务：旭宏医疗 - AI心电智能筛查服务。" in text
    assert "产品结构：心电诊断系统 医院/临床机构 远程心电诊断 AI自动诊断" in text
    assert "应用场景：远程心电诊断 医疗诊断 医院/临床机构 支持临床远程心电诊断及监护。" in text
    assert "最近动态：2026-05-01 funding 旭宏医疗完成天使轮融资。" in text


def test_compose_company_text_includes_team_highlights_and_funding_details():
    text = _compose_company_text(
        _company_row(
            team_members_json=[
                {
                    "name": "王博洋",
                    "role": "CEO&联合创始人",
                    "background": "长期参与医疗产品商业化。",
                    "experience_highlights": ["医疗产品商业化", "公司经营管理"],
                    "relevance": "负责心电产品商业化。",
                }
            ],
            recent_events_json=[
                {
                    "event_type": "funding",
                    "event_date": "2026-05-01",
                    "summary": "完成A轮融资。",
                    "normalized": {
                        "round": "A轮",
                        "amount": "数千万元人民币",
                        "investors": ["力合科创"],
                    },
                }
            ],
        )
    )

    assert "团队：王博洋 CEO&联合创始人 长期参与医疗产品商业化。" in text
    assert "医疗产品商业化 公司经营管理 负责心电产品商业化。" in text
    assert "最近动态：2026-05-01 funding 完成A轮融资。 A轮 数千万元人民币 力合科创" in text


def test_company_payload_profile_summary_contains_enrichment_snippets():
    from src.data_agents.company.vectorizer import _company_row_to_payload

    payload = _company_row_to_payload(
        _company_row(
            products_json=[
                {
                    "name": "旭宏医疗",
                    "description": "AI心电智能筛查服务。",
                    "application_scenarios": ["临床心电诊断"],
                }
            ],
            application_scenarios_json=[{"scenario_name": "临床心电诊断"}],
            recent_events_json=[
                {
                    "event_type": "funding",
                    "event_date": "2026-05-01",
                    "summary": "旭宏医疗完成天使轮融资。",
                }
            ],
        ),
        [0.1] * _VECTOR_DIM,
    )

    assert "旭宏医疗" in payload["profile_summary"]
    assert "临床心电诊断" in payload["profile_summary"]
    assert "天使轮融资" in payload["profile_summary"]


def test_vectorize_and_upsert_writes_single_profile_vector(monkeypatch):
    milvus = _FakeMilvusClient()
    monkeypatch.setattr(
        vectorizer_module,
        "_create_milvus_client",
        lambda uri: milvus,
    )
    embed = _embedding_client()
    vectorizer = CompanyVectorizer(embedding_client=embed, milvus_uri="test.db")

    count = vectorizer.vectorize_and_upsert([_company_row()])

    assert count == 1
    assert embed.embed_batch.call_count == 1
    payload = milvus.upsert_calls[0]["data"][0]
    assert milvus.upsert_calls[0]["collection_name"] == COMPANY_PROFILES_COLLECTION
    assert payload["id"] == "COMP-001"
    assert payload["name"] == "Example Robotics"
    assert payload["profile_vector"] == [0.1] * _VECTOR_DIM


def test_vectorize_and_upsert_skips_rows_without_name(monkeypatch):
    milvus = _FakeMilvusClient()
    monkeypatch.setattr(
        vectorizer_module,
        "_create_milvus_client",
        lambda uri: milvus,
    )
    embed = _embedding_client()
    vectorizer = CompanyVectorizer(embedding_client=embed, milvus_uri="test.db")

    count = vectorizer.vectorize_and_upsert([_company_row(canonical_name="")])

    assert count == 0
    embed.embed_batch.assert_not_called()
    assert milvus.upsert_calls == []


def test_ensure_collection_is_idempotent():
    vectorizer = CompanyVectorizer(
        embedding_client=_embedding_client(),
        milvus_uri=":memory:",
    )

    vectorizer.ensure_collection()
    vectorizer.ensure_collection()

    assert vectorizer._milvus_client.has_collection(COMPANY_PROFILES_COLLECTION)
