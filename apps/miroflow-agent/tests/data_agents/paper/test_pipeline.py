from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data_agents.contracts import ProfessorRecord
from src.data_agents.evidence import build_evidence
from src.data_agents.paper.pipeline import run_paper_pipeline


TIMESTAMP = datetime(2026, 4, 2, tzinfo=timezone.utc)


def _professor_record(professor_id: str, name: str) -> ProfessorRecord:
    return ProfessorRecord(
        id=professor_id,
        name=name,
        institution="深圳大学",
        department="教育学部",
        title="教授",
        profile_summary=f"{name}现任深圳大学教育学部教授。",
        evidence=[
            build_evidence(
                source_type="official_site",
                source_url="https://fe.szu.edu.cn/info/1021/1191.htm",
                fetched_at=TIMESTAMP,
                confidence=0.9,
            )
        ],
        last_updated=TIMESTAMP,
    )


def test_run_paper_pipeline_is_retired_before_any_author_discovery() -> None:
    discover_called = False

    def fake_discover_papers(**_kwargs):
        nonlocal discover_called
        discover_called = True
        raise AssertionError("retired pipeline must not call author discovery")

    with pytest.warns(DeprecationWarning, match="retired"):
        with pytest.raises(RuntimeError, match="retired"):
            run_paper_pipeline(
                professors=[_professor_record("PROF-1", "靳玉乐")],
                discover_papers=fake_discover_papers,
                max_workers=1,
                max_papers_per_professor=5,
                now=TIMESTAMP,
            )

    assert discover_called is False
