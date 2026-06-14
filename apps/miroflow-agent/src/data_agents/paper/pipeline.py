"""Retired per-professor author-discovery paper pipeline.

``run_paper_pipeline`` used Semantic Scholar/OpenAlex/Crossref
author-discovery to generate paper candidates. Under the page-first
contract, paper discovery is restricted to professor-page extraction via
``paper.homepage_ingest``; external databases are enrichment-only.

Migration target: callers should invoke ``paper.homepage_ingest`` for
discovery + ``paper.enrichment.enrich_paper_with_hybrid_sources`` for
enrichment of each discovered paper.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from src.data_agents.contracts import PaperRecord, ProfessorRecord, ReleasedObject

from .models import AuthorPaperMetrics

DiscoverPapers = Callable[..., object]

_RETIREMENT_MESSAGE = (
    "paper.pipeline.run_paper_pipeline is retired under paper-pipeline-cleanup. "
    "Use paper.homepage_ingest for page-first discovery and "
    "paper.enrichment.enrich_paper_with_hybrid_sources for DOI/identifier "
    "metadata enrichment."
)


class PaperPipelineRetiredError(RuntimeError):
    """Raised when the retired author-discovery pipeline is invoked."""


@dataclass(frozen=True, slots=True)
class PaperPipelineReport:
    input_professor_count: int
    matched_author_count: int
    professor_without_author_count: int
    discovered_paper_count: int
    released_paper_count: int
    duplicate_paper_count: int
    feedback_professor_count: int
    failed_professor_count: int


@dataclass(frozen=True, slots=True)
class PaperPipelineResult:
    paper_records: list[PaperRecord]
    released_objects: list[ReleasedObject]
    updated_professors: list[ProfessorRecord]
    author_metrics: dict[str, AuthorPaperMetrics]
    report: PaperPipelineReport


def run_paper_pipeline(
    *,
    professors: list[ProfessorRecord],
    discover_papers: DiscoverPapers | None = None,
    request_json: Any | None = None,
    max_workers: int = 4,
    max_papers_per_professor: int = 20,
    now: datetime | None = None,
) -> PaperPipelineResult:
    """Retired. Raise before any author-discovery or release work runs."""
    _ = (
        professors,
        discover_papers,
        request_json,
        max_workers,
        max_papers_per_professor,
        now,
    )
    warnings.warn(_RETIREMENT_MESSAGE, DeprecationWarning, stacklevel=2)
    raise PaperPipelineRetiredError(_RETIREMENT_MESSAGE)
