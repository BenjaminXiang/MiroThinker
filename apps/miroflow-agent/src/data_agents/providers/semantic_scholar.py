from __future__ import annotations

import os

SEMANTIC_SCHOLAR_API_KEY_ENV_NAMES = (
    "SEMANTIC_SCHOLAR_API_KEY",
    "S2_API_KEY",
)


def semantic_scholar_api_key() -> str | None:
    for env_name in SEMANTIC_SCHOLAR_API_KEY_ENV_NAMES:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return None


def semantic_scholar_request_headers() -> dict[str, str]:
    api_key = semantic_scholar_api_key()
    return {"x-api-key": api_key} if api_key else {}
