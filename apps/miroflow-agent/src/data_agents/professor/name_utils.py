# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Name parsing helpers for professor enrichment."""
from __future__ import annotations

from collections import Counter
from html import unescape
import re
from urllib.parse import urlparse


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_ENGLISH_NAME_RE = re.compile(
    r"\b[A-Z][a-z]+(?:[-'][A-Za-z]+)?(?:\s+[A-Z][a-z]+(?:[-'][A-Za-z]+)?){1,3}\b"
)
_URL_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{3,32}$")
_URL_SUFFIX_RE = re.compile(r"\.(?:html?|php|aspx?)$", re.IGNORECASE)
_GENERIC_URL_SLUGS = {
    "faculty",
    "home",
    "homepage",
    "index",
    "info",
    "list",
    "main",
    "member",
    "members",
    "people",
    "profile",
    "profiles",
    "search",
    "staff",
    "teacher",
    "teachers",
}
_STOPWORDS = {
    "Access",
    "Professor",
    "Associate",
    "Assistant",
    "English",
    "Research",
    "School",
    "College",
    "University",
    "Department",
    "Faculty",
    "Publications",
    "Publication",
    "Curriculum",
    "Vitae",
    "Profile",
    "Published",
    "Time",
    "URL",
    "Source",
    "Markdown",
    "Content",
    "Network",
    "Learning",
    "Recognition",
    "Processing",
    "Communication",
    "Design",
    "Model",
    "Models",
    "Analysis",
    "Review",
    "Journal",
    "Transactions",
    "Proceedings",
    "Materials",
    "Applied",
    "Association",
    "View",
    "More",
    "Nano",
    "Lett",
    "Letters",
    "Menu",
    "Nature",
    "Photonic",
    "Photonics",
    "Road",
    "Search",
    "Statistica",
    "Sinica",
    "Statistics",
    "Statistical",
    "Society",
    "International",
    "Institute",
    "Center",
    "Centre",
    "Laboratory",
    "Lab",
    "Academy",
    "Hospital",
    "Clinic",
    "Bio-X",
    "Mediated",
    "Social",
    "Touch",
    "In",
    "Light",
    "Sci",
}
_STOPWORDS_CASEFOLD = {word.casefold() for word in _STOPWORDS}
_BLOCKED_PHRASES_CASEFOLD = {
    "applied statistics",
    "acta materialia",
    "early access",
    "english search",
    "gongchang road",
    "integrative plant biology",
    "view more",
    "nano lett",
    "nature photonics",
    "search menu",
    "statistica sinica",
    "bio-x international institute",
    "mediated social touch",
    "light sci",
    "central saint martins",
    "arts london",
    "all rights reserved",
}
_COMPOUND_SURNAMES = (
    "ouyang",
    "zhuge",
    "shangguan",
    "huangfu",
    "sima",
    "situ",
    "duanmu",
    "linghu",
    "ximen",
    "gongsun",
    "nangong",
)
_COMMON_SURNAMES = (
    "zhang", "wang", "li", "zhao", "liu", "chen", "yang", "huang", "wu", "zhou",
    "xu", "sun", "ma", "zhu", "hu", "guo", "he", "gao", "lin", "luo", "zheng",
    "liang", "xie", "song", "tang", "han", "feng", "cao", "peng", "zeng", "xiao",
    "tian", "dong", "pan", "yuan", "cai", "jiang", "yu", "du", "wei", "su", "ye",
    "lv", "ding", "ren", "shen", "yao", "fan", "lu", "dai", "fu", "fang", "bai",
    "meng", "qian", "hou", "yin", "xiong", "tan", "jin", "shi", "yan", "kong",
    "xian",
)


def normalize_english_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _WHITESPACE_RE.sub(" ", value).strip(" ,;:/")
    if not normalized or not any(char.isascii() and char.isalpha() for char in normalized):
        return None
    return normalized


def extract_english_name_candidates(text: str) -> list[str]:
    plain_text = _WHITESPACE_RE.sub(" ", unescape(_HTML_TAG_RE.sub(" ", text or "")))
    candidates: list[str] = []
    seen: set[str] = set()
    for match in _ENGLISH_NAME_RE.finditer(plain_text):
        candidate = _normalize_name_candidate(match.group(0))
        if candidate is None:
            continue
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


def select_best_english_name_candidate(
    text: str,
    *,
    url: str | None = None,
) -> str | None:
    plain_text = _WHITESPACE_RE.sub(" ", unescape(_HTML_TAG_RE.sub(" ", text or "")))
    matches: list[str] = []
    for match in _ENGLISH_NAME_RE.finditer(plain_text):
        candidate = _normalize_name_candidate(match.group(0))
        if candidate is not None:
            matches.append(candidate)
    if not matches:
        return None

    counts = Counter(matches)
    url_candidates = {
        candidate.casefold(): candidate
        for candidate in derive_english_name_candidates_from_url(url)
    }
    for candidate in matches:
        if candidate.casefold() in url_candidates:
            return candidate

    ranked = sorted(
        counts.items(),
        key=lambda item: (-item[1], matches.index(item[0]), item[0]),
    )
    best_candidate, best_count = ranked[0]
    if best_count >= 2:
        return best_candidate
    if len(counts) == 1:
        return best_candidate
    return None


def sanitize_english_person_name(value: str | None) -> str | None:
    if not value:
        return None
    return _normalize_name_candidate(value)


def derive_english_name_candidates_from_url(url: str | None) -> list[str]:
    if not url:
        return []

    parsed = urlparse(url)
    slug = (parsed.path.rstrip("/").split("/")[-1] if parsed.path else "").strip()
    slug = _URL_SUFFIX_RE.sub("", slug)
    slug_lower = slug.casefold()
    if not slug or not _URL_SLUG_RE.fullmatch(slug_lower):
        return []
    if slug_lower in _GENERIC_URL_SLUGS:
        return []

    if "-" in slug_lower or "_" in slug_lower:
        raw_parts = [part for part in re.split(r"[-_]+", slug_lower) if part]
        if len(raw_parts) >= 2:
            surname = raw_parts[0]
            given = "".join(raw_parts[1:])
        else:
            surname, given = "", ""
    else:
        compact_slug = re.sub(r"[^a-z]", "", slug_lower)
        surname = _match_surname_prefix(compact_slug)
        given = compact_slug[len(surname):] if surname else ""

    if not surname or not given:
        return []

    surname_text = _title_case_pinyin(surname)
    given_text = _title_case_pinyin(given)
    return [
        f"{given_text} {surname_text}",
        f"{surname_text} {given_text}",
    ]


def _match_surname_prefix(slug: str) -> str:
    for candidate in _COMPOUND_SURNAMES:
        if slug.startswith(candidate) and len(slug) > len(candidate):
            return candidate
    for candidate in _COMMON_SURNAMES:
        if slug.startswith(candidate) and len(slug) > len(candidate):
            return candidate
    return ""


def _title_case_pinyin(value: str) -> str:
    return value[:1].upper() + value[1:]


def _normalize_name_candidate(value: str) -> str | None:
    candidate = normalize_english_name(value)
    if not candidate:
        return None
    if candidate.casefold() in _BLOCKED_PHRASES_CASEFOLD:
        return None
    tokens = candidate.split()
    if not (2 <= len(tokens) <= 4):
        return None
    if any(token.casefold() in _STOPWORDS_CASEFOLD for token in tokens):
        return None
    return candidate
