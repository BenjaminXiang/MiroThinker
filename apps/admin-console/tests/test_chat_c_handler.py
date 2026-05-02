from __future__ import annotations

from typing import Any

import pytest
from fastapi import Response

from backend.api import chat as chat_module


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, chat_module.SessionContext] = {}

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        key = session_id or "w13-c-session"
        self.sessions.setdefault(key, chat_module.SessionContext(session_id=key))
        return self.sessions[key]

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.sessions[ctx.session_id] = ctx.model_copy(deep=True)


class _FakeRetrievalService:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.rows = rows or []
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    def get_related_objects(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return list(self.rows)


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> _FakeSessionStore:
    fake = _FakeSessionStore()
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", fake)
    return fake


def _classify_c(target_domain: str | None = "paper") -> dict[str, str]:
    payload = {
        "type": "C",
        "topic": "",
        "name": "",
        "reason": "test",
    }
    if target_domain is not None:
        payload["target_domain"] = target_domain
    return payload


def _seed_session(
    store: _FakeSessionStore,
    *,
    session_id: str = "w13-c-session",
    kind: chat_module.TargetDomain,
    object_id: str,
    label: str,
) -> None:
    session = chat_module.SessionContext(session_id=session_id)
    session.push_entity(chat_module.SessionEntity(kind=kind, id=object_id, label=label))
    store.sessions[session_id] = session


def test_c_handler_professor_to_paper_pushes_top_target(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeSessionStore,
) -> None:
    _seed_session(store, kind="professor", object_id="PROF-001", label="丁文伯")
    service = _FakeRetrievalService(
        [
            {
                "paper_id": "PAPER-001",
                "title_clean": "Force Control for Robots",
                "year": 2025,
                "venue": "ICRA",
            }
        ]
    )
    monkeypatch.setattr(chat_module, "_classify_query_with_llm", lambda _query: _classify_c("paper"))
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)

    response = chat_module.chat(
        chat_module.ChatRequest(query="关联论文"),
        response=Response(),
        miroflow_chat_session="w13-c-session",
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_related"
    assert "Force Control for Robots" in response.answer_text
    assert response.citations[0].type == "paper"
    assert service.calls == [
        {
            "source_domain": "professor",
            "source_id": "PROF-001",
            "target_domain": "paper",
            "limit": 5,
        }
    ]
    assert store.sessions["w13-c-session"].latest_for("paper").id == "PAPER-001"


def test_c_handler_professor_to_company(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeSessionStore,
) -> None:
    _seed_session(store, kind="professor", object_id="PROF-001", label="丁文伯")
    service = _FakeRetrievalService(
        [
            {
                "company_id": "COMP-001",
                "canonical_name": "未来机器人",
                "industry": "机器人",
            }
        ]
    )
    monkeypatch.setattr(chat_module, "_classify_query_with_llm", lambda _query: _classify_c("company"))
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)

    response = chat_module.chat(
        chat_module.ChatRequest(query="他参与的公司"),
        response=Response(),
        miroflow_chat_session="w13-c-session",
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_related"
    assert response.citations[0].type == "company"
    assert "未来机器人" in response.answer_text
    assert store.sessions["w13-c-session"].latest_for("company").id == "COMP-001"


def test_c_handler_company_to_patent(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeSessionStore,
) -> None:
    _seed_session(store, kind="company", object_id="COMP-001", label="广和通")
    service = _FakeRetrievalService(
        [
            {
                "patent_id": "PAT-001",
                "patent_number": "CN202400001",
                "title_clean": "通信模组控制方法",
            }
        ]
    )
    monkeypatch.setattr(chat_module, "_classify_query_with_llm", lambda _query: _classify_c("patent"))
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)

    response = chat_module.chat(
        chat_module.ChatRequest(query="相关专利"),
        response=Response(),
        miroflow_chat_session="w13-c-session",
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_related"
    assert response.citations[0].type == "patent"
    assert "CN202400001" in response.answer_text
    assert store.sessions["w13-c-session"].latest_for("patent").id == "PAT-001"


def test_c_handler_empty_stack_clarifies_without_retrieval(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeSessionStore,
) -> None:
    service = _FakeRetrievalService()
    monkeypatch.setattr(chat_module, "_classify_query_with_llm", lambda _query: _classify_c("paper"))
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)

    response = chat_module.chat(
        chat_module.ChatRequest(query="关联论文"),
        response=Response(),
        miroflow_chat_session="w13-c-session",
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_clarification"
    assert "请先确认" in response.answer_text
    assert service.calls == []
    assert store.sessions["w13-c-session"].latest_for("paper") is None


def test_c_handler_same_target_only_stack_clarifies(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeSessionStore,
) -> None:
    _seed_session(store, kind="paper", object_id="PAPER-001", label="Force Control")
    service = _FakeRetrievalService()
    monkeypatch.setattr(chat_module, "_classify_query_with_llm", lambda _query: _classify_c("paper"))
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)

    response = chat_module.chat(
        chat_module.ChatRequest(query="关联论文"),
        response=Response(),
        miroflow_chat_session="w13-c-session",
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_clarification"
    assert service.calls == []


def test_c_handler_retrieval_failure_falls_back_to_a_path(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeSessionStore,
) -> None:
    _seed_session(store, kind="professor", object_id="PROF-001", label="丁文伯")
    service = _FakeRetrievalService(exc=RuntimeError("db down"))
    monkeypatch.setattr(chat_module, "_classify_query_with_llm", lambda _query: _classify_c("paper"))
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)
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

    response = chat_module.chat(
        chat_module.ChatRequest(query="Force Control for Robots"),
        response=Response(),
        miroflow_chat_session="w13-c-session",
        conn=object(),
    )

    assert response.query_type == "A_paper_profile"
    assert response.citations[0].id == "PAPER-001"
    assert service.calls[0]["source_domain"] == "professor"
