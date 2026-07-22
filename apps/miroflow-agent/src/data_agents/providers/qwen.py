from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .openai_client_compat import build_openai_client


class QwenProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://star.sustech.edu.cn/service/model/qwen35/v1",
        api_key: str = "",
        model: str = "qwen3.5-35b-a3b",
        timeout: float = 300.0,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
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
        stream: bool = True,
        temperature: float = 0.8,
        top_p: float = 0.85,
        frequency_penalty: float = 1.0,
        presence_penalty: float = 0.8,
        max_tokens: int = 192,
        repetition_penalty: float = 1.1,
        thinking: bool = False,
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "max_tokens": max_tokens,
            "stream": stream,
            "extra_body": {
                "separate_reasoning": thinking,
                "chat_template_kwargs": {"enable_thinking": thinking},
                "repetition_penalty": repetition_penalty,
            },
        }
