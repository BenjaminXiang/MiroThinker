from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.data_agents.contracts import (
    CompanyKeyPerson,
    CompanyRecord,
    EducationExperience,
    Evidence,
    PaperRecord,
    PatentRecord,
    ProfessorCompanyRole,
    ProfessorPaperLinkRecord,
    ProfessorRecord,
    ReleasedObject,
)


TIMESTAMP = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _evidence() -> Evidence:
    return Evidence(
        source_type="official_site",
        source_url="https://www.sustech.edu.cn",
        fetched_at=TIMESTAMP,
        snippet="Verified against an official profile page.",
    )


def _public_web_evidence() -> Evidence:
    return Evidence(
        source_type="public_web",
        source_url="https://example.com/profile",
        fetched_at=TIMESTAMP,
        snippet="Collected from a public profile page.",
    )


def test_release_contracts_map_to_shared_released_object():
    professor = ProfessorRecord(
        id="PROF-001",
        name="Ada Lovelace",
        institution="SUSTech",
        department="Computer Science",
        title="Professor",
        email="ada@example.com",
        homepage="https://example.com/ada",
        research_directions=["AI", "Systems"],
        education_structured=[
            EducationExperience(
                school="University of London",
                degree="Mathematics",
                field="Mathematics",
            )
        ],
        work_experience=["Analytical Engines advisor"],
        paper_count=12,
        citation_count=128,
        profile_summary="Focuses on agent runtime design.",
        evaluation_summary="Has a strong publication and systems track record.",
        company_roles=[
            ProfessorCompanyRole(company_name="Analytical Engines", role="Advisor")
        ],
        patent_ids=["PAT-001"],
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )
    company = CompanyRecord(
        id="COMP-001",
        name="Analytical Engines",
        normalized_name="AnalyticalEngines",
        industry="Automation",
        website="https://example.com",
        key_personnel=[CompanyKeyPerson(name="Ada Lovelace", role="Advisor")],
        profile_summary="Builds industrial automation systems.",
        evaluation_summary="Strong engineering depth and execution quality.",
        technology_route_summary="Combines control systems and local models.",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )
    paper = PaperRecord(
        id="PAPER-001",
        title="On the Analytical Engine",
        authors=["Ada Lovelace", "Charles Babbage"],
        year=1843,
        venue="Journal of Computing",
        publication_date="1843-01-01",
        keywords=["analysis engine", "programming"],
        professor_ids=["PROF-001"],
        summary_zh="介绍了分析机的设计与意义。",
        summary_text="介绍了分析机的设计、背景、方法与影响。",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )
    patent = PatentRecord(
        id="PAT-001",
        title="Improved Computing Apparatus",
        patent_number="CN-123",
        applicants=["Analytical Engines"],
        inventors=["Ada Lovelace"],
        patent_type="invention",
        filing_date="1843-01-01",
        publication_date="1844-01-01",
        company_ids=["COMP-001"],
        professor_ids=["PROF-001"],
        summary_text="Covers a configurable computing apparatus.",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )

    released = [
        professor.to_released_object(),
        company.to_released_object(),
        paper.to_released_object(),
        patent.to_released_object(),
    ]

    assert [record.object_type for record in released] == [
        "professor",
        "company",
        "paper",
        "patent",
    ]
    assert [record.display_name for record in released] == [
        "Ada Lovelace",
        "Analytical Engines",
        "On the Analytical Engine",
        "Improved Computing Apparatus",
    ]
    assert released[0].summary_fields["profile_summary"] == (
        "Focuses on agent runtime design."
    )
    assert released[0].core_facts["email"] == "ada@example.com"
    assert released[0].core_facts["homepage"] == "https://example.com/ada"
    assert released[0].core_facts["education_structured"] == [
        {
            "school": "University of London",
            "degree": "Mathematics",
            "field": "Mathematics",
            "start_year": None,
            "end_year": None,
        }
    ]
    assert released[0].core_facts["work_experience"] == ["Analytical Engines advisor"]
    assert released[0].core_facts["paper_count"] == 12
    assert "top_papers" not in released[0].core_facts
    assert released[0].core_facts["citation_count"] == 128
    assert released[0].core_facts["patent_ids"] == ["PAT-001"]
    assert released[1].core_facts["normalized_name"] == "AnalyticalEngines"
    assert released[2].core_facts["authors"] == ["Ada Lovelace", "Charles Babbage"]
    assert released[2].core_facts["year"] == 1843
    assert released[2].core_facts["keywords"] == ["analysis engine", "programming"]
    assert released[2].summary_fields["summary_zh"] == "介绍了分析机的设计与意义。"
    assert released[3].core_facts["patent_number"] == "CN-123"
    assert released[3].core_facts["applicants"] == ["Analytical Engines"]
    assert released[3].core_facts["inventors"] == ["Ada Lovelace"]
    assert released[3].core_facts["patent_type"] == "invention"
    assert released[3].core_facts["filing_date"] == "1843-01-01"
    assert released[3].core_facts["publication_date"] == "1844-01-01"




def test_professor_paper_link_contract_maps_to_released_object():
    record = ProfessorPaperLinkRecord(
        id="PPLINK-001",
        professor_id="PROF-001",
        paper_id="PAPER-001",
        professor_name="Ada Lovelace",
        paper_title="On the Analytical Engine",
        link_status="verified",
        evidence_source="official_linked_google_scholar",
        evidence_url="https://scholar.google.com/citations?user=ada",
        match_reason="Official scholar profile contains the paper.",
        verified_by="pipeline_v3",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )

    released = record.to_released_object()

    assert released.object_type == "professor_paper_link"
    assert released.core_facts["professor_id"] == "PROF-001"
    assert released.core_facts["paper_id"] == "PAPER-001"
    assert released.core_facts["link_status"] == "verified"
    assert released.summary_fields["match_reason"] == "Official scholar profile contains the paper."


def test_shared_contracts_default_to_non_ready_quality_status():
    released = ReleasedObject(
        id="OBJ-1",
        object_type="paper",
        display_name="Test Paper",
        core_facts={"title": "Test Paper"},
        summary_fields={"summary_text": "Test"},
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )
    professor = ProfessorRecord(
        id="PROF-001",
        name="Ada Lovelace",
        institution="SUSTech",
        profile_summary="Focuses on agent runtime design.",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )
    paper = PaperRecord(
        id="PAPER-001",
        title="On the Analytical Engine",
        authors=["Ada Lovelace"],
        year=1843,
        publication_date="1843-01-01",
        summary_zh="介绍了分析机的设计与意义。",
        summary_text="介绍了分析机的设计、背景、方法与影响。",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )
    link = ProfessorPaperLinkRecord(
        id="PPLINK-001",
        professor_id="PROF-001",
        paper_id="PAPER-001",
        professor_name="Ada Lovelace",
        paper_title="On the Analytical Engine",
        link_status="candidate",
        match_reason="Awaiting verification.",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )

    assert released.quality_status == "needs_review"
    assert professor.quality_status == "needs_review"
    assert paper.quality_status == "needs_review"
    assert link.quality_status == "needs_review"

def test_released_object_requires_evidence():
    with pytest.raises(ValidationError, match="evidence"):
        ReleasedObject(
            id="COMP-001",
            object_type="company",
            display_name="Analytical Engines",
            core_facts={"name": "Analytical Engines"},
            summary_fields={},
            evidence=[],
            last_updated=TIMESTAMP,
        )


def test_display_name_defaults_for_domain_contracts():
    record = CompanyRecord(
        id="COMP-001",
        name="Analytical Engines",
        normalized_name="AnalyticalEngines",
        industry="Automation",
        profile_summary="Profile",
        evaluation_summary="Evaluation",
        technology_route_summary="Route",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )

    assert record.display_name == "Analytical Engines"


def test_company_record_requires_industry():
    with pytest.raises(ValidationError, match="industry"):
        CompanyRecord(
            id="COMP-001",
            name="Analytical Engines",
            normalized_name="AnalyticalEngines",
            profile_summary="Profile",
            evaluation_summary="Evaluation",
            technology_route_summary="Route",
            evidence=[_evidence()],
            last_updated=TIMESTAMP,
        )


def test_company_record_rejects_blank_required_text_fields():
    with pytest.raises(ValidationError) as exc_info:
        CompanyRecord(
            id="COMP-001",
            name="Analytical Engines",
            normalized_name="AnalyticalEngines",
            industry=" ",
            profile_summary="",
            evaluation_summary=" ",
            technology_route_summary="",
            evidence=[_evidence()],
            last_updated=TIMESTAMP,
        )

    message = str(exc_info.value)
    assert "industry" in message
    assert "profile_summary" in message
    assert "evaluation_summary" in message
    assert "technology_route_summary" in message


def test_professor_record_allows_missing_department_and_title():
    record = ProfessorRecord(
        id="PROF-001",
        name="Ada Lovelace",
        institution="SUSTech",
        department=None,
        title=None,
        research_directions=["AI"],
        profile_summary="Profile",
        evaluation_summary="Evaluation",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )

    released = record.to_released_object()

    assert record.department is None
    assert record.title is None
    assert "department" in released.core_facts
    assert "title" in released.core_facts
    assert released.core_facts["department"] is None
    assert released.core_facts["title"] is None


def test_professor_record_requires_name_and_institution():
    with pytest.raises(ValidationError) as exc_info:
        ProfessorRecord(
            id="PROF-001",
            name=" ",
            institution=" ",
            department=None,
            title=None,
            research_directions=["AI"],
            profile_summary="Profile",
            evaluation_summary="Evaluation",
            evidence=[_evidence()],
            last_updated=TIMESTAMP,
        )

    message = str(exc_info.value)
    assert "name" in message
    assert "institution" in message


def test_professor_record_requires_shenzhen_institution():
    with pytest.raises(ValidationError, match="institution"):
        ProfessorRecord(
            id="PROF-001",
            name="Ada Lovelace",
            institution="Non Shenzhen University",
            department="Computer Science",
            title="Professor",
            research_directions=["AI"],
            profile_summary="Profile",
            evaluation_summary="Evaluation",
            evidence=[_evidence()],
            last_updated=TIMESTAMP,
        )


def test_professor_record_requires_at_least_one_official_source():
    with pytest.raises(ValidationError, match="official_site"):
        ProfessorRecord(
            id="PROF-001",
            name="Ada Lovelace",
            institution="SUSTech",
            department="Computer Science",
            title="Professor",
            research_directions=["AI"],
            profile_summary="Profile",
            evaluation_summary="Evaluation",
            evidence=[_public_web_evidence()],
            last_updated=TIMESTAMP,
        )


def test_paper_record_allows_missing_venue():
    record = PaperRecord(
        id="PAPER-001",
        title="On the Analytical Engine",
        authors=["Ada Lovelace"],
        year=1843,
        keywords=["analysis engine"],
        professor_ids=["PROF-001"],
        summary_zh="介绍了分析机的设计与意义。",
        summary_text="介绍了分析机的设计、背景、方法与影响。",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )

    released = record.to_released_object()

    assert record.venue is None
    assert released.core_facts["venue"] is None


def test_paper_record_rejects_blank_required_text_fields():
    with pytest.raises(ValidationError) as exc_info:
        PaperRecord(
            id="PAPER-001",
            title=" ",
            authors=["Ada Lovelace"],
            year=1843,
            venue=" ",
            keywords=["analysis engine"],
            professor_ids=["PROF-001"],
            summary_zh="",
            summary_text=" ",
            evidence=[_evidence()],
            last_updated=TIMESTAMP,
        )

    message = str(exc_info.value)
    assert "title" in message
    assert "venue" in message
    assert "summary_zh" in message
    assert "summary_text" in message


def test_patent_record_allows_single_available_date():
    record = PatentRecord(
        id="PAT-001",
        title="Improved Computing Apparatus",
        applicants=["Analytical Engines"],
        inventors=[],
        patent_type="invention",
        filing_date="1843-01-01",
        publication_date=None,
        summary_text="Covers a configurable computing apparatus.",
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
    )

    assert record.filing_date == "1843-01-01"
    assert record.publication_date is None
    assert record.inventors == []


def test_patent_record_requires_at_least_one_date():
    with pytest.raises(ValidationError, match="filing_date or publication_date"):
        PatentRecord(
            id="PAT-001",
            title="Improved Computing Apparatus",
            applicants=["Analytical Engines"],
            inventors=["Ada Lovelace"],
            patent_type="invention",
            filing_date=None,
            publication_date=None,
            summary_text="Covers a configurable computing apparatus.",
            evidence=[_evidence()],
            last_updated=TIMESTAMP,
        )


def test_evidence_requires_source_reference_and_supports_confidence():
    evidence = Evidence(
        source_type="xlsx_import",
        source_file="qimingpian_export_202603.xlsx",
        fetched_at=TIMESTAMP,
        confidence=0.95,
    )

    assert evidence.source_type == "xlsx_import"
    assert evidence.source_file == "qimingpian_export_202603.xlsx"
    assert evidence.confidence == 0.95


def test_evidence_rejects_missing_source_url_and_source_file():
    with pytest.raises(ValidationError, match="source_url or source_file"):
        Evidence(
            source_type="public_web",
            fetched_at=TIMESTAMP,
        )


def test_evidence_rejects_non_spec_extra_fields():
    with pytest.raises(ValidationError, match="source_name"):
        Evidence(
            source_type="official_site",
            source_url="https://www.sustech.edu.cn",
            fetched_at=TIMESTAMP,
            source_name="SUSTech",
        )


def test_evidence_uses_fetched_at_instead_of_retrieved_at():
    with pytest.raises(ValidationError, match="fetched_at"):
        Evidence(
            source_type="official_site",
            source_url="https://www.sustech.edu.cn",
            retrieved_at=TIMESTAMP,
        )
