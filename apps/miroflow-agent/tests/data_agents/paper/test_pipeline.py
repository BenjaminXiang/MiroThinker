from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data_agents.contracts import ProfessorRecord
from src.data_agents.evidence import build_evidence
from src.data_agents.paper.models import ProfessorPaperDiscoveryResult
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


def test_run_paper_pipeline_without_explicit_discovery_backend_is_retired():
    with pytest.raises(RuntimeError, match="paper.homepage_ingest"):
        run_paper_pipeline(
            professors=[_professor_record("PROF-1", "靳玉乐")],
            max_workers=1,
            max_papers_per_professor=5,
            now=TIMESTAMP,
        )


def test_run_paper_pipeline_supports_custom_discovery_function():
    def fake_discover_papers(**kwargs):
        return ProfessorPaperDiscoveryResult(
            professor_id=kwargs["professor_id"],
            professor_name=kwargs["professor_name"],
            institution=kwargs["institution"],
            author_id=None,
            h_index=None,
            citation_count=None,
            papers=[],
        )

    result = run_paper_pipeline(
        professors=[_professor_record("PROF-1", "靳玉乐")],
        discover_papers=fake_discover_papers,
        max_workers=1,
        max_papers_per_professor=5,
        now=TIMESTAMP,
    )

    assert result.report.input_professor_count == 1
    assert result.report.professor_without_author_count == 1
