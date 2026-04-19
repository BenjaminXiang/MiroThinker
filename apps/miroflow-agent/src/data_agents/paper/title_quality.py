"""Rule-based paper-title plausibility guard.

Round 7.12' targets a narrow failure mode in ``paper.title_clean``: author
lists and editorial bios pasted into the title field. This v1 is intentionally
rule-based only; there is no LLM fallback.
"""

from __future__ import annotations

import re


_WHITESPACE_RE = re.compile(r"\s+")
_PAREN_PREFIX_RE = re.compile(r"^\(\d+\)[A-Z]")
_EDITORIAL_ROLE_RE = re.compile(
    r"(?:\bassociate editor\b|\beditor(?:-in-chief)?\b|\bco-chair\b|\bchair\b|主席)",
    re.IGNORECASE,
)
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_INITIAL_RE = re.compile(r"[A-Z]\.")
_CAPITALIZED_RE = re.compile(r"[A-Z][a-z]+(?:[-'][A-Z][a-z]+)*")
_UPPER_RE = re.compile(r"[A-Z]{2,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _normalize(title: str) -> str:
    return _WHITESPACE_RE.sub(" ", title.replace("\ufeff", " ")).strip()


def _is_name_token(token: str) -> bool:
    return bool(
        _INITIAL_RE.fullmatch(token)
        or _CAPITALIZED_RE.fullmatch(token)
        or _UPPER_RE.fullmatch(token)
    )


def _looks_like_first_last(segment: str) -> bool:
    if "," in segment:
        return False
    tokens = segment.split()
    if not 2 <= len(tokens) <= 4:
        return False
    if not all(_is_name_token(token) for token in tokens):
        return False
    return any(_CAPITALIZED_RE.fullmatch(token) for token in tokens)


def _looks_like_lastname_first(segment: str) -> bool:
    if segment.count(",") != 1:
        return False
    last, first = (part.strip() for part in segment.split(",", 1))
    if not last or not first:
        return False
    last_tokens = last.split()
    first_tokens = first.split()
    if not 1 <= len(last_tokens) <= 3 or not 1 <= len(first_tokens) <= 3:
        return False
    if not all(_is_name_token(token) for token in last_tokens + first_tokens):
        return False
    return any(_CAPITALIZED_RE.fullmatch(token) for token in last_tokens + first_tokens)


def _looks_like_author_segment(segment: str) -> bool:
    cleaned = segment.strip().strip("()[]{}")
    cleaned = cleaned.rstrip(".")
    cleaned = cleaned.replace("…", "").replace("...", "").strip()
    if not cleaned:
        return False
    return _looks_like_lastname_first(cleaned) or _looks_like_first_last(cleaned)


def _count_author_like_segments(title: str, separator: str) -> int:
    parts = [part.strip() for part in title.split(separator)]
    return sum(1 for part in parts if _looks_like_author_segment(part))




def _looks_like_comma_author_list(title: str) -> bool:
    if title.count(", ") < 3:
        return False
    parts = [part.strip() for part in title.split(",")]
    if len(parts) < 4:
        return False
    author_like = [part for part in parts if _looks_like_author_segment(part)]
    return len(author_like) >= 4 and len(author_like) >= len(parts) - 1


def _looks_like_editorial_bio(title: str) -> bool:
    return bool(_EDITORIAL_ROLE_RE.search(title) and len(_ACRONYM_RE.findall(title)) >= 2)


def is_plausible_paper_title(title: str | None) -> bool:
    """Return whether *title* looks like a real paper title."""
    if title is None:
        return False
    normalized = _normalize(str(title))
    if len(normalized) < 8 or len(normalized) > 300:
        return False
    if normalized.count(";") > 3:
        return False
    if normalized.count("; ") >= 2 and _count_author_like_segments(normalized, ";") >= 3:
        return False
    if _looks_like_comma_author_list(normalized):
        return False
    if _PAREN_PREFIX_RE.match(normalized):
        return False
    if _looks_like_editorial_bio(normalized):
        return False
    return True
