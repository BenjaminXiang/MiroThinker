from __future__ import annotations

from datetime import datetime, timezone

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
        evaluation_summary=f"{name}当前资料完整度为structured。",
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


def test_run_paper_pipeline_collects_papers_and_updates_professors():
    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/author/search"):
            query = str(params["query"])
            if query == "靳玉乐":
                return {
                    "data": [
                        {
                            "authorId": "136691277",
                            "name": "靳玉乐",
                            "paperCount": 18,
                            "citationCount": 7,
                            "hIndex": 3,
                        }
                    ]
                }
            return {"data": []}
        if url.endswith("/author/136691277/papers"):
            return {
                "data": [
                    {
                        "paperId": "paper-a",
                        "title": "要认真对待高校课程思政的“泛意识形态化”倾向",
                        "venue": "江苏高教",
                        "year": 2021,
                        "publicationDate": "2021-04-15",
                        "citationCount": 2,
                        "url": "https://www.semanticscholar.org/paper/paper-a",
                        "externalIds": {
                            "DOI": "10.16697/J.1674-5485.2021.04.005",
                        },
                        "abstract": "讨论高校课程思政泛意识形态化倾向的表现与治理路径。",
                        "authors": [
                            {"authorId": "136691277", "name": "靳玉乐"},
                            {"authorId": "2054877067", "name": "张良"},
                        ],
                    }
                ]
            }
        raise AssertionError(f"unexpected URL: {url}")

    result = run_paper_pipeline(
        professors=[
            _professor_record("PROF-1", "靳玉乐"),
            _professor_record("PROF-2", "不存在老师"),
        ],
        request_json=fake_request_json,
        max_workers=2,
        max_papers_per_professor=5,
        now=TIMESTAMP,
    )

    assert result.report.input_professor_count == 2
    assert result.report.matched_author_count == 1
    assert result.report.professor_without_author_count == 1
    assert result.report.discovered_paper_count == 1
    assert result.report.released_paper_count == 1
    assert result.report.feedback_professor_count == 2
    assert len(result.paper_records) == 1
    assert len(result.updated_professors) == 2
    assert result.updated_professors[0].h_index == 3


def test_run_paper_pipeline_keeps_batch_running_when_one_professor_lookup_fails():
    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/author/search") and params["query"] == "异常老师":
            raise RuntimeError("Semantic Scholar temporary failure")
        return {"data": []}

    result = run_paper_pipeline(
        professors=[
            _professor_record("PROF-1", "异常老师"),
            _professor_record("PROF-2", "不存在老师"),
        ],
        request_json=fake_request_json,
        max_workers=2,
        max_papers_per_professor=5,
        now=TIMESTAMP,
    )

    assert result.report.failed_professor_count == 1
    assert result.report.professor_without_author_count == 1
    assert result.report.feedback_professor_count == 2
    assert len(result.paper_records) == 0
    assert len(result.updated_professors) == 2


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
