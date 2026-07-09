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


class _ResetSessionStore:
    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        assert session_id is None
        return chat_module.SessionContext(session_id="fresh-session-id")


def test_chat_session_reset_issues_fresh_session_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_module, "_SESSION_STORE", _ResetSessionStore())

    response = Response()
    payload = chat_module.reset_chat_session(response=response)

    assert payload.session_id == "fresh-session-id"
    cookie = response.headers["set-cookie"]
    assert "miroflow_chat_session=fresh-session-id" in cookie
    assert "HttpOnly" in cookie
    assert "Max-Age=1800" in cookie


@pytest.mark.parametrize("followup_query", ["他的论文", "看看他的论文"])
def test_chat_persists_professor_context_for_pronoun_followup(
    monkeypatch: pytest.MonkeyPatch,
    followup_query: str,
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
        chat_module.ChatRequest(query=followup_query),
        response=Response(),
        miroflow_chat_session="test-chat-session-cookie",
        conn=object(),
    )

    assert second.query_type == "D_prof_papers_followup"
    assert lookup_names[-1] == "丁文伯"
    assert len(store.persisted) == 2
    assert store.persisted[-1]["turns"][-1]["query"] == followup_query


@pytest.mark.parametrize("query", ["夏树涛是谁？", "夏树涛是谁?"])
def test_named_professor_who_query_with_question_mark_routes_profile(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    store = _FakeSessionStore()
    lookup_names: list[str] = []

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setenv("CHAT_QUERY_CLASSIFIER", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)

    def lookup_professor(
        _conn: Any, *, name: str, institutions: tuple[str, ...] | None
    ) -> list[dict[str, Any]]:
        del institutions
        lookup_names.append(name)
        if name == "夏树涛":
            return [
                {
                    "professor_id": "PROF-XIA",
                    "canonical_name": "夏树涛",
                    "institution": "清华大学深圳国际研究生院",
                    "title": "教授",
                }
            ]
        return []

    monkeypatch.setattr(chat_module, "_lookup_professor", lookup_professor)
    monkeypatch.setattr(chat_module, "_prof_research_topics", lambda *_args: ["信息安全"])
    monkeypatch.setattr(chat_module, "_prof_paper_count", lambda *_args: 211)

    response = chat_module.chat(
        chat_module.ChatRequest(query=query),
        response=Response(),
        miroflow_chat_session=None,
        conn=object(),
    )

    assert response.query_type == "A_prof_profile"
    assert lookup_names[-1] == "夏树涛"
    assert response.structured_payload["professor_id"] == "PROF-XIA"
    assert response.structured_payload["verified_paper_count"] == 211


@pytest.mark.parametrize("query", ["夏树涛有哪些论文？", "夏树涛有哪些论文?"])
def test_named_professor_papers_query_with_question_mark_routes_to_prof_papers(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    store = _FakeSessionStore()
    lookup_names: list[str] = []

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setenv("CHAT_QUERY_CLASSIFIER", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)

    def lookup_professor(
        _conn: Any, *, name: str, institutions: tuple[str, ...] | None
    ) -> list[dict[str, Any]]:
        del institutions
        lookup_names.append(name)
        if name == "夏树涛":
            return [
                {
                    "professor_id": "PROF-XIA",
                    "canonical_name": "夏树涛",
                    "institution": "清华大学深圳国际研究生院",
                    "title": "教授",
                }
            ]
        return []

    monkeypatch.setattr(chat_module, "_lookup_professor", lookup_professor)
    monkeypatch.setattr(
        chat_module,
        "_lookup_verified_papers_for_prof",
        lambda *_args, **_kwargs: [
            {
                "paper_id": "PAPER-XIA-001",
                "title_clean": "Information Theoretic Security",
                "year": 2026,
                "venue": "IEEE Transactions",
                "citation_count": 12,
                "topic_consistency_score": 1.0,
                "total_count": 211,
            }
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query=query),
        response=Response(),
        miroflow_chat_session=None,
        conn=object(),
    )

    assert response.query_type == "D_prof_papers_followup"
    assert lookup_names[-1] == "夏树涛"
    assert response.structured_payload["professor_id"] == "PROF-XIA"
    assert response.structured_payload["paper_count"] == 211
    assert [citation.id for citation in response.citations] == ["PAPER-XIA-001"]


def test_institution_prefixed_professor_papers_query_routes_to_prof_papers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    lookup_calls: list[tuple[str, tuple[str, ...] | None]] = []

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setenv("CHAT_QUERY_CLASSIFIER", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)

    def lookup_professor(
        _conn: Any, *, name: str, institutions: tuple[str, ...] | None
    ) -> list[dict[str, Any]]:
        lookup_calls.append((name, institutions))
        if name == "王伟" and institutions == ("中山大学（深圳）",):
            return [
                {
                    "professor_id": "PROF-WANG",
                    "canonical_name": "王伟",
                    "institution": "中山大学（深圳）",
                    "title": "教授",
                }
            ]
        return []

    monkeypatch.setattr(chat_module, "_lookup_professor", lookup_professor)
    monkeypatch.setattr(
        chat_module,
        "_lookup_verified_papers_for_prof",
        lambda *_args, **_kwargs: [
            {
                "paper_id": "PAPER-WANG-001",
                "title_clean": "Adaptive Signal Processing for Radar",
                "year": 2024,
                "venue": "Signal Processing",
                "citation_count": 8,
                "topic_consistency_score": 1.0,
                "total_count": 3,
            }
        ],
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="中山大学深圳王伟教授有哪些论文？"),
        response=Response(),
        miroflow_chat_session=None,
        conn=object(),
    )

    assert response.query_type == "D_prof_papers_followup"
    assert lookup_calls[-1] == ("王伟", ("中山大学（深圳）",))
    assert response.structured_payload["professor_id"] == "PROF-WANG"
    assert response.structured_payload["paper_count"] == 3
    assert [citation.id for citation in response.citations] == ["PAPER-WANG-001"]


def test_institution_prefixed_professor_topics_query_resolves_institution_and_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    lookup_calls: list[tuple[str, tuple[str, ...] | None]] = []

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setenv("CHAT_QUERY_CLASSIFIER", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)

    def lookup_professor(
        _conn: Any, *, name: str, institutions: tuple[str, ...] | None
    ) -> list[dict[str, Any]]:
        lookup_calls.append((name, institutions))
        if name == "王伟" and institutions == ("中山大学（深圳）",):
            return [
                {
                    "professor_id": "PROF-WANG",
                    "canonical_name": "王伟",
                    "institution": "中山大学（深圳）",
                    "title": "教授",
                }
            ]
        return []

    monkeypatch.setattr(chat_module, "_lookup_professor", lookup_professor)
    monkeypatch.setattr(
        chat_module,
        "_prof_research_topics",
        lambda *_args: ["雷达信号处理", "抗干扰"],
    )
    monkeypatch.setattr(chat_module, "_prof_paper_count", lambda *_args: 0)

    response = chat_module.chat(
        chat_module.ChatRequest(query="中山大学深圳王伟教授的研究方向是什么？"),
        response=Response(),
        miroflow_chat_session=None,
        conn=object(),
    )

    assert response.query_type == "A_prof_profile"
    assert lookup_calls[-1] == ("王伟", ("中山大学（深圳）",))
    assert response.structured_payload["professor_id"] == "PROF-WANG"
    assert response.structured_payload["research_topics"] == ["雷达信号处理", "抗干扰"]


def test_independent_topic_switch_clears_previous_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    session = chat_module.SessionContext(session_id="test-chat-session-cookie")
    session.push_entity(
        chat_module.SessionEntity(
            kind="professor",
            id="PROF-001",
            label="丁文伯",
        )
    )
    session.push_result_set("professor", ["PROF-001"])
    store.sessions[session.session_id] = session
    seen: dict[str, str] = {}

    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)

    def lookup_by_topic(
        _conn: Any,
        *,
        domain: str,
        topic: str,
        limit: int,
        raw_query: str = "",
    ) -> list[dict[str, Any]]:
        seen["domain"] = domain
        seen["topic"] = topic
        seen["limit"] = str(limit)
        seen["raw_query"] = raw_query
        return [
            {
                "company_id": "COMP-001",
                "canonical_name": "速腾聚创",
                "industry": "激光雷达",
                "business": "激光雷达系统",
                "total_count": 1,
            }
        ]

    monkeypatch.setattr(chat_module, "_lookup_domain_by_topic", lookup_by_topic)
    # Web augmentation fires a real Serper search here and injects URL rows that
    # would pollute last_result_set["company"]; mock it to a no-op for determinism
    # (same pattern as 535ed9e for the paper-topic tests).
    monkeypatch.setattr(chat_module, "_augment_rows_with_web", lambda _q, rows, **_k: rows)

    response = chat_module.chat(
        chat_module.ChatRequest(query="对了，深圳哪些公司做激光雷达"),
        response=Response(),
        miroflow_chat_session="test-chat-session-cookie",
        conn=object(),
    )

    assert response.query_type == "B_company_topic_search"
    assert seen == {
        "domain": "company",
        "topic": "激光雷达",
        "limit": "20",
        "raw_query": "对了，深圳哪些公司做激光雷达",
    }
    persisted = store.persisted[-1]
    assert persisted["entities"] == []
    assert persisted["last_result_set"] == {"company": ["COMP-001"]}
    assert persisted["turns"][-1]["query"] == "对了，深圳哪些公司做激光雷达"
