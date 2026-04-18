from __future__ import annotations

import hashlib
from urllib.parse import urlsplit

from ..normalization import normalize_company_name


def generate_company_id(
    *, unified_credit_code: str | None, website: str | None, registered_name: str
) -> str:
    """Return a deterministic company id using the configured precedence."""
    key = _clean(unified_credit_code)
    if key:
        return _build_company_id(key)

    host = _extract_host(website)
    if host:
        return _build_company_id(host)

    normalized_name = normalize_company_name(registered_name or "")
    fallback = _clean(normalized_name)
    if fallback:
        return _build_company_id(fallback)

    raise ValueError("at least one company identity input must be non-empty")


def _build_company_id(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"COMP-{digest}"


def _extract_host(website: str | None) -> str | None:
    cleaned = _clean(website)
    if not cleaned:
        return None

    candidate = cleaned if "://" in cleaned else f"https://{cleaned}"
    try:
        parsed = urlsplit(candidate)
    except Exception:
        return None

    return _clean(parsed.hostname.lower() if parsed.hostname else None)


def _clean(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None
