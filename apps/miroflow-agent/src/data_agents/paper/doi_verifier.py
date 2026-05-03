from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

from src.data_agents.paper.title_cleaner import clean_paper_title
from src.data_agents.paper.title_resolver import (
    ResolvedPaper,
    _arxiv_entry_to_resolved,
    _normalize_title_for_match,
    _openalex_work_to_resolved,
    _search_arxiv_by_title,
    _search_openalex_by_title,
)

VerificationSource = Literal["cache", "openalex", "arxiv"]

_TITLE_SCORE_THRESHOLD = 85.0
_AUTHOR_JACCARD_THRESHOLD = 0.3
_AUTHOR_SPLIT_RE = re.compile(r"\s*(?:,|，|;|；|、|\band\b)\s*", re.IGNORECASE)
_AUTHOR_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")


@dataclass(frozen=True, slots=True)
class DoiVerification:
    status: Literal["confirmed"]
    source: VerificationSource
    resolved: ResolvedPaper
    title_score: float
    author_jaccard: float

    @property
    def external_id(self) -> str | None:
        return external_id_from_resolved(self.resolved)


def verify_via_cache(paper_row: Mapping[str, Any]) -> DoiVerification | None:
    resolved = _coerce_resolved_paper(
        paper_row.get("cached_resolution") or paper_row.get("resolved")
    )
    if resolved is None or external_id_from_resolved(resolved) is None:
        return None
    return DoiVerification(
        status="confirmed",
        source="cache",
        resolved=resolved,
        title_score=100.0,
        author_jaccard=1.0,
    )


def verify_via_openalex(
    title: str,
    authors: object,
    *,
    openalex_client=None,
) -> DoiVerification | None:
    clean_title = clean_paper_title(title)
    if not clean_title:
        return None
    candidates = _search_openalex_by_title(clean_title, http_client=openalex_client)
    return _best_confirmed_candidate(
        candidates,
        query_title=clean_title,
        query_authors=authors,
        source="openalex",
        converter=_openalex_work_to_resolved,
    )


def verify_via_arxiv(
    title: str,
    authors: object,
    *,
    arxiv_client=None,
) -> DoiVerification | None:
    clean_title = clean_paper_title(title)
    if not clean_title:
        return None
    candidates = _search_arxiv_by_title(clean_title, http_client=arxiv_client)
    return _best_confirmed_candidate(
        candidates,
        query_title=clean_title,
        query_authors=authors,
        source="arxiv",
        converter=_arxiv_entry_to_resolved,
    )


def verify_paper_row(
    paper_row: Mapping[str, Any],
    *,
    cached_resolution: ResolvedPaper | Mapping[str, Any] | None = None,
    openalex_client=None,
    arxiv_client=None,
) -> DoiVerification | None:
    row_with_cache = dict(paper_row)
    row_with_cache["cached_resolution"] = cached_resolution
    cached = verify_via_cache(row_with_cache)
    if cached is not None:
        return cached

    title = str(paper_row.get("title_clean") or paper_row.get("title_raw") or "")
    authors = normalize_authors(
        paper_row.get("authors_raw") or paper_row.get("authors_display")
    )
    openalex = verify_via_openalex(
        title,
        authors,
        openalex_client=openalex_client,
    )
    if openalex is not None:
        return openalex
    return verify_via_arxiv(title, authors, arxiv_client=arxiv_client)


def external_id_from_resolved(value: ResolvedPaper) -> str | None:
    return value.doi or value.arxiv_id or value.openalex_id


def normalize_authors(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return tuple(
                item
                for item in (
                    clean_paper_title(part) for part in _AUTHOR_SPLIT_RE.split(value)
                )
                if item
            )
        return normalize_authors(parsed)
    if isinstance(value, Mapping):
        nested_authors = value.get("authors")
        if nested_authors is not None:
            return normalize_authors(nested_authors)
        name = _author_name_from_mapping(value)
        return (name,) if name else ()
    if isinstance(value, Sequence):
        authors: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                name = _author_name_from_mapping(item)
            else:
                name = clean_paper_title(str(item or ""))
            if name:
                authors.append(name)
        return tuple(authors)
    return ()


def title_match_score(left: str, right: str) -> float:
    normalized_left = _normalize_title_for_match(clean_paper_title(left))
    normalized_right = _normalize_title_for_match(clean_paper_title(right))
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio() * 100.0


def author_token_jaccard(left: object, right: object) -> float:
    left_tokens = _author_tokens(normalize_authors(left))
    right_tokens = _author_tokens(normalize_authors(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _best_confirmed_candidate(
    candidates: object,
    *,
    query_title: str,
    query_authors: object,
    source: VerificationSource,
    converter,
) -> DoiVerification | None:
    if not isinstance(candidates, Sequence):
        return None

    best: DoiVerification | None = None
    for candidate in candidates:
        try:
            resolved, _confidence = converter(
                candidate,
                query_title=query_title,
                author_hint=None,
                year_hint=None,
            )
        except TypeError:
            raise
        except Exception:
            continue

        decision = _confirmed_if_match(
            query_title=query_title,
            query_authors=query_authors,
            resolved=resolved,
            source=source,
        )
        if decision is None:
            continue
        if best is None or _decision_sort_key(decision) > _decision_sort_key(best):
            best = decision
    return best


def _confirmed_if_match(
    *,
    query_title: str,
    query_authors: object,
    resolved: ResolvedPaper,
    source: VerificationSource,
) -> DoiVerification | None:
    if external_id_from_resolved(resolved) is None:
        return None
    title_score = title_match_score(query_title, resolved.title)
    author_jaccard = author_token_jaccard(query_authors, resolved.authors)
    if title_score < _TITLE_SCORE_THRESHOLD:
        return None
    if author_jaccard < _AUTHOR_JACCARD_THRESHOLD:
        return None
    return DoiVerification(
        status="confirmed",
        source=source,
        resolved=resolved,
        title_score=title_score,
        author_jaccard=author_jaccard,
    )


def _decision_sort_key(decision: DoiVerification) -> tuple[float, float]:
    return (decision.title_score, decision.author_jaccard)


def _coerce_resolved_paper(value: object) -> ResolvedPaper | None:
    if isinstance(value, ResolvedPaper):
        return value
    if not isinstance(value, Mapping):
        return None
    authors = value.get("authors") or ()
    return ResolvedPaper(
        title=str(value.get("title") or ""),
        doi=_optional_str(value.get("doi")),
        openalex_id=_optional_str(value.get("openalex_id")),
        arxiv_id=_optional_str(value.get("arxiv_id")),
        abstract=_optional_str(value.get("abstract")),
        pdf_url=_optional_str(value.get("pdf_url")),
        authors=normalize_authors(authors),
        year=_optional_int(value.get("year")),
        venue=_optional_str(value.get("venue")),
        match_confidence=float(value.get("match_confidence") or 0.0),
        match_source=str(value.get("match_source") or "cache"),
    )


def _author_name_from_mapping(value: Mapping[str, Any]) -> str:
    for key in ("name", "display_name", "author_name", "full_name"):
        name = clean_paper_title(value.get(key))
        if name:
            return name
    author = value.get("author")
    if isinstance(author, Mapping):
        return _author_name_from_mapping(author)
    family = clean_paper_title(value.get("family"))
    given = clean_paper_title(value.get("given"))
    if family or given:
        return " ".join(part for part in (given, family) if part)
    return ""


def _author_tokens(authors: Sequence[str]) -> frozenset[str]:
    tokens: set[str] = set()
    for author in authors:
        cleaned = clean_paper_title(author).casefold()
        if not cleaned:
            continue
        compact = re.sub(r"\s+", "", cleaned)
        if compact:
            tokens.add(compact)
        for token in _AUTHOR_TOKEN_RE.findall(cleaned):
            if len(token) >= 2:
                tokens.add(token)
    return frozenset(tokens)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
