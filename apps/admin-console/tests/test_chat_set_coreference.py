from __future__ import annotations

from typing import Any

import pytest
from fastapi import Response

from backend.api import chat as chat_module
from backend.services.chat_context import detect_set_referent, result_ids_by_domain


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, chat_module.SessionContext] = {}

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        key = session_id or "set-coref-session"
        self.sessions.setdefault(key, chat_module.SessionContext(session_id=key))
        return self.sessions[key]

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.sessions[ctx.session_id] = ctx.model_copy(deep=True)


@pytest.fixture(autouse=True)
def _disable_llm_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setenv("CHAT_QUERY_CLASSIFIER", "off")


def test_result_set_capture_ignores_undisplayed_retrieval_evidence() -> None:
    structured_payload: dict[str, Any] = {
        "professor_id": "PROF-PRIMARY",
        "company_id": "COMP-PRIMARY",
        "matched_professors": [{"professor_id": "PROF-LIST"}],
        "companies": [{"company_id": "COMP-LIST"}],
        "papers": [{"paper_id": "PAPER-LIST"}],
        "patents": [{"patent_id": "PAT-LIST"}],
        "retrieval_evidence": [
            {"type": "professor", "professor_id": "PROF-HIDDEN"},
            {"type": "company", "company_id": "COMP-HIDDEN"},
            {"type": "paper", "paper_id": "PAPER-HIDDEN"},
            {"type": "patent", "patent_id": "PAT-HIDDEN"},
        ],
    }
    citations = [
        chat_module.ChatCitation(
            type="professor",
            id="PROF-CITED",
            label="引用教授",
            url="/browse#professor/PROF-CITED",
        )
    ]

    ctx = chat_module.SessionContext(session_id="displayed-only")
    for domain, ids in result_ids_by_domain(structured_payload, citations).items():
        ctx.push_result_set(domain, ids)

    assert ctx.last_result_set == {
        "company": ["COMP-PRIMARY", "COMP-LIST"],
        "paper": ["PAPER-LIST"],
        "patent": ["PAT-LIST"],
        "professor": ["PROF-PRIMARY", "PROF-LIST", "PROF-CITED"],
    }


@pytest.mark.parametrize(
    ("query", "domain", "surface"),
    [
        ("他们发表了哪些论文", None, "他们"),
        ("这些有哪些专利", None, "这些"),
        ("上述哪些在深圳", None, "上述"),
        ("上面这些做大模型的是谁", None, "上面这些"),
        ("上述教授参与的企业", "professor", "上述教授"),
        ("这些教授发表了哪些论文", "professor", "这些教授"),
        ("上述公司有哪些专利", "company", "上述公司"),
        ("这些企业有哪些论文", "company", "这些企业"),
        ("上述论文的作者是谁", "paper", "上述论文"),
        ("这些专利的申请人是谁", "patent", "这些专利"),
    ],
)
def test_detect_set_referent_table_positives(
    query: str,
    domain: str | None,
    surface: str,
) -> None:
    referent = detect_set_referent(query)

    assert referent is not None
    assert referent.domain == domain
    assert referent.surface == surface


@pytest.mark.parametrize(
    "query",
    [
        "他的论文",
        "她参与的企业",
        "这位教授的专利",
        "这家公司有哪些专利",
        "这篇论文的作者是谁",
        "这论文的作者是谁",
        "该篇论文的作者是谁",
        "该专利的申请人是谁",
    ],
)
def test_detect_set_referent_does_not_match_singular_pronouns(query: str) -> None:
    assert detect_set_referent(query) is None


def test_explicit_domain_set_referent_with_empty_domain_clarifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    session = chat_module.SessionContext(session_id="set-coref-session")
    session.push_result_set("company", ["COMP-001", "COMP-002"])
    store.sessions[session.session_id] = session
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(
        chat_module,
        "_lookup_narrowed_results",
        lambda *_args, **_kwargs: pytest.fail("narrowing should not run"),
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="上述教授参与的企业"),
        response=Response(),
        miroflow_chat_session="set-coref-session",
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_clarification"
    assert "当前上下文没有可指代的教授列表" in response.answer_text
    assert "请先检索" in response.answer_text
    assert "企业" in response.answer_text
    assert response.structured_payload == {
        "referent_domain": "professor",
        "available_result_set_domains": ["company"],
    }


def test_bare_set_referent_without_any_result_set_clarifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)

    response = chat_module.chat(
        chat_module.ChatRequest(query="他们发表了哪些论文"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_clarification"
    assert "当前上下文没有可指代的结果列表" in response.answer_text
    assert "请先检索" in response.answer_text
    assert response.structured_payload == {
        "referent_domain": None,
        "available_result_set_domains": [],
    }


def test_session_resolves_set_referent_to_existing_domain_set() -> None:
    ctx = chat_module.SessionContext(session_id="resolve-set")
    ctx.push_result_set("company", ["COMP-001"])
    ctx.push_result_set("professor", ["PROF-001", "PROF-002"])

    explicit = detect_set_referent("上述公司有哪些专利")
    bare = detect_set_referent("他们有哪些论文")

    assert explicit is not None
    assert bare is not None
    assert ctx.resolve_set_referent(explicit) == ("company", ["COMP-001"])
    assert ctx.resolve_set_referent(bare) == ("professor", ["PROF-001", "PROF-002"])


def test_zhe_lunwen_pronoun_rewrites_to_latest_paper() -> None:
    ctx = chat_module.SessionContext(session_id="paper-pronoun")
    ctx.push_entity(
        chat_module.SessionEntity(
            kind="paper",
            id="PAPER-001",
            label="可解释图学习论文",
        )
    )

    assert (
        chat_module._rewrite_query_with_context("这论文的作者是谁", ctx)
        == "可解释图学习论文的作者是谁"
    )
    assert (
        chat_module._rewrite_query_with_context("该篇论文的作者是谁", ctx)
        == "可解释图学习论文的作者是谁"
    )
