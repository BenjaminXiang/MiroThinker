from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from fastapi import Response
import pytest

from backend.api import chat as chat_module


class _FakeSessionStore:
    def __init__(self) -> None:
        self.session = chat_module.SessionContext(session_id="company-layer-c-test")

    def get_or_create(self, session_id: str | None) -> chat_module.SessionContext:
        del session_id
        return self.session

    def persist(self, ctx: chat_module.SessionContext) -> None:
        self.session = ctx.model_copy(deep=True)


@pytest.fixture(autouse=True)
def _session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_module, "_SESSION_STORE", _FakeSessionStore())
    monkeypatch.setattr(chat_module, "_get_web_search_provider_or_none", lambda: None)


def test_company_topic_score_terms_use_specific_compound_without_generic_ai() -> None:
    groups = chat_module._company_topic_term_groups("深圳有哪些做具身智能的公司")

    assert ["AI", "人工智能", "智能"] in groups
    assert chat_module._company_topic_score_terms(
        "深圳有哪些做具身智能的公司",
        groups,
    ) == ["具身智能"]


@pytest.mark.parametrize("query", ["AI", "智能", "人工智能"])
def test_company_topic_score_terms_fall_back_for_pure_generic_ai(query: str) -> None:
    groups = chat_module._company_topic_term_groups(query)
    score_terms = chat_module._company_topic_score_terms(query, groups)

    assert "AI" in score_terms
    assert "人工智能" in score_terms
    assert "智能" in score_terms


def test_select_company_leaders_step1_ranks_caps_and_audit_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[dict[str, Any]] = []

    class _FakeCompletions:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "leaders": [
                                        {"index": 12, "reason": "leader 12"},
                                        {"index": 3, "reason": "leader 3"},
                                        {"index": 3, "reason": "duplicate"},
                                        {"index": 11, "reason": "leader 11"},
                                        {"index": 10, "reason": "leader 10"},
                                        {"index": 9, "reason": "leader 9"},
                                        {"index": 8, "reason": "leader 8"},
                                        {"index": 7, "reason": "leader 7"},
                                        {"index": 6, "reason": "leader 6"},
                                        {"index": 5, "reason": "leader 5"},
                                        {"index": 4, "reason": "leader 4"},
                                        {"index": 2, "reason": "over cap"},
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        )
                    )
                ]
            )

    class _FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(
        chat_module,
        "resolve_professor_llm_settings",
        lambda _profile, include_profile=True: {
            "local_llm_base_url": "http://llm.test/v1",
            "local_llm_api_key": "test-key",
            "local_llm_model": "deepseek-test",
        },
    )
    monkeypatch.setattr(chat_module, "build_non_thinking_extra_body", lambda model: {"model": model})
    monkeypatch.setattr(chat_module, "OpenAI", _FakeOpenAI)
    candidates = [
        {
            "company_id": f"C{i}",
            "canonical_name": f"公司{i}",
            "business": f"具身智能业务{i}",
            "profile_summary": f"profile {i} " * 20,
            "core_score": i,
        }
        for i in range(1, 13)
    ]

    with caplog.at_level(logging.INFO, logger=chat_module.logger.name):
        selected = chat_module._select_company_leaders_step1(
            candidates,
            "深圳有哪些做具身智能的公司",
        )

    assert [row["company_id"] for row in selected] == [
        "C12",
        "C3",
        "C11",
        "C10",
        "C9",
        "C8",
        "C7",
        "C6",
        "C5",
        "C4",
    ]
    assert len(selected) == 10
    assert calls[0]["temperature"] == 0
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["extra_body"] == {"model": "deepseek-test"}
    assert "specific_term_count" in calls[0]["messages"][1]["content"]
    assert "company_topic_step1_selection" in caplog.text
    assert "公司12" in caplog.text


def test_select_company_leaders_step1_adds_specificity_topk_not_selected_by_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeCompletions:
        def create(self, **_kwargs: Any) -> Any:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "leaders": [
                                        {"index": 1, "reason": "recognized 1"},
                                        {"index": 2, "reason": "recognized 2"},
                                        {"index": 2, "reason": "duplicate 2"},
                                        {"index": 3, "reason": "recognized 3"},
                                        {"index": 6, "reason": "recognized 6"},
                                        {"index": 7, "reason": "recognized 7"},
                                        {"index": 8, "reason": "recognized 8"},
                                        {"index": 9, "reason": "recognized 9"},
                                        {"index": 10, "reason": "recognized 10"},
                                        {"index": 11, "reason": "recognized 11"},
                                        {"index": 12, "reason": "recognized 12"},
                                        {"index": 16, "reason": "over cap"},
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        )
                    )
                ]
            )

    class _FakeOpenAI:
        def __init__(self, **_kwargs: Any) -> None:
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(
        chat_module,
        "resolve_professor_llm_settings",
        lambda _profile, include_profile=True: {
            "local_llm_base_url": "http://llm.test/v1",
            "local_llm_api_key": "test-key",
            "local_llm_model": "deepseek-test",
        },
    )
    monkeypatch.setattr(chat_module, "build_non_thinking_extra_body", lambda _model: {})
    monkeypatch.setattr(chat_module, "OpenAI", _FakeOpenAI)
    candidates = [
        {
            "company_id": f"C{i}",
            "canonical_name": f"公司{i}",
            "business": f"业务{i}",
            "profile_summary": f"公司{i} profile",
            "core_score": {
                4: 50,
                5: 45,
                13: 40,
                14: 35,
                15: 30,
            }.get(i, 1),
        }
        for i in range(1, 19)
    ]

    selected = chat_module._select_company_leaders_step1(
        candidates,
        "深圳有哪些做具身智能的公司",
    )

    assert [row["company_id"] for row in selected] == [
        "C1",
        "C2",
        "C3",
        "C6",
        "C7",
        "C8",
        "C9",
        "C10",
        "C11",
        "C12",
        "C4",
        "C5",
        "C13",
        "C14",
        "C15",
    ]
    assert len(selected) == 15
    assert [row["leader_selection_rank"] for row in selected] == list(range(1, 16))
    assert [row["company_id"] for row in selected].count("C2") == 1
    assert selected[10]["leader_selection_reason"] == "高主题相关度(具体主题词 top-K)"


def test_select_company_leaders_step1_fallback_also_adds_specificity_topk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_settings(_profile: object, include_profile: bool = True) -> dict[str, str]:
        del include_profile
        raise RuntimeError("selector unavailable")

    monkeypatch.setattr(chat_module, "resolve_professor_llm_settings", _raise_settings)
    candidates = [
        {
            "company_id": f"C{i}",
            "canonical_name": f"公司{i}",
            "business": f"业务{i}",
            "profile_summary": f"公司{i} profile",
            "core_score": {
                14: 50,
                15: 45,
                16: 40,
                4: 35,
                5: 30,
            }.get(i, 1),
        }
        for i in range(1, 17)
    ]

    selected = chat_module._select_company_leaders_step1(
        candidates,
        "深圳有哪些做具身智能的公司",
    )

    assert [row["company_id"] for row in selected] == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
        "C8",
        "C9",
        "C10",
        "C14",
        "C15",
        "C16",
    ]
    assert selected[10]["leader_selection_rank"] == 11
    assert selected[10]["leader_selection_reason"] == "高主题相关度(具体主题词 top-K)"


def test_b_company_topic_selects_before_enriching_and_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "on")
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: False)
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "B",
            "topic": "具身智能",
            "name": "",
            "target_domain": "company",
            "reason": "test",
        },
    )
    candidates = [
        {
            "company_id": f"C{i}",
            "canonical_name": f"公司{i}",
            "industry": "机器人",
            "business": f"具身智能业务{i}",
            "profile_summary": f"公司{i} profile",
            "snippet": f"公司{i} snippet",
            "core_score": i,
            "total_count": 45,
        }
        for i in range(1, 46)
    ]
    selected_ids = ["C40", "C3", "C11"]
    selector_seen: dict[str, Any] = {}

    def _select(cands: list[dict], query: str) -> list[dict]:
        selector_seen["candidate_count"] = len(cands)
        selector_seen["query"] = query
        by_id = {row["company_id"]: row for row in cands}
        return [by_id[cid] for cid in selected_ids]

    enriched_ids: list[str] = []

    def _company_rich(_conn: Any, cid: str) -> dict[str, Any]:
        enriched_ids.append(cid)
        return {"company_products": [f"{cid} flagship"]}

    synthesis_seen: dict[str, str] = {}

    def _synthesis(query: str, evidence_text: str, **_kwargs: Any) -> str:
        synthesis_seen["query"] = query
        synthesis_seen["evidence_text"] = evidence_text
        return "合成回答 [1]"

    monkeypatch.setattr(chat_module, "_lookup_companies_by_topic", lambda _conn, *, topic: candidates)
    monkeypatch.setattr(chat_module, "_select_company_leaders_step1", _select)
    monkeypatch.setattr(chat_module, "_company_rich_facts", _company_rich)
    monkeypatch.setattr(chat_module, "_call_gemma_synthesis", _synthesis)

    response = chat_module.chat(
        chat_module.ChatRequest(query="深圳有哪些做具身智能的公司"),
        response=Response(),
        conn=object(),
    )

    assert selector_seen == {
        "candidate_count": 45,
        "query": "深圳有哪些做具身智能的公司",
    }
    assert [row["company_id"] for row in response.structured_payload["matched_objects"]] == selected_ids
    assert enriched_ids == selected_ids
    assert "公司40" in synthesis_seen["evidence_text"]
    assert "C40 flagship" in synthesis_seen["evidence_text"]
    assert "公司2：" not in synthesis_seen["evidence_text"]
    assert [citation.id for citation in response.citations] == selected_ids
