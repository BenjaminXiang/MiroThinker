from __future__ import annotations

from typing import Any

import pytest
from fastapi import Response

from backend.api import chat as chat_module


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, chat_module.SessionContext] = {}

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        key = session_id or "w11-6-session"
        self.sessions.setdefault(key, chat_module.SessionContext(session_id=key))
        return self.sessions[key]

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.sessions[ctx.session_id] = ctx.model_copy(deep=True)


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> _FakeSessionStore:
    fake = _FakeSessionStore()
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", fake)
    return fake


def _classify_a(domain: str, name: str) -> dict[str, str]:
    return {
        "type": "A",
        "topic": "",
        "name": name,
        "target_domain": domain,
        "reason": "test",
    }


def _classify_b(domain: str, topic: str) -> dict[str, str]:
    return {
        "type": "B",
        "topic": topic,
        "name": "",
        "target_domain": domain,
        "reason": "test",
    }


class _CaptureConn:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    def execute(self, sql: str, params: tuple[Any, ...]):
        self.sql = sql
        self.params = params
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return []


def test_company_query_pushes_entity(
    monkeypatch: pytest.MonkeyPatch, store: _FakeSessionStore
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: _classify_a("company", "无界智航"),
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_company",
        lambda _conn, *, name: [
            {
                "company_id": "COMP-001",
                "canonical_name": name,
                "industry": "低空经济",
                "business": "无人机系统",
            }
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="无界智航"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_company_profile"
    assert store.sessions["w11-6-session"].latest_for("company").label == "无界智航"


def test_company_product_query_includes_enrichment_fields(
    monkeypatch: pytest.MonkeyPatch, store: _FakeSessionStore
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: _classify_a("company", "旭宏医疗"),
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_company",
        lambda _conn, *, name: [
            {
                "company_id": "COMP-SEM",
                "canonical_name": "深圳旭宏医疗科技",
                "industry": "医疗健康",
                "business": "人工智能慢病预防与管理企业",
                "products": [
                    {
                        "name": "Semacare",
                        "description": "AI 自动诊断技术支持临床和远程心电诊断及监护。",
                        "product_category": "AI 心电诊断系统",
                        "target_customers": ["医院/临床机构"],
                        "application_scenarios": ["远程心电诊断", "心电监护"],
                        "technical_tags": ["AI 自动诊断", "远程监护"],
                    }
                ],
                "application_scenarios": [
                    {
                        "scenario_name": "远程心电诊断",
                        "target_customer": "医院/临床机构",
                        "description": "支持临床远程心电诊断及监护。",
                    }
                ],
                "recent_events": [
                    {
                        "event_type": "funding",
                        "event_date": "2020-07-07",
                        "summary": "完成A轮融资。",
                        "normalized": {
                            "round": "A轮",
                            "amount_raw": "数千万人民币",
                            "investors": ["力合科创"],
                        },
                    }
                ],
            }
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="旭宏医疗产品是什么"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_company_profile"
    assert "Semacare" in response.answer_text
    assert "AI 自动诊断" in response.answer_text
    assert "AI 心电诊断系统" in response.answer_text
    assert "医院/临床机构" in response.answer_text
    assert "远程监护" in response.answer_text
    assert "远程心电诊断" in response.answer_text
    assert "2020-07-07" in response.answer_text
    assert "数千万人民币" in response.answer_text
    assert "力合科创" in response.answer_text
    assert response.structured_payload["products"][0]["name"] == "Semacare"
    assert response.structured_payload["application_scenarios"][0]["scenario_name"] == "远程心电诊断"
    assert response.structured_payload["recent_events"][0]["event_type"] == "funding"


def test_company_topic_sql_searches_products_events_and_funding() -> None:
    conn = _CaptureConn()

    chat_module._lookup_companies_by_topic(
        conn,
        topic="医疗 AI 最近融资的深圳医疗 AI 公司",
    )

    assert "company_product" in conn.sql
    assert "company_application_scenario" in conn.sql
    assert "cp.quality_status = 'ready'" in conn.sql
    assert "cas.quality_status = 'ready'" in conn.sql
    assert "scenarios.scenario_text" in conn.sql
    assert "company_signal_event" in conn.sql
    assert "latest.latest_funding_time IS NOT NULL" in conn.sql
    assert "ORDER BY latest.latest_funding_time DESC" in conn.sql
    assert "%医疗%" in conn.params
    assert "%人工智能%" in conn.params


def test_company_topic_chat_uses_raw_query_for_funding_context(
    monkeypatch: pytest.MonkeyPatch, store: _FakeSessionStore
) -> None:
    seen: dict[str, str] = {}
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: _classify_b("company", "医疗 AI"),
    )
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: True)

    def lookup_companies(_conn: Any, *, topic: str) -> list[dict[str, Any]]:
        seen["topic"] = topic
        return [
            {
                "company_id": "COMP-SEM",
                "canonical_name": "深圳旭宏医疗科技",
                "industry": "医疗健康",
                "business": "人工智能慢病预防与管理企业",
                "snippet": "2020-07-07 funding A轮 数千万人民币",
                "latest_funding_time": "2020-07-07",
                "total_count": 1,
            }
        ]

    monkeypatch.setattr(chat_module, "_lookup_companies_by_topic", lookup_companies)

    response = chat_module.chat(
        chat_module.ChatRequest(query="最近融资的深圳医疗 AI 公司"),
        response=Response(),
        conn=object(),
    )

    assert "最近融资" in seen["topic"]
    assert response.query_type == "B_company_topic_search"
    assert "深圳旭宏医疗科技" in response.answer_text
    assert "A轮" in response.answer_text


def test_paper_query_pushes_entity(
    monkeypatch: pytest.MonkeyPatch, store: _FakeSessionStore
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: _classify_a("paper", "Robot Force Control"),
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_paper",
        lambda _conn, *, title: [
            {
                "paper_id": "PAPER-001",
                "title_clean": title,
                "year": 2025,
                "venue": "ICRA",
            }
        ],
    )

    chat_module.chat(
        chat_module.ChatRequest(query="Robot Force Control 论文"),
        response=Response(),
        conn=object(),
    )

    assert store.sessions["w11-6-session"].latest_for("paper").label == "Robot Force Control"


def test_patent_query_pushes_entity(
    monkeypatch: pytest.MonkeyPatch, store: _FakeSessionStore
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: _classify_a("patent", "CN12345"),
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_patent",
        lambda _conn, *, query: [
            {
                "patent_id": "PAT-001",
                "patent_number": query,
                "title_clean": "机器人控制系统",
                "applicants_raw": "优必选",
            }
        ],
    )

    chat_module.chat(
        chat_module.ChatRequest(query="CN12345 专利"),
        response=Response(),
        conn=object(),
    )

    assert store.sessions["w11-6-session"].latest_for("patent").label == "CN12345"


def test_pronoun_company_resolves_to_latest_company(
    monkeypatch: pytest.MonkeyPatch, store: _FakeSessionStore
) -> None:
    session = chat_module.SessionContext(session_id="w11-6-session")
    session.push_entity(chat_module.SessionEntity(kind="company", id="COMP-001", label="无界智航"))
    store.sessions[session.session_id] = session
    seen: dict[str, str] = {}

    def lookup_patents(_conn: Any, *, company_name: str) -> list[dict[str, Any]]:
        seen["company_name"] = company_name
        return []

    monkeypatch.setattr(chat_module, "_lookup_patents_by_applicant", lookup_patents)

    response = chat_module.chat(
        chat_module.ChatRequest(query="这家公司的专利"),
        response=Response(),
        miroflow_chat_session="w11-6-session",
        conn=object(),
    )

    assert response.query_type == "A_patent_by_applicant"
    assert seen["company_name"] == "无界智航"


def test_stack_lru_5_eviction_across_domains() -> None:
    ctx = chat_module.SessionContext(session_id="s1")
    for idx, domain in enumerate(
        ["professor", "company", "paper", "patent", "professor", "company"]
    ):
        ctx.push_entity(
            chat_module.SessionEntity(
                kind=domain,
                id=f"ID-{idx}",
                label=f"Entity {idx}",
            )
        )

    assert len(ctx.entities) == 5
    assert [entity.id for entity in ctx.entities] == [
        "ID-1",
        "ID-2",
        "ID-3",
        "ID-4",
        "ID-5",
    ]
