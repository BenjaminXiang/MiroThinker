from __future__ import annotations

import pytest

from src.data_agents.professor.hit_playwright_profile import (
    HIT_PROFILE_SOURCE,
    extract_hit_profile_fields,
)


RUN_ID = "22222222-2222-2222-2222-222222222222"


def test_hit_profile_provenance_requires_run_id() -> None:
    with pytest.raises(ValueError, match="run_id is required"):
        extract_hit_profile_fields(
            "<html><body><h1>何道敬</h1><p>研究方向：人工智能</p></body></html>",
            source_url="https://homepage.hit.edu.cn/hedaojing",
            professor_id="PROF-HIT-HEDAOJING",
            run_id="",
        )


def test_hit_profile_provenance_emits_no_fact_without_source_and_run_id() -> None:
    extraction = extract_hit_profile_fields(
        "<html><body><h1>何道敬</h1><p>研究方向：人工智能</p><p>邮箱：hedaojing@hit.edu.cn</p></body></html>",
        source_url="https://homepage.hit.edu.cn/hedaojing",
        professor_id="PROF-HIT-HEDAOJING",
        run_id=RUN_ID,
    )

    assert extraction.facts
    for fact in extraction.facts:
        assert fact.source == HIT_PROFILE_SOURCE
        assert str(fact.run_id) == RUN_ID
        assert fact.evidence_span
        assert fact.source_url == "https://homepage.hit.edu.cn/hedaojing"
