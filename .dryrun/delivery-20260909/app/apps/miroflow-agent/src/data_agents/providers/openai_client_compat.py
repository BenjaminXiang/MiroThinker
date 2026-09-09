# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import openai


def build_openai_client(
    *, base_url: str, api_key: str, timeout: float
) -> openai.Client:
    try:
        return openai.Client(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
    except ImportError as exc:
        if "socksio" not in str(exc):
            raise
    except TypeError as exc:
        if "proxies" not in str(exc):
            raise

    return openai.Client(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        http_client=openai.DefaultHttpxClient(
            timeout=timeout,
            trust_env=False,
        ),
    )
