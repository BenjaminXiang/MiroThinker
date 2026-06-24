from __future__ import annotations

import re

from src.data_agents.paper.text_sanitizer import sanitize_text_for_postgres

_AUTHOR_LIST_HEAD_RE = re.compile(
    r"^[A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+)*"
    r"(?:\s*,\s*[A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+)*){2,}"
)
_CITATION_METADATA_RE = re.compile(
    r"\b(?:Proceedings of the|Annual Meeting of the|Conference on|"
    r"International Joint Conference|Association for Computational Linguistics)\b",
    re.IGNORECASE,
)
_PUBLISHER_NOTE_RE = re.compile(
    r"^\s*(?:please note|the publisher is not responsible|"
    r"proceedings of the national academy of sciences|international audience)\b",
    re.IGNORECASE,
)
_TRUNCATED_FRAGMENT_RE = re.compile(r"\[\s*\.\.\.\s*\]")
_LEADING_FRAGMENT_RE = re.compile(r"^\s*(?:and|or|but)\b", re.IGNORECASE)
_VENUE_ONLY_RE = re.compile(
    r"^\s*[A-Z][A-Za-z&/ .'-]+Conference\s+\d{4},\s+"
    r"[A-Z][A-Za-z .'-]+,\s+[A-Za-z .'-]+,\s+"
    r"(?:\d{1,2}-\d{1,2}\s+[A-Z][A-Za-z]+\s+\d{4}|"
    r"[A-Z][A-Za-z]+\s+\d{1,2}-\d{1,2},\s+\d{4})\s*$"
)
_AUTHOR_AFFILIATION_RE = re.compile(
    r"^\s*[A-Z][A-Za-z'’.-]+[a-z]?\*?"
    r".{0,220}\b[a-z]\s+"
    r"(?:School|Department|University|Institute|College)\b",
    re.IGNORECASE,
)


def is_usable_paper_source_text(value: object) -> bool:
    text = sanitize_text_for_postgres(str(value or "").strip()) or ""
    if not text:
        return False
    if len(text) < 30:
        return False
    if _PUBLISHER_NOTE_RE.search(text):
        return False
    if _TRUNCATED_FRAGMENT_RE.search(text):
        return False
    if _LEADING_FRAGMENT_RE.search(text):
        return False
    if _VENUE_ONLY_RE.search(text):
        return False
    if _AUTHOR_AFFILIATION_RE.search(text):
        return False
    if _CITATION_METADATA_RE.search(text) and _AUTHOR_LIST_HEAD_RE.search(text):
        return False
    return True
