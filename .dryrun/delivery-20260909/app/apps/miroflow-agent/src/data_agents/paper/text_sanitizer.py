from __future__ import annotations

import re
from typing import Any

_POSTGRES_UNSAFE_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text_for_postgres(value: str | None) -> str | None:
    """Remove control characters that PostgreSQL text/json fields reject."""
    if value is None:
        return None
    cleaned = value.replace("\f", "\n")
    return _POSTGRES_UNSAFE_CONTROL_RE.sub("", cleaned)


def sanitize_optional_text_for_postgres(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = sanitize_text_for_postgres(value)
    if cleaned is None:
        return None
    item = cleaned.strip()
    return item or None


def sanitize_json_for_postgres(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text_for_postgres(value)
    if isinstance(value, list):
        return [sanitize_json_for_postgres(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_json_for_postgres(item) for item in value]
    if isinstance(value, dict):
        return {
            str(sanitize_text_for_postgres(str(key))): sanitize_json_for_postgres(item)
            for key, item in value.items()
        }
    return value
