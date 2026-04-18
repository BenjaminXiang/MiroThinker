# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Institution alias helpers for Shenzhen professor enrichment."""
from __future__ import annotations

import re


_NON_ALNUM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")

_ALIASES: dict[str, tuple[str, ...]] = {
    "南方科技大学": (
        "南方科技大学",
        "Southern University of Science and Technology",
        "SUSTech",
    ),
    "清华大学深圳国际研究生院": (
        "清华大学深圳国际研究生院",
        "Tsinghua Shenzhen International Graduate School",
        "SIGS",
    ),
    "北京大学深圳研究生院": (
        "北京大学深圳研究生院",
        "Peking University Shenzhen Graduate School",
        "PKUSZ",
    ),
    "深圳大学": (
        "深圳大学",
        "Shenzhen University",
        "SZU",
    ),
    "深圳理工大学": (
        "深圳理工大学",
        "Shenzhen University of Advanced Technology",
        "Shenzhen University of Technology",
        "SUAT",
    ),
    "哈尔滨工业大学（深圳）": (
        "哈尔滨工业大学（深圳）",
        "Harbin Institute of Technology, Shenzhen",
        "Harbin Institute of Technology Shenzhen",
        "HIT Shenzhen",
    ),
    "香港中文大学（深圳）": (
        "香港中文大学（深圳）",
        "The Chinese University of Hong Kong, Shenzhen",
        "Chinese University of Hong Kong Shenzhen",
        "CUHK-Shenzhen",
    ),
    "中山大学（深圳）": (
        "中山大学（深圳）",
        "Sun Yat-sen University Shenzhen",
        "SYSU Shenzhen",
        "SYSU",
    ),
    "深圳技术大学": (
        "深圳技术大学",
        "Shenzhen Technology University",
        "SZTU",
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
