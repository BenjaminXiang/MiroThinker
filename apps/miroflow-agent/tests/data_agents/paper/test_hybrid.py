from __future__ import annotations

import requests

from src.data_agents.paper.hybrid import (
    discover_professor_paper_candidates_from_hybrid_sources,
)
from src.data_agents.paper.models import ProfessorPaperDiscoveryResult


def test_discover_professor_paper_candidates_from_hybrid_sources_falls_back_when_openalex_is_rate_limited(
    monkeypatch,
) -> None:
    def fake_openalex_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        del kwargs
        raise requests.HTTPError("429 Too Many Requests")

    def fake_semantic_scholar_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        return ProfessorPaperDiscoveryResult(
            professor_id=kwargs["professor_id"],
            professor_name=kwargs["professor_name"],
            institution=kwargs["institution"],
            author_id="S2-1",
            h_index=12,
            citation_count=345,
            papers=[],
        )

    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates_from_openalex",
        fake_openalex_discovery,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates",
        fake_semantic_scholar_discovery,
    )

    result = discover_professor_paper_candidates_from_hybrid_sources(
        professor_id="PROF-1",
        professor_name="丁南",
        institution="深圳大学",
        max_papers=5,
    )

    assert result.author_id == "S2-1"
    assert result.h_index == 12
    assert result.citation_count == 345


def test_discover_professor_paper_candidates_from_hybrid_sources_falls_back_when_openalex_has_no_exact_name_match(
    monkeypatch,
) -> None:
    def fake_openalex_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        return ProfessorPaperDiscoveryResult(
            professor_id=kwargs["professor_id"],
            professor_name=kwargs["professor_name"],
            institution=kwargs["institution"],
            author_id=None,
            h_index=None,
            citation_count=None,
            papers=[],
        )

    def fake_semantic_scholar_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        return ProfessorPaperDiscoveryResult(
            professor_id=kwargs["professor_id"],
            professor_name=kwargs["professor_name"],
            institution=kwargs["institution"],
            author_id="S2-2",
            h_index=3,
            citation_count=42,
            papers=[],
        )

    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates_from_openalex",
        fake_openalex_discovery,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates",
        fake_semantic_scholar_discovery,
    )

    result = discover_professor_paper_candidates_from_hybrid_sources(
        professor_id="PROF-2",
        professor_name="高会军",
        institution="南方科技大学",
        max_papers=5,
    )

    assert result.author_id == "S2-2"
    assert result.h_index == 3
    assert result.citation_count == 42


def test_discover_professor_paper_candidates_from_hybrid_sources_falls_back_to_crossref_when_semantic_scholar_is_rate_limited(
    monkeypatch,
) -> None:
    def fake_openalex_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        del kwargs
        raise requests.HTTPError("429 Too Many Requests")

    def fake_semantic_scholar_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        del kwargs
        raise requests.HTTPError("429 Too Many Requests")

    def fake_crossref_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        return ProfessorPaperDiscoveryResult(
            professor_id=kwargs["professor_id"],
            professor_name=kwargs["professor_name"],
            institution=kwargs["institution"],
            author_id="crossref:PROF-3:丁南",
            h_index=None,
            citation_count=9,
            papers=[],
        )

    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates_from_openalex",
        fake_openalex_discovery,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates",
        fake_semantic_scholar_discovery,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates_from_crossref",
        fake_crossref_discovery,
    )

    result = discover_professor_paper_candidates_from_hybrid_sources(
        professor_id="PROF-3",
        professor_name="丁南",
        institution="南方科技大学",
        max_papers=5,
    )

    assert result.author_id == "crossref:PROF-3:丁南"
    assert result.citation_count == 9


def test_discover_professor_paper_candidates_from_hybrid_sources_skips_semantic_scholar_after_waf_block(
    monkeypatch,
) -> None:
    semantic_scholar_call_count = 0

    def fake_openalex_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        return ProfessorPaperDiscoveryResult(
            professor_id=kwargs["professor_id"],
            professor_name=kwargs["professor_name"],
            institution=kwargs["institution"],
            author_id=None,
            h_index=None,
            citation_count=None,
            papers=[],
        )

    class FakeResponse:
        status_code = 429
        headers = {"x-api-key": "blocked-by-waf"}

    def fake_semantic_scholar_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        del kwargs
        nonlocal semantic_scholar_call_count
        semantic_scholar_call_count += 1
        raise requests.HTTPError("429 Too Many Requests", response=FakeResponse())

    def fake_crossref_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        return ProfessorPaperDiscoveryResult(
            professor_id=kwargs["professor_id"],
            professor_name=kwargs["professor_name"],
            institution=kwargs["institution"],
            author_id=f"crossref:{kwargs['professor_id']}",
            h_index=None,
            citation_count=1,
            papers=[],
        )

    monkeypatch.setattr(
        "src.data_agents.paper.hybrid._SEMANTIC_SCHOLAR_WAF_BLOCKED",
        False,
        raising=False,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates_from_openalex",
        fake_openalex_discovery,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates",
        fake_semantic_scholar_discovery,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates_from_crossref",
        fake_crossref_discovery,
    )

    first_result = discover_professor_paper_candidates_from_hybrid_sources(
        professor_id="PROF-4",
        professor_name="丁南",
        institution="南方科技大学",
        max_papers=5,
    )
    second_result = discover_professor_paper_candidates_from_hybrid_sources(
        professor_id="PROF-5",
        professor_name="高会军",
        institution="南方科技大学",
        max_papers=5,
    )

    assert first_result.author_id == "crossref:PROF-4"
    assert second_result.author_id == "crossref:PROF-5"
    assert semantic_scholar_call_count == 1


def test_discover_professor_paper_candidates_from_hybrid_sources_skips_openalex_after_budget_exhaustion(
    monkeypatch,
) -> None:
    openalex_call_count = 0

    class FakeResponse:
        status_code = 429
        headers: dict[str, str] = {}
        text = '{"message":"Insufficient budget. This request costs $0.001 but you only have $0 remaining."}'

    def fake_openalex_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        del kwargs
        nonlocal openalex_call_count
        openalex_call_count += 1
        raise requests.HTTPError("429 Too Many Requests", response=FakeResponse())

    def fake_semantic_scholar_discovery(**kwargs) -> ProfessorPaperDiscoveryResult:
        return ProfessorPaperDiscoveryResult(
            professor_id=kwargs["professor_id"],
            professor_name=kwargs["professor_name"],
            institution=kwargs["institution"],
            author_id=f"S2:{kwargs['professor_id']}",
            h_index=1,
            citation_count=2,
            papers=[],
        )

    monkeypatch.setattr(
        "src.data_agents.paper.hybrid._OPENALEX_BUDGET_EXHAUSTED",
        False,
        raising=False,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates_from_openalex",
        fake_openalex_discovery,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.hybrid.discover_professor_paper_candidates",
        fake_semantic_scholar_discovery,
    )

    first_result = discover_professor_paper_candidates_from_hybrid_sources(
        professor_id="PROF-6",
        professor_name="丁南",
        institution="南方科技大学",
        max_papers=5,
    )
    second_result = discover_professor_paper_candidates_from_hybrid_sources(
        professor_id="PROF-7",
        professor_name="高会军",
        institution="南方科技大学",
        max_papers=5,
    )

    assert first_result.author_id == "S2:PROF-6"
    assert second_result.author_id == "S2:PROF-7"
    assert openalex_call_count == 1
