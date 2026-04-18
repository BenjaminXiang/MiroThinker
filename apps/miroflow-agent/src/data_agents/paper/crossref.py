from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Callable

import requests

from src.data_agents.normalization import normalize_person_name

from .models import (
    DiscoveredPaper,
    PaperMetadataEnrichment,
    ProfessorPaperDiscoveryResult,
)

_WORKS_ENDPOINT = "https://api.crossref.org/works"
_CACHE_ROOT = (
    Path(__file__).resolve().parents[5] / "logs" / "debug" / "paper_crossref_cache"
)
_MAX_RETRIES = 2
_REQUEST_TIMEOUT = (5, 20)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TRAILING_TITLE_RE = re.compile(r"(院士|教授|副教授|助理教授|讲师|老师)$")

RequestParams = Mapping[str, str | int]
RequestJson = Callable[[str, RequestParams], dict[str, object]]


def discover_professor_paper_candidates_from_crossref(
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
    request_json: RequestJson | None = None,
    max_papers: int = 20,
) -> ProfessorPaperDiscoveryResult:
    fetch_json = request_json or _request_json
    query_name = _normalize_query_name(professor_name)
    payload = fetch_json(
        _WORKS_ENDPOINT,
        {
            "query.author": query_name,
            "rows": max_papers,
            "mailto": "mirothinker-data-agent@example.com",
        },
    )
    message = payload.get("message")
    if not isinstance(message, dict):
        message = {}

    items = message.get("items", [])
    if not isinstance(items, list):
        items = []
    papers = [
        paper
        for item in items
        if (
            paper := _to_discovered_paper(
                item,
                professor_id=professor_id,
                professor_name=query_name,
            )
        )
        is not None
    ]
    return ProfessorPaperDiscoveryResult(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        author_id=(
            f"crossref:{professor_id}:{normalize_person_name(query_name)}"
            if papers
            else None
        ),
        h_index=None,
        citation_count=max(
            (paper.citation_count or 0 for paper in papers), default=None
        ),
        papers=papers,
        paper_count=len(papers) if papers else None,
        source="crossref",
        school_matched=False,
        fallback_used=False,
        name_disambiguation_conflict=False,
        candidate_count=1 if papers else 0,
        query_name=query_name,
    )


def enrich_paper_metadata_from_crossref(
    doi: str,
    *,
    request_json: RequestJson | None = None,
) -> PaperMetadataEnrichment | None:
    normalized_doi = _normalize_optional_str(doi)
    if not normalized_doi:
        return None
    fetch_json = request_json or _request_json
    payload = fetch_json(
        f"{_WORKS_ENDPOINT}/{normalized_doi}",
        {"mailto": "mirothinker-data-agent@example.com"},
    )
    message = payload.get("message")
    if not isinstance(message, dict):
        return None

    year, publication_date = _extract_date(message)
    enrichment = PaperMetadataEnrichment(
        abstract=_clean_abstract(message.get("abstract")),
        venue=_first_text(message.get("container-title"))
        or _first_text(message.get("short-container-title")),
        publication_date=publication_date if year is not None else None,
        fields_of_study=_extract_subjects(message.get("subject")),
        license=_extract_license_url(message.get("license")),
        funders=_extract_funders(message.get("funder")),
        reference_count=_coerce_non_negative_int(message.get("reference-count")),
        source_url=(
            _normalize_optional_str(message.get("URL"))
            or f"https://doi.org/{normalized_doi}"
        ),
        enrichment_sources=("crossref",),
    )
    if not _has_enrichment_content(enrichment):
        return None
    return enrichment


def _request_json(url: str, params: RequestParams) -> dict[str, object]:
    cache_path = _CACHE_ROOT / f"{_cache_key(url, params)}.json"
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
        raise RuntimeError(f"Crossref request did not run: {url}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected Crossref payload from {url}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _to_discovered_paper(
    item: object,
    *,
    professor_id: str,
    professor_name: str,
) -> DiscoveredPaper | None:
    if not isinstance(item, dict):
        return None

    authors = _extract_authors(item.get("author"))
    if not authors:
        return None
    target_name = normalize_person_name(professor_name).lower()
    if target_name not in {
        normalize_person_name(author_name).lower() for author_name in authors
    }:
        return None

    title = _first_text(item.get("title"))
    year, publication_date = _extract_date(item)
    doi = _normalize_optional_str(item.get("DOI"))
    source_url = _normalize_optional_str(item.get("URL")) or (
        f"https://doi.org/{doi}" if doi else None
    )
    if not title or year is None or not doi or not source_url:
        return None

    return DiscoveredPaper(
        paper_id=doi,
        title=title,
        year=year,
        publication_date=publication_date,
        venue=_first_text(item.get("container-title"))
        or _first_text(item.get("short-container-title")),
        doi=doi,
        arxiv_id=None,
        abstract=_clean_abstract(item.get("abstract")),
        authors=tuple(authors),
        professor_ids=(professor_id,),
        citation_count=_coerce_non_negative_int(item.get("is-referenced-by-count")),
        source_url=source_url,
    )


def _extract_authors(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for author in value:
        if not isinstance(author, dict):
            continue
        given = _normalize_optional_str(author.get("given"))
        family = _normalize_optional_str(author.get("family"))
        if not given and not family:
            continue
        if _contains_cjk(given or "") or _contains_cjk(family or ""):
            authors.append(f"{family or ''}{given or ''}".strip())
        else:
            authors.append(" ".join(part for part in (given, family) if part))
    return authors


def _extract_date(item: dict[str, object]) -> tuple[int | None, str | None]:
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
    return _normalize_optional_str(_HTML_TAG_RE.sub(" ", text))


def _extract_subjects(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        subject for item in value if (subject := _normalize_optional_str(item))
    )


def _extract_license_url(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        if url := _normalize_optional_str(item.get("URL")):
            return url
    return None


def _extract_funders(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    funders: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        funder = _normalize_optional_str(item.get("name"))
        if not funder:
            continue
        key = funder.casefold()
        if key in seen:
            continue
        seen.add(key)
        funders.append(funder)
    return tuple(funders)


def _normalize_query_name(name: str) -> str:
    normalized = normalize_person_name(name).strip().strip("\u200b\ufeff")
    normalized = _TRAILING_TITLE_RE.sub("", normalized)
    return normalized or name.strip()


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


def _has_enrichment_content(enrichment: PaperMetadataEnrichment) -> bool:
    return any(
        (
            enrichment.abstract,
            enrichment.venue,
            enrichment.publication_date,
            enrichment.fields_of_study,
            enrichment.license,
            enrichment.funders,
            enrichment.reference_count is not None,
            enrichment.source_url,
        )
    )


def _cache_key(url: str, params: RequestParams) -> str:
    payload = json.dumps(
        {"url": url, "params": params},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
