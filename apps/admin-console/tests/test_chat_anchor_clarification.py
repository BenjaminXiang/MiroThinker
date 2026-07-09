from __future__ import annotations

from typing import Any

import pytest
from fastapi import Response

from backend.api import chat as chat_module


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, chat_module.SessionContext] = {}

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        key = session_id or "anchor-clarification-session"
        self.sessions.setdefault(key, chat_module.SessionContext(session_id=key))
        return self.sessions[key]

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.sessions[ctx.session_id] = ctx.model_copy(deep=True)


class _FakeRetrievalService:
    def __init__(self, objects: dict[tuple[str, str], dict[str, Any]] | None = None) -> None:
        self.objects = objects or {}
        self.object_calls: list[dict[str, Any]] = []
        self.related_calls: list[dict[str, Any]] = []

    def get_object(self, **kwargs: Any) -> dict[str, Any] | None:
        self.object_calls.append(kwargs)
        return self.objects.get((str(kwargs["domain"]), str(kwargs["object_id"])))

    def get_related_objects(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.related_calls.append(kwargs)
        return []


@pytest.fixture(autouse=True)
def _disable_external_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_AUGMENT_WEB", "0")
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setenv("CHAT_QUERY_CLASSIFIER", "off")


def _professor_list_rows() -> list[dict[str, Any]]:
    return [
        {
            "professor_id": "PROF-LI",
            "canonical_name": "李明",
            "institution": "南方科技大学",
            "matched_topics": ["力控"],
            "total_count": 2,
        },
        {
            "professor_id": "PROF-ZHANG",
            "canonical_name": "张敏",
            "institution": "南方科技大学",
            "matched_topics": ["力控"],
            "total_count": 2,
        },
    ]


def _install_professor_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_module,
        "_lookup_professors_by_topic",
        lambda _conn, *, institutions, topic, limit: _professor_list_rows(),
    )


def _install_professor_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def lookup_professor(
        _conn: Any, *, name: str, institutions: tuple[str, ...] | None
    ) -> list[dict[str, Any]]:
        del institutions
        if name == "丁文伯":
            return [
                {
                    "professor_id": "PROF-DING",
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
                "paper_id": "PAPER-DING-1",
                "title_clean": "Robot Force Control",
                "year": 2025,
                "venue": "ICRA",
                "citation_count": 10,
                "topic_consistency_score": 0.9,
                "total_count": 1,
            }
        ],
    )


def test_member_listing_clarification_lists_live_set_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    service = _FakeRetrievalService(
        {
            ("professor", "PROF-LI"): {
                "professor_id": "PROF-LI",
                "canonical_name": "李明",
                "institution": "南方科技大学",
            },
            ("professor", "PROF-ZHANG"): {
                "professor_id": "PROF-ZHANG",
                "canonical_name": "张敏",
                "institution": "南方科技大学",
            },
        }
    )
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)
    _install_professor_list(monkeypatch)

    first = chat_module.chat(
        chat_module.ChatRequest(query="南科大做力控的教授"),
        response=Response(),
        miroflow_chat_session="anchor-clarification-session",
        conn=object(),
    )

    assert first.query_type == "A_prof_list_by_topic"
    assert store.sessions["anchor-clarification-session"].latest_for("professor") is None

    second = chat_module.chat(
        chat_module.ChatRequest(query="他的论文是哪些"),
        response=Response(),
        miroflow_chat_session="anchor-clarification-session",
        conn=object(),
    )

    assert second.query_type == "C_cross_domain_clarification"
    assert "李明" in second.answer_text
    assert "张敏" in second.answer_text
    assert second.structured_payload is not None
    assert second.structured_payload["referent_domain"] == "professor"
    assert second.structured_payload["candidate_ids"] == ["PROF-LI", "PROF-ZHANG"]
    assert (
        second.structured_payload["clarification_reason"]
        == "singular_pronoun_no_anchor_live_set"
    )
    assert service.object_calls == [
        {"domain": "professor", "object_id": "PROF-LI"},
        {"domain": "professor", "object_id": "PROF-ZHANG"},
    ]
    assert service.related_calls == []


def test_profile_then_singular_pronoun_resolves_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    _install_professor_profile(monkeypatch)

    first = chat_module.chat(
        chat_module.ChatRequest(query="介绍清华的丁文伯"),
        response=Response(),
        miroflow_chat_session="anchor-profile-session",
        conn=object(),
    )

    assert first.query_type == "A_prof_profile"
    assert store.sessions["anchor-profile-session"].latest_for("professor") is not None

    second = chat_module.chat(
        chat_module.ChatRequest(query="他的论文"),
        response=Response(),
        miroflow_chat_session="anchor-profile-session",
        conn=object(),
    )

    assert second.query_type == "D_prof_papers_followup"
    assert second.structured_payload is not None
    assert second.structured_payload["professor_id"] == "PROF-DING"
    assert "Robot Force Control" in second.answer_text


def test_list_answers_leave_no_anchor_but_profile_answers_push_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    _install_professor_list(monkeypatch)
    _install_professor_profile(monkeypatch)

    list_response = chat_module.chat(
        chat_module.ChatRequest(query="南科大做力控的教授"),
        response=Response(),
        miroflow_chat_session="anchor-discipline-session",
        conn=object(),
    )

    assert list_response.query_type == "A_prof_list_by_topic"
    ctx = store.sessions["anchor-discipline-session"]
    assert ctx.last_result_set["professor"] == ["PROF-LI", "PROF-ZHANG"]
    assert ctx.latest_for("professor") is None

    profile_response = chat_module.chat(
        chat_module.ChatRequest(query="介绍清华的丁文伯"),
        response=Response(),
        miroflow_chat_session="anchor-discipline-session",
        conn=object(),
    )

    assert profile_response.query_type == "A_prof_profile"
    anchor = store.sessions["anchor-discipline-session"].latest_for("professor")
    assert anchor is not None
    assert anchor.id == "PROF-DING"
    assert anchor.label == "丁文伯"


def test_singular_pronoun_without_live_set_uses_generic_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    service = _FakeRetrievalService()
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)

    response = chat_module.chat(
        chat_module.ChatRequest(query="他的论文"),
        response=Response(),
        miroflow_chat_session="no-live-set-session",
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_clarification"
    assert "请先确认要查询哪一个实体" in response.answer_text
    assert "李明" not in response.answer_text
    assert "张敏" not in response.answer_text
    assert response.structured_payload == {"target_domain": "paper"}
    assert service.object_calls == []
    assert service.related_calls == []
