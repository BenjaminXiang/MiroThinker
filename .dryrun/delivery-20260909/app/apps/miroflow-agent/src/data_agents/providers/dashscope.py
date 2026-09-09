# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""OpenAI-compatible provider for Alibaba DashScope (qwen3.6-plus).

Used as the online LLM escalation tier when local Qwen3.5-35B fails
to produce satisfactory structured output.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from .qwen import build_openai_client


class DashScopeProvider:
    def __init__(
        self,
        *,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key: str = "",
        model: str = "qwen3.6-plus",
        timeout: float = 120.0,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "").strip()
        self.model = model
        self.timeout = timeout
        self.client_factory = client_factory or build_openai_client

    def create_client(self) -> Any:
        return self.client_factory(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
        )

    def build_request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
