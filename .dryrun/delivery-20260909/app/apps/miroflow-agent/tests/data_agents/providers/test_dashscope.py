# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.data_agents.providers.dashscope import DashScopeProvider


def test_build_request_produces_valid_openai_format():
    provider = DashScopeProvider(api_key="test-key")
    request = provider.build_request(
        system_prompt="You are a helpful assistant.",
        user_prompt="Extract professor info.",
    )
    assert request["model"] == "qwen3.6-plus"
    assert len(request["messages"]) == 2
    assert request["messages"][0]["role"] == "system"
    assert request["messages"][1]["role"] == "user"
    assert request["temperature"] == 0.7
    assert request["max_tokens"] == 4096
    assert request["stream"] is False


def test_build_request_custom_params():
    provider = DashScopeProvider(model="qwen-plus", api_key="key")
    request = provider.build_request(
        system_prompt="sys",
        user_prompt="usr",
        temperature=0.3,
        max_tokens=2048,
        stream=True,
    )
    assert request["model"] == "qwen-plus"
    assert request["temperature"] == 0.3
    assert request["max_tokens"] == 2048
    assert request["stream"] is True


def test_create_client_with_mock_factory():
    mock_client = object()
    provider = DashScopeProvider(
        api_key="test-key",
        client_factory=lambda **kwargs: mock_client,
    )
    client = provider.create_client()
    assert client is mock_client


def test_default_values():
    provider = DashScopeProvider(api_key="k")
    assert provider.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert provider.model == "qwen3.6-plus"
    assert provider.timeout == 120.0
