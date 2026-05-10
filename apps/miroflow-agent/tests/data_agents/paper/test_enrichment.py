"""Tests for paper.enrichment — Theme 7.1-compliant aggregator.

Per OpenSpec change `prof-paper-patent-from-page-flow`
`paper-patent-from-prof-page` capability "Async enrichment workflow"
Requirement.
"""

from __future__ import annotations

import pytest

from src.data_agents.paper.enrichment import enrich_paper_with_hybrid_sources
from src.data_agents.paper.models import PaperMetadataEnrichment


def _make(**overrides) -> PaperMetadataEnrichment:
    """Helper to build PaperMetadataEnrichment fixtures."""
    base = dict(
        abstract=None,
        venue=None,
        publication_date=None,
        citation_count=None,
        fields_of_study=(),
        tldr=None,
        license=None,
        funders=(),
        oa_status=None,
        reference_count=None,
        source_url=None,
        enrichment_sources=(),
    )
    base.update(overrides)
    return PaperMetadataEnrichment(**base)


def test_returns_none_when_doi_blank():
    assert enrich_paper_with_hybrid_sources(None) is None
    assert enrich_paper_with_hybrid_sources("") is None
    assert enrich_paper_with_hybrid_sources("   ") is None


def test_openalex_only_returns_its_payload():
    openalex = _make(
        abstract="Abstract from OpenAlex.",
        venue="VenueA",
        citation_count=42,
        publication_date="2026-01-15",
        oa_status="green",
        enrichment_sources=("openalex",),
    )
    result = enrich_paper_with_hybrid_sources(
        "10.1234/abc",
        openalex_lookup=lambda d: openalex,
        crossref_lookup=lambda d: None,
        semantic_scholar_lookup=lambda d: None,
    )
    assert result is not None
    assert result.abstract == "Abstract from OpenAlex."
    assert result.venue == "VenueA"
    assert result.citation_count == 42
    assert result.oa_status == "green"
    assert result.enrichment_sources == ("openalex",)


def test_crossref_fills_when_openalex_missing_field():
    """Per spec: abstract falls back OpenAlex → Crossref → S2 → arXiv."""
    openalex = _make(
        abstract=None,  # OpenAlex has no abstract for this paper
        venue="VenueA",
        citation_count=10,
        enrichment_sources=("openalex",),
    )
    crossref = _make(
        abstract="Abstract from Crossref.",
        venue="VenueCrossref",  # ignored — OpenAlex venue wins
        license="https://creativecommons.org/licenses/by/4.0",
        funders=("NSFC",),
        enrichment_sources=("crossref",),
    )
    result = enrich_paper_with_hybrid_sources(
        "10.1234/abc",
        openalex_lookup=lambda d: openalex,
        crossref_lookup=lambda d: crossref,
        semantic_scholar_lookup=lambda d: None,
    )
    assert result is not None
    # OpenAlex provided venue → wins (Crossref's not used)
    assert result.venue == "VenueA"
    # OpenAlex had no abstract → Crossref fills
    assert result.abstract == "Abstract from Crossref."
    # OpenAlex citation_count preserved (Crossref's omitted)
    assert result.citation_count == 10
    # Crossref-only fields fill
    assert result.license == "https://creativecommons.org/licenses/by/4.0"
    assert result.funders == ("NSFC",)
    assert result.enrichment_sources == ("openalex", "crossref")


def test_citation_count_is_openalex_only_even_when_others_have_it():
    """Per spec: citation_count is OpenAlex-only canonical; downstream
    sources are not allowed to fill it."""
    openalex = _make(citation_count=None, enrichment_sources=("openalex",))
    crossref = _make(
        citation_count=999,  # Crossref claims 999 — must be ignored
        enrichment_sources=("crossref",),
    )
    s2 = _make(
        citation_count=888,  # S2 claims 888 — must be ignored
        enrichment_sources=("semantic_scholar",),
    )
    result = enrich_paper_with_hybrid_sources(
        "10.1234/abc",
        openalex_lookup=lambda d: openalex,
        crossref_lookup=lambda d: crossref,
        semantic_scholar_lookup=lambda d: s2,
    )
    assert result is not None
    # OpenAlex returned None → no fallback to Crossref/S2 for citation
    assert result.citation_count is None


def test_s2_fills_tldr_when_others_lack_it():
    s2 = _make(
        tldr="Short TLDR summary.",
        enrichment_sources=("semantic_scholar",),
    )
    result = enrich_paper_with_hybrid_sources(
        "10.1234/abc",
        openalex_lookup=lambda d: None,
        crossref_lookup=lambda d: None,
        semantic_scholar_lookup=lambda d: s2,
    )
    assert result is not None
    assert result.tldr == "Short TLDR summary."
    assert result.enrichment_sources == ("semantic_scholar",)


def test_returns_none_when_all_sources_empty():
    result = enrich_paper_with_hybrid_sources(
        "10.1234/abc",
        openalex_lookup=lambda d: None,
        crossref_lookup=lambda d: None,
        semantic_scholar_lookup=lambda d: None,
    )
    assert result is None


def test_lookup_exception_does_not_propagate():
    """Enrichment must never raise — failures degrade to None."""
    def boom(_doi):
        raise RuntimeError("network fail")

    s2 = _make(abstract="S2 saved the day.", enrichment_sources=("semantic_scholar",))
    result = enrich_paper_with_hybrid_sources(
        "10.1234/abc",
        openalex_lookup=boom,  # raises
        crossref_lookup=boom,  # raises
        semantic_scholar_lookup=lambda d: s2,
    )
    assert result is not None
    assert result.abstract == "S2 saved the day."
    assert result.enrichment_sources == ("semantic_scholar",)


def test_reference_count_takes_max_across_sources():
    openalex = _make(reference_count=10, enrichment_sources=("openalex",))
    crossref = _make(reference_count=15, enrichment_sources=("crossref",))
    s2 = _make(reference_count=12, enrichment_sources=("semantic_scholar",))
    result = enrich_paper_with_hybrid_sources(
        "10.1234/abc",
        openalex_lookup=lambda d: openalex,
        crossref_lookup=lambda d: crossref,
        semantic_scholar_lookup=lambda d: s2,
    )
    assert result is not None
    assert result.reference_count == 15
    assert result.enrichment_sources == ("openalex", "crossref", "semantic_scholar")


def test_sources_order_preserved_in_enrichment_sources():
    openalex = _make(abstract="A", enrichment_sources=("openalex",))
    crossref = _make(abstract=None, enrichment_sources=("crossref",))
    s2 = _make(abstract=None, enrichment_sources=("semantic_scholar",))
    result = enrich_paper_with_hybrid_sources(
        "10.1234/abc",
        openalex_lookup=lambda d: openalex,
        crossref_lookup=lambda d: crossref,
        semantic_scholar_lookup=lambda d: s2,
    )
    assert result is not None
    assert result.enrichment_sources == ("openalex", "crossref", "semantic_scholar")


def test_doi_with_https_prefix_is_passed_through():
    """The aggregator does not normalize DOI; per-source helpers handle that."""
    captured: list[str] = []

    def fake_openalex(doi: str) -> PaperMetadataEnrichment | None:
        captured.append(doi)
        return _make(abstract="ok", enrichment_sources=("openalex",))

    enrich_paper_with_hybrid_sources(
        "https://doi.org/10.1234/abc",
        openalex_lookup=fake_openalex,
        crossref_lookup=lambda d: None,
        semantic_scholar_lookup=lambda d: None,
    )
    assert captured == ["https://doi.org/10.1234/abc"]
