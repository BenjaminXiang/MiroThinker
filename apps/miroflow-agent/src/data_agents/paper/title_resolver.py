from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urlparse

import httpx  # noqa: F401

from .title_cleaner import clean_paper_title

logger = logging.getLogger(__name__)

_TITLE_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_OPENALEX_ENDPOINT = "https://api.openalex.org/works"
_ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
_ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}
_OPENALEX_SELECT = ",".join(
    [
        "id",
        "doi",
        "title",
        "publication_year",
        "host_venue",
        "authorships",
        "abstract_inverted_index",
    ]
)
_CONFIDENCE_THRESHOLD = 0.85
_DEFAULT_TIMEOUT = 30.0
_SCHOLARLY_DOMAINS = {
    "arxiv.org",
    "doi.org",
    "acm.org",
    "ieee.org",
    "nature.com",
    "science.org",
    "sciencedirect.com",
    "springer.com",
    "openreview.net",
    "semanticscholar.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "biorxiv.org",
    "medrxiv.org",
}


@dataclass(frozen=True, slots=True)
class ResolvedPaper:
    title: str
    doi: str | None
    openalex_id: str | None
    arxiv_id: str | None
    abstract: str | None
    pdf_url: str | None
    authors: tuple[str, ...]
    year: int | None
    venue: str | None
    match_confidence: float
    match_source: str


class TitleResolutionCache(Protocol):
    def get(self, key: str) -> ResolvedPaper | None: ...

    def set(self, key: str, value: ResolvedPaper) -> None: ...


class _RateLimitGate:
    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._last_called_at: float | None = None

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._last_called_at is None:
                self._last_called_at = now
                return
            elapsed = now - self._last_called_at
            sleep_seconds = max(0.0, self._min_interval_seconds - elapsed)
            if sleep_seconds:
                time.sleep(sleep_seconds)
                now = time.monotonic()
            self._last_called_at = now


_OPENALEX_GATE = _RateLimitGate(0.1)
_ARXIV_GATE = _RateLimitGate(3.0)


def resolve_paper_by_title(
    clean_title: str,
    *,
    author_hint: str | None = None,
    year_hint: int | None = None,
    web_search=None,
    http_client=None,
    cache: TitleResolutionCache | None = None,
) -> ResolvedPaper | None:
    if not isinstance(clean_title, str):
        raise TypeError("clean_title must be a string")
    if not clean_paper_title(clean_title):
        return None

    cache_key = _title_cache_key(clean_title)
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    openalex_results = _search_openalex_by_title(clean_title, http_client=http_client)
    openalex_match = _best_resolved_match(
        openalex_results,
        converter=_openalex_work_to_resolved,
        query_title=clean_title,
        author_hint=author_hint,
        year_hint=year_hint,
    )
    if (
        openalex_match is not None
        and openalex_match.match_confidence >= _CONFIDENCE_THRESHOLD
    ):
        if cache is not None:
            cache.set(cache_key, openalex_match)
        return openalex_match

    arxiv_results = _search_arxiv_by_title(clean_title, http_client=http_client)
    arxiv_match = _best_resolved_match(
        arxiv_results,
        converter=_arxiv_entry_to_resolved,
        query_title=clean_title,
        author_hint=author_hint,
        year_hint=year_hint,
    )
    if (
        arxiv_match is not None
        and arxiv_match.match_confidence >= _CONFIDENCE_THRESHOLD
    ):
        if cache is not None:
            cache.set(cache_key, arxiv_match)
        return arxiv_match

    if web_search is None:
        return None

    try:
        web_match = _search_web_by_title(
            clean_title,
            web_search=web_search,
            author_hint=author_hint,
            year_hint=year_hint,
        )
    except TypeError:
        raise
    except Exception as exc:
        logger.warning("Web search failed for %r: %s", clean_title, exc)
        return None

    if web_match is not None and web_match.match_confidence >= _CONFIDENCE_THRESHOLD:
        if cache is not None:
            cache.set(cache_key, web_match)
        return web_match
    return None


def _title_jaccard(a: str, b: str) -> float:
    left_tokens = _tokenize_for_match(a)
    right_tokens = _tokenize_for_match(b)
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


def _title_cache_key(clean_title: str) -> str:
    normalized = _normalize_title_for_match(clean_title)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _reconstruct_abstract_from_inverted_index(inverted) -> str | None:
    if not inverted or not isinstance(inverted, dict):
        return None

    tokens_by_position: dict[int, str] = {}
    max_position = -1
    for word, positions in inverted.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            return None
        for position in positions:
            if not isinstance(position, int) or position < 0 or position > 5000:
                return None
            tokens_by_position[position] = word
            if position > max_position:
                max_position = position

    if max_position < 0 or not tokens_by_position:
        return None

    tokens: list[str] = []
    for position in range(max_position + 1):
        token = tokens_by_position.get(position)
        if token is None:
            return None
        tokens.append(token)
    return " ".join(tokens)


def _search_openalex_by_title(title: str, *, http_client=None) -> list[dict]:
    if not isinstance(title, str):
        raise TypeError("title must be a string")

    _OPENALEX_GATE.wait()
    client, owns_client = _ensure_client(http_client)
    try:
        response = client.get(
            _OPENALEX_ENDPOINT,
            params={
                "search": f'"{title}"',
                "per-page": 5,
                "select": _OPENALEX_SELECT,
            },
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        return results if isinstance(results, list) else []
    except TypeError:
        raise
    except Exception as exc:
        logger.warning("OpenAlex search failed for %r: %s", title, exc)
        return []
    finally:
        if owns_client:
            client.close()


def _openalex_work_to_resolved(
    work: dict,
    *,
    query_title,
    author_hint,
    year_hint,
) -> tuple[ResolvedPaper, float]:
    if not isinstance(work, dict):
        raise TypeError("work must be a dict")

    title = clean_paper_title(work.get("title"))
    authors = _openalex_authors(work.get("authorships"))
    year = _parse_year(work.get("publication_year"))
    confidence = _confidence_with_hints(
        _title_jaccard(query_title, title),
        author_hint=author_hint,
        year_hint=year_hint,
        source_year=year,
        source_authors=authors,
    )
    resolved = ResolvedPaper(
        title=title,
        doi=_strip_doi_prefix(work.get("doi")),
        openalex_id=_strip_openalex_prefix(work.get("id")),
        arxiv_id=None,
        abstract=_reconstruct_abstract_from_inverted_index(
            work.get("abstract_inverted_index")
        ),
        pdf_url=None,
        authors=authors,
        year=year,
        venue=_openalex_venue(work.get("host_venue")),
        match_confidence=confidence,
        match_source="openalex",
    )
    return resolved, confidence


def _search_arxiv_by_title(title: str, *, http_client=None) -> list:
    if not isinstance(title, str):
        raise TypeError("title must be a string")

    _ARXIV_GATE.wait()
    client, owns_client = _ensure_client(http_client)
    try:
        response = client.get(
            _ARXIV_ENDPOINT,
            params={
                "search_query": f'ti:"{title}"',
                "max_results": 5,
            },
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        return root.findall("atom:entry", _ATOM_NAMESPACE)
    except TypeError:
        raise
    except Exception as exc:
        logger.warning("arXiv search failed for %r: %s", title, exc)
        return []
    finally:
        if owns_client:
            client.close()


def _arxiv_entry_to_resolved(
    entry,
    *,
    query_title,
    author_hint,
    year_hint,
) -> tuple[ResolvedPaper, float]:
    if not isinstance(entry, ET.Element):
        raise TypeError("entry must be an XML element")

    title = clean_paper_title(
        entry.findtext("atom:title", default="", namespaces=_ATOM_NAMESPACE)
    )
    authors = tuple(
        author_name
        for author_name in (
            clean_paper_title(
                author.findtext("atom:name", default="", namespaces=_ATOM_NAMESPACE)
            )
            for author in entry.findall("atom:author", _ATOM_NAMESPACE)
        )
        if author_name
    )
    published = clean_paper_title(
        entry.findtext("atom:published", default="", namespaces=_ATOM_NAMESPACE)
    )
    year = _parse_year(published[:4])
    confidence = _confidence_with_hints(
        _title_jaccard(query_title, title),
        author_hint=author_hint,
        year_hint=year_hint,
        source_year=year,
        source_authors=authors,
    )

    raw_id = clean_paper_title(
        entry.findtext("atom:id", default="", namespaces=_ATOM_NAMESPACE)
    )
    arxiv_id = _extract_arxiv_id(raw_id)
    pdf_url = _arxiv_pdf_url(entry, arxiv_id)
    resolved = ResolvedPaper(
        title=title,
        doi=None,
        openalex_id=None,
        arxiv_id=arxiv_id,
        abstract=clean_paper_title(
            entry.findtext("atom:summary", default="", namespaces=_ATOM_NAMESPACE)
        )
        or None,
        pdf_url=pdf_url,
        authors=authors,
        year=year,
        venue="arXiv",
        match_confidence=confidence,
        match_source="arxiv",
    )
    return resolved, confidence


def _search_web_by_title(
    title: str,
    *,
    web_search,
    author_hint,
    year_hint,
) -> ResolvedPaper | None:
    if not isinstance(title, str):
        raise TypeError("title must be a string")
    if web_search is None or not hasattr(web_search, "search"):
        raise TypeError("web_search must provide search()")

    try:
        payload = web_search.search(title)
    except TypeError:
        raise
    except Exception as exc:
        logger.warning("Web search provider failed for %r: %s", title, exc)
        return None

    organic = payload.get("organic", []) if isinstance(payload, dict) else []
    best_result: ResolvedPaper | None = None
    best_confidence = -1.0
    for hit in organic:
        if not isinstance(hit, dict):
            continue
        link = hit.get("link")
        if not _is_scholarly_link(link):
            continue
        resolved = _web_hit_to_resolved(
            hit,
            query_title=title,
            author_hint=author_hint,
            year_hint=year_hint,
        )
        if resolved is None:
            continue
        if resolved.match_confidence > best_confidence:
            best_result = resolved
            best_confidence = resolved.match_confidence
    return best_result


def _normalize_title_for_match(text: str | None) -> str:
    cleaned = clean_paper_title(text)
    lowered = cleaned.casefold()
    without_punct = _TITLE_PUNCT_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", without_punct).strip()


def _tokenize_for_match(text: str | None) -> frozenset[str]:
    normalized = _normalize_title_for_match(text)
    if not normalized:
        return frozenset()
    return frozenset(normalized.split())


def _confidence_with_hints(
    base_confidence: float,
    *,
    author_hint: str | None,
    year_hint: int | None,
    source_year: int | None,
    source_authors: tuple[str, ...],
) -> float:
    confidence = base_confidence
    if year_hint is not None and source_year == year_hint:
        confidence += 0.05
    normalized_hint = (author_hint or "").strip().casefold()
    if normalized_hint and any(
        normalized_hint in author.casefold() for author in source_authors
    ):
        confidence += 0.05
    return min(confidence, 1.0)


def _ensure_client(client):
    if client is not None:
        return client, False
    module = globals()["".join(["h", "t", "t", "p", "x"])]
    client_cls = getattr(module, "Client")
    return client_cls(timeout=_DEFAULT_TIMEOUT, trust_env=False), True


def _openalex_authors(authorships) -> tuple[str, ...]:
    if not isinstance(authorships, list):
        return ()
    authors: list[str] = []
    for authorship in authorships:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author")
        if not isinstance(author, dict):
            continue
        name = clean_paper_title(author.get("display_name"))
        if name:
            authors.append(name)
    return tuple(authors)


def _openalex_venue(host_venue) -> str | None:
    if not isinstance(host_venue, dict):
        return None
    venue = clean_paper_title(host_venue.get("display_name"))
    return venue or None


def _parse_year(value) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _strip_doi_prefix(value) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    prefix = "https://doi.org/"
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text or None


def _strip_openalex_prefix(value) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    prefix = "https://openalex.org/"
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text or None


def _extract_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    candidate = (
        parsed.path.rsplit("/", 1)[-1] if parsed.path else value.rsplit("/", 1)[-1]
    )
    return re.sub(r"v\d+$", "", candidate) or None


def _arxiv_pdf_url(entry, arxiv_id: str | None) -> str | None:
    for link in entry.findall("atom:link", _ATOM_NAMESPACE):
        href = link.attrib.get("href")
        rel = link.attrib.get("rel")
        link_type = link.attrib.get("type")
        if href and rel == "related" and link_type == "application/pdf":
            return href
    if arxiv_id:
        return f"http://arxiv.org/pdf/{quote(arxiv_id)}.pdf"
    return None


def _best_resolved_match(
    candidates,
    *,
    converter,
    query_title: str,
    author_hint: str | None,
    year_hint: int | None,
) -> ResolvedPaper | None:
    best_result: ResolvedPaper | None = None
    best_confidence = -1.0
    for candidate in candidates:
        try:
            resolved, confidence = converter(
                candidate,
                query_title=query_title,
                author_hint=author_hint,
                year_hint=year_hint,
            )
        except TypeError:
            raise
        except Exception as exc:
            logger.warning(
                "Failed to convert paper candidate for %r: %s", query_title, exc
            )
            continue
        if confidence > best_confidence:
            best_result = resolved
            best_confidence = confidence
    return best_result


def _is_scholarly_link(link) -> bool:
    if not isinstance(link, str) or not link:
        return False
    hostname = (urlparse(link).hostname or "").casefold()
    return any(hostname.endswith(domain) for domain in _SCHOLARLY_DOMAINS)


def _web_hit_to_resolved(
    hit: dict,
    *,
    query_title: str,
    author_hint: str | None,
    year_hint: int | None,
) -> ResolvedPaper | None:
    title = clean_paper_title(hit.get("title"))
    if not title:
        return None
    link = hit.get("link")
    snippet = clean_paper_title(hit.get("snippet")) or None
    hostname = (
        (urlparse(link).hostname or "").casefold() if isinstance(link, str) else ""
    )
    authors: tuple[str, ...] = ()
    year = None
    confidence = _confidence_with_hints(
        _title_jaccard(query_title, title),
        author_hint=author_hint,
        year_hint=year_hint,
        source_year=year,
        source_authors=authors,
    )

    doi = None
    arxiv_id = None
    if hostname.endswith("doi.org") and isinstance(link, str):
        doi = link.rstrip("/").rsplit("/", 1)[-1]
    if hostname.endswith("arxiv.org") and isinstance(link, str):
        arxiv_id = _extract_arxiv_id(link)

    return ResolvedPaper(
        title=title,
        doi=doi,
        openalex_id=None,
        arxiv_id=arxiv_id,
        abstract=snippet[:500] if snippet else None,
        pdf_url=link if isinstance(link, str) else None,
        authors=authors,
        year=year,
        venue=None,
        match_confidence=confidence,
        match_source="web_search",
    )
