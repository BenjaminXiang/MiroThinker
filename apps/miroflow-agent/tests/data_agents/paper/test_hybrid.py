from __future__ import annotations

import pytest

from src.data_agents.paper import hybrid


def test_hybrid_discovery_wrapper_is_retired_and_points_to_homepage_ingest() -> None:
    with pytest.warns(DeprecationWarning, match="retired"):
        with pytest.raises(RuntimeError, match="paper.homepage_ingest"):
            hybrid.discover_professor_paper_candidates_from_hybrid_sources(
                professor_id="PROF-1",
                professor_name="丁南",
                institution="深圳大学",
                max_papers=5,
            )


def test_hybrid_discovery_wrapper_does_not_call_external_backends(monkeypatch) -> None:
    calls: list[str] = []

    def record_call(**_kwargs):
        calls.append("called")

    monkeypatch.setattr(
        hybrid,
        "discover_professor_paper_candidates_from_openalex",
        record_call,
        raising=False,
    )
    monkeypatch.setattr(
        hybrid,
        "discover_professor_paper_candidates",
        record_call,
        raising=False,
    )
    monkeypatch.setattr(
        hybrid,
        "discover_professor_paper_candidates_from_crossref",
        record_call,
        raising=False,
    )

    with pytest.warns(DeprecationWarning):
        with pytest.raises(RuntimeError):
            hybrid.discover_professor_paper_candidates_from_hybrid_sources(
                professor_id="PROF-1",
                professor_name="丁南",
                institution="深圳大学",
                max_papers=5,
            )

    assert calls == []
