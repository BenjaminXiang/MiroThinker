from __future__ import annotations

import pytest

from src.data_agents.paper.hybrid import (
    discover_professor_paper_candidates_from_hybrid_sources,
)


def test_discover_professor_paper_candidates_from_hybrid_sources_is_retired_wrapper() -> None:
    with pytest.warns(DeprecationWarning, match="retired"):
        result = discover_professor_paper_candidates_from_hybrid_sources(
            professor_id="PROF-1",
            professor_name="丁南",
            institution="深圳大学",
            max_papers=5,
        )

    assert result.professor_id == "PROF-1"
    assert result.professor_name == "丁南"
    assert result.institution == "深圳大学"
    assert result.author_id is None
    assert result.h_index is None
    assert result.citation_count is None
    assert result.paper_count is None
    assert result.papers == []
    assert result.source is None
    assert result.school_matched is False
    assert result.fallback_used is False
