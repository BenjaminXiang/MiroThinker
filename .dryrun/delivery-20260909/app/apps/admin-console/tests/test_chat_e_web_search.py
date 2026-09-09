from __future__ import annotations

from typing import Any

import pytest
from fastapi import Response

from backend.api import chat as chat_module


class _FakeCache:
    def __init__(self, cached: list[dict] | None = None) -> None:
        self.cached = cached
        self.set_calls: list[tuple[str, list[dict]]] = []

    def get(self, query: str, provider: str = "serper") -> list[dict] | None:
        del provider
        return self.cached

    def set(self, query: str, results: list[dict], *, provider: str = "serper") -> None:
        del provider
        self.set_calls.append((query, results))


class _FakeProvider:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.api_key = "serper-key"
        self.payload = payload or {"organic": []}
        self.calls: list[str] = []

    def search(self, query: str) -> dict[str, Any]:
        self.calls.append(query)
        return self.payload


def _organic(title: str, link: str = "https://example.com") -> dict[str, str]:
    return {"title": title, "link": link, "snippet": f"{title} snippet"}


def test_e_web_search_cache_hit_skips_serper(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _FakeCache(cached=[_organic("GAN overview")])
    provider = _FakeProvider()
    monkeypatch.setattr(chat_module, "_get_web_search_cache", lambda: cache)
    monkeypatch.setattr(chat_module, "_get_web_search_provider_or_none", lambda: provider)
    monkeypatch.setattr(
        chat_module,
        "_call_gemma_synthesis",
        lambda query, evidence_text, timeout: "GAN 是生成对抗网络[1]。",
    )

    answer, err, evidence = chat_module._answer_knowledge_qa_with_web_search("什么是 GAN")

    assert err is None
    assert "GAN" in answer
    assert evidence[0]["source_type"] == "web"
    assert provider.calls == []
    assert cache.set_calls == []


def test_e_web_search_cold_path_sets_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _FakeCache()
    provider = _FakeProvider(
        {"organic": [_organic("Transformer", "https://arxiv.org/abs/1")]}
    )
    monkeypatch.setattr(chat_module, "_get_web_search_cache", lambda: cache)
    monkeypatch.setattr(chat_module, "_get_web_search_provider_or_none", lambda: provider)
    monkeypatch.setattr(
        chat_module,
        "_call_gemma_synthesis",
        lambda query, evidence_text, timeout: "Transformer 可用于序列建模[1]。",
    )

    answer, err, evidence = chat_module._answer_knowledge_qa_with_web_search(
        "transformer 应用场景"
    )

    assert err is None
    assert "Transformer" in answer
    assert evidence[0]["url"] == "https://arxiv.org/abs/1"
    assert provider.calls == ["transformer 应用场景"]
    assert cache.set_calls[0][0] == "transformer 应用场景"


def test_e_web_search_serper_down_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingProvider:
        api_key = "serper-key"

        def search(self, query: str) -> dict[str, Any]:
            del query
            raise RuntimeError("Serper down")

    monkeypatch.setattr(chat_module, "_get_web_search_cache", lambda: _FakeCache())
    monkeypatch.setattr(chat_module, "_get_web_search_provider_or_none", lambda: _FailingProvider())
    monkeypatch.setattr(
        chat_module,
        "_answer_knowledge_qa_fallback",
        lambda query: ("纯 LLM 回答", None),
    )

    answer, err, evidence = chat_module._answer_knowledge_qa_with_web_search("什么是 GAN")

    assert "未引用网络搜索" in answer
    assert "纯 LLM 回答" in answer
    assert err == "Serper down"
    assert evidence == []


def test_e_chat_response_exposes_web_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_LLM_SYNTHESIS", "off")
    monkeypatch.setattr(
        chat_module,
        "_classify_query_with_llm",
        lambda _query: {
            "type": "E",
            "topic": "GAN",
            "name": "",
            "reason": "knowledge",
        },
    )
    evidence = [
        {
            "type": "web",
            "source_type": "web",
            "id": "https://example.com/gan",
            "title": "GAN",
            "snippet": "GAN snippet",
            "url": "https://example.com/gan",
            "score": 1.0,
        }
    ]
    monkeypatch.setattr(
        chat_module,
        "_answer_knowledge_qa_with_web_search",
        lambda query: ("GAN 是生成模型。", None, evidence),
    )

    response = chat_module.chat(
        chat_module.ChatRequest(query="什么是 GAN"),
        response=Response(),
        conn=object(),
    )

    assert response.query_type == "E_knowledge_qa"
    assert response.evidence == evidence
    assert response.structured_payload["retrieval_evidence"] == evidence
