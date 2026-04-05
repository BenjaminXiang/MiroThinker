from __future__ import annotations

import re
from hashlib import sha1


_WHITESPACE_RE = re.compile(r"\s+")
_COMPANY_SUFFIX_RE = re.compile(
    r"(股份有限公司|有限责任公司|集团有限公司|有限公司|集团)$"
)


def build_stable_id(prefix: str, natural_key: str) -> str:
    normalized_prefix = prefix.strip().upper()
    normalized_key = natural_key.strip().lower()
    digest = sha1(normalized_key.encode("utf-8")).hexdigest()[:12].upper()
    return f"{normalized_prefix}-{digest}"


def normalize_company_name(name: str) -> str:
    normalized = _WHITESPACE_RE.sub("", name or "")
    if normalized.startswith("深圳市"):
        normalized = normalized[3:]
    return _COMPANY_SUFFIX_RE.sub("", normalized)


def normalize_person_name(name: str) -> str:
    return _WHITESPACE_RE.sub("", name or "")
