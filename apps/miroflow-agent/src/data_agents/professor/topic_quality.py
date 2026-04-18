"""Research-topic plausibility guard.

Scraped research_directions occasionally produce sentence fragments,
truncated journal references, or dangling "等" (etc) markers. This guard
rejects obvious non-topic shapes without requiring a hand-curated
denylist of good topics.
"""

from __future__ import annotations

import re

_META_PHRASES = (
    "主要研究方向",
    "研究方向包括",
    "研究领域包括",
    "research areas include",
    "research interests include",
    "研究兴趣",
    "研究方向为",
    "仍缺乏",
    "尚未解决",
    "值得研究",
    "有待研究",
    "等问题",
    "等方面",
    "等内容",
    "等工作",
    "等研究",
    "等相关",
)

_TRAILING_PUNCT_RE = re.compile(r"[，,、：:；;。．\.（(《]$")
_LEADING_PUNCT_RE = re.compile(r"^[）)、，,：:；;。．\.》]")


def _normalize(value: str) -> str:
    return value.replace("\ufeff", "").strip()


def is_plausible_research_topic(value: str | None) -> bool:
    """Return True if *value* looks like a research topic phrase.

    Real topics are short (≤40 chars), don't end mid-sentence, and
    aren't meta-narration about someone's research area.
    """
    if not value:
        return False
    normalized = _normalize(value)
    if not normalized:
        return False
    if len(normalized) > 80:
        return False
    if len(normalized) < 2:
        return False
    if normalized.startswith(("以及", "及", "and ", "And ")):
        return False
    if _TRAILING_PUNCT_RE.search(normalized):
        return False
    if _LEADING_PUNCT_RE.search(normalized):
        return False
    if normalized.endswith(("等", "等）", "等)", "……", "...", "…")):
        return False
    # Unbalanced brackets
    if normalized.count("《") != normalized.count("》"):
        return False
    if normalized.count("（") != normalized.count("）"):
        return False
    if normalized.count("(") != normalized.count(")"):
        return False
    lowered = normalized.lower()
    if any(phrase in normalized or phrase in lowered for phrase in _META_PHRASES):
        return False
    return True
