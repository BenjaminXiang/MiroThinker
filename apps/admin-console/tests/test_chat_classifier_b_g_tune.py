from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.api import chat as chat_module


B_CASES = {
    "深圳哪些公司做激光雷达": {
        "type": "B",
        "topic": "激光雷达",
        "name": "",
        "target_domain": "company",
    },
    "深圳做合成数据平台的企业": {
        "type": "B",
        "topic": "合成数据平台",
        "name": "",
        "target_domain": "company",
    },
    "做脑机接口的深圳团队": {
        "type": "B",
        "topic": "脑机接口",
        "name": "",
        "target_domain": "company",
    },
    "有没有做工业视觉检测的深圳企业": {
        "type": "B",
        "topic": "工业视觉检测",
        "name": "",
        "target_domain": "company",
    },
    "研究力控的深圳高校教授有哪些": {
        "type": "B",
        "topic": "力控",
        "name": "",
        "target_domain": "professor",
    },
}
G_CASES = {
    "介绍无界智航": {
        "type": "G",
        "topic": "",
        "name": "无界智航",
        "target_domain": "company",
    },
    "介绍无界智航的相关信息": {
        "type": "G",
        "topic": "",
        "name": "无界智航",
        "target_domain": "company",
    },
    "介绍王伟": {
        "type": "G",
        "topic": "",
        "name": "王伟",
        "target_domain": "professor",
    },
    "王伟是谁": {
        "type": "G",
        "topic": "",
        "name": "王伟",
        "target_domain": "professor",
    },
    "李雪芳是谁": {
        "type": "G",
        "topic": "",
        "name": "李雪芳",
        "target_domain": "professor",
    },
}


def _classify_with_mock_llm(monkeypatch: pytest.MonkeyPatch, query: str):
    cases = {**B_CASES, **G_CASES}

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
            assert kwargs["temperature"] == 0.0
            assert kwargs["extra_body"] == {
                "chat_template_kwargs": {"enable_thinking": False}
            }
            messages = kwargs["messages"]
            system_prompt = messages[0]["content"]
            user_query = messages[1]["content"]
            assert user_query == query
            assert "深圳哪些公司做激光雷达" in system_prompt
            assert "深圳做合成数据平台的企业" in system_prompt
            assert "做脑机接口的深圳团队" in system_prompt
            assert "介绍无界智航" in system_prompt
            assert "介绍王伟" in system_prompt
            assert "X 是谁" in system_prompt
            assert "不是单纯'地域 + 产业/技术'组合" in system_prompt
            payload = {**cases[user_query], "reason": "w13-7 mock"}
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(payload, ensure_ascii=False),
                        )
                    )
                ]
            )

    monkeypatch.delenv("CHAT_QUERY_CLASSIFIER", raising=False)
    monkeypatch.setattr(chat_module, "resolve_professor_llm_settings", _fake_settings)
    monkeypatch.setattr(chat_module, "OpenAI", _FakeOpenAI)

    return chat_module._classify_query_with_llm(query)


@pytest.mark.parametrize("query", B_CASES)
def test_b_regional_single_domain_queries_stay_b(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    result = _classify_with_mock_llm(monkeypatch, query)

    assert result is not None
    ctype = result["type"]
    assert ctype == "B"


@pytest.mark.parametrize("query", G_CASES)
def test_g_intro_and_who_queries_stay_g(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    result = _classify_with_mock_llm(monkeypatch, query)

    assert result is not None
    ctype = result["type"]
    assert ctype == "G"
