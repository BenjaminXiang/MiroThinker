from __future__ import annotations

import os
from pathlib import Path

_ENV_NAMES = ("API_KEY", "OPENAI_API_KEY", "SGLANG_API_KEY")
_KEY_FILENAME = ".sglang_api_key"


def load_local_api_key(repo_root: Path | None = None) -> str:
    for env_name in _ENV_NAMES:
        api_key = os.getenv(env_name, "").strip()
        if api_key:
            return api_key

    if repo_root is not None:
        key_path = repo_root / _KEY_FILENAME
        try:
            return key_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    for parent in Path(__file__).resolve().parents:
        key_path = parent / _KEY_FILENAME
        try:
            api_key = key_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
        if api_key:
            return api_key

    return ""
