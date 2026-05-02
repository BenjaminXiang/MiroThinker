from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.api import chat as chat_module


def _json_payload(**overrides: str) -> str:
    payload = {
        "type": "C",
        "topic": "",
        "name": "",
        "reason": "test reason",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _classify_with_payload(monkeypatch: pytest.MonkeyPatch, payload: str):
    def _fake_settings(profile_name: str, *, include_profile: bool = False):
        assert profile_name == "gemma4"
        assert include_profile is True
        return {
            "local_llm_base_url": "http://127.0.0.1:8000/v1",
            "local_llm_api_key": "test-key",
            "local_llm_model": "gemma-4b-it",
        }

    class _FakeOpenAI:
        def __init__(self, *, base_url: str, api_key: str, timeout: float) -> None:
            assert base_url == "http://127.0.0.1:8000/v1"
            assert api_key == "test-key"
            assert timeout == chat_module._CLASSIFIER_TIMEOUT
            self.chat = SimpleNamespace(completions=self)

        def create(self, **kwargs):
            assert kwargs["model"] == "gemma-4b-it"
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=payload,
                        )
                    )
                ]
            )

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "resolve_professor_llm_settings", _fake_settings)
    monkeypatch.setattr(chat_module, "OpenAI", _FakeOpenAI)

    return chat_module._classify_query_with_llm("他的论文")


def test_c_type_returns_target_domain_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _classify_with_payload(
        monkeypatch,
        _json_payload(target_domain="paper"),
    )

    assert result == {
        "type": "C",
        "topic": "",
        "name": "",
        "reason": "test reason",
        "target_domain": "paper",
    }


def test_c_type_returns_target_domain_company(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _classify_with_payload(
        monkeypatch,
        _json_payload(target_domain="company"),
    )

    assert result == {
        "type": "C",
        "topic": "",
        "name": "",
        "reason": "test reason",
        "target_domain": "company",
    }


def test_c_type_returns_target_domain_patent(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _classify_with_payload(
        monkeypatch,
        _json_payload(target_domain="patent"),
    )

    assert result == {
        "type": "C",
        "topic": "",
        "name": "",
        "reason": "test reason",
        "target_domain": "patent",
    }


def test_c_type_default_paper_if_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _classify_with_payload(
        monkeypatch,
        _json_payload(),
    )

    assert result == {
        "type": "C",
        "topic": "",
        "name": "",
        "reason": "test reason",
        "target_domain": "paper",
    }


@pytest.mark.parametrize(
    ("query_type", "topic", "name"),
    [
        ("A", "", "丁文伯"),
        ("B", "机器人", ""),
        ("D", "AI 生态", ""),
        ("E", "大模型蒸馏", ""),
        ("F", "", ""),
        ("G", "", "王伟"),
    ],
)
def test_existing_a_b_d_e_f_g_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    query_type: str,
    topic: str,
    name: str,
) -> None:
    result = _classify_with_payload(
        monkeypatch,
        _json_payload(
            type=query_type,
            topic=topic,
            name=name,
            target_domain="paper",
            reason="kept",
        ),
    )

    assert result == {
        "type": query_type,
        "topic": topic,
        "name": name,
        "reason": "kept",
    }
