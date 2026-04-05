from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import time
from typing import Callable

import requests

from src.data_agents.normalization import normalize_person_name

from .models import DiscoveredPaper, ProfessorPaperDiscoveryResult

_AUTHOR_SEARCH_ENDPOINT = "https://api.semanticscholar.org/graph/v1/author/search"
_AUTHOR_PAPERS_ENDPOINT = "https://api.semanticscholar.org/graph/v1/author/{author_id}/papers"
_CACHE_ROOT = Path(__file__).resolve().parents[5] / "logs" / "debug" / "paper_semantic_scholar_cache"
_MAX_RETRIES = 2
_REQUEST_TIMEOUT = (5, 20)

RequestParams = Mapping[str, str | int]
RequestJson = Callable[[str, RequestParams], dict[str, object]]


def discover_professor_paper_candidates(
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
    request_json: RequestJson | None = None,
    max_papers: int = 20,
) -> ProfessorPaperDiscoveryResult:
    fetch_json = request_json or _request_json
    author_payload = fetch_json(
        _AUTHOR_SEARCH_ENDPOINT,
        {
            "query": professor_name,
            "limit": 10,
            "fields": "name,affiliations,paperCount,citationCount,hIndex,url",
        },
    )
    author = _select_exact_name_author(professor_name, author_payload.get("data", []))
    if author is None:
        return ProfessorPaperDiscoveryResult(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
            author_id=None,
            h_index=None,
            citation_count=None,
            papers=[],
        )

    author_id = str(author.get("authorId") or "").strip() or None
    h_index = _coerce_non_negative_int(author.get("hIndex"))
    citation_count = _coerce_non_negative_int(author.get("citationCount"))
    if not author_id:
        return ProfessorPaperDiscoveryResult(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
            author_id=None,
            h_index=None,
            citation_count=None,
            papers=[],
        )

    papers_payload = fetch_json(
        _AUTHOR_PAPERS_ENDPOINT.format(author_id=author_id),
        {
            "fields": (
                "title,year,publicationDate,venue,url,citationCount,"
                "externalIds,abstract,authors"
            ),
            "limit": max_papers,
        },
    )
    paper_items = papers_payload.get("data", [])
    if not isinstance(paper_items, list):
        paper_items = []
    papers = [
        paper
        for payload in paper_items
        if (
            paper := _to_discovered_paper(
                payload,
                professor_id=professor_id,
            )
        )
        is not None
    ]

    return ProfessorPaperDiscoveryResult(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        author_id=author_id,
        h_index=h_index,
        citation_count=citation_count,
        papers=papers,
    )


def _request_json(url: str, params: RequestParams) -> dict[str, object]:
    cache_path = _cache_root() / f"{_cache_key(url, params)}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload

    response = None
    for attempt in range(_MAX_RETRIES):
        response = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
        if response.status_code != 429 and response.status_code < 500:
            break
        if attempt + 1 >= _MAX_RETRIES:
            break
        time.sleep(float(min(2**attempt, 4)))
    if response is None:
        raise RuntimeError(f"Semantic Scholar request did not run: {url}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected Semantic Scholar payload from {url}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _select_exact_name_author(
    professor_name: str,
    candidates: object,
) -> dict[str, object] | None:
    if not isinstance(candidates, list):
        return None

    target_name = normalize_person_name(professor_name)
    exact_matches: list[dict[str, object]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        candidate_name = normalize_person_name(str(item.get("name") or ""))
        if candidate_name != target_name:
            continue
        exact_matches.append(item)

    if not exact_matches:
        return None

    return max(
        exact_matches,
        key=lambda item: (
            _coerce_non_negative_int(item.get("hIndex")) or 0,
            _coerce_non_negative_int(item.get("citationCount")) or 0,
            _coerce_non_negative_int(item.get("paperCount")) or 0,
            str(item.get("authorId") or ""),
        ),
    )


def _to_discovered_paper(
    payload: object,
    *,
    professor_id: str,
) -> DiscoveredPaper | None:
    if not isinstance(payload, dict):
        return None
    paper_id = str(payload.get("paperId") or "").strip()
    title = str(payload.get("title") or "").strip()
    year = _coerce_non_negative_int(payload.get("year"))
    source_url = str(payload.get("url") or "").strip()
    if not paper_id or not title or year is None or not source_url:
        return None

    external_ids = payload.get("externalIds")
    if not isinstance(external_ids, dict):
        external_ids = {}
    raw_authors = payload.get("authors", [])
    if not isinstance(raw_authors, list):
        raw_authors = []
    authors = tuple(
        str(author.get("name") or "").strip()
        for author in raw_authors
        if isinstance(author, dict) and str(author.get("name") or "").strip()
    )
    if not authors:
        return None

    return DiscoveredPaper(
        paper_id=paper_id,
        title=title,
        year=year,
        publication_date=_normalize_optional_str(payload.get("publicationDate")),
        venue=_normalize_optional_str(payload.get("venue")),
        doi=_normalize_optional_str(external_ids.get("DOI")),
        arxiv_id=_normalize_optional_str(external_ids.get("ArXiv")),
        abstract=_normalize_optional_str(payload.get("abstract")),
        authors=authors,
        professor_ids=(professor_id,),
        citation_count=_coerce_non_negative_int(payload.get("citationCount")),
        source_url=source_url,
    )


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


def _cache_root() -> Path:
    return _CACHE_ROOT


def _cache_key(url: str, params: RequestParams) -> str:
    payload = json.dumps(
        {"url": url, "params": params},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
