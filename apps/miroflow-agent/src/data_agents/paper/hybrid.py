"""Retired hybrid paper-discovery compatibility surface.

Paper discovery is page-first: production code must extract paper
candidates from professor pages and use external literature databases
only to enrich already discovered rows. The former hybrid author-search
aggregator is kept as an import-compatible wrapper so stale callers fail
with a clear migration message instead of silently querying OpenAlex,
Semantic Scholar, or Crossref by professor identity.
"""

from __future__ import annotations

import warnings

from .models import ProfessorPaperDiscoveryResult

_RETIRED_MESSAGE = (
    "paper.hybrid.discover_professor_paper_candidates_from_hybrid_sources "
    "is retired by OpenSpec change paper-pipeline-cleanup. Use "
    "paper.homepage_ingest for page-first discovery, then "
    "paper.enrichment.enrich_paper_with_hybrid_sources for DOI/identifier "
    "metadata enrichment."
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
    del (
        professor_id,
        professor_name,
        institution,
        institution_id,
        request_json,
        max_papers,
        author_picker,
        target_research_directions,
    )
    warnings.warn(_RETIRED_MESSAGE, DeprecationWarning, stacklevel=2)
    raise RuntimeError(_RETIRED_MESSAGE)
