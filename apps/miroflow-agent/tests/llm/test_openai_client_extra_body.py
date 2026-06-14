from __future__ import annotations

from types import SimpleNamespace

import pytest
from omegaconf import OmegaConf

from src.llm.providers.openai_client import OpenAIClient


class _FakeTaskLog:
    def log_step(self, *_args, **_kwargs) -> None:
        return None


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="ok"),
                )
            ],
            usage=None,
        )


class _FakeOpenAIClient(OpenAIClient):
    def _create_client(self):
        self.fake_completions = _FakeCompletions()
        return SimpleNamespace(chat=SimpleNamespace(completions=self.fake_completions))


def _cfg(model_name: str):
    return OmegaConf.create(
        {
            "llm": {
                "provider": "openai",
                "model_name": model_name,
                "temperature": 0.1,
                "top_p": 1.0,
                "min_p": 0.0,
                "top_k": -1,
                "max_context_length": 4096,
                "max_tokens": 64,
                "async_client": False,
                "api_key": "test-key",
                "base_url": "https://api.deepseek.com",
                "use_tool_calls": False,
                "repetition_penalty": 1.0,
            },
            "agent": {"keep_tool_result": -1},
        }
    )


def test_openai_client_ignores_ambient_proxy_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:9999")
    monkeypatch.setenv("all_proxy", "socks5://127.0.0.1:9999")

    client = OpenAIClient(
        task_id="test-task",
        cfg=_cfg("deepseek-v4-pro"),
        task_log=_FakeTaskLog(),
    )

    assert client.client is not None


@pytest.mark.asyncio
async def test_openai_client_disables_deepseek_v4_thinking_by_default():
    client = _FakeOpenAIClient(
        task_id="test-task",
        cfg=_cfg("deepseek-v4-pro"),
        task_log=_FakeTaskLog(),
    )

    await client._create_message(
        system_prompt="",
        messages_history=[{"role": "user", "content": "hello"}],
        tools_definitions=[],
    )

    assert client.fake_completions.calls[0]["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
