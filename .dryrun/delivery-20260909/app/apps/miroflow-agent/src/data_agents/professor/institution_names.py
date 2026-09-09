# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Institution alias helpers for Shenzhen professor enrichment."""
from __future__ import annotations

import re


_NON_ALNUM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")

_ALIASES: dict[str, tuple[str, ...]] = {
    "南方科技大学": (
        "南方科技大学",
        "南科大",
        "南方科大",
        "Southern University of Science and Technology",
        "SUSTech",
        "SUSTech University",
    ),
    "清华大学深圳国际研究生院": (
        "清华大学深圳国际研究生院",
        "清华深研",
        "清华深圳国际研究生院",
        "Tsinghua Shenzhen International Graduate School",
        "Tsinghua SIGS",
        "SIGS",
        "THU-SIGS",
    ),
    "清华大学深圳研究生院": (
        "清华大学深圳研究生院",
        "清华深研院",
        "Tsinghua Shenzhen Graduate School",
    ),
    "北京大学深圳研究生院": (
        "北京大学深圳研究生院",
        "北大深研",
        "北大深圳",
        "Peking University Shenzhen Graduate School",
        "PKUSZ",
        "PKU-SZ",
        "PKU Shenzhen",
    ),
    "深圳大学": (
        "深圳大学",
        "深大",
        "Shenzhen University",
        "SZU",
    ),
    "深圳理工大学": (
        "深圳理工大学",
        "深理工",
        "深圳理工",
        "Shenzhen University of Advanced Technology",
        "Shenzhen University of Technology",
        "SUAT",
        "SZIT",
    ),
    "哈尔滨工业大学（深圳）": (
        "哈尔滨工业大学（深圳）",
        "哈深",
        "哈工大深圳",
        "哈工大（深圳）",
        "Harbin Institute of Technology, Shenzhen",
        "Harbin Institute of Technology Shenzhen",
        "HIT Shenzhen",
        "HITSZ",
        "HIT-Shenzhen",
    ),
    "香港中文大学（深圳）": (
        "香港中文大学（深圳）",
        "香港中文大学(深圳)",
        "香港中文大学深圳分校",
        "港中深",
        "港中大深圳",
        "中大香港（深圳）",
        "The Chinese University of Hong Kong, Shenzhen",
        "The Chinese University of Hong Kong (Shenzhen)",
        "Chinese University of Hong Kong Shenzhen",
        "CUHK-Shenzhen",
        "CUHKSZ",
        "CUHK(SZ)",
        "CUHK (SZ)",
        "CUHK Shenzhen",
    ),
    "中山大学（深圳）": (
        "中山大学（深圳）",
        "中山大学深圳校区",
        "中大深圳",
        "Sun Yat-sen University Shenzhen",
        "Sun Yat-sen University, Shenzhen",
        "SYSU Shenzhen",
        "SYSU-SZ",
        "SYSU",
    ),
    "深圳技术大学": (
        "深圳技术大学",
        "深技大",
        "Shenzhen Technology University",
        "SZTU",
    ),
    "中国科学院深圳先进技术研究院": (
        "中国科学院深圳先进技术研究院",
        "中科院深圳先进院",
        "深先院",
        "深圳先进技术研究院",
        "Shenzhen Institute of Advanced Technology",
        "SIAT",
    ),
}


def normalize_institution_text(value: str | None) -> str:
    if not value:
        return ""
    return _NON_ALNUM_RE.sub("", value.casefold())


def get_institution_aliases(institution_name: str | None) -> tuple[str, ...]:
    normalized = normalize_institution_text(institution_name)
    if not normalized:
        return ()

    for aliases in _ALIASES.values():
        normalized_aliases = {
            normalize_institution_text(alias)
            for alias in aliases
            if alias
        }
        if normalized in normalized_aliases:
            return aliases

    return (institution_name.strip(),) if institution_name else ()


def get_primary_english_institution_name(institution_name: str | None) -> str | None:
    aliases = get_institution_aliases(institution_name)
    for alias in aliases:
        if alias and alias.isascii() and " " in alias:
            return alias
    if institution_name and institution_name.isascii():
        return institution_name.strip() or None
    return None


def normalize_institution(raw: str | None) -> str | None:
    """Return the canonical Shenzhen institution name for *raw*, else None.

    Round 7.19b: recognize and collapse institution variants (CUHKSZ, 港中深,
    SUSTech, etc.) to the canonical Chinese form. Unknown strings return
    None so the caller can decide the fallback (e.g. UNKNOWN_INSTITUTION
    or pipeline_issue).
    """
    if not raw:
        return None
    normalized = normalize_institution_text(raw)
    if not normalized:
        return None
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            if normalize_institution_text(alias) == normalized:
                return canonical
    # Also allow substring match on raw text for cases where the scraped
    # institution string wraps the alias in extra context (e.g.
    # "深圳理工大学生命健康学院" → 深圳理工大学).
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_institution_text(alias)
            if alias_norm and alias_norm in normalized and len(alias_norm) >= 4:
                return canonical
    return None
