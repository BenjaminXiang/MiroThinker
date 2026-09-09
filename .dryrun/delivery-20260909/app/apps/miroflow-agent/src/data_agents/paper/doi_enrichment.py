from __future__ import annotations

from dataclasses import replace
import logging
from typing import Callable

from .crossref import enrich_paper_metadata_from_crossref
from .models import DiscoveredPaper, PaperMetadataEnrichment
from .semantic_scholar import enrich_paper_metadata_from_semantic_scholar

LookupByDoi = Callable[[str], PaperMetadataEnrichment | None]

logger = logging.getLogger(__name__)


def enrich_discovered_papers_by_doi(
    papers: list[DiscoveredPaper],
    *,
    crossref_lookup: LookupByDoi | None = None,
    semantic_scholar_lookup: LookupByDoi | None = None,
) -> list[DiscoveredPaper]:
    if not papers:
        return []

    resolve_crossref = crossref_lookup or enrich_paper_metadata_from_crossref
    resolve_semantic = (
        semantic_scholar_lookup or enrich_paper_metadata_from_semantic_scholar
    )

    enriched: list[DiscoveredPaper] = []
    for paper in papers:
        doi = (paper.doi or "").strip()
        if not doi:
            enriched.append(paper)
            continue
        current = paper
        for source_name, lookup in (
            ("crossref", resolve_crossref),
            ("semantic_scholar", resolve_semantic),
        ):
            try:
                metadata = lookup(doi)
            except Exception as error:
                logger.debug(
                    "DOI enrichment failed for %s via %s: %s",
                    doi,
                    source_name,
                    error,
                )
                continue
            if metadata is None:
                continue
            current = _merge_discovered_paper(current, metadata)
        enriched.append(current)
    return enriched


def _merge_discovered_paper(
    paper: DiscoveredPaper,
    metadata: PaperMetadataEnrichment,
) -> DiscoveredPaper:
    return replace(
        paper,
        abstract=_prefer_longer_text(paper.abstract, metadata.abstract),
        venue=paper.venue or metadata.venue,
        publication_date=paper.publication_date or metadata.publication_date,
        citation_count=_max_optional_int(paper.citation_count, metadata.citation_count),
        fields_of_study=_merge_unique_strings(
            paper.fields_of_study, metadata.fields_of_study
        ),
        tldr=paper.tldr or metadata.tldr,
        license=paper.license or metadata.license,
        funders=_merge_unique_strings(paper.funders, metadata.funders),
        oa_status=paper.oa_status or metadata.oa_status,
        reference_count=_max_optional_int(
            paper.reference_count, metadata.reference_count
        ),
        source_url=paper.source_url or metadata.source_url or "",
        enrichment_sources=_merge_unique_strings(
            paper.enrichment_sources,
            metadata.enrichment_sources,
        ),
    )


def _prefer_longer_text(current: str | None, candidate: str | None) -> str | None:
    if not candidate:
        return current
    if not current or len(candidate) > len(current):
        return candidate
    return current


def _merge_unique_strings(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in [*left, *right]:
        item = value.strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return tuple(merged)


def _max_optional_int(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    if not values:
        return None
    return max(values)
