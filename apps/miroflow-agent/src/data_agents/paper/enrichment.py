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

import json
from dataclasses import replace
from typing import Callable

from .crossref import enrich_paper_metadata_from_crossref
from .models import IdentifierConflict, PaperAuthor, PaperMetadataEnrichment
from .openalex import enrich_paper_with_openalex
from .semantic_scholar import enrich_paper_metadata_from_semantic_scholar

EnrichmentLookup = Callable[[str], PaperMetadataEnrichment | None]


def enrich_paper_with_hybrid_sources(
    doi: str | None,
    *,
    arxiv_id: str | None = None,
    openalex_lookup: EnrichmentLookup | None = None,
    crossref_lookup: EnrichmentLookup | None = None,
    semantic_scholar_lookup: EnrichmentLookup | None = None,
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
    normalized_doi = _normalize_identifier(doi)
    normalized_arxiv_id = _normalize_identifier(arxiv_id)
    if not normalized_doi and not normalized_arxiv_id:
        return None

    fetch_openalex = openalex_lookup or enrich_paper_with_openalex
    fetch_crossref = crossref_lookup or enrich_paper_metadata_from_crossref
    fetch_s2 = semantic_scholar_lookup or enrich_paper_metadata_from_semantic_scholar
    fetch_arxiv = arxiv_lookup or enrich_paper_metadata_from_arxiv

    merged: PaperMetadataEnrichment | None = None

    if normalized_doi:
        try:
            openalex_result = fetch_openalex(normalized_doi)
        except Exception:  # noqa: BLE001 — enrichment must never raise
            openalex_result = None
        if openalex_result is not None:
            merged = _merge_enrichment(
                merged,
                openalex_result,
                omit_citation=False,
                canonical_doi=normalized_doi,
                canonical_arxiv_id=normalized_arxiv_id,
            )

        try:
            crossref_result = fetch_crossref(normalized_doi)
        except Exception:  # noqa: BLE001
            crossref_result = None
        if crossref_result is not None:
            merged = _merge_enrichment(
                merged,
                crossref_result,
                omit_citation=True,
                canonical_doi=normalized_doi,
                canonical_arxiv_id=normalized_arxiv_id,
            )

        try:
            s2_result = fetch_s2(normalized_doi)
        except Exception:  # noqa: BLE001
            s2_result = None
        if s2_result is not None:
            merged = _merge_enrichment(
                merged,
                s2_result,
                omit_citation=True,
                canonical_doi=normalized_doi,
                canonical_arxiv_id=normalized_arxiv_id,
            )

    try:
        arxiv_result = fetch_arxiv(normalized_arxiv_id or normalized_doi or "")
    except Exception:  # noqa: BLE001
        arxiv_result = None
    if arxiv_result is not None:
        merged = _merge_enrichment(
            merged,
            arxiv_result,
            omit_citation=True,
            canonical_doi=normalized_doi,
            canonical_arxiv_id=normalized_arxiv_id,
        )

    return merged


def _merge_enrichment(
    base: PaperMetadataEnrichment | None,
    incoming: PaperMetadataEnrichment,
    *,
    omit_citation: bool,
    canonical_doi: str | None = None,
    canonical_arxiv_id: str | None = None,
) -> PaperMetadataEnrichment:
    """Merge ``incoming`` into ``base``; ``incoming`` only fills gaps.

    When ``omit_citation`` is True, ``incoming.citation_count`` is
    discarded — citation_count is OpenAlex-only.
    """
    if base is None:
        if omit_citation and incoming.citation_count is not None:
            incoming = replace(incoming, citation_count=None)
        conflicts = _detect_identifier_conflicts(
            None,
            incoming,
            canonical_doi=canonical_doi,
            canonical_arxiv_id=canonical_arxiv_id,
        )
        if conflicts:
            incoming = replace(
                incoming,
                identifier_conflicts=_merge_conflicts(
                    incoming.identifier_conflicts, conflicts
                ),
            )
        return incoming

    conflicts = _detect_identifier_conflicts(
        base,
        incoming,
        canonical_doi=canonical_doi,
        canonical_arxiv_id=canonical_arxiv_id,
    )

    return PaperMetadataEnrichment(
        abstract=base.abstract or incoming.abstract,
        venue=base.venue or incoming.venue,
        publication_date=base.publication_date or incoming.publication_date,
        citation_count=base.citation_count
        if (omit_citation or base.citation_count is not None)
        else incoming.citation_count,
        authors=_merge_authors(base.authors, incoming.authors),
        doi=base.doi or incoming.doi,
        arxiv_id=base.arxiv_id or incoming.arxiv_id,
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
        identifier_conflicts=_merge_conflicts(
            _merge_conflicts(base.identifier_conflicts, incoming.identifier_conflicts),
            conflicts,
        ),
    )


def enrich_paper_metadata_from_arxiv(identifier: str) -> PaperMetadataEnrichment | None:
    """Placeholder arXiv enrichment entry point.

    The aggregator wires arXiv as the fourth source and tests inject a
    deterministic lookup. Network-backed arXiv parsing belongs with the
    title/full-text clients and can replace this no-op without changing
    the merge contract.
    """
    del identifier
    return None


def write_identifier_contradiction_issues(
    conn,
    *,
    paper_id: str,
    run_id: str,
    conflicts: tuple[IdentifierConflict, ...],
    professor_id: str | None = None,
    link_id: str | None = None,
) -> None:
    for conflict in conflicts:
        evidence_snapshot = json.dumps(
            {
                "paper_id": paper_id,
                "run_id": str(run_id),
                "identifier_type": conflict.identifier_type,
                "canonical_value": conflict.canonical_value,
                "incoming_value": conflict.incoming_value,
                "incoming_source": conflict.incoming_source,
            },
            ensure_ascii=False,
        )
        conn.execute(
            """
            INSERT INTO pipeline_issue (
                professor_id,
                link_id,
                institution,
                stage,
                severity,
                description,
                evidence_snapshot,
                reported_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                professor_id,
                link_id,
                None,
                "paper_quality",
                "medium",
                (
                    "[identifier_contradiction] "
                    f"{paper_id} {conflict.identifier_type}: "
                    f"{conflict.canonical_value} != {conflict.incoming_value} "
                    f"from {conflict.incoming_source}"
                ),
                evidence_snapshot,
                "paper_enrichment",
            ),
        )


def _normalize_identifier(value: str | None) -> str | None:
    item = (value or "").strip()
    return item or None


def _detect_identifier_conflicts(
    base: PaperMetadataEnrichment | None,
    incoming: PaperMetadataEnrichment,
    *,
    canonical_doi: str | None,
    canonical_arxiv_id: str | None,
) -> tuple[IdentifierConflict, ...]:
    source = incoming.enrichment_sources[0] if incoming.enrichment_sources else "unknown"
    conflicts: list[IdentifierConflict] = []
    doi_anchor = canonical_doi or (base.doi if base else None)
    arxiv_anchor = canonical_arxiv_id or (base.arxiv_id if base else None)
    incoming_doi = _normalize_identifier(incoming.doi)
    incoming_arxiv = _normalize_identifier(incoming.arxiv_id)
    if doi_anchor and incoming_doi and doi_anchor.casefold() != incoming_doi.casefold():
        conflicts.append(
            IdentifierConflict(
                identifier_type="doi",
                canonical_value=doi_anchor,
                incoming_value=incoming_doi,
                incoming_source=source,
            )
        )
    if (
        arxiv_anchor
        and incoming_arxiv
        and arxiv_anchor.casefold() != incoming_arxiv.casefold()
    ):
        conflicts.append(
            IdentifierConflict(
                identifier_type="arxiv_id",
                canonical_value=arxiv_anchor,
                incoming_value=incoming_arxiv,
                incoming_source=source,
            )
        )
    return tuple(conflicts)


def _merge_authors(
    base: tuple[PaperAuthor, ...],
    incoming: tuple[PaperAuthor, ...],
) -> tuple[PaperAuthor, ...]:
    merged: list[PaperAuthor] = list(base)
    seen_orcids = {author.orcid.casefold() for author in merged if author.orcid}
    seen_names = {author.name.casefold() for author in merged if author.name}
    for author in incoming:
        if author.orcid and author.orcid.casefold() in seen_orcids:
            continue
        if author.name and author.name.casefold() in seen_names:
            continue
        merged.append(author)
        if author.orcid:
            seen_orcids.add(author.orcid.casefold())
        if author.name:
            seen_names.add(author.name.casefold())
    return tuple(merged)


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


def _merge_conflicts(
    base: tuple[IdentifierConflict, ...],
    incoming: tuple[IdentifierConflict, ...],
) -> tuple[IdentifierConflict, ...]:
    merged: list[IdentifierConflict] = list(base)
    for conflict in incoming:
        if conflict not in merged:
            merged.append(conflict)
    return tuple(merged)
