from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from src.data_agents.contracts import PaperRecord, ProfessorRecord, ReleasedObject

from .feedback import apply_paper_feedback_to_professors
from .models import AuthorPaperMetrics, DiscoveredPaper, ProfessorPaperDiscoveryResult
from .release import build_paper_release
from .semantic_scholar import RequestJson, discover_professor_paper_candidates

DiscoverPapers = Callable[..., ProfessorPaperDiscoveryResult]


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
    request_json: RequestJson | None = None,
    max_workers: int = 4,
    max_papers_per_professor: int = 20,
    now: datetime | None = None,
) -> PaperPipelineResult:
    discovery_results, failed_professor_count = _discover_all_professor_papers(
        professors=professors,
        discover_papers=discover_papers or discover_professor_paper_candidates,
        request_json=request_json,
        max_workers=max_workers,
        max_papers_per_professor=max_papers_per_professor,
    )
    all_papers: list[DiscoveredPaper] = [
        paper for result in discovery_results.values() for paper in result.papers
    ]
    author_metrics = {
        professor_id: AuthorPaperMetrics(
            professor_id=professor_id,
            author_id=result.author_id,
            h_index=result.h_index,
            citation_count=result.citation_count,
        )
        for professor_id, result in discovery_results.items()
        if result.author_id
    }

    release_result = build_paper_release(papers=all_papers, now=now)
    updated_professors = apply_paper_feedback_to_professors(
        professors=professors,
        papers=all_papers,
        author_metrics=author_metrics,
        now=now,
    )

    matched_author_count = len(author_metrics)
    report = PaperPipelineReport(
        input_professor_count=len(professors),
        matched_author_count=matched_author_count,
        professor_without_author_count=len(discovery_results) - matched_author_count,
        discovered_paper_count=len(all_papers),
        released_paper_count=len(release_result.paper_records),
        duplicate_paper_count=release_result.report.duplicate_paper_count,
        feedback_professor_count=len(updated_professors),
        failed_professor_count=failed_professor_count,
    )
    return PaperPipelineResult(
        paper_records=release_result.paper_records,
        released_objects=release_result.released_objects,
        updated_professors=updated_professors,
        author_metrics=author_metrics,
        report=report,
    )


def _discover_all_professor_papers(
    *,
    professors: list[ProfessorRecord],
    discover_papers: DiscoverPapers,
    request_json: RequestJson | None,
    max_workers: int,
    max_papers_per_professor: int,
) -> tuple[dict[str, ProfessorPaperDiscoveryResult], int]:
    if not professors:
        return {}, 0

    results: dict[str, ProfessorPaperDiscoveryResult] = {}
    failed_professor_count = 0
    resolved_workers = min(max(1, max_workers), len(professors))
    with ThreadPoolExecutor(max_workers=resolved_workers) as executor:
        future_to_professor = {
            executor.submit(
                discover_papers,
                professor_id=professor.id,
                professor_name=professor.name,
                institution=professor.institution,
                request_json=request_json,
                max_papers=max_papers_per_professor,
            ): professor
            for professor in professors
        }
        for future in as_completed(future_to_professor):
            professor = future_to_professor[future]
            try:
                results[professor.id] = future.result()
            except Exception:
                failed_professor_count += 1
    return results, failed_professor_count
