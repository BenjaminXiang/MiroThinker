from __future__ import annotations

import hashlib
from urllib.parse import urlsplit

from ..normalization import normalize_company_name

_SHARED_IDENTITY_HOSTS = {
    "mp.weixin.qq.com",
    "weixin.qq.com",
    "weibo.com",
    "m.weibo.cn",
    "qcc.com",
    "tianyancha.com",
    "aiqicha.baidu.com",
    "baike.baidu.com",
    "linkedin.com",
    "github.com",
    "gitlab.com",
    "gitee.com",
    "zhihu.com",
    "36kr.com",
    "pitchhub.36kr.com",
    "iyiou.com",
    "data.iyiou.com",
}


def generate_company_id(
    *, unified_credit_code: str | None, website: str | None, registered_name: str
) -> str:
    """Return a deterministic company id using the configured precedence."""
    key = _clean(unified_credit_code)
    if key:
        return _build_company_id(key)

    host = _extract_host(website)
    if host and not _is_shared_identity_host(host):
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


def _is_shared_identity_host(host: str | None) -> bool:
    cleaned = _clean(host)
    if not cleaned:
        return False
    normalized = cleaned.lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized in _SHARED_IDENTITY_HOSTS


def _clean(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None
