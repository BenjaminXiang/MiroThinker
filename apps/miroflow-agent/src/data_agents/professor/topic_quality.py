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

_PROFILE_TOPIC_NOISE_RE = re.compile(
    r"\b(?:personal\s+profile|group\s+website|profile)\b",
    re.IGNORECASE,
)
_CJK_ROLE_LABELS = frozenset(
    {
        "教授",
        "副教授",
        "助理教授",
        "讲师",
        "导师",
        "博士",
        "博士后",
        "院士",
        "客座教授",
    }
)
_ENGLISH_PROFESSOR_ROLE_RE = re.compile(
    r"\b(?:assistant|assistance|associate|invited|full)?\s*professor\b",
    re.IGNORECASE,
)
_CJK_PERSON_TITLE_SUFFIX_RE = re.compile(
    r"[\u3400-\u9fff]{2,8}(?:博士|教授|副教授|讲师|导师|院士)$"
)
_CJK_NAME_WITH_DOCTOR_RE = re.compile(r"[\u3400-\u9fff]{2,4}博士")
_CJK_NAME_ROLE_SEQUENCE_RE = re.compile(
    r"^[\u3400-\u9fff]{2,6}(?:\s+(?:博士|教授|副教授|讲师|导师|院士)){1,4}$"
)


# Round 7.18b — separators used to split compound research_topic values like
# "计算神经科学，机器学习，人工智能" into atomic topics. Deliberately excludes
# colon (":") and slash ("/"): those appear inside single legitimate topics
# (e.g. "AI4Science/AI+Science"). Splitting is top-level only: separators
# inside brackets often belong to bilingual translations or acronym lists.
_COMPOUND_SEPARATORS = frozenset("，、;；,")
_ASCII_COMMA = ","
_OPEN_TO_CLOSE = {
    "(": ")",
    "（": "）",
    "[": "]",
    "【": "】",
    "{": "}",
    "《": "》",
}
_CLOSING_BRACKETS = frozenset(_OPEN_TO_CLOSE.values())
_CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff]")


def _normalize(value: str) -> str:
    return value.replace("\ufeff", "").strip()


def _contains_cjk(value: str) -> bool:
    return bool(_CJK_CHAR_RE.search(value))


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
    if _is_person_role_or_profile_noise(normalized):
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
    pieces = _split_top_level_topics(normalized)
    if len(pieces) <= 1:
        return [normalized] if is_plausible_research_topic(normalized) else []
    atomic: list[str] = []
    seen: set[str] = set()
    unsafe_invalid_piece = False
    for piece in pieces:
        if not is_plausible_research_topic(piece):
            if _is_disposable_topic_fragment(piece):
                continue
            unsafe_invalid_piece = True
            continue
        key = piece.casefold()
        if key in seen:
            continue
        seen.add(key)
        atomic.append(piece)
    if unsafe_invalid_piece:
        return [normalized] if is_plausible_research_topic(normalized) else []
    return atomic


def _split_top_level_topics(value: str) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    bracket_stack: list[str] = []
    for index, char in enumerate(value):
        if char in _OPEN_TO_CLOSE:
            bracket_stack.append(_OPEN_TO_CLOSE[char])
            current.append(char)
            continue
        if bracket_stack and char == bracket_stack[-1]:
            bracket_stack.pop()
            current.append(char)
            continue
        if char in _CLOSING_BRACKETS:
            current.append(char)
            continue
        if not bracket_stack and char in _COMPOUND_SEPARATORS:
            left = "".join(current)
            right = value[index + 1 :]
            if char != _ASCII_COMMA or (
                _contains_cjk(left) and _right_starts_with_cjk(right)
            ):
                piece = _normalize(left)
                if piece:
                    pieces.append(piece)
                current = []
                continue
        current.append(char)
    tail = _normalize("".join(current))
    if tail:
        pieces.append(tail)
    return pieces


def _right_starts_with_cjk(value: str) -> bool:
    stripped = value.lstrip()
    return bool(stripped and _CJK_CHAR_RE.match(stripped[0]))


def _is_disposable_topic_fragment(value: str) -> bool:
    normalized = _normalize(value)
    if not normalized:
        return True
    lowered = normalized.lower()
    if lowered in _EXACT_META_LABELS:
        return True
    if normalized in {"等", "等）", "等)", "...", "…", "……"}:
        return True
    if any(phrase in normalized or phrase in lowered for phrase in _META_PHRASES):
        return True
    if _NUMBERED_FRAGMENT_RE.match(normalized) and len(normalized) <= 8:
        return True
    return bool(_METRIC_COUNT_RE.search(normalized))


def _is_person_role_or_profile_noise(value: str) -> bool:
    if value in _CJK_ROLE_LABELS:
        return True
    if any(marker in value for marker in ("个人简介", "个人资料", "课题组网站")):
        return True
    if _PROFILE_TOPIC_NOISE_RE.search(value):
        return True
    if _ENGLISH_PROFESSOR_ROLE_RE.search(value):
        return True
    if "长期招聘" in value or "招聘博士后" in value:
        return True
    if "博士后" in value and any(
        marker in value for marker in ("基金", "研究工作", "项目", "助研")
    ):
        return True
    if _CJK_PERSON_TITLE_SUFFIX_RE.search(value) and len(value) <= 18:
        return True
    if _CJK_NAME_ROLE_SEQUENCE_RE.match(value):
        return True
    if _CJK_NAME_WITH_DOCTOR_RE.search(value) and any(
        marker in value for marker in ("长期", "聚焦", "等", "教授")
    ):
        return True
    if "老师" in value and len(value) <= 24:
        return True
    return False
