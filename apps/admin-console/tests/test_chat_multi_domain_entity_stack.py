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
