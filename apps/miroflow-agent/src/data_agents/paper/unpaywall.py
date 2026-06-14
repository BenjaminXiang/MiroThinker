from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import requests

from .models import PaperMetadataEnrichment

_ENDPOINT = "https://api.unpaywall.org/v2/{doi}?email={email}"
_CACHE_ROOT = (
    Path(__file__).resolve().parents[5] / "logs" / "debug" / "paper_unpaywall_cache"
)
_REQUEST_TIMEOUT = (5, 20)

RequestJson = Callable[[str], dict[str, object]]


def enrich_paper_metadata_from_unpaywall(
    doi: str,
    *,
    email: str | None = None,
    request_json: RequestJson | None = None,
) -> PaperMetadataEnrichment | None:
    normalized_doi = _normalize_optional_str(doi)
    normalized_email = _normalize_optional_str(email) or _configured_email()
    if not normalized_doi or not normalized_email:
        return None

    fetch_json = request_json or _request_json
    url = _ENDPOINT.format(
        doi=quote(normalized_doi, safe=""),
        email=quote(normalized_email, safe=""),
    )
    try:
        payload = fetch_json(url)
    except (requests.RequestException, ValueError, RuntimeError):
        return None
    if not isinstance(payload, dict):
        return None

    pdf_url, source_url = _extract_location_urls(payload)
    enrichment = PaperMetadataEnrichment(
        doi=_normalize_optional_str(payload.get("doi")) or normalized_doi,
        oa_status=_extract_oa_status(payload),
        source_url=source_url,
        pdf_url=pdf_url,
        enrichment_sources=("unpaywall",),
    )
    if not _has_enrichment_content(enrichment):
        return None
    return enrichment


def _request_json(url: str) -> dict[str, object]:
    cache_path = _CACHE_ROOT / f"{quote(url, safe='')}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload

    response = requests.get(url, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected Unpaywall payload from {url}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _configured_email() -> str | None:
    for key in ("UNPAYWALL_EMAIL", "OPENALEX_EMAIL", "OPENALEX_MAILTO"):
        if value := _normalize_optional_str(os.getenv(key)):
            return value
    return None


def _extract_location_urls(payload: dict[str, object]) -> tuple[str | None, str | None]:
    for location in _candidate_locations(payload):
        pdf_url = _normalize_optional_str(location.get("url_for_pdf"))
        source_url = (
            _normalize_optional_str(location.get("url_for_landing_page"))
            or _normalize_optional_str(location.get("url"))
        )
        if pdf_url:
            return pdf_url, source_url
    for location in _candidate_locations(payload):
        if source_url := (
            _normalize_optional_str(location.get("url_for_landing_page"))
            or _normalize_optional_str(location.get("url"))
        ):
            return None, source_url
    return None, None


def _candidate_locations(payload: dict[str, object]) -> list[dict[str, object]]:
    locations: list[dict[str, object]] = []
    for key in ("best_oa_location", "first_oa_location"):
        value = payload.get(key)
        if isinstance(value, dict):
            locations.append(value)
    raw_locations = payload.get("oa_locations")
    if isinstance(raw_locations, list):
        locations.extend(item for item in raw_locations if isinstance(item, dict))
    return locations


def _extract_oa_status(payload: dict[str, object]) -> str | None:
    if value := _normalize_optional_str(payload.get("oa_status")):
        return value
    if payload.get("is_oa") is True:
        return "open"
    if payload.get("is_oa") is False:
        return "closed"
    return None


def _has_enrichment_content(enrichment: PaperMetadataEnrichment) -> bool:
    return any((enrichment.oa_status, enrichment.source_url, enrichment.pdf_url))


def _normalize_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip()
    return item or None
