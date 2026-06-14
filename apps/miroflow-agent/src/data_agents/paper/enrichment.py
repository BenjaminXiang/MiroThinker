"""Paper enrichment — Theme 7.1-compliant aggregator.

Per `docs/Paper-Requirement-Review-2026-05-10.md §3.1 P10` and OpenSpec
change `prof-paper-patent-from-page-flow`, this module is the canonical
entry point for **enrichment** of paper canonical rows that were already
**discovered** from professor pages (Tier 2 / Tier 3) via
`paper.homepage_ingest`.

External literature databases (OpenAlex / Crossref / Semantic Scholar /
arXiv) participate only as enrichment sources here. They MUST NOT be
used to discover new papers from professor-author lookups; that role is
owned exclusively by `paper.homepage_ingest`. The legacy
`paper.hybrid.discover_*_from_*` functions remain for backward
compatibility but are deprecated; see `paper/hybrid.py` module docstring.

Field-level fallback priority (per spec Requirement
"Async enrichment workflow"):

  abstract        : OpenAlex → Crossref → Semantic Scholar → arXiv (first
                    available wins)
  citation_count  : OpenAlex only (canonical source; do not call others)
  venue / year    : OpenAlex (publication_date / source.display_name)
  fields_of_study : OpenAlex preferred; Semantic Scholar / Crossref fill
  oa_status       : OpenAlex preferred; Semantic Scholar fills
  tldr            : Semantic Scholar only
  license         : Crossref only
  funders         : Crossref only
  reference_count : OpenAlex / Crossref / Semantic Scholar (max wins)
  source_url      : first non-empty across sources
  pdf_url         : first non-empty OpenAlex / Crossref / Semantic Scholar /
                    Unpaywall / arXiv PDF URL

This is consistent with `apps/miroflow-agent/src/data_agents/paper/openalex.py`
+ `crossref.py` + `semantic_scholar.py` existing per-source enrichment
helpers; the aggregator below merges their output into a single
`PaperMetadataEnrichment`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

import requests

from .arxiv import enrich_paper_metadata_from_arxiv
from .crossref import enrich_paper_metadata_from_crossref
from .models import (
    PaperAuthorMetadata,
    PaperIdentifierContradiction,
    PaperMetadataEnrichment,
)
from .openalex import enrich_paper_with_openalex
from .semantic_scholar import enrich_paper_metadata_from_semantic_scholar
from .unpaywall import enrich_paper_metadata_from_unpaywall

EnrichmentLookup = Callable[[str], PaperMetadataEnrichment | None]
_OPENALEX_WORKS_ENDPOINT = "https://api.openalex.org/works"


def enrich_paper_with_hybrid_sources(
    doi: str | None,
    *,
    arxiv_id: str | None = None,
    openalex_id: str | None = None,
    openalex_lookup: EnrichmentLookup | None = None,
    openalex_id_lookup: EnrichmentLookup | None = None,
    crossref_lookup: EnrichmentLookup | None = None,
    semantic_scholar_lookup: EnrichmentLookup | None = None,
    unpaywall_lookup: EnrichmentLookup | None = None,
    arxiv_lookup: EnrichmentLookup | None = None,
) -> PaperMetadataEnrichment | None:
    """Enrich a paper canonical row by DOI lookup across multiple sources.

    Returns merged enrichment fields, or ``None`` when no source produced
    any content.

    Sources are queried in priority order; per-field fallback fills gaps
    only when the higher-priority source returned ``None`` for that
    specific field. Citation count is intentionally ``OpenAlex-only`` —
    do not let downstream sources fill it (they may report stale or
    incompatible numbers).
    """
    lookup_doi = doi.strip() if doi and doi.strip() else None
    normalized_doi = _normalize_doi(doi)
    normalized_arxiv_id = _normalize_arxiv_id(arxiv_id)
    normalized_openalex_id = _normalize_openalex_id(openalex_id)
    if (
        normalized_doi is None
        and normalized_arxiv_id is None
        and normalized_openalex_id is None
    ):
        return None

    fetch_openalex = openalex_lookup or enrich_paper_with_openalex
    fetch_openalex_id = openalex_id_lookup or enrich_paper_with_openalex_id
    fetch_crossref = crossref_lookup or enrich_paper_metadata_from_crossref
    fetch_s2 = semantic_scholar_lookup or enrich_paper_metadata_from_semantic_scholar
    fetch_unpaywall = unpaywall_lookup or enrich_paper_metadata_from_unpaywall
    fetch_arxiv = arxiv_lookup or enrich_paper_metadata_from_arxiv

    merged: PaperMetadataEnrichment | None = None
    if normalized_openalex_id is not None:
        try:
            openalex_id_result = fetch_openalex_id(normalized_openalex_id)
        except Exception:  # noqa: BLE001 — enrichment must never raise
            openalex_id_result = None
        if openalex_id_result is not None:
            merged = _merge_enrichment(
                merged,
                _with_identifier_contradictions(
                    openalex_id_result,
                    canonical_doi=normalized_doi,
                    canonical_arxiv_id=normalized_arxiv_id,
                ),
                omit_citation=False,
            )

    if lookup_doi is not None and normalized_doi is not None:
        # Source 1: OpenAlex (primary)
        try:
            openalex_result = fetch_openalex(lookup_doi)
        except Exception:  # noqa: BLE001 — enrichment must never raise
            openalex_result = None
        if openalex_result is not None:
            merged = _merge_enrichment(
                merged,
                _with_identifier_contradictions(
                    openalex_result,
                    canonical_doi=normalized_doi,
                    canonical_arxiv_id=normalized_arxiv_id,
                ),
                omit_citation=False,
            )

        # Source 2: Crossref (fills gaps; never overrides OpenAlex)
        try:
            crossref_result = fetch_crossref(lookup_doi)
        except Exception:  # noqa: BLE001
            crossref_result = None
        if crossref_result is not None:
            merged = _merge_enrichment(
                merged,
                _with_identifier_contradictions(
                    crossref_result,
                    canonical_doi=normalized_doi,
                    canonical_arxiv_id=normalized_arxiv_id,
                ),
                omit_citation=True,
            )

        # Source 3: Semantic Scholar (fills gaps; never overrides OpenAlex)
        try:
            s2_result = fetch_s2(lookup_doi)
        except Exception:  # noqa: BLE001
            s2_result = None
        if s2_result is not None:
            merged = _merge_enrichment(
                merged,
                _with_identifier_contradictions(
                    s2_result,
                    canonical_doi=normalized_doi,
                    canonical_arxiv_id=normalized_arxiv_id,
                ),
                omit_citation=True,
            )

        # Source 4: Unpaywall (open-access PDF/OA metadata only)
        try:
            unpaywall_result = fetch_unpaywall(lookup_doi)
        except Exception:  # noqa: BLE001
            unpaywall_result = None
        if unpaywall_result is not None:
            merged = _merge_enrichment(
                merged,
                _with_identifier_contradictions(
                    unpaywall_result,
                    canonical_doi=normalized_doi,
                    canonical_arxiv_id=normalized_arxiv_id,
                ),
                omit_citation=True,
            )

    # Source 5: arXiv (fills gaps by arXiv id; never overrides stronger data)
    if normalized_arxiv_id is not None:
        try:
            arxiv_result = fetch_arxiv(normalized_arxiv_id)
        except Exception:  # noqa: BLE001
            arxiv_result = None
        if arxiv_result is not None:
            merged = _merge_enrichment(
                merged,
                _with_identifier_contradictions(
                    arxiv_result,
                    canonical_doi=normalized_doi,
                    canonical_arxiv_id=normalized_arxiv_id,
                ),
                omit_citation=True,
            )

    return merged


def enrich_paper_with_openalex_id(
    openalex_id: str,
    *,
    request_json: Callable[[str], Any] | None = None,
) -> PaperMetadataEnrichment | None:
    normalized_id = _normalize_openalex_id(openalex_id)
    if normalized_id is None:
        return None
    fetch_json = request_json or _request_openalex_json
    try:
        payload = fetch_json(f"{_OPENALEX_WORKS_ENDPOINT}/{normalized_id}")
    except Exception:  # noqa: BLE001 — enrichment must never raise
        return None
    if not isinstance(payload, dict):
        return None

    primary_location = payload.get("primary_location")
    if not isinstance(primary_location, dict):
        primary_location = {}
    source_meta = primary_location.get("source")
    if not isinstance(source_meta, dict):
        source_meta = {}

    enrichment = PaperMetadataEnrichment(
        doi=_normalize_doi(payload.get("doi")),
        abstract=_decode_openalex_abstract(payload.get("abstract_inverted_index")),
        venue=_normalize_optional_str(source_meta.get("display_name")),
        publication_date=_normalize_optional_str(payload.get("publication_date")),
        citation_count=_coerce_non_negative_int(payload.get("cited_by_count")),
        fields_of_study=_extract_openalex_concepts(payload.get("concepts")),
        oa_status=_extract_openalex_oa_status(payload),
        source_url=(
            _normalize_optional_str(primary_location.get("landing_page_url"))
            or f"https://openalex.org/{normalized_id}"
        ),
        pdf_url=_extract_openalex_pdf_url(payload),
        enrichment_sources=("openalex",),
    )
    if not _enrichment_has_content(enrichment):
        return None
    return enrichment


def _request_openalex_json(url: str) -> Any:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def _merge_enrichment(
    base: PaperMetadataEnrichment | None,
    incoming: PaperMetadataEnrichment,
    *,
    omit_citation: bool,
) -> PaperMetadataEnrichment:
    """Merge ``incoming`` into ``base``; ``incoming`` only fills gaps.

    When ``omit_citation`` is True, ``incoming.citation_count`` is
    discarded — citation_count is OpenAlex-only.
    """
    if base is None:
        if omit_citation and incoming.citation_count is not None:
            incoming = replace(incoming, citation_count=None)
        return incoming

    return PaperMetadataEnrichment(
        doi=base.doi or incoming.doi,
        arxiv_id=base.arxiv_id or incoming.arxiv_id,
        abstract=base.abstract or incoming.abstract,
        venue=base.venue or incoming.venue,
        publication_date=base.publication_date or incoming.publication_date,
        citation_count=base.citation_count
        if (omit_citation or base.citation_count is not None)
        else incoming.citation_count,
        fields_of_study=base.fields_of_study or incoming.fields_of_study,
        tldr=base.tldr or incoming.tldr,
        license=base.license or incoming.license,
        funders=base.funders or incoming.funders,
        oa_status=base.oa_status or incoming.oa_status,
        reference_count=_max_int(base.reference_count, incoming.reference_count),
        source_url=base.source_url or incoming.source_url,
        pdf_url=base.pdf_url or incoming.pdf_url,
        enrichment_sources=_merge_unique_strings(
            base.enrichment_sources, incoming.enrichment_sources
        ),
        authors=_merge_authors(base.authors, incoming.authors),
        identifier_contradictions=_merge_contradictions(
            base.identifier_contradictions,
            incoming.identifier_contradictions,
        ),
    )


def _max_int(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _merge_unique_strings(
    base: tuple[str, ...], incoming: tuple[str, ...]
) -> tuple[str, ...]:
    merged: list[str] = list(base)
    for source in incoming:
        if source not in merged:
            merged.append(source)
    return tuple(merged)


def _merge_authors(
    base: tuple[PaperAuthorMetadata, ...],
    incoming: tuple[PaperAuthorMetadata, ...],
) -> tuple[PaperAuthorMetadata, ...]:
    merged: list[PaperAuthorMetadata] = list(base)
    index_by_name = {
        _author_key(author.display_name): index
        for index, author in enumerate(merged)
        if _author_key(author.display_name)
    }
    for author in incoming:
        key = _author_key(author.display_name)
        if not key:
            continue
        existing_index = index_by_name.get(key)
        if existing_index is None:
            index_by_name[key] = len(merged)
            merged.append(author)
            continue
        existing = merged[existing_index]
        if existing.orcid:
            continue
        if author.orcid:
            merged[existing_index] = replace(existing, orcid=author.orcid)
    return tuple(merged)


def _author_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _with_identifier_contradictions(
    enrichment: PaperMetadataEnrichment,
    *,
    canonical_doi: str | None,
    canonical_arxiv_id: str | None,
) -> PaperMetadataEnrichment:
    contradictions: list[PaperIdentifierContradiction] = list(
        enrichment.identifier_contradictions
    )
    source = _source_name(enrichment)
    incoming_doi = _normalize_doi(enrichment.doi)
    if canonical_doi and incoming_doi and incoming_doi != canonical_doi:
        contradictions.append(
            PaperIdentifierContradiction(
                identifier_type="doi",
                canonical_value=canonical_doi,
                source_value=incoming_doi,
                source=source,
            )
        )
    incoming_arxiv_id = _normalize_arxiv_id(enrichment.arxiv_id)
    if (
        canonical_arxiv_id
        and incoming_arxiv_id
        and incoming_arxiv_id != canonical_arxiv_id
    ):
        contradictions.append(
            PaperIdentifierContradiction(
                identifier_type="arxiv_id",
                canonical_value=canonical_arxiv_id,
                source_value=incoming_arxiv_id,
                source=source,
            )
        )
    canonicalized = replace(
        enrichment,
        doi=canonical_doi or incoming_doi,
        arxiv_id=canonical_arxiv_id or incoming_arxiv_id,
    )
    if tuple(contradictions) == enrichment.identifier_contradictions:
        return canonicalized
    return replace(
        canonicalized,
        identifier_contradictions=_merge_contradictions((), tuple(contradictions)),
    )


def _merge_contradictions(
    base: tuple[PaperIdentifierContradiction, ...],
    incoming: tuple[PaperIdentifierContradiction, ...],
) -> tuple[PaperIdentifierContradiction, ...]:
    merged: list[PaperIdentifierContradiction] = list(base)
    seen = {
        (
            item.identifier_type,
            item.canonical_value,
            item.source_value,
            item.source,
        )
        for item in merged
    }
    for item in incoming:
        key = (
            item.identifier_type,
            item.canonical_value,
            item.source_value,
            item.source,
        )
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return tuple(merged)


def _source_name(enrichment: PaperMetadataEnrichment) -> str:
    if enrichment.enrichment_sources:
        return enrichment.enrichment_sources[0]
    return "unknown"


def _normalize_doi(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip()
    if not item:
        return None
    item = item.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    return item.lower()


def _normalize_arxiv_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip()
    if not item:
        return None
    for prefix in (
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
        "https://arxiv.org/pdf/",
        "http://arxiv.org/pdf/",
    ):
        if item.startswith(prefix):
            item = item[len(prefix) :]
            break
    return item.removesuffix(".pdf").lower()


def _normalize_openalex_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip()
    if not item:
        return None
    if item.startswith("https://openalex.org/"):
        item = item.rsplit("/", 1)[-1]
    if item.startswith("http://openalex.org/"):
        item = item.rsplit("/", 1)[-1]
    return item if item.startswith("W") else None


def _normalize_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip()
    return item or None


def _coerce_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _decode_openalex_abstract(value: object) -> str | None:
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


def _extract_openalex_concepts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    fields: list[str] = []
    for concept in value:
        if not isinstance(concept, dict):
            continue
        name = _normalize_optional_str(concept.get("display_name"))
        if name and name not in fields:
            fields.append(name)
    return tuple(fields)


def _extract_openalex_oa_status(payload: dict[str, object]) -> str | None:
    open_access = payload.get("open_access")
    if not isinstance(open_access, dict):
        return None
    return _normalize_optional_str(open_access.get("oa_status"))


def _enrichment_has_content(value: PaperMetadataEnrichment) -> bool:
    return any(
        (
            value.doi,
            value.arxiv_id,
            value.abstract,
            value.venue,
            value.publication_date,
            value.citation_count is not None,
            value.fields_of_study,
            value.tldr,
            value.license,
            value.funders,
            value.oa_status,
            value.reference_count is not None,
            value.source_url,
            value.pdf_url,
            value.authors,
        )
    )


def _extract_openalex_pdf_url(payload: dict[str, object]) -> str | None:
    primary_location = payload.get("primary_location")
    if isinstance(primary_location, dict):
        if pdf_url := _normalize_optional_str(primary_location.get("pdf_url")):
            return pdf_url

    best_oa_location = payload.get("best_oa_location")
    if isinstance(best_oa_location, dict):
        if pdf_url := _normalize_optional_str(best_oa_location.get("pdf_url")):
            return pdf_url

    locations = payload.get("locations")
    if isinstance(locations, list):
        for location in locations:
            if not isinstance(location, dict):
                continue
            if pdf_url := _normalize_optional_str(location.get("pdf_url")):
                return pdf_url
    return None
