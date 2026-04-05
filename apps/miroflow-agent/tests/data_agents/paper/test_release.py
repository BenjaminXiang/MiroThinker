from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.paper.models import DiscoveredPaper
from src.data_agents.paper.release import build_paper_release, publish_paper_release


TIMESTAMP = datetime(2026, 4, 2, tzinfo=timezone.utc)


def test_build_paper_release_deduplicates_by_doi_and_generates_released_objects():
    release_result = build_paper_release(
        papers=[
            DiscoveredPaper(
                paper_id="paper-a",
                title="Course Ideology Governance in Higher Education",
                year=2021,
                publication_date="2021-04-15",
                venue="Jiangsu Higher Education",
                doi="10.16697/J.1674-5485.2021.04.005",
                arxiv_id="2401.01234",
                abstract="This paper discusses governance paths for curriculum ideology.",
                authors=("靳玉乐", "张良"),
                professor_ids=("PROF-1",),
                citation_count=2,
                source_url="https://www.semanticscholar.org/paper/paper-a",
            ),
            DiscoveredPaper(
                paper_id="paper-a-duplicate",
                title="Course Ideology Governance in Higher Education",
                year=2021,
                publication_date="2021-04-15",
                venue="Jiangsu Higher Education",
                doi="10.16697/J.1674-5485.2021.04.005",
                arxiv_id=None,
                abstract="Duplicate copy from another source.",
                authors=("靳玉乐", "张良"),
                professor_ids=("PROF-1",),
                citation_count=1,
                source_url="https://www.semanticscholar.org/paper/paper-a-duplicate",
            ),
        ],
        now=TIMESTAMP,
    )

    assert release_result.report.input_paper_count == 2
    assert release_result.report.released_record_count == 1
    assert release_result.report.duplicate_paper_count == 1
    assert len(release_result.paper_records) == 1

    record = release_result.paper_records[0]
    assert record.id.startswith("PAPER-")
    assert record.title == "Course Ideology Governance in Higher Education"
    assert record.title_zh == "Course Ideology Governance in Higher Education"
    assert record.venue == "Jiangsu Higher Education"
    assert record.doi == "10.16697/J.1674-5485.2021.04.005"
    assert record.arxiv_id == "2401.01234"
    assert record.abstract == "This paper discusses governance paths for curriculum ideology."
    assert record.professor_ids == ["PROF-1"]
    assert record.citation_count == 2
    assert record.summary_zh
    assert record.summary_text == record.summary_zh
    assert any(item.source_type == "academic_platform" for item in record.evidence)

    released = release_result.released_objects[0]
    assert released.object_type == "paper"
    assert released.core_facts["doi"] == "10.16697/J.1674-5485.2021.04.005"
    assert released.summary_fields["summary_text"] == record.summary_text


def test_publish_paper_release_writes_jsonl_outputs(tmp_path: Path):
    release_result = build_paper_release(
        papers=[
            DiscoveredPaper(
                paper_id="paper-a",
                title="深圳高校智能体研究综述",
                year=2024,
                publication_date="2024-05-01",
                venue="深圳科技",
                doi=None,
                arxiv_id=None,
                abstract=None,
                authors=("张三",),
                professor_ids=("PROF-1",),
                citation_count=0,
                source_url="https://www.semanticscholar.org/paper/paper-a",
            )
        ],
        now=TIMESTAMP,
    )
    paper_path = tmp_path / "paper_records.jsonl"
    released_path = tmp_path / "released_objects.jsonl"

    publish_paper_release(
        release_result,
        paper_records_path=paper_path,
        released_objects_path=released_path,
    )

    paper_lines = paper_path.read_text(encoding="utf-8").strip().splitlines()
    released_lines = released_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(paper_lines) == 1
    assert len(released_lines) == 1
    paper_payload = json.loads(paper_lines[0])
    released_payload = json.loads(released_lines[0])
    assert paper_payload["id"] == released_payload["id"]
    assert released_payload["object_type"] == "paper"
