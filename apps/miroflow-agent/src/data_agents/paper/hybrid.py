from __future__ import annotations

from threading import Lock

import requests

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
    request_json=None,
    max_papers: int = 20,
) -> ProfessorPaperDiscoveryResult:
    openalex_result = None
    if not _is_openalex_budget_exhausted():
        try:
            openalex_result = discover_professor_paper_candidates_from_openalex(
                professor_id=professor_id,
                professor_name=professor_name,
                institution=institution,
                request_json=request_json,
                max_papers=max_papers,
            )
        except requests.RequestException as error:
            _mark_openalex_budget_exhausted_if_needed(error)

    if (
        openalex_result is not None
        and openalex_result.author_id
        and openalex_result.papers
    ):
        return openalex_result

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
        return semantic_scholar_result

    crossref_result = discover_professor_paper_candidates_from_crossref(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        request_json=request_json,
        max_papers=max_papers,
    )
    if crossref_result.author_id:
        return crossref_result
    if semantic_scholar_result is not None and semantic_scholar_result.author_id:
        return semantic_scholar_result
    if openalex_result is not None:
        return openalex_result
    if semantic_scholar_result is not None:
        return semantic_scholar_result
    return crossref_result


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
