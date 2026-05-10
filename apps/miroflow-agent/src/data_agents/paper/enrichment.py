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

This is consistent with `apps/miroflow-agent/src/data_agents/paper/openalex.py`
+ `crossref.py` + `semantic_scholar.py` existing per-source enrichment
helpers; the aggregator below merges their output into a single
`PaperMetadataEnrichment`. arXiv is not yet implemented as an
enrichment source (no client exists); it is silently skipped and noted
in this change's spec drift addendum.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from .crossref import enrich_paper_metadata_from_crossref
from .models import PaperMetadataEnrichment
from .openalex import enrich_paper_with_openalex
from .semantic_scholar import enrich_paper_metadata_from_semantic_scholar

EnrichmentLookup = Callable[[str], PaperMetadataEnrichment | None]


def enrich_paper_with_hybrid_sources(
    doi: str | None,
    *,
    openalex_lookup: EnrichmentLookup | None = None,
    crossref_lookup: EnrichmentLookup | None = None,
    semantic_scholar_lookup: EnrichmentLookup | None = None,
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
    if not doi or not doi.strip():
        return None
    normalized_doi = doi.strip()

    fetch_openalex = openalex_lookup or enrich_paper_with_openalex
    fetch_crossref = crossref_lookup or enrich_paper_metadata_from_crossref
    fetch_s2 = semantic_scholar_lookup or enrich_paper_metadata_from_semantic_scholar

    # Source 1: OpenAlex (primary)
    merged: PaperMetadataEnrichment | None = None
    try:
        openalex_result = fetch_openalex(normalized_doi)
    except Exception:  # noqa: BLE001 — enrichment must never raise
        openalex_result = None
    if openalex_result is not None:
        merged = openalex_result

    # Source 2: Crossref (fills gaps; never overrides OpenAlex)
    try:
        crossref_result = fetch_crossref(normalized_doi)
    except Exception:  # noqa: BLE001
        crossref_result = None
    if crossref_result is not None:
        merged = _merge_enrichment(merged, crossref_result, omit_citation=True)

    # Source 3: Semantic Scholar (fills gaps; never overrides OpenAlex)
    try:
        s2_result = fetch_s2(normalized_doi)
    except Exception:  # noqa: BLE001
        s2_result = None
    if s2_result is not None:
        merged = _merge_enrichment(merged, s2_result, omit_citation=True)

    # Source 4: arXiv — not yet implemented (no client). Spec drift
    # addendum documents the deferral.

    return merged


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
        enrichment_sources=_merge_unique_strings(
            base.enrichment_sources, incoming.enrichment_sources
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
