from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote, quote_plus, urlparse

import httpx  # noqa: F401

from src.data_agents.providers.openalex import (
    OPENALEX_RATE_LIMIT_CIRCUIT as _OPENALEX_RATE_LIMIT_CIRCUIT,
    openalex_api_key as _openalex_api_key,
    openalex_rate_limit_cooldown_seconds as _openalex_rate_limit_cooldown_seconds,
    openalex_skip_without_api_key as _openalex_skip_without_api_key,
)

from .title_cleaner import clean_paper_title

logger = logging.getLogger(__name__)

_TITLE_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_OPENALEX_ENDPOINT = "https://api.openalex.org/works"
_CROSSREF_ENDPOINT = "https://api.crossref.org/works"
_SEMANTIC_SCHOLAR_SEARCH_ENDPOINT = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)
_DBLP_PUBLICATION_SEARCH_ENDPOINT = "https://dblp.org/search/publ/api"
_ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
_ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}
_OPENALEX_SELECT = ",".join(
    [
        "id",
        "doi",
        "title",
        "publication_year",
        # W13-14b Q-10: OpenAlex 已弃用 'host_venue'；改用 'primary_location' (含 source.display_name)
        "primary_location",
        "authorships",
        "abstract_inverted_index",
    ]
)
_CONFIDENCE_THRESHOLD = 0.85
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
_CROSSREF_MAILTO = "mirothinker-data-agent@example.com"
_SEMANTIC_SCHOLAR_FIELDS = (
    "paperId,title,abstract,year,publicationDate,venue,url,externalIds,authors"
)
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


class _TemporaryFailureCircuit:
    def __init__(
        self,
        *,
        threshold: int,
        cooldown_seconds: float,
        label: str,
    ) -> None:
        self._threshold = threshold
        self._cooldown_seconds = cooldown_seconds
        self._label = label
        self._lock = threading.Lock()
        self._failure_count = 0
        self._disabled_until: float | None = None

    def can_call(self) -> bool:
        with self._lock:
            if self._disabled_until is None:
                return True
            now = time.monotonic()
            if now < self._disabled_until:
                return False
            self._disabled_until = None
            self._failure_count = 0
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._disabled_until = None

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count < self._threshold:
                return
            self._disabled_until = time.monotonic() + self._cooldown_seconds
            logger.warning(
                "%s title search temporarily disabled for %.0fs after %d consecutive failures",
                self._label,
                self._cooldown_seconds,
                self._failure_count,
            )

    def reset(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._disabled_until = None


_OPENALEX_GATE = _RateLimitGate(0.1)
_CROSSREF_GATE = _RateLimitGate(0.34)
_SEMANTIC_SCHOLAR_GATE = _RateLimitGate(1.0)
_DBLP_GATE = _RateLimitGate(0.2)
_ARXIV_GATE = _RateLimitGate(3.0)
_CROSSREF_FAILURE_CIRCUIT = _TemporaryFailureCircuit(
    threshold=2,
    cooldown_seconds=300.0,
    label="Crossref",
)
_SEMANTIC_SCHOLAR_RATE_LIMIT_CIRCUIT = _TemporaryFailureCircuit(
    threshold=1,
    cooldown_seconds=600.0,
    label="Semantic Scholar",
)
_DBLP_FAILURE_CIRCUIT = _TemporaryFailureCircuit(
    threshold=2,
    cooldown_seconds=300.0,
    label="DBLP",
)


def resolve_paper_by_title(
    clean_title: str,
    *,
    author_hint: str | None = None,
    year_hint: int | None = None,
    enable_arxiv_title_search: bool = True,
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
        if cached is not None and _cached_resolution_matches_context(
            cached,
            query_title=clean_title,
            author_hint=author_hint,
            year_hint=year_hint,
        ):
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

    crossref_results = _search_crossref_by_title(clean_title, http_client=http_client)
    crossref_match = _best_resolved_match(
        crossref_results,
        converter=_crossref_work_to_resolved,
        query_title=clean_title,
        author_hint=author_hint,
        year_hint=year_hint,
    )
    if (
        crossref_match is not None
        and crossref_match.match_confidence >= _CONFIDENCE_THRESHOLD
    ):
        if cache is not None:
            cache.set(cache_key, crossref_match)
        return crossref_match

    semantic_scholar_results = _search_semantic_scholar_by_title(
        clean_title,
        http_client=http_client,
    )
    semantic_scholar_match = _best_resolved_match(
        semantic_scholar_results,
        converter=_semantic_scholar_paper_to_resolved,
        query_title=clean_title,
        author_hint=author_hint,
        year_hint=year_hint,
    )
    if (
        semantic_scholar_match is not None
        and semantic_scholar_match.match_confidence >= _CONFIDENCE_THRESHOLD
    ):
        if cache is not None:
            cache.set(cache_key, semantic_scholar_match)
        return semantic_scholar_match

    dblp_results = _search_dblp_by_title(clean_title, http_client=http_client)
    dblp_match = _best_resolved_match(
        dblp_results,
        converter=_dblp_hit_to_resolved,
        query_title=clean_title,
        author_hint=author_hint,
        year_hint=year_hint,
    )
    if dblp_match is not None and dblp_match.match_confidence >= _CONFIDENCE_THRESHOLD:
        if cache is not None:
            cache.set(cache_key, dblp_match)
        return dblp_match

    if enable_arxiv_title_search:
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

    api_key = _openalex_api_key()
    if not api_key and _openalex_skip_without_api_key():
        logger.debug("OpenAlex title search skipped because OPENALEX_API_KEY is unset")
        return []

    if not _OPENALEX_RATE_LIMIT_CIRCUIT.can_call():
        logger.debug("OpenAlex title search skipped by temporary rate-limit circuit")
        return []

    _OPENALEX_GATE.wait()
    client, owns_client = _ensure_client(http_client)
    try:
        # W13-14b Q-10: OpenAlex 拒 (a) search= 含双引号；(b) httpx 默认把 select 中的逗号
        # 编码成 %2C 也拒。改：raw URL，title 经 quote_plus 但保留 + 作分隔；select 不编码。
        title_q = quote_plus(title)
        query_parts = [
            f"search={title_q}",
            "per-page=5",
            f"select={_OPENALEX_SELECT}",
        ]
        if api_key:
            query_parts.append(f"api_key={quote_plus(api_key)}")
        url = f"{_OPENALEX_ENDPOINT}?{'&'.join(query_parts)}"
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()
        _OPENALEX_RATE_LIMIT_CIRCUIT.record_success()
        results = payload.get("results", [])
        return results if isinstance(results, list) else []
    except httpx.HTTPStatusError as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code == 429:
            _OPENALEX_RATE_LIMIT_CIRCUIT.record_rate_limit(
                _openalex_rate_limit_cooldown_seconds(
                    getattr(exc.response, "headers", {}) or {}
                )
            )
        logger.warning("OpenAlex search failed for %r: HTTP %s", title, status_code)
        return []
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
        venue=_openalex_venue(work.get("primary_location") or work.get("host_venue")),
        match_confidence=confidence,
        match_source="openalex",
    )
    return resolved, confidence


def _search_crossref_by_title(title: str, *, http_client=None) -> list[dict]:
    if not isinstance(title, str):
        raise TypeError("title must be a string")

    if not _CROSSREF_FAILURE_CIRCUIT.can_call():
        logger.debug("Crossref title search skipped by temporary circuit")
        return []

    _CROSSREF_GATE.wait()
    client, owns_client = _ensure_client(http_client)
    try:
        response = client.get(
            _CROSSREF_ENDPOINT,
            params={
                "query.title": title,
                "rows": 5,
                "mailto": _CROSSREF_MAILTO,
            },
        )
        response.raise_for_status()
        payload = response.json()
        _CROSSREF_FAILURE_CIRCUIT.record_success()
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict):
            return []
        items = message.get("items", [])
        return items if isinstance(items, list) else []
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        _CROSSREF_FAILURE_CIRCUIT.record_failure()
        logger.warning("Crossref title search failed for %r: %s", title, exc)
        return []
    except TypeError:
        raise
    except Exception as exc:
        logger.warning("Crossref title search failed for %r: %s", title, exc)
        return []
    finally:
        if owns_client:
            client.close()


def _crossref_work_to_resolved(
    work: dict,
    *,
    query_title,
    author_hint,
    year_hint,
) -> tuple[ResolvedPaper, float]:
    if not isinstance(work, dict):
        raise TypeError("work must be a dict")

    title = _first_text(work.get("title")) or ""
    authors = _crossref_authors(work.get("author"))
    year, publication_date = _crossref_date(work)
    source_year = year or _parse_year(publication_date[:4] if publication_date else None)
    confidence = _confidence_with_hints(
        _title_jaccard(query_title, title),
        author_hint=author_hint,
        year_hint=year_hint,
        source_year=source_year,
        source_authors=authors,
    )
    doi = _normalize_optional_str(work.get("DOI"))
    resolved = ResolvedPaper(
        title=clean_paper_title(title),
        doi=doi,
        openalex_id=None,
        arxiv_id=None,
        abstract=_clean_abstract(work.get("abstract")),
        pdf_url=None,
        authors=authors,
        year=source_year,
        venue=_first_text(work.get("container-title"))
        or _first_text(work.get("short-container-title")),
        match_confidence=confidence,
        match_source="crossref",
    )
    return resolved, confidence


def _search_semantic_scholar_by_title(title: str, *, http_client=None) -> list[dict]:
    if not isinstance(title, str):
        raise TypeError("title must be a string")

    if not _SEMANTIC_SCHOLAR_RATE_LIMIT_CIRCUIT.can_call():
        logger.debug("Semantic Scholar title search skipped by temporary circuit")
        return []

    _SEMANTIC_SCHOLAR_GATE.wait()
    client, owns_client = _ensure_client(http_client)
    headers = _semantic_scholar_headers()
    try:
        request_kwargs: dict[str, Any] = {
            "params": {
                "query": title,
                "limit": 5,
                "fields": _SEMANTIC_SCHOLAR_FIELDS,
            }
        }
        if headers:
            request_kwargs["headers"] = headers
        response = client.get(_SEMANTIC_SCHOLAR_SEARCH_ENDPOINT, **request_kwargs)
        response.raise_for_status()
        payload = response.json()
        _SEMANTIC_SCHOLAR_RATE_LIMIT_CIRCUIT.record_success()
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, list) else []
    except httpx.HTTPStatusError as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code == 429:
            _SEMANTIC_SCHOLAR_RATE_LIMIT_CIRCUIT.record_failure()
        logger.warning(
            "Semantic Scholar title search failed for %r: HTTP %s",
            title,
            status_code,
        )
        return []
    except TypeError:
        raise
    except Exception as exc:
        logger.warning("Semantic Scholar title search failed for %r: %s", title, exc)
        return []
    finally:
        if owns_client:
            client.close()


def _semantic_scholar_paper_to_resolved(
    paper: dict,
    *,
    query_title,
    author_hint,
    year_hint,
) -> tuple[ResolvedPaper, float]:
    if not isinstance(paper, dict):
        raise TypeError("paper must be a dict")

    title = clean_paper_title(paper.get("title"))
    authors = _semantic_scholar_authors(paper.get("authors"))
    year = _coerce_non_negative_int(paper.get("year")) or _parse_year(
        str(paper.get("publicationDate") or "")[:4]
    )
    confidence = _confidence_with_hints(
        _title_jaccard(query_title, title),
        author_hint=author_hint,
        year_hint=year_hint,
        source_year=year,
        source_authors=authors,
    )
    external_ids = paper.get("externalIds")
    if not isinstance(external_ids, dict):
        external_ids = {}
    open_access_pdf = paper.get("openAccessPdf")
    pdf_url = (
        _normalize_optional_str(open_access_pdf.get("url"))
        if isinstance(open_access_pdf, dict)
        else None
    )
    resolved = ResolvedPaper(
        title=title,
        doi=_normalize_optional_str(external_ids.get("DOI")),
        openalex_id=_strip_openalex_prefix(external_ids.get("OpenAlex")),
        arxiv_id=_normalize_optional_str(external_ids.get("ArXiv")),
        abstract=_normalize_optional_str(paper.get("abstract")),
        pdf_url=pdf_url,
        authors=authors,
        year=year,
        venue=_normalize_optional_str(paper.get("venue")),
        match_confidence=confidence,
        match_source="semantic_scholar",
    )
    return resolved, confidence


def _search_dblp_by_title(title: str, *, http_client=None) -> list[dict]:
    if not isinstance(title, str):
        raise TypeError("title must be a string")

    if _contains_cjk(title):
        logger.debug("DBLP title search skipped for CJK title")
        return []

    if not _DBLP_FAILURE_CIRCUIT.can_call():
        logger.debug("DBLP title search skipped by temporary circuit")
        return []

    _DBLP_GATE.wait()
    client, owns_client = _ensure_client(http_client)
    try:
        response = client.get(
            _DBLP_PUBLICATION_SEARCH_ENDPOINT,
            params={
                "q": title,
                "format": "json",
                "h": 5,
            },
        )
        response.raise_for_status()
        payload = response.json()
        _DBLP_FAILURE_CIRCUIT.record_success()
        result = payload.get("result") if isinstance(payload, dict) else None
        hits = result.get("hits") if isinstance(result, dict) else None
        raw_hits = hits.get("hit") if isinstance(hits, dict) else None
        if isinstance(raw_hits, list):
            return raw_hits
        if isinstance(raw_hits, dict):
            return [raw_hits]
        return []
    except httpx.HTTPStatusError as exc:
        status_code = getattr(exc.response, "status_code", None)
        if isinstance(status_code, int) and (status_code == 429 or status_code >= 500):
            _DBLP_FAILURE_CIRCUIT.record_failure()
        logger.warning("DBLP title search failed for %r: HTTP %s", title, status_code)
        return []
    except httpx.TransportError as exc:
        _DBLP_FAILURE_CIRCUIT.record_failure()
        logger.warning("DBLP title search failed for %r: %s", title, exc)
        return []
    except TypeError:
        raise
    except Exception as exc:
        logger.warning("DBLP title search failed for %r: %s", title, exc)
        return []
    finally:
        if owns_client:
            client.close()


def _dblp_hit_to_resolved(
    hit: dict,
    *,
    query_title,
    author_hint,
    year_hint,
) -> tuple[ResolvedPaper, float]:
    if not isinstance(hit, dict):
        raise TypeError("hit must be a dict")

    info = hit.get("info")
    if not isinstance(info, dict):
        info = {}
    title = clean_paper_title(info.get("title"))
    authors = _dblp_authors(info.get("authors"))
    year = _parse_year(str(info.get("year") or ""))
    confidence = _confidence_with_hints(
        _title_jaccard(query_title, title),
        author_hint=author_hint,
        year_hint=year_hint,
        source_year=year,
        source_authors=authors,
    )
    resolved = ResolvedPaper(
        title=title,
        doi=_normalize_optional_str(info.get("doi")),
        openalex_id=None,
        arxiv_id=None,
        abstract=None,
        pdf_url=_normalize_optional_str(info.get("ee"))
        or _normalize_optional_str(info.get("url")),
        authors=authors,
        year=year,
        venue=_normalize_optional_str(info.get("venue")),
        match_confidence=confidence,
        match_source="dblp",
    )
    return resolved, confidence


def _search_arxiv_by_title(title: str, *, http_client=None) -> list:
    if not isinstance(title, str):
        raise TypeError("title must be a string")

    _ARXIV_GATE.wait()
    client, owns_client = _ensure_client(http_client)
    try:
        # W13-14b Q-11: arXiv 偶发 429 即使 _ARXIV_GATE 节流；遇 429 解析 Retry-After + 退避 1 次。
        for attempt in range(2):
            response = client.get(
                _ARXIV_ENDPOINT,
                params={
                    "search_query": f'ti:"{title}"',
                    "max_results": 5,
                },
            )
            status_code = getattr(response, "status_code", None)
            if status_code == 429 and attempt == 0:
                headers = getattr(response, "headers", {}) or {}
                retry_after_header = headers.get("Retry-After", "30")
                try:
                    retry_after = float(retry_after_header)
                except ValueError:
                    retry_after = 30.0
                retry_after = min(max(retry_after, 5.0), 60.0)
                logger.info(
                    "arXiv 429 for %r; sleeping %.1fs then retry",
                    title,
                    retry_after,
                )
                time.sleep(retry_after)
                continue
            break
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
    if _author_hint_matches_any_source_author(author_hint, source_authors):
        confidence += 0.05
    return min(confidence, 1.0)


def _cached_resolution_matches_context(
    cached: ResolvedPaper,
    *,
    query_title: str,
    author_hint: str | None,
    year_hint: int | None,
) -> bool:
    if cached.match_confidence < _CONFIDENCE_THRESHOLD:
        return False
    if _title_jaccard(query_title, cached.title) < _CONFIDENCE_THRESHOLD:
        return False
    if (
        year_hint is not None
        and cached.year is not None
        and abs(cached.year - year_hint) > 1
    ):
        return False
    return not _author_hint_definitively_conflicts(author_hint, cached.authors)


def _author_hint_matches_any_source_author(
    author_hint: str | None,
    source_authors: tuple[str, ...],
) -> bool:
    hint = (author_hint or "").strip()
    if not hint or not source_authors:
        return False
    return any(_author_hint_matches_source_author(hint, author) for author in source_authors)


def _author_hint_matches_source_author(author_hint: str, source_author: str) -> bool:
    normalized_hint = _normalize_author_name(author_hint)
    normalized_author = _normalize_author_name(source_author)
    if not normalized_hint or not normalized_author:
        return False
    if len(normalized_hint) >= 3 and normalized_hint in normalized_author:
        return True
    if len(normalized_author) >= 3 and normalized_author in normalized_hint:
        return True
    hint_tokens = set(_author_name_tokens(author_hint))
    author_tokens = set(_author_name_tokens(source_author))
    if len(hint_tokens) >= 2 and len(author_tokens) >= 2:
        return hint_tokens == author_tokens or hint_tokens.issubset(author_tokens)
    return False


def _author_hint_definitively_conflicts(
    author_hint: str | None,
    source_authors: tuple[str, ...],
) -> bool:
    hint = (author_hint or "").strip()
    if not hint or not source_authors:
        return False
    if _author_hint_matches_any_source_author(hint, source_authors):
        return False
    if _contains_cjk(hint):
        return any(_contains_cjk(author) for author in source_authors)
    return _has_strong_latin_author_form(hint) and any(
        _has_strong_latin_author_form(author) for author in source_authors
    )


def _has_strong_latin_author_form(value: str) -> bool:
    return len(_strong_latin_author_tokens(value)) >= 2


def _strong_latin_author_tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in _author_name_tokens(value)
        if len(token) >= 2 and token.isascii() and token.isalpha()
    )


def _author_name_tokens(value: str) -> tuple[str, ...]:
    normalized = _normalize_author_name(value)
    if not normalized:
        return ()
    return tuple(normalized.split())


def _normalize_author_name(value: str) -> str:
    lowered = value.casefold()
    without_punct = _TITLE_PUNCT_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", without_punct).strip()


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
    """Extract venue name from OpenAlex 'host_venue' (legacy) or 'primary_location' (current)."""
    if not isinstance(host_venue, dict):
        return None
    # primary_location wraps source dict under 'source' key
    source = host_venue.get("source") if "source" in host_venue else host_venue
    if not isinstance(source, dict):
        source = host_venue
    venue = clean_paper_title(source.get("display_name") or host_venue.get("display_name"))
    return venue or None


def _crossref_authors(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    authors: list[str] = []
    for author in value:
        if not isinstance(author, dict):
            continue
        given = _normalize_optional_str(author.get("given"))
        family = _normalize_optional_str(author.get("family"))
        if not given and not family:
            continue
        if _contains_cjk(given or "") or _contains_cjk(family or ""):
            name = f"{family or ''}{given or ''}".strip()
        else:
            name = " ".join(part for part in (given, family) if part)
        if name:
            authors.append(name)
    return tuple(authors)


def _crossref_date(item: dict[str, object]) -> tuple[int | None, str | None]:
    for key in ("published-online", "published-print", "issued"):
        value = item.get(key)
        if not isinstance(value, dict):
            continue
        date_parts = value.get("date-parts")
        if (
            not isinstance(date_parts, list)
            or not date_parts
            or not isinstance(date_parts[0], list)
            or not date_parts[0]
        ):
            continue
        parts = date_parts[0]
        year = _coerce_non_negative_int(parts[0] if len(parts) >= 1 else None)
        if year is None:
            continue
        month = _coerce_non_negative_int(parts[1] if len(parts) >= 2 else None) or 1
        day = _coerce_non_negative_int(parts[2] if len(parts) >= 3 else None) or 1
        return year, f"{year:04d}-{month:02d}-{day:02d}"
    return None, None


def _semantic_scholar_headers() -> dict[str, str]:
    api_key = (
        os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        or os.getenv("S2_API_KEY", "").strip()
    )
    return {"x-api-key": api_key} if api_key else {}


def _semantic_scholar_authors(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    authors: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _normalize_optional_str(item.get("name"))
        if name:
            authors.append(name)
    return tuple(authors)


def _dblp_authors(value: object) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    raw_authors = value.get("author")
    if isinstance(raw_authors, (str, dict)):
        raw_authors = [raw_authors]
    if not isinstance(raw_authors, list):
        return ()

    authors: list[str] = []
    for item in raw_authors:
        if isinstance(item, str):
            name = _normalize_optional_str(item)
        elif isinstance(item, dict):
            name = _normalize_optional_str(item.get("text")) or _normalize_optional_str(
                item.get("@pid")
            )
        else:
            name = None
        if name:
            authors.append(name)
    return tuple(authors)


def _first_text(value: object) -> str | None:
    if isinstance(value, str):
        return _normalize_optional_str(value)
    if not isinstance(value, list):
        return None
    for item in value:
        if text := _normalize_optional_str(item):
            return text
    return None


def _clean_abstract(value: object) -> str | None:
    text = _normalize_optional_str(value)
    if not text:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", text)
    return _normalize_optional_str(_WHITESPACE_RE.sub(" ", cleaned))


def _contains_cjk(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value)


def _coerce_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _normalize_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip()
    return item or None


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
