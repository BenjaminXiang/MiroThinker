from __future__ import annotations

from typing import Any

import pytest
from fastapi import Response

from backend.api import chat as chat_module


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, chat_module.SessionContext] = {}
        self.persisted: list[dict[str, Any]] = []

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        new_id = session_id or "test-chat-session-cookie"
        if new_id not in self.sessions:
            self.sessions[new_id] = chat_module.SessionContext(session_id=new_id)
        return self.sessions[new_id]

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.sessions[ctx.session_id] = ctx.model_copy(deep=True)
        self.persisted.append(ctx.model_dump(mode="json"))


def test_chat_persists_professor_context_for_pronoun_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    lookup_names: list[str] = []

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)

    def lookup_professor(
        _conn: Any, *, name: str, institutions: tuple[str, ...] | None
    ) -> list[dict[str, Any]]:
        del institutions
        lookup_names.append(name)
        if name == "丁文伯":
            return [
                {
                    "professor_id": "PROF-001",
                    "canonical_name": "丁文伯",
                    "canonical_name_en": "Wenbo Ding",
                    "institution": "清华大学深圳国际研究生院",
                    "title": "教授",
                    "discipline_family": "控制科学与工程",
                }
            ]
        return []

    monkeypatch.setattr(chat_module, "_lookup_professor", lookup_professor)
    monkeypatch.setattr(chat_module, "_prof_research_topics", lambda *_args: ["机器人"])
    monkeypatch.setattr(chat_module, "_prof_paper_count", lambda *_args: 1)
    monkeypatch.setattr(
        chat_module,
        "_lookup_verified_papers_for_prof",
        lambda *_args, **_kwargs: [
            {
                "paper_id": "PAPER-001",
                "title_clean": "Robot Force Control",
                "year": 2025,
                "venue": "ICRA",
                "citation_count": 10,
                "topic_consistency_score": 0.9,
                "total_count": 1,
            }
        ],
    )

    first_response = Response()
    first = chat_module.chat(
        chat_module.ChatRequest(query="介绍清华的丁文伯"),
        response=first_response,
        miroflow_chat_session=None,
        conn=object(),
    )

    assert first.query_type == "A_prof_profile"
    assert store.persisted[-1]["entities"] == [
        {"kind": "professor", "id": "PROF-001", "label": "丁文伯"}
    ]
    assert store.persisted[-1]["turns"][0]["query"] == "介绍清华的丁文伯"

    second = chat_module.chat(
        chat_module.ChatRequest(query="他的论文"),
        response=Response(),
        miroflow_chat_session="test-chat-session-cookie",
        conn=object(),
    )

    assert second.query_type == "D_prof_papers_followup"
    assert lookup_names[-1] == "丁文伯"
    assert len(store.persisted) == 2
    assert store.persisted[-1]["turns"][-1]["query"] == "他的论文"
