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
    "research syntheses",
    "research interests",
    "research areas",
    "research topics",
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

# Round 7.18b — standalone meta-labels masquerading as topics. Exact-match only
# so that "其他计算机视觉技术" (a legit topic that starts with "其他") still passes.
_EXACT_META_LABELS = frozenset(
    label.lower()
    for label in (
        "其他",
        "其它",
        "Others",
        "Other",
        "Miscellaneous",
        "Misc",
        "杂项",
        "待补充",
        "暂无",
    )
)

# Round 7.9' extension: journal names extracted as topics. Shapes seen in
# miroflow_real research_topic column:
#   "Conservation Biology，2023", "Nature Communications，2025",
#   "One Earth，2023", "Journal of Biogeography，2021"
# Bare journal names: "Nano Letters", "JACS", "Matter and Radia".
# Heuristic: English phrase ending with comma+year, OR bare well-known
# journal name or abbreviation used alone.
_JOURNAL_YEAR_RE = re.compile(
    r"^[A-Za-z][A-Za-z\s&/\-]+[,，]\s*\d{4}\s*$"
)

_KNOWN_JOURNAL_TOKENS = frozenset(
    token.lower()
    for token in (
        "Nature Communications", "Nature", "Science", "Cell", "JACS",
        "PNAS", "Nano Letters", "Nano Lett", "Angew Chem",
        "Conservation Biology", "One Earth", "Journal of Biogeography",
        "Matter and Radia", "Physical Review Letters", "PRL",
        "IEEE Trans", "IEEE Transactions", "ACS Nano",
    )
)

_TRAILING_PUNCT_RE = re.compile(r"[，,、：:；;。．\.（(《]$")
_LEADING_PUNCT_RE = re.compile(r"^[）)、，,：:；;。．\.》]")
_NUMBERED_FRAGMENT_RE = re.compile(r"^[（(]?[0-9一二三四五六七八九十]{1,2}[)）]")

# Round 7.18b — publication/achievement metrics that look like topics but aren't.
# Real samples from miroflow_real: "发表学术论文350多篇", "出版著作30余部",
# "获得授权发明专利20余项". These appear when scrapers concatenate a research
# direction with a CV bullet under the same field.
_METRIC_COUNT_RE = re.compile(
    r"\d+\s*(多|余|以上|以下)?\s*(篇|部|本|项|件|册|卷|章)"
)


# Round 7.18b — separators used to split compound research_topic values like
# "计算神经科学，机器学习，人工智能" into atomic topics. Deliberately excludes
# colon (":") and slash ("/"): those appear inside single legitimate topics
# (e.g. "AI4Science/AI+Science"). Parenthetical English is not split because
# commas inside parens are rare and the whole phrase is normally atomic.
_COMPOUND_SEPARATOR_RE = re.compile(r"[，,、;；]")


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
    if lowered in _EXACT_META_LABELS:
        return False
    if any(phrase in normalized or phrase in lowered for phrase in _META_PHRASES):
        return False
    # Journal name + year suffix: "Conservation Biology，2023"
    if _JOURNAL_YEAR_RE.match(normalized):
        return False
    # Bare well-known journal name used alone
    if lowered in _KNOWN_JOURNAL_TOKENS:
        return False
    # Section number fragments: "（1）3D", "1. 研究方向", "2) Topic"
    if _NUMBERED_FRAGMENT_RE.match(normalized) and len(normalized) <= 8:
        return False
    # Publication/achievement metrics masquerading as topics
    if _METRIC_COUNT_RE.search(normalized):
        return False
    return True


def split_compound_research_topic(value: str | None) -> list[str]:
    """Break a compound topic string into atomic plausible topics.

    Scraped research_directions sometimes pack 2+ topics into one fact:
        "计算神经科学，机器学习，人工智能，数据科学，生物图像分析"

    Returns a list of atomic topics, each of which independently passes
    `is_plausible_research_topic`. Garbage pieces (e.g. "等") are dropped.
    A single-topic input returns `[input]`; pure-noise input returns `[]`.

    Does NOT split on colon or slash — those appear inside single topics
    (e.g. ``基于 PyTorch 的模型`` can have colons in English variants).
    """
    if not value:
        return []
    normalized = _normalize(value)
    if not normalized:
        return []
    pieces = [p.strip() for p in _COMPOUND_SEPARATOR_RE.split(normalized)]
    pieces = [p for p in pieces if p]
    if len(pieces) <= 1:
        return [normalized] if is_plausible_research_topic(normalized) else []
    return [p for p in pieces if is_plausible_research_topic(p)]
