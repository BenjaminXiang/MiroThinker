from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _load_build_openai_client() -> Callable[..., Any]:
    try:
        from openai_client_compat import build_openai_client

        return build_openai_client
    except ModuleNotFoundError:
        helper_path = Path(__file__).resolve().parents[5] / "openai_client_compat.py"
        spec = importlib.util.spec_from_file_location(
            "openai_client_compat",
            helper_path,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load compatibility client helper from {helper_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.build_openai_client


build_openai_client = _load_build_openai_client()


class MiroThinkerProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://star.sustech.edu.cn/service/model/mirothinker/v1",
        api_key: str = "",
        model: str = "mirothinker-1.7-235b-fp8",
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
        temperature: float = 0.1,
        top_p: float = 0.9,
        frequency_penalty: float = 0.2,
        presence_penalty: float = 0.0,
        max_tokens: int = 512,
        repetition_penalty: float = 1.05,
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
                "separate_reasoning": True,
                "chat_template_kwargs": {"enable_thinking": thinking},
                "repetition_penalty": repetition_penalty,
            },
        }
