from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.paper.models import DiscoveredPaper
from src.data_agents.paper.release import build_paper_release, publish_paper_release
from src.data_agents.professor.cross_domain import PaperStagingRecord
from src.data_agents.professor.paper_publication import build_paper_domain_publication


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
                fields_of_study=("Education",),
                tldr="A concise educational governance summary.",
                license="CC-BY-4.0",
                funders=("NSFC",),
                oa_status="open",
                reference_count=25,
                enrichment_sources=("crossref", "semantic_scholar"),
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
                fields_of_study=("Political Science",),
                funders=("National Social Science Fund",),
                enrichment_sources=("crossref",),
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
    assert record.fields_of_study == ["Education", "Political Science"]
    assert record.tldr == "A concise educational governance summary."
    assert record.license == "CC-BY-4.0"
    assert record.funders == ["NSFC", "National Social Science Fund"]
    assert record.oa_status == "open"
    assert record.reference_count == 25
    assert record.enrichment_sources == ["crossref", "semantic_scholar"]
    assert record.summary_zh
    assert record.summary_text == record.summary_zh
    assert any(item.source_type == "academic_platform" for item in record.evidence)

    released = release_result.released_objects[0]
    assert released.object_type == "paper"
    assert released.core_facts["doi"] == "10.16697/J.1674-5485.2021.04.005"
    assert released.core_facts["license"] == "CC-BY-4.0"
    assert released.core_facts["funders"] == ["NSFC", "National Social Science Fund"]
    assert released.summary_fields["summary_text"] == record.summary_text


def test_build_paper_release_cleans_markup_polluted_titles():
    release_result = build_paper_release(
        papers=[
            DiscoveredPaper(
                paper_id="paper-mathml",
                title=(
                    "Manipulation of valley pseudospin in "
                    "<mml:math xmlns:mml=\"http://www.w3.org/1998/Math/MathML\">"
                    "<mml:msub><mml:mi>WSe</mml:mi><mml:mn>2</mml:mn></mml:msub>"
                    "<mml:mo>/</mml:mo>"
                    "<mml:msub><mml:mi>CrI</mml:mi><mml:mn>3</mml:mn></mml:msub>"
                    "</mml:math> heterostructures by the magnetic proximity effect"
                ),
                year=2024,
                publication_date="2024-01-01",
                venue="Nature",
                doi=None,
                arxiv_id=None,
                abstract="A heterostructure study.",
                authors=("吴亚北",),
                professor_ids=("PROF-1",),
                citation_count=8,
                source_url="https://openalex.org/W1",
            )
        ],
        now=TIMESTAMP,
    )

    record = release_result.paper_records[0]
    assert record.title == "Manipulation of valley pseudospin in WSe2/CrI3 heterostructures by the magnetic proximity effect"
    assert record.title_zh == record.title


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


def test_build_paper_domain_publication_builds_verified_link_objects():
    result = build_paper_domain_publication(
        staging_records=[
            PaperStagingRecord(
                title="JIAJIA: A software DSM system based on a new cache coherence protocol",
                authors=["唐志敏", "张三"],
                year=1993,
                venue="International Conference on Parallel Processing",
                abstract="A DSM protocol paper.",
                doi="10.1000/jiajia.1993",
                citation_count=12,
                keywords=["DSM", "Cache Coherence"],
                source_url="https://scholar.google.com/citations?user=LchbZ8wAAAAJ",
                source="official_linked_google_scholar",
                anchoring_professor_id="PROF-TANG",
                anchoring_professor_name="唐志敏",
                anchoring_institution="深圳理工大学",
            ),
            PaperStagingRecord(
                title="JIAJIA: A software DSM system based on a new cache coherence protocol",
                authors=["唐志敏", "张三"],
                year=1993,
                venue="International Conference on Parallel Processing",
                abstract="A DSM protocol paper.",
                doi="10.1000/jiajia.1993",
                citation_count=12,
                keywords=["DSM", "Cache Coherence"],
                source_url="https://scholar.google.com/citations?user=LchbZ8wAAAAJ",
                source="official_linked_google_scholar",
                anchoring_professor_id="PROF-TANG-2",
                anchoring_professor_name="唐志敏（并列锚点）",
                anchoring_institution="深圳理工大学",
            ),
        ],
        now=TIMESTAMP,
    )

    assert len(result.paper_records) == 1
    assert len(result.paper_released_objects) == 1
    assert len(result.link_records) == 2
    assert len(result.link_released_objects) == 2
    assert {item.professor_id for item in result.link_records} == {"PROF-TANG", "PROF-TANG-2"}
    assert {item.paper_id for item in result.link_records} == {result.paper_records[0].id}
    assert all(item.link_status == "verified" for item in result.link_records)
    assert all(item.evidence_source == "official_linked_google_scholar" for item in result.link_records)
