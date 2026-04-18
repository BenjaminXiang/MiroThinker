from __future__ import annotations

from threading import Lock

import requests

from .doi_enrichment import enrich_discovered_papers_by_doi
from .models import ProfessorPaperDiscoveryResult
from .crossref import discover_professor_paper_candidates_from_crossref
from .openalex import discover_professor_paper_candidates_from_openalex
from .semantic_scholar import discover_professor_paper_candidates

_SEMANTIC_SCHOLAR_WAF_BLOCKED = False
_SEMANTIC_SCHOLAR_WAF_LOCK = Lock()
_OPENALEX_BUDGET_EXHAUSTED = False
_OPENALEX_BUDGET_LOCK = Lock()


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
    openalex_result = None
    if not _is_openalex_budget_exhausted():
        try:
            openalex_result = discover_professor_paper_candidates_from_openalex(
                professor_id=professor_id,
                professor_name=professor_name,
                institution=institution,
                institution_id=institution_id,
                request_json=request_json,
                max_papers=max_papers,
                author_picker=author_picker,
                target_research_directions=target_research_directions,
            )
        except requests.RequestException as error:
            _mark_openalex_budget_exhausted_if_needed(error)

    if (
        openalex_result is not None
        and openalex_result.author_id
        and openalex_result.papers
    ):
        return _apply_doi_enrichment(openalex_result)

    semantic_scholar_result = None
    if not _is_semantic_scholar_waf_blocked():
        try:
            semantic_scholar_result = discover_professor_paper_candidates(
                professor_id=professor_id,
                professor_name=professor_name,
                institution=institution,
                request_json=request_json,
                max_papers=max_papers,
            )
        except requests.RequestException as error:
            _mark_semantic_scholar_waf_blocked_if_needed(error)

    if (
        semantic_scholar_result is not None
        and semantic_scholar_result.author_id
        and semantic_scholar_result.papers
    ):
        return _apply_doi_enrichment(_mark_fallback_used(semantic_scholar_result))

    crossref_result = discover_professor_paper_candidates_from_crossref(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        request_json=request_json,
        max_papers=max_papers,
    )
    if crossref_result.author_id:
        return _apply_doi_enrichment(_mark_fallback_used(crossref_result))
    if semantic_scholar_result is not None and semantic_scholar_result.author_id:
        return _apply_doi_enrichment(_mark_fallback_used(semantic_scholar_result))
    if openalex_result is not None:
        return _apply_doi_enrichment(openalex_result)
    if semantic_scholar_result is not None:
        return _apply_doi_enrichment(_mark_fallback_used(semantic_scholar_result))
    return _apply_doi_enrichment(_mark_fallback_used(crossref_result))


def _apply_doi_enrichment(
    result: ProfessorPaperDiscoveryResult,
) -> ProfessorPaperDiscoveryResult:
    if not result.papers:
        return result
    return ProfessorPaperDiscoveryResult(
        professor_id=result.professor_id,
        professor_name=result.professor_name,
        institution=result.institution,
        author_id=result.author_id,
        h_index=result.h_index,
        citation_count=result.citation_count,
        papers=enrich_discovered_papers_by_doi(result.papers),
        paper_count=result.paper_count,
        source=result.source,
        school_matched=result.school_matched,
        fallback_used=result.fallback_used,
        name_disambiguation_conflict=result.name_disambiguation_conflict,
        candidate_count=result.candidate_count,
        query_name=result.query_name,
    )


def _mark_fallback_used(
    result: ProfessorPaperDiscoveryResult,
) -> ProfessorPaperDiscoveryResult:
    source = result.source
    if not source:
        author_id = (result.author_id or "").lower()
        if "openalex.org" in author_id:
            source = "openalex"
        elif author_id.startswith("crossref:"):
            source = "crossref"
        else:
            source = "semantic_scholar"
    return ProfessorPaperDiscoveryResult(
        professor_id=result.professor_id,
        professor_name=result.professor_name,
        institution=result.institution,
        author_id=result.author_id,
        h_index=result.h_index,
        citation_count=result.citation_count,
        papers=result.papers,
        paper_count=result.paper_count,
        source=source,
        school_matched=result.school_matched,
        fallback_used=True,
        name_disambiguation_conflict=result.name_disambiguation_conflict,
        candidate_count=result.candidate_count,
        query_name=result.query_name,
    )


def _is_semantic_scholar_waf_blocked() -> bool:
    with _SEMANTIC_SCHOLAR_WAF_LOCK:
        return _SEMANTIC_SCHOLAR_WAF_BLOCKED


def _mark_semantic_scholar_waf_blocked_if_needed(
    error: requests.RequestException,
) -> None:
    response = getattr(error, "response", None)
    if response is None:
        return
    if getattr(response, "status_code", None) != 429:
        return
    headers = getattr(response, "headers", {}) or {}
    if headers.get("x-api-key") != "blocked-by-waf":
        return
    global _SEMANTIC_SCHOLAR_WAF_BLOCKED
    with _SEMANTIC_SCHOLAR_WAF_LOCK:
        _SEMANTIC_SCHOLAR_WAF_BLOCKED = True


def _is_openalex_budget_exhausted() -> bool:
    with _OPENALEX_BUDGET_LOCK:
        return _OPENALEX_BUDGET_EXHAUSTED


def _mark_openalex_budget_exhausted_if_needed(
    error: requests.RequestException,
) -> None:
    response = getattr(error, "response", None)
    if response is None:
        return
    if getattr(response, "status_code", None) != 429:
        return
    if "Insufficient budget" not in (getattr(response, "text", "") or ""):
        return
    global _OPENALEX_BUDGET_EXHAUSTED
    with _OPENALEX_BUDGET_LOCK:
        _OPENALEX_BUDGET_EXHAUSTED = True
