from __future__ import annotations

import requests

from src.data_agents.paper.doi_enrichment import enrich_discovered_papers_by_doi
from src.data_agents.paper.models import DiscoveredPaper, PaperMetadataEnrichment


def test_enrich_discovered_papers_by_doi_merges_crossref_and_semantic_scholar_fields() -> None:
    paper = DiscoveredPaper(
        paper_id="https://openalex.org/W1",
        title="Twisted bilayer graphene",
        year=2024,
        publication_date="2024-01-01",
        venue="Nature",
        doi="10.1234/example",
        arxiv_id=None,
        abstract="Short abstract.",
        authors=("Yabei Wu",),
        professor_ids=("PROF-1",),
        citation_count=88,
        source_url="https://example.org/paper/w1",
    )

    crossref_enrichment = PaperMetadataEnrichment(
        abstract="A much longer Crossref abstract for the same DOI.",
        license="CC-BY-4.0",
        funders=("NSFC",),
        fields_of_study=("Condensed Matter",),
        reference_count=42,
        enrichment_sources=("crossref",),
    )
    semantic_enrichment = PaperMetadataEnrichment(
        tldr="A concise summary from Semantic Scholar.",
        fields_of_study=("Physics", "Materials Science"),
        oa_status="open",
        citation_count=91,
        enrichment_sources=("semantic_scholar",),
    )

    enriched = enrich_discovered_papers_by_doi(
        [paper],
        crossref_lookup=lambda doi: crossref_enrichment if doi == "10.1234/example" else None,
        semantic_scholar_lookup=lambda doi: semantic_enrichment if doi == "10.1234/example" else None,
    )

    assert len(enriched) == 1
    result = enriched[0]
    assert result.abstract == "A much longer Crossref abstract for the same DOI."
    assert result.tldr == "A concise summary from Semantic Scholar."
    assert result.license == "CC-BY-4.0"
    assert result.funders == ("NSFC",)
    assert result.fields_of_study == (
        "Condensed Matter",
        "Physics",
        "Materials Science",
    )
    assert result.oa_status == "open"
    assert result.reference_count == 42
    assert result.citation_count == 91
    assert result.enrichment_sources == ("crossref", "semantic_scholar")


def test_enrich_discovered_papers_by_doi_skips_papers_without_doi() -> None:
    paper = DiscoveredPaper(
        paper_id="paper-without-doi",
        title="Paper without DOI",
        year=2024,
        publication_date=None,
        venue=None,
        doi=None,
        arxiv_id=None,
        abstract=None,
        authors=("Author",),
        professor_ids=("PROF-1",),
        citation_count=None,
        source_url="https://example.org/paper/no-doi",
    )

    enriched = enrich_discovered_papers_by_doi(
        [paper],
        crossref_lookup=lambda _doi: (_ for _ in ()).throw(AssertionError("should not be called")),
        semantic_scholar_lookup=lambda _doi: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    assert enriched == [paper]


def test_enrich_discovered_papers_by_doi_tolerates_single_source_lookup_failure() -> None:
    paper = DiscoveredPaper(
        paper_id="https://openalex.org/W2",
        title="Robust paper metadata",
        year=2024,
        publication_date="2024-01-01",
        venue="ACL",
        doi="10.18653/v1/2023.findings-emnlp.725",
        arxiv_id=None,
        abstract=None,
        authors=("Author",),
        professor_ids=("PROF-2",),
        citation_count=5,
        source_url="https://example.org/paper/w2",
    )

    crossref_enrichment = PaperMetadataEnrichment(
        abstract="Crossref abstract survives even when Semantic Scholar 404s.",
        enrichment_sources=("crossref",),
    )

    def broken_semantic_lookup(_doi: str) -> PaperMetadataEnrichment | None:
        response = requests.Response()
        response.status_code = 404
        raise requests.HTTPError("404 Client Error", response=response)

    enriched = enrich_discovered_papers_by_doi(
        [paper],
        crossref_lookup=lambda doi: crossref_enrichment if doi == paper.doi else None,
        semantic_scholar_lookup=broken_semantic_lookup,
    )

    assert len(enriched) == 1
    assert enriched[0].abstract == "Crossref abstract survives even when Semantic Scholar 404s."
    assert enriched[0].enrichment_sources == ("crossref",)
