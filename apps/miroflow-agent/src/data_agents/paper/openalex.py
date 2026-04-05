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

_AUTHOR_SEARCH_ENDPOINT = "https://api.openalex.org/authors"
_WORKS_ENDPOINT = "https://api.openalex.org/works"
_CACHE_ROOT = Path(__file__).resolve().parents[5] / "logs" / "debug" / "paper_openalex_cache"
_MAX_RETRIES = 2
_REQUEST_TIMEOUT = (5, 20)

RequestParams = Mapping[str, str | int]
RequestJson = Callable[[str, RequestParams], dict[str, object]]


def discover_professor_paper_candidates_from_openalex(
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
            "search": professor_name,
            "per-page": 10,
            "mailto": "mirothinker-data-agent@example.com",
        },
    )
    author = _select_exact_name_author(professor_name, author_payload.get("results", []))
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

    author_id = str(author.get("id") or "").strip() or None
    h_index = _summary_h_index(author)
    citation_count = _coerce_non_negative_int(author.get("cited_by_count"))
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

    works_payload = fetch_json(
        _WORKS_ENDPOINT,
        {
            "filter": f"authorships.author.id:{author_id}",
            "sort": "cited_by_count:desc,publication_year:desc",
            "per-page": max_papers,
            "mailto": "mirothinker-data-agent@example.com",
        },
    )
    work_items = works_payload.get("results", [])
    if not isinstance(work_items, list):
        work_items = []
    papers = [
        paper
        for payload in work_items
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
    cache_path = _CACHE_ROOT / f"{_cache_key(url, params)}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload

    response = None
    for attempt in range(_MAX_RETRIES):
        response = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
        if response.status_code < 500 and response.status_code != 429:
            break
        if attempt + 1 >= _MAX_RETRIES:
            break
        time.sleep(float(min(2**attempt, 4)))
    if response is None:
        raise RuntimeError(f"OpenAlex request did not run: {url}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected OpenAlex payload from {url}")
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
        display_name = normalize_person_name(str(item.get("display_name") or ""))
        if display_name == target_name:
            exact_matches.append(item)
    if not exact_matches:
        return None
    return max(
        exact_matches,
        key=lambda item: (
            _summary_h_index(item) or 0,
            _coerce_non_negative_int(item.get("cited_by_count")) or 0,
            _coerce_non_negative_int(item.get("works_count")) or 0,
            str(item.get("id") or ""),
        ),
    )


def _summary_h_index(author: dict[str, object]) -> int | None:
    stats = author.get("summary_stats")
    if not isinstance(stats, dict):
        return None
    return _coerce_non_negative_int(stats.get("h_index"))


def _to_discovered_paper(
    payload: object,
    *,
    professor_id: str,
) -> DiscoveredPaper | None:
    if not isinstance(payload, dict):
        return None
    paper_id = str(payload.get("id") or "").strip()
    title = str(payload.get("display_name") or "").strip()
    year = _coerce_non_negative_int(payload.get("publication_year"))
    if not paper_id or not title or year is None:
        return None

    primary_location = payload.get("primary_location")
    if not isinstance(primary_location, dict):
        primary_location = {}
    source = primary_location.get("source")
    if not isinstance(source, dict):
        source = {}
    source_url = (
        str(primary_location.get("landing_page_url") or "").strip()
        or paper_id
    )
    authorships = payload.get("authorships", [])
    if not isinstance(authorships, list):
        authorships = []
    authors = tuple(
        str((authorship.get("author") or {}).get("display_name") or "").strip()
        for authorship in authorships
        if isinstance(authorship, dict)
        and isinstance(authorship.get("author"), dict)
        and str((authorship.get("author") or {}).get("display_name") or "").strip()
    )
    if not authors:
        return None

    return DiscoveredPaper(
        paper_id=paper_id,
        title=title,
        year=year,
        publication_date=_normalize_optional_str(payload.get("publication_date")),
        venue=_normalize_optional_str(source.get("display_name")),
        doi=_normalize_doi(payload.get("doi")),
        arxiv_id=None,
        abstract=_decode_abstract(payload.get("abstract_inverted_index")),
        authors=authors,
        professor_ids=(professor_id,),
        citation_count=_coerce_non_negative_int(payload.get("cited_by_count")),
        source_url=source_url,
    )


def _decode_abstract(value: object) -> str | None:
    if not isinstance(value, dict) or not value:
        return None
    positioned_tokens: list[tuple[int, str]] = []
    for token, positions in value.items():
        if not isinstance(token, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and position >= 0:
                positioned_tokens.append((position, token))
    if not positioned_tokens:
        return None
    return " ".join(token for _, token in sorted(positioned_tokens))


def _normalize_doi(value: object) -> str | None:
    item = _normalize_optional_str(value)
    if item and item.lower().startswith("https://doi.org/"):
        return item[16:]
    return item


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


def _cache_key(url: str, params: RequestParams) -> str:
    payload = json.dumps(
        {"url": url, "params": params},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
