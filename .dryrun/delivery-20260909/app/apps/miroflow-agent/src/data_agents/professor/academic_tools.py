from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)

_ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}
_PUNCTUATION_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


@dataclass(frozen=True, slots=True)
class AcademicAuthorInfo:
    h_index: int | None
    citation_count: int | None
    paper_count: int | None
    source: str


@dataclass(frozen=True, slots=True)
class RawPaperRecord:
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    abstract: str | None
    doi: str | None
    citation_count: int | None
    keywords: list[str]
    source_url: str
    source: str


@dataclass(frozen=True, slots=True)
class PaperCollectionResult:
    papers: list[RawPaperRecord]
    author_info: AcademicAuthorInfo | None
    disambiguation_confidence: float
    sources_attempted: list[str]
    sources_succeeded: list[str]


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _WHITESPACE_RE.sub(" ", str(value)).strip()
    return text or None


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _author_name_from_value(value: Any) -> str | None:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        for key in ("text", "#text", "name"):
            text = _clean_text(value.get(key))
            if text:
                return text
    return _clean_text(value)


def _extract_affiliations(author: dict[str, Any]) -> list[str]:
    affiliations: list[str] = []
    for affiliation in _as_list(author.get("affiliations")):
        text = _author_name_from_value(affiliation)
        if text:
            affiliations.append(text)
    return affiliations


def _normalized_text(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.casefold()
    lowered = _PUNCTUATION_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", lowered).strip()


def _normalized_title(value: str) -> str:
    return _normalized_text(value)


def _normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def _record_quality(record: RawPaperRecord) -> int:
    return sum(
        (
            bool(record.authors),
            record.year is not None,
            record.venue is not None,
            record.abstract is not None,
            record.doi is not None,
            record.citation_count is not None,
            bool(record.keywords),
            bool(record.source_url),
        )
    )


def _prefer_richer_record(current: RawPaperRecord, candidate: RawPaperRecord) -> RawPaperRecord:
    if _record_quality(candidate) > _record_quality(current):
        return candidate
    return current


def _keyword_overlap_score(record: RawPaperRecord, existing_directions: list[str]) -> float:
    if not existing_directions:
        return 0.0

    normalized_directions = [_normalized_text(direction) for direction in existing_directions]
    normalized_directions = [direction for direction in normalized_directions if direction]
    if not normalized_directions:
        return 0.0

    keyword_texts = [_normalized_text(keyword) for keyword in record.keywords]
    keyword_texts = [keyword for keyword in keyword_texts if keyword]
    if not keyword_texts:
        return 0.0

    keyword_tokens = {
        token
        for keyword in keyword_texts
        for token in _WORD_RE.findall(keyword)
    }
    direction_tokens = {
        token
        for direction in normalized_directions
        for token in _WORD_RE.findall(direction)
    }

    exact_matches = sum(
        1
        for direction in normalized_directions
        if any(direction in keyword or keyword in direction for keyword in keyword_texts)
    )
    token_overlap = len(keyword_tokens & direction_tokens)
    total = max(len(normalized_directions), 1)
    return min(1.0, max(exact_matches / total, token_overlap / max(len(direction_tokens), 1)))


def _name_match_score(authors: list[str], target_name: str) -> float:
    normalized_target = _normalized_text(target_name)
    if not normalized_target:
        return 0.0
    if not authors:
        return 0.0

    best_score = 0.0
    for author in authors:
        normalized_author = _normalized_text(author)
        if not normalized_author:
            continue
        if normalized_author == normalized_target:
            return 1.0
        if normalized_target in normalized_author or normalized_author in normalized_target:
            best_score = max(best_score, 0.85)
            continue
        best_score = max(best_score, SequenceMatcher(None, normalized_author, normalized_target).ratio())
    return best_score


def _institution_match_score(record: RawPaperRecord, target_institution: str) -> float:
    normalized_institution = _normalized_text(target_institution)
    if not normalized_institution:
        return 0.0

    fields = (
        _normalized_text(record.venue),
        _normalized_text(record.source_url),
        _normalized_text(record.source),
    )
    haystack = " ".join(field for field in fields if field)
    if not haystack:
        return 0.0
    if normalized_institution in haystack:
        return 1.0

    institution_tokens = set(_WORD_RE.findall(normalized_institution))
    haystack_tokens = set(_WORD_RE.findall(haystack))
    if not institution_tokens or not haystack_tokens:
        return 0.0
    return len(institution_tokens & haystack_tokens) / len(institution_tokens)


def scrape_semantic_scholar(
    name: str,
    institution: str,
    *,
    fetch_html: Any,
    timeout: float,
) -> tuple[list[RawPaperRecord], AcademicAuthorInfo | None]:
    del fetch_html

    response = requests.get(
        "https://api.semanticscholar.org/graph/v1/author/search",
        params={
            "query": name,
            "fields": (
                "name,hIndex,citationCount,paperCount,affiliations,"
                "papers.title,papers.year,papers.venue,papers.citationCount,"
                "papers.externalIds,papers.abstract"
            ),
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    authors = _as_list(payload.get("data"))

    normalized_institution = _normalized_text(institution)
    selected_author: dict[str, Any] | None = None
    fallback_author: dict[str, Any] | None = None

    for author in authors:
        if not isinstance(author, dict):
            continue
        fallback_author = fallback_author or author
        affiliations = _extract_affiliations(author)
        if normalized_institution and any(
            normalized_institution in _normalized_text(affiliation) for affiliation in affiliations
        ):
            selected_author = author
            break

    selected_author = selected_author or fallback_author
    if selected_author is None:
        return [], None

    author_name = _clean_text(selected_author.get("name")) or name
    author_id = _clean_text(selected_author.get("authorId"))
    author_source_url = (
        f"https://www.semanticscholar.org/author/{author_id}" if author_id else "https://www.semanticscholar.org"
    )

    papers: list[RawPaperRecord] = []
    for paper in _as_list(selected_author.get("papers")):
        if not isinstance(paper, dict):
            continue
        title = _clean_text(paper.get("title"))
        if not title:
            continue
        paper_authors = [_clean_text(author_name)] if author_name else []
        papers.append(
            RawPaperRecord(
                title=title,
                authors=[author for author in paper_authors if author],
                year=_parse_int(paper.get("year")),
                venue=_clean_text(paper.get("venue")),
                abstract=_clean_text(paper.get("abstract")),
                doi=_clean_text((paper.get("externalIds") or {}).get("DOI")),
                citation_count=_parse_int(paper.get("citationCount")),
                keywords=[],
                source_url=author_source_url,
                source="semantic_scholar",
            )
        )

    author_info = AcademicAuthorInfo(
        h_index=_parse_int(selected_author.get("hIndex")),
        citation_count=_parse_int(selected_author.get("citationCount")),
        paper_count=_parse_int(selected_author.get("paperCount")),
        source="semantic_scholar",
    )
    return papers, author_info


def scrape_dblp(name: str, *, fetch_html: Any, timeout: float) -> list[RawPaperRecord]:
    del fetch_html

    response = requests.get(
        "https://dblp.org/search/publ/api",
        params={"q": f"author:{name}", "format": "json", "h": 100},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    hits = _as_list(payload.get("result", {}).get("hits", {}).get("hit"))

    papers: list[RawPaperRecord] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        info = hit.get("info") or {}
        title = _clean_text(info.get("title"))
        if not title:
            continue
        authors_payload = (info.get("authors") or {}).get("author")
        authors = [
            author
            for author in (_author_name_from_value(value) for value in _as_list(authors_payload))
            if author
        ]
        papers.append(
            RawPaperRecord(
                title=title,
                authors=authors,
                year=_parse_int(info.get("year")),
                venue=_clean_text(info.get("venue")),
                abstract=None,
                doi=_clean_text(info.get("doi")),
                citation_count=None,
                keywords=[],
                source_url=_clean_text(info.get("url")) or "https://dblp.org",
                source="dblp",
            )
        )
    return papers


def scrape_arxiv(name: str, *, fetch_html: Any, timeout: float) -> list[RawPaperRecord]:
    del fetch_html

    response = requests.get(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": f"au:{name}",
            "max_results": 50,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)

    papers: list[RawPaperRecord] = []
    for entry in root.findall("atom:entry", _ATOM_NAMESPACE):
        title = _clean_text(entry.findtext("atom:title", default="", namespaces=_ATOM_NAMESPACE))
        if not title:
            continue

        authors = [
            author_name
            for author_name in (
                _clean_text(author.findtext("atom:name", default="", namespaces=_ATOM_NAMESPACE))
                for author in entry.findall("atom:author", _ATOM_NAMESPACE)
            )
            if author_name
        ]
        published = _clean_text(entry.findtext("atom:published", default="", namespaces=_ATOM_NAMESPACE))
        year = _parse_int(published[:4]) if published else None
        keywords = [
            category_term
            for category_term in (
                _clean_text(category.attrib.get("term"))
                for category in entry.findall("atom:category", _ATOM_NAMESPACE)
            )
            if category_term
        ]
        papers.append(
            RawPaperRecord(
                title=title,
                authors=authors,
                year=year,
                venue="arXiv",
                abstract=_clean_text(entry.findtext("atom:summary", default="", namespaces=_ATOM_NAMESPACE)),
                doi=None,
                citation_count=None,
                keywords=keywords,
                source_url=(
                    _clean_text(entry.findtext("atom:id", default="", namespaces=_ATOM_NAMESPACE))
                    or "https://arxiv.org"
                ),
                source="arxiv",
            )
        )
    return papers


def merge_papers(*paper_lists: list[RawPaperRecord]) -> list[RawPaperRecord]:
    by_doi: dict[str, RawPaperRecord] = {}
    without_doi: list[RawPaperRecord] = []

    for paper_list in paper_lists:
        for paper in paper_list:
            normalized_doi = _normalize_doi(paper.doi)
            if normalized_doi:
                if normalized_doi in by_doi:
                    by_doi[normalized_doi] = _prefer_richer_record(by_doi[normalized_doi], paper)
                else:
                    by_doi[normalized_doi] = paper
            else:
                without_doi.append(paper)

    merged_records = [*by_doi.values(), *without_doi]
    by_title_year: dict[tuple[str, int | None], RawPaperRecord] = {}
    ordered_keys: list[tuple[str, int | None]] = []

    for paper in merged_records:
        key = (_normalized_title(paper.title), paper.year)
        if key not in by_title_year:
            by_title_year[key] = paper
            ordered_keys.append(key)
            continue
        by_title_year[key] = _prefer_richer_record(by_title_year[key], paper)

    return [by_title_year[key] for key in ordered_keys]


def disambiguate_author(
    candidates: list[RawPaperRecord],
    *,
    target_name: str,
    target_institution: str,
    existing_directions: list[str],
) -> tuple[list[RawPaperRecord], float]:
    if not candidates:
        return [], 0.0

    scored_candidates: list[tuple[RawPaperRecord, float]] = []
    max_institution = 0.0
    max_research = 0.0
    max_name = 0.0

    for candidate in candidates:
        institution_score = _institution_match_score(candidate, target_institution)
        research_score = _keyword_overlap_score(candidate, existing_directions)
        name_score = _name_match_score(candidate.authors, target_name)

        max_institution = max(max_institution, institution_score)
        max_research = max(max_research, research_score)
        max_name = max(max_name, name_score)

        score = (0.4 * institution_score) + (0.35 * research_score) + (0.25 * name_score)
        scored_candidates.append((candidate, score))

    confidence = round(min(1.0, (0.4 * max_institution) + (0.35 * max_research) + (0.25 * max_name)), 3)
    filtered = [candidate for candidate, score in scored_candidates if score >= 0.35]
    return filtered, confidence


def collect_papers(
    *,
    name: str,
    name_en: str | None,
    institution: str,
    institution_en: str | None,
    existing_directions: list[str],
    fetch_html: Any,
    timeout: float = 30,
    crawl_delay: float = 2.0,
) -> PaperCollectionResult:
    search_name = name_en or name
    search_institution = institution_en or institution

    sources_attempted: list[str] = []
    sources_succeeded: list[str] = []
    all_paper_lists: list[list[RawPaperRecord]] = []
    author_info: AcademicAuthorInfo | None = None

    source_calls = (
        ("semantic_scholar", lambda: scrape_semantic_scholar(search_name, search_institution, fetch_html=fetch_html, timeout=timeout)),
        ("dblp", lambda: scrape_dblp(search_name, fetch_html=fetch_html, timeout=timeout)),
        ("arxiv", lambda: scrape_arxiv(search_name, fetch_html=fetch_html, timeout=timeout)),
    )

    for index, (source_name, source_call) in enumerate(source_calls):
        sources_attempted.append(source_name)
        try:
            result = source_call()
            if source_name == "semantic_scholar":
                papers, author_info = result
            else:
                papers = result
            all_paper_lists.append(papers)
            sources_succeeded.append(source_name)
        except Exception as exc:  # noqa: BLE001 - source failure should not abort the pipeline.
            LOGGER.warning("academic source scrape failed for %s via %s: %s", search_name, source_name, exc)
        if index < len(source_calls) - 1:
            time.sleep(crawl_delay)

    merged_papers = merge_papers(*all_paper_lists)
    filtered_papers, confidence = disambiguate_author(
        merged_papers,
        target_name=search_name,
        target_institution=search_institution,
        existing_directions=existing_directions,
    )
    return PaperCollectionResult(
        papers=filtered_papers,
        author_info=author_info,
        disambiguation_confidence=confidence,
        sources_attempted=sources_attempted,
        sources_succeeded=sources_succeeded,
    )
