from __future__ import annotations

import re
from hashlib import sha1


_WHITESPACE_RE = re.compile(r"\s+")
_COMPANY_SUFFIX_RE = re.compile(
    r"(股份有限公司|有限责任公司|集团有限公司|有限公司|集团)$"
)
_PUNCTUATION_RE = re.compile(r"[\s\-_·•.,，。:：;；()（）\[\]【】{}<>《》\"'“”‘’/\\|]+")
_COMPANY_REGION_PREFIXES_V2 = (
    "广东省",
    "深圳市",
    "上海市",
    "北京市",
    "广东",
    "深圳",
    "北京",
)
_COMPANY_SUFFIXES_V2 = (
    "股份有限公司",
    "有限责任公司",
    "集团有限公司",
    "科技有限公司",
    "有限公司",
    "科技股份",
    "股份",
    "集团",
    "无线",
)
_COMPANY_PAREN_MODIFIER_RE = re.compile(r"[（(]\s*(深圳|中国)\s*[）)]", re.IGNORECASE)


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


def normalize_company_name_v2(name: str) -> str:
    normalized = _WHITESPACE_RE.sub("", name or "").casefold()
    normalized = _strip_region_prefixes(normalized)
    normalized = _strip_company_suffixes(normalized)
    normalized = _COMPANY_PAREN_MODIFIER_RE.sub("", normalized)
    normalized = _PUNCTUATION_RE.sub("", normalized)
    return normalized.strip()


def normalize_person_name(name: str) -> str:
    return _WHITESPACE_RE.sub("", name or "")


def _strip_region_prefixes(value: str) -> str:
    normalized = value
    changed = True
    while changed:
        changed = False
        for prefix in _COMPANY_REGION_PREFIXES_V2:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                changed = True
                break
    return normalized


def _strip_company_suffixes(value: str) -> str:
    normalized = value
    changed = True
    while changed:
        changed = False
        for suffix in _COMPANY_SUFFIXES_V2:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                changed = True
                break
    return normalized
