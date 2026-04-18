# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Clean research directions — remove courses, education text, HTML fragments, and junk.

Called after regex extraction (Stage 2) and after homepage crawling (Stage 3)
to ensure research_directions contains only actual research topics.
"""
from __future__ import annotations

import re

# Sentinel phrases that indicate non-research content
_SENTINEL_PHRASES = (
    "主讲课程",
    "课程：",
    "课程:",
    "课程建设",
    "主讲",
    "教学成果",
    "教学改革",
    "教育背景",
    "教材",
    "科研项目",
    "讲授",
    "承担",
    "本科",
    "研究生",
    "博士生",
    "硕士生",
    "学时",
)

# Patterns matching year ranges like 2012-2017 or 2012–2017
_YEAR_RANGE_RE = re.compile(r"\d{4}[-–—]\d{4}")

# HTML tag remnants
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Leading/trailing punctuation to strip (Chinese and ASCII)
_PUNCT_STRIP = "，。、；：！？.,;:!? \t\n·•►▶◆■□●○—–-"

# Separators for compound items
_COMPOUND_SEP_RE = re.compile(r"[、；;]")

# Max length for a single research direction
_MAX_DIRECTION_LEN = 30


def clean_directions(raw: list[str]) -> list[str]:
    """Clean a list of raw research directions.

    Rules:
    - Truncate items at sentinel phrases (keep text before the sentinel)
    - Drop items containing year ranges
    - Drop items longer than 30 characters
    - Strip HTML tags
    - Strip leading/trailing punctuation and whitespace
    - Split compound items containing '、' or '；'
    - Deduplicate case-insensitively (keep first occurrence)
    - Return empty list rather than garbage
    """
    cleaned: list[str] = []

    for item in raw:
        if not item or not item.strip():
            continue

        # Strip HTML tags
        item = _HTML_TAG_RE.sub("", item)

        # Split compound items first
        parts = _COMPOUND_SEP_RE.split(item)

        for part in parts:
            processed = _process_single(part)
            if processed:
                cleaned.append(processed)

    return _deduplicate(cleaned)


def _process_single(item: str) -> str | None:
    """Process a single direction string. Returns None if it should be dropped."""
    # Truncate at sentinel phrases
    for sentinel in _SENTINEL_PHRASES:
        idx = item.find(sentinel)
        if idx != -1:
            item = item[:idx]

    # Strip punctuation and whitespace
    item = item.strip(_PUNCT_STRIP)

    if not item:
        return None

    # Drop items with year ranges
    if _YEAR_RANGE_RE.search(item):
        return None

    # Drop overly long items
    if len(item) > _MAX_DIRECTION_LEN:
        return None

    return item


def _deduplicate(items: list[str]) -> list[str]:
    """Deduplicate case-insensitively, keeping first occurrence."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
