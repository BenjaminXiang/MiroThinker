from __future__ import annotations

from typing import Any

import pytest
from fastapi import Response

from backend.api import chat as chat_module
from backend.services.chat_context import detect_set_operation


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, chat_module.SessionContext] = {}

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        key = session_id or "set-traversal-session"
        self.sessions.setdefault(key, chat_module.SessionContext(session_id=key))
        return self.sessions[key]

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.sessions[ctx.session_id] = ctx.model_copy(deep=True)


class _FakeRetrievalService:
    def __init__(
        self,
        *,
        related: dict[tuple[str, str, str], list[dict[str, Any]]] | None = None,
        objects: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.related = related or {}
        self.objects = objects or {}
        self.related_calls: list[dict[str, Any]] = []
        self.object_calls: list[dict[str, Any]] = []

    def get_related_objects(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.related_calls.append(kwargs)
        key = (
            str(kwargs["source_domain"]),
            str(kwargs["source_id"]),
            str(kwargs["target_domain"]),
        )
        return list(self.related.get(key, []))

    def get_object(self, **kwargs: Any) -> dict[str, Any] | None:
        self.object_calls.append(kwargs)
        return self.objects.get((str(kwargs["domain"]), str(kwargs["object_id"])))


@pytest.fixture(autouse=True)
def _disable_llm_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setenv("CHAT_QUERY_CLASSIFIER", "off")


def _seed_professor_set(
    store: _FakeSessionStore,
    ids: list[str],
    *,
    session_id: str = "set-traversal-session",
) -> chat_module.SessionContext:
    session = chat_module.SessionContext(session_id=session_id)
    session.push_result_set("professor", ids)
    store.sessions[session_id] = session
    return session


@pytest.mark.parametrize(
    ("query", "source_domain", "expected"),
    [
        ("上述教授参与的企业", "professor", ("traverse", "company")),
        ("这些教授发表了哪些论文", "professor", ("traverse", "paper")),
        ("这些公司有哪些专利", "company", ("traverse", "patent")),
        ("上述论文关联的教授", "paper", ("traverse", "professor")),
        ("上述教授的研究方向", "professor", ("narrow", None)),
        ("这些公司企业信息", "company", ("narrow", None)),
        ("这些教授的论文和专利", "professor", ("narrow", None)),
        ("他们有哪些项目", "professor", ("narrow", None)),
    ],
)
def test_detect_set_operation_matrix(
    query: str,
    source_domain: str,
    expected: tuple[str, str | None],
) -> None:
    assert detect_set_operation(query, source_domain) == expected


def test_related_row_to_chat_row_preserves_link_metadata() -> None:
    row = chat_module._related_row_to_chat_row(
        "company",
        {
            "company_id": "COMP-A",
            "canonical_name": "未来机器人",
            "role_type": "founder",
            "link_status": "candidate",
            "match_reason": "professor bio mentions founder role",
        },
    )

    assert row["role_type"] == "founder"
    assert row["link_status"] == "candidate"
    assert row["match_reason"] == "professor bio mentions founder role"


def test_set_traversal_target_centric_render_payload_and_chaining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    _seed_professor_set(store, ["PROF-1", "PROF-2", "PROF-EMPTY"])
    service = _FakeRetrievalService(
        objects={
            ("professor", "PROF-1"): {
                "professor_id": "PROF-1",
                "canonical_name": "李明",
            },
            ("professor", "PROF-2"): {
                "professor_id": "PROF-2",
                "canonical_name": "王强",
            },
            ("professor", "PROF-EMPTY"): {
                "professor_id": "PROF-EMPTY",
                "canonical_name": "赵空",
            },
        },
        related={
            ("professor", "PROF-1", "company"): [
                {
                    "company_id": "COMP-A",
                    "canonical_name": "未来机器人",
                    "role_type": "founder",
                    "link_status": "verified",
                    "match_reason": "official profile",
                },
                {
                    "company_id": "COMP-B",
                    "canonical_name": "湾区智能",
                    "role_type": "advisor",
                    "link_status": "candidate",
                    "match_reason": "news mention",
                },
            ],
            ("professor", "PROF-2", "company"): [
                {
                    "company_id": "COMP-A",
                    "canonical_name": "未来机器人",
                    "role_type": "scientific_advisor",
                    "link_status": "candidate",
                    "match_reason": "company page",
                }
            ],
        },
    )
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)
    monkeypatch.setattr(
        chat_module,
        "_lookup_narrowed_results",
        lambda *_args, **_kwargs: pytest.fail("set traversal must not use D narrowing"),
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="上述教授参与的企业"),
        response=Response(),
        miroflow_chat_session="set-traversal-session",
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_related"
    assert (
        "上轮 3 位教授中，2 位有企业关联记录，共涉及 2 个企业。其余 1 位暂无收录。"
        in response.answer_text
    )
    assert response.answer_text.count("未来机器人") == 1
    assert "李明（founder, verified）" in response.answer_text
    assert "王强（scientific_advisor, 候选）" in response.answer_text
    assert "湾区智能" in response.answer_text
    assert "李明（advisor, 候选）" in response.answer_text
    assert "暂无收录：赵空" in response.answer_text
    assert [citation.id for citation in response.citations] == ["COMP-A", "COMP-B"]
    assert store.sessions["set-traversal-session"].latest_result_domain() == "company"
    assert store.sessions["set-traversal-session"].last_result_set["company"] == [
        "COMP-A",
        "COMP-B",
    ]
    assert response.structured_payload["source_domain"] == "professor"
    assert response.structured_payload["source_ids"] == [
        "PROF-1",
        "PROF-2",
        "PROF-EMPTY",
    ]
    assert response.structured_payload["target_domain"] == "company"
    assert response.structured_payload["member_target_mapping"][2] == {
        "member_id": "PROF-EMPTY",
        "member_label": "赵空",
        "targets": [],
    }
    assert {
        row["company_id"] for row in response.structured_payload["retrieval_evidence"]
    } == {"COMP-A", "COMP-B"}
    assert service.related_calls == [
        {
            "source_domain": "professor",
            "source_id": "PROF-1",
            "target_domain": "company",
            "limit": 5,
        },
        {
            "source_domain": "professor",
            "source_id": "PROF-2",
            "target_domain": "company",
            "limit": 5,
        },
        {
            "source_domain": "professor",
            "source_id": "PROF-EMPTY",
            "target_domain": "company",
            "limit": 5,
        },
    ]


def test_set_traversal_member_centric_when_query_says_fenbie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    _seed_professor_set(store, ["PROF-1", "PROF-EMPTY"])
    service = _FakeRetrievalService(
        objects={
            ("professor", "PROF-1"): {
                "professor_id": "PROF-1",
                "canonical_name": "李明",
            },
            ("professor", "PROF-EMPTY"): {
                "professor_id": "PROF-EMPTY",
                "canonical_name": "赵空",
            },
        },
        related={
            ("professor", "PROF-1", "company"): [
                {
                    "company_id": "COMP-A",
                    "canonical_name": "未来机器人",
                    "role_type": "founder",
                    "link_status": "verified",
                }
            ],
        },
    )
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)

    response = chat_module.chat(
        chat_module.ChatRequest(query="他们分别参与了哪些企业"),
        response=Response(),
        miroflow_chat_session="set-traversal-session",
        conn=object(),
    )

    assert response.query_type == "C_cross_domain_related"
    assert "李明：未来机器人（founder, verified）" in response.answer_text
    assert "赵空：暂无收录" in response.answer_text
    assert (
        "上轮 2 位教授中，1 位有企业关联记录，共涉及 1 个企业。其余 1 位暂无收录。"
        in response.answer_text
    )


def test_set_traversal_caps_source_ids_to_ten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    ids = [f"PROF-{index:02d}" for index in range(12)]
    _seed_professor_set(store, ids)
    service = _FakeRetrievalService(
        objects={
            ("professor", object_id): {
                "professor_id": object_id,
                "canonical_name": object_id,
            }
            for object_id in ids
        }
    )
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)

    response = chat_module.chat(
        chat_module.ChatRequest(query="上述教授参与的企业"),
        response=Response(),
        miroflow_chat_session="set-traversal-session",
        conn=object(),
    )

    assert len(service.related_calls) == 10
    assert response.structured_payload["source_ids"] == ids[:10]
    assert "本次仅处理前 10 位教授" in response.answer_text


def test_set_traversal_chains_to_target_domain_for_next_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeSessionStore()
    _seed_professor_set(store, ["PROF-1"])
    service = _FakeRetrievalService(
        objects={
            ("professor", "PROF-1"): {
                "professor_id": "PROF-1",
                "canonical_name": "李明",
            },
            ("company", "COMP-A"): {
                "company_id": "COMP-A",
                "canonical_name": "未来机器人",
            },
            ("company", "COMP-B"): {
                "company_id": "COMP-B",
                "canonical_name": "湾区智能",
            },
        },
        related={
            ("professor", "PROF-1", "company"): [
                {
                    "company_id": "COMP-A",
                    "canonical_name": "未来机器人",
                    "role_type": "founder",
                    "link_status": "verified",
                },
                {
                    "company_id": "COMP-B",
                    "canonical_name": "湾区智能",
                    "role_type": "advisor",
                    "link_status": "candidate",
                },
            ],
            ("company", "COMP-A", "patent"): [
                {
                    "patent_id": "PAT-1",
                    "patent_number": "CN202400001",
                    "title_clean": "机器人控制方法",
                    "link_status": "verified",
                    "link_role": "applicant",
                }
            ],
        },
    )
    monkeypatch.setattr(chat_module, "_SESSION_STORE", store)
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)

    first = chat_module.chat(
        chat_module.ChatRequest(query="上述教授参与的企业"),
        response=Response(),
        miroflow_chat_session="set-traversal-session",
        conn=object(),
    )
    second = chat_module.chat(
        chat_module.ChatRequest(query="这些公司有哪些专利"),
        response=Response(),
        miroflow_chat_session="set-traversal-session",
        conn=object(),
    )

    assert [citation.id for citation in first.citations] == ["COMP-A", "COMP-B"]
    assert second.query_type == "C_cross_domain_related"
    assert second.structured_payload["source_domain"] == "company"
    assert second.structured_payload["source_ids"] == ["COMP-A", "COMP-B"]
    assert [citation.id for citation in second.citations] == ["PAT-1"]
    assert store.sessions["set-traversal-session"].latest_result_domain() == "patent"
    assert store.sessions["set-traversal-session"].last_result_set["patent"] == [
        "PAT-1"
    ]
