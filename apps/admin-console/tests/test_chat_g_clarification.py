from __future__ import annotations

from typing import Any

import pytest
from fastapi import Response

from backend.api import chat as chat_module


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, chat_module.SessionContext] = {}

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        key = session_id or "w11-2-session"
        self.sessions.setdefault(key, chat_module.SessionContext(session_id=key))
        return self.sessions[key]

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.sessions[ctx.session_id] = ctx.model_copy(deep=True)


@pytest.fixture(autouse=True)
def _session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", _FakeSessionStore())


def _prof(idx: int, *, paper_count: int) -> dict[str, Any]:
    return {
        "professor_id": f"PROF-{idx}",
        "canonical_name": "王伟",
        "institution": f"深圳高校 {idx}",
        "title": "教授",
        "paper_count": paper_count,
        "citation_count": paper_count * 10,
    }


def test_g_returns_structured_clarification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "G",
            "topic": "",
            "name": "王伟",
            "reason": "same name",
        },
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_professor",
        lambda _conn, *, name, institutions: [_prof(1, paper_count=3), _prof(2, paper_count=8)],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="王伟是谁"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "G_ambiguous_clarification"
    assert response.clarification is not None
    assert response.clarification.default_id == "PROF-2"
    assert [option.id for option in response.clarification.options] == ["PROF-2", "PROF-1"]
    assert "请加上学校" in response.answer_text


def test_clarification_capped_at_5(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "G",
            "topic": "",
            "name": "王伟",
            "reason": "same name",
        },
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_professor",
        lambda _conn, *, name, institutions: [
            _prof(idx, paper_count=idx) for idx in range(7)
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="王伟是谁"),
        response=Response(),
        conn=object(),
    )

    assert response.clarification is not None
    assert len(response.clarification.options) == 5
    assert response.clarification.omitted == 2


def test_entity_id_hint_bypasses_g(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"classifier": False}

    def classify(_query: str) -> dict[str, str]:
        called["classifier"] = True
        return {"type": "G", "topic": "", "name": "王伟", "reason": "same name"}

    monkeypatch.setattr(chat_module, "_classify_query_with_llm", classify)
    monkeypatch.setattr(
        chat_module,
        "_lookup_professor_by_id",
        lambda _conn, *, professor_id: {
            "professor_id": professor_id,
            "canonical_name": "王伟",
            "institution": "南方科技大学",
            "title": "教授",
        },
    )
    monkeypatch.setattr(chat_module, "_prof_research_topics", lambda *_args: ["机器人"])
    monkeypatch.setattr(chat_module, "_prof_paper_count", lambda *_args: 5)

    response = chat_module.chat(
        chat_module.ChatRequest(query="王伟是谁", entity_id_hint="PROF-9"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_prof_profile"
    assert response.clarification is None
    assert response.structured_payload["professor_id"] == "PROF-9"
    assert called["classifier"] is False


def test_invalid_entity_id_hint_falls_back_to_g(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_module, "_lookup_professor_by_id", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "G",
            "topic": "",
            "name": "王伟",
            "reason": "same name",
        },
    )
    monkeypatch.setattr(
        chat_module,
        "_lookup_professor",
        lambda _conn, *, name, institutions: [_prof(1, paper_count=1), _prof(2, paper_count=2)],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="王伟是谁", entity_id_hint="missing"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "G_ambiguous_clarification"
    assert response.clarification is not None
