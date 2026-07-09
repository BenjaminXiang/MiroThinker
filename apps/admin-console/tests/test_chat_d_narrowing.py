from __future__ import annotations

from typing import Any

import pytest
from fastapi import Response

from backend.api import chat as chat_module


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, chat_module.SessionContext] = {}

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        key = session_id or "w11-3-session"
        self.sessions.setdefault(key, chat_module.SessionContext(session_id=key))
        return self.sessions[key]

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.sessions[ctx.session_id] = ctx.model_copy(deep=True)


def test_session_context_push_result_set_caps_and_preserves_domains() -> None:
    ctx = chat_module.SessionContext(session_id="s1")

    ctx.push_result_set("professor", [f"PROF-{i:03d}" for i in range(105)])
    ctx.push_result_set("company", ["COMP-001"])

    assert len(ctx.last_result_set["professor"]) == 100
    assert ctx.last_result_set["professor"][0] == "PROF-000"
    assert ctx.last_result_set["professor"][-1] == "PROF-099"
    assert ctx.last_result_set["company"] == ["COMP-001"]


def test_professor_list_pushes_last_result_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(
        chat_module,
        "_lookup_professors_by_topic",
        lambda _conn, *, institutions, topic, limit: [
            {
                "professor_id": "PROF-001",
                "canonical_name": "李明",
                "institution": "南方科技大学",
                "matched_topics": ["力控"],
                "total_count": 2,
            },
            {
                "professor_id": "PROF-002",
                "canonical_name": "张敏",
                "institution": "南方科技大学",
                "matched_topics": ["力控"],
                "total_count": 2,
            },
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="南科大做力控的教授"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_prof_list_by_topic"
    ctx = store.sessions["w11-3-session"]
    assert ctx.last_result_set["professor"] == ["PROF-001", "PROF-002"]


def test_institution_topic_list_hydrates_and_filters_retrieval_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "on")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: True)

    class _FakeRetrievalService:
        def retrieve(self, **kwargs: Any):
            assert kwargs["query"] == "信息论编码"
            assert kwargs["domains"] == ("professor",)
            assert kwargs["filters"] == {"institution": "清华大学深圳国际研究生院"}
            return [
                chat_module.Evidence(
                    object_type="professor",
                    object_id="PROF-TSINGHUA",
                    score=0.91,
                    snippet="信息论编码",
                    source_url=None,
                    metadata={"name": "", "institution": ""},
                ),
                chat_module.Evidence(
                    object_type="professor",
                    object_id="PROF-SZU",
                    score=0.88,
                    snippet="信息论编码",
                    source_url=None,
                    metadata={"name": "深圳大学候选", "institution": "深圳大学"},
                ),
            ]

    def lookup_by_id(_conn: Any, *, professor_id: str):
        return {
            "PROF-TSINGHUA": {
                "professor_id": "PROF-TSINGHUA",
                "canonical_name": "夏树涛",
                "institution": "清华大学深圳国际研究生院",
                "title": "教授",
                "discipline_family": "信息科学",
                "h_index": 12,
                "citation_count": 345,
                "paper_count": 67,
            },
            "PROF-SZU": {
                "professor_id": "PROF-SZU",
                "canonical_name": "深圳大学候选",
                "institution": "深圳大学",
                "title": "教授",
                "discipline_family": "信息科学",
                "h_index": 10,
                "citation_count": 200,
                "paper_count": 40,
            },
        }.get(professor_id)

    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: _FakeRetrievalService())
    monkeypatch.setattr(chat_module, "_lookup_professor_by_id", lookup_by_id)
    monkeypatch.setattr(chat_module, "_prof_rich_profile_facts", lambda *_args: {})

    response = chat_module.chat(
        chat_module.ChatRequest(query="找清华大学深圳国际研究生院做信息论编码的教授"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_prof_list_by_topic"
    assert "夏树涛" in response.answer_text
    assert "深圳大学候选" not in response.answer_text
    assert response.citations[0].label == "夏树涛 - 清华大学深圳国际研究生院"
    assert response.structured_payload["matched_professors"] == [
        {
            "professor_id": "PROF-TSINGHUA",
            "canonical_name": "夏树涛",
            "institution": "清华大学深圳国际研究生院",
            "matched_topics": [],
            "h_index": 12,
            "citation_count": 345,
            "paper_count": 67,
        }
    ]


def test_institution_topic_list_falls_back_to_sql_when_retrieval_rows_filter_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "on")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: True)

    class _FakeRetrievalService:
        def retrieve(self, **kwargs: Any):
            assert kwargs["query"] == "信息论编码"
            assert kwargs["filters"] == {"institution": "清华大学深圳国际研究生院"}
            return [
                chat_module.Evidence(
                    object_type="professor",
                    object_id="PROF-SZU",
                    score=0.88,
                    snippet="信息论编码",
                    source_url=None,
                    metadata={"name": "深圳大学候选", "institution": "深圳大学"},
                )
            ]

    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: _FakeRetrievalService())
    monkeypatch.setattr(chat_module, "_prof_rich_profile_facts", lambda *_args: {})
    monkeypatch.setattr(
        chat_module,
        "_lookup_professors_by_topic_sql",
        lambda _conn, *, institutions, topic, limit: [
            {
                "professor_id": "PROF-TSINGHUA",
                "canonical_name": "夏树涛",
                "institution": "清华大学深圳国际研究生院",
                "matched_topics": ["• 信息论编码"],
                "h_index": 12,
                "citation_count": 345,
                "paper_count": 67,
                "total_count": 1,
            }
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="找清华大学深圳国际研究生院做信息论编码的教授"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "A_prof_list_by_topic"
    assert "夏树涛" in response.answer_text
    assert "深圳大学候选" not in response.answer_text
    assert response.structured_payload["matched_professors"][0]["matched_topics"] == [
        "• 信息论编码"
    ]


def test_d_narrowing_filters_last_result_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    session = chat_module.SessionContext(session_id="w11-3-session")
    session.push_result_set("professor", ["PROF-001", "PROF-002", "PROF-003"])
    store.sessions[session.session_id] = session

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)

    def narrow(
        _conn: Any,
        *,
        domain: str,
        allowed_ids: list[str],
        topic: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        assert domain == "professor"
        assert allowed_ids == ["PROF-001", "PROF-002", "PROF-003"]
        assert topic == "大模型"
        return [
            {
                "type": "professor",
                "id": "PROF-002",
                "professor_id": "PROF-002",
                "canonical_name": "张敏",
                "institution": "南方科技大学",
            }
        ]

    monkeypatch.setattr(chat_module, "_lookup_narrowed_results", narrow)

    response = chat_module.chat(
        chat_module.ChatRequest(query="其中做大模型的"),
        response=Response(),
        miroflow_chat_session="w11-3-session",
        conn=object(),
    )

    assert response.query_type == "D_narrowing"
    assert "张敏" in response.answer_text
    assert store.sessions["w11-3-session"].last_result_set["professor"] == ["PROF-002"]


def test_d_narrowing_without_result_set_falls_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setenv("CHAT_QUERY_CLASSIFIER", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)

    response = chat_module.chat(
        chat_module.ChatRequest(query="其中做大模型的"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "unknown"
    assert "v0" not in response.answer_text
    assert "教授、企业、论文、专利" in response.answer_text
