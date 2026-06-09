from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable

import requests

from .models import PaperAuthorMetadata, PaperMetadataEnrichment

RequestText = Callable[[str, dict[str, object]], str]

_ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
_ATOM_NAMESPACE = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
_REQUEST_TIMEOUT = (5, 20)
_WHITESPACE_RE = re.compile(r"\s+")


def enrich_paper_metadata_from_arxiv(
    arxiv_id: str,
    *,
    request_text: RequestText | None = None,
) -> PaperMetadataEnrichment | None:
    normalized_id = _normalize_optional_str(arxiv_id)
    if not normalized_id:
        return None
    fetch_text = request_text or _request_text
    try:
        raw_xml = fetch_text(_ARXIV_ENDPOINT, {"id_list": normalized_id})
        root = ET.fromstring(raw_xml)
    except (requests.RequestException, ET.ParseError, RuntimeError, ValueError):
        return None
    entry = root.find("atom:entry", _ATOM_NAMESPACE)
    if entry is None:
        return None

    enrichment = PaperMetadataEnrichment(
        arxiv_id=_arxiv_id_from_entry(entry) or normalized_id,
        abstract=_clean_text(
            entry.findtext("atom:summary", default="", namespaces=_ATOM_NAMESPACE)
        ),
        venue="arXiv",
        publication_date=_publication_date(entry),
        fields_of_study=_categories(entry),
        source_url=_clean_text(
            entry.findtext("atom:id", default="", namespaces=_ATOM_NAMESPACE)
        ),
        authors=_authors(entry),
        enrichment_sources=("arxiv",),
    )
    if not _has_enrichment_content(enrichment):
        return None
    return enrichment


def _request_text(url: str, params: dict[str, object]) -> str:
    response = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def _publication_date(entry: ET.Element) -> str | None:
    published = _clean_text(
        entry.findtext("atom:published", default="", namespaces=_ATOM_NAMESPACE)
    )
    if not published or len(published) < 10:
        return None
    return published[:10]


def _arxiv_id_from_entry(entry: ET.Element) -> str | None:
    source_url = _clean_text(
        entry.findtext("atom:id", default="", namespaces=_ATOM_NAMESPACE)
    )
    if not source_url:
        return None
    for prefix in ("http://arxiv.org/abs/", "https://arxiv.org/abs/"):
        if source_url.startswith(prefix):
            return source_url[len(prefix) :]
    return source_url


def _categories(entry: ET.Element) -> tuple[str, ...]:
    values: list[str] = []
    primary = entry.find("arxiv:primary_category", _ATOM_NAMESPACE)
    if primary is not None:
        _append_unique(values, primary.attrib.get("term"))
    for category in entry.findall("atom:category", _ATOM_NAMESPACE):
        _append_unique(values, category.attrib.get("term"))
    return tuple(values)


def _authors(entry: ET.Element) -> tuple[PaperAuthorMetadata, ...]:
    authors: list[PaperAuthorMetadata] = []
    for author in entry.findall("atom:author", _ATOM_NAMESPACE):
        name = _clean_text(
            author.findtext("atom:name", default="", namespaces=_ATOM_NAMESPACE)
        )
        if name:
            authors.append(PaperAuthorMetadata(display_name=name, source="arxiv"))
    return tuple(authors)


def _append_unique(values: list[str], value: object) -> None:
    text = _clean_text(value)
    if text and text not in values:
        values.append(text)


def _normalize_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _clean_text(value)


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    item = _WHITESPACE_RE.sub(" ", value).strip()
    return item or None


def _has_enrichment_content(enrichment: PaperMetadataEnrichment) -> bool:
    return any(
        (
            enrichment.abstract,
            enrichment.publication_date,
            enrichment.fields_of_study,
            enrichment.source_url,
            enrichment.authors,
        )
    )
