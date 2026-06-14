"""Retired hybrid author-discovery compatibility wrapper.

Paper discovery is page-first only. External literature databases may
enrich an already discovered paper row, but this module no longer
queries OpenAlex, Semantic Scholar, or Crossref by professor identity to
generate candidate papers.
"""

from __future__ import annotations

import warnings

from .models import ProfessorPaperDiscoveryResult

_RETIREMENT_MESSAGE = (
    "discover_professor_paper_candidates_from_hybrid_sources is retired "
    "under paper-pipeline-cleanup. Use paper.homepage_ingest for "
    "page-first discovery and paper.enrichment.enrich_paper_with_hybrid_sources "
    "for DOI/identifier metadata enrichment."
)


def discover_professor_paper_candidates_from_hybrid_sources(
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
    institution_id: str | None = None,
    request_json=None,
    max_papers: int = 20,
    author_picker=None,
    target_research_directions: list[str] | None = None,
) -> ProfessorPaperDiscoveryResult:
    """Return an empty compatibility result for the retired discovery API."""
    _ = (
        institution_id,
        request_json,
        max_papers,
        author_picker,
        target_research_directions,
    )
    warnings.warn(_RETIREMENT_MESSAGE, DeprecationWarning, stacklevel=2)
    return ProfessorPaperDiscoveryResult(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        author_id=None,
        h_index=None,
        citation_count=None,
        paper_count=None,
        papers=[],
        source=None,
        school_matched=False,
        fallback_used=False,
        name_disambiguation_conflict=False,
        candidate_count=0,
        query_name=None,
    )
