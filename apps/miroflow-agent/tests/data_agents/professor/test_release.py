from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.professor.models import MergedProfessorProfileRecord
from src.data_agents.professor.release import (
    ProfessorSummaries,
    build_professor_release,
    publish_professor_release,
)


TIMESTAMP = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _merged_record(
    *,
    name: str = "李志",
    institution: str = "南方科技大学",
    department: str = "计算机科学与工程系",
    title: str | None = "教授",
    extraction_status: str = "structured",
    profile_url: str = "https://scholar.example.com/lizhi",
    roster_source: str = "https://www.sustech.edu.cn/zh/letter/",
) -> MergedProfessorProfileRecord:
    return MergedProfessorProfileRecord(
        name=name,
        institution=institution,
        department=department,
        title=title,
        email="lizhi@sustech.edu.cn",
        office="工学院南楼",
        homepage=None,
        profile_url=profile_url,
        source_urls=(profile_url,),
        evidence=(profile_url,),
        research_directions=("机器学习", "具身智能"),
        extraction_status=extraction_status,
        skip_reason=None,
        error=None,
        roster_source=roster_source,
    )


def test_build_professor_release_generates_contract_valid_record_with_fallback_summary():
    profile = _merged_record()

    release_result = build_professor_release(
        profiles=[profile],
        official_domain_suffixes=("sustech.edu.cn",),
        now=TIMESTAMP,
    )
    release_result_again = build_professor_release(
        profiles=[profile],
        official_domain_suffixes=("sustech.edu.cn",),
        now=TIMESTAMP,
    )

    assert len(release_result.professor_records) == 1
    professor = release_result.professor_records[0]
    assert professor.id.startswith("PROF-")
    assert professor.id == release_result_again.professor_records[0].id
    assert professor.profile_summary
    assert professor.evaluation_summary
    assert "李志" in professor.profile_summary
    assert 200 <= len(professor.profile_summary) <= 300
    assert 100 <= len(professor.evaluation_summary) <= 150
    assert any(item.source_type == "official_site" for item in professor.evidence)
    assert any(item.source_type == "public_web" for item in professor.evidence)
    assert professor.email == "lizhi@sustech.edu.cn"
    assert professor.office == "工学院南楼"
    assert professor.homepage == "https://scholar.example.com/lizhi"
    assert professor.education_structured == []
    assert professor.work_experience == []
    assert professor.citation_count is None
    assert professor.patent_ids == []
    assert len(release_result.released_objects) == 1
    assert release_result.released_objects[0].object_type == "professor"
    assert release_result.released_objects[0].id == professor.id
    assert release_result.released_objects[0].core_facts["email"] == "lizhi@sustech.edu.cn"
    assert release_result.released_objects[0].core_facts["homepage"] == "https://scholar.example.com/lizhi"
    assert release_result.released_objects[0].core_facts["office"] == "工学院南楼"
    assert release_result.released_objects[0].core_facts["education_structured"] == []
    assert release_result.released_objects[0].core_facts["work_experience"] == []
    assert release_result.released_objects[0].core_facts["citation_count"] is None
    assert release_result.released_objects[0].core_facts["patent_ids"] == []
    assert release_result.report.input_profile_count == 1
    assert release_result.report.released_record_count == 1
    assert release_result.report.skipped_record_count == 0
    assert release_result.report.official_evidence_count >= 1
    assert release_result.report.auxiliary_evidence_count >= 1


def test_build_professor_release_supports_custom_summarizer_and_reports_skips():
    valid = _merged_record(name="王五", profile_url="https://people.example.edu/wangwu")
    missing_title = _merged_record(
        name="赵六",
        title=None,
        profile_url="https://people.example.edu/zhaoliu",
    )
    missing_department_and_title = _merged_record(
        name="钱七",
        department=None,
        title=None,
        profile_url="https://people.example.edu/qianqi",
    )
    missing_institution = _merged_record(
        name="孙八",
        institution=None,
        profile_url="https://people.example.edu/sunba",
    )

    release_result = build_professor_release(
        profiles=[
            valid,
            missing_title,
            missing_department_and_title,
            missing_institution,
        ],
        summarizer=lambda profile: ProfessorSummaries(
            profile_summary=f"PROFILE::{profile.name}",
            evaluation_summary=f"EVAL::{profile.name}",
        ),
        official_domain_suffixes=("sustech.edu.cn",),
        now=TIMESTAMP,
    )

    assert len(release_result.professor_records) == 3
    records_by_name = {
        record.name: record for record in release_result.professor_records
    }

    assert "PROFILE::王五" in records_by_name["王五"].profile_summary
    assert "EVAL::王五" in records_by_name["王五"].evaluation_summary
    assert records_by_name["钱七"].department is None
    assert records_by_name["钱七"].title is None
    assert 200 <= len(records_by_name["王五"].profile_summary) <= 300
    assert 100 <= len(records_by_name["王五"].evaluation_summary) <= 150
    assert release_result.report.input_profile_count == 4
    assert release_result.report.released_record_count == 3
    assert release_result.report.skipped_record_count == 1
    assert release_result.report.skip_reasons["missing_required_fields"] == 1


def test_build_professor_release_uses_stable_id_fallback_without_department():
    profile_a = _merged_record(
        name="同名教师",
        department=None,
        title=None,
        profile_url="https://people.example.edu/faculty/name-a",
    )
    profile_b = _merged_record(
        name="同名教师",
        department=None,
        title=None,
        profile_url="https://people.example.edu/faculty/name-b",
    )

    release_result = build_professor_release(
        profiles=[profile_a, profile_b],
        official_domain_suffixes=("sustech.edu.cn",),
        now=TIMESTAMP,
    )
    release_result_again = build_professor_release(
        profiles=[profile_a, profile_b],
        official_domain_suffixes=("sustech.edu.cn",),
        now=TIMESTAMP,
    )

    ids = [record.id for record in release_result.professor_records]
    ids_again = [record.id for record in release_result_again.professor_records]

    assert len(ids) == 2
    assert len(set(ids)) == 2
    assert ids == ids_again


def test_publish_professor_release_writes_both_jsonl_outputs(tmp_path: Path):
    release_result = build_professor_release(
        profiles=[_merged_record()],
        official_domain_suffixes=("sustech.edu.cn",),
        now=TIMESTAMP,
    )
    professor_path = tmp_path / "professor_records.jsonl"
    released_path = tmp_path / "released_objects.jsonl"

    publish_professor_release(
        release_result,
        professor_records_path=professor_path,
        released_objects_path=released_path,
    )

    professor_lines = professor_path.read_text(encoding="utf-8").strip().splitlines()
    released_lines = released_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(professor_lines) == 1
    assert len(released_lines) == 1
    professor_payload = json.loads(professor_lines[0])
    released_payload = json.loads(released_lines[0])
    assert professor_payload["id"] == released_payload["id"]
    assert released_payload["object_type"] == "professor"


def test_fallback_evaluation_summary_does_not_claim_auxiliary_without_auxiliary_evidence():
    profile = _merged_record(
        profile_url="https://cse.sustech.edu.cn/faculty/lizhi/",
        roster_source="https://www.sustech.edu.cn/zh/letter/",
    )
    release_result = build_professor_release(
        profiles=[profile],
        official_domain_suffixes=("sustech.edu.cn",),
        now=TIMESTAMP,
    )

    assert len(release_result.professor_records) == 1
    evaluation_summary = release_result.professor_records[0].evaluation_summary
    assert "包含辅助公开页面" not in evaluation_summary


def test_fallback_evaluation_summary_uses_official_classification_not_domain_difference():
    profile = _merged_record(
        profile_url="https://faculty.official-b.edu.cn/lizhi",
        roster_source="https://portal.official-a.edu.cn/teachers",
    )
    release_result = build_professor_release(
        profiles=[profile],
        official_domain_suffixes=("official-a.edu.cn", "official-b.edu.cn"),
        now=TIMESTAMP,
    )

    assert len(release_result.professor_records) == 1
    evaluation_summary = release_result.professor_records[0].evaluation_summary
    assert "包含辅助公开页面" not in evaluation_summary


def test_fallback_profile_summary_stays_generic_when_department_and_title_missing():
    profile = _merged_record(
        department=None,
        title=None,
        profile_url="https://people.example.edu/lizhi",
    )
    release_result = build_professor_release(
        profiles=[profile],
        official_domain_suffixes=("sustech.edu.cn",),
        now=TIMESTAMP,
    )

    assert len(release_result.professor_records) == 1
    profile_summary = release_result.professor_records[0].profile_summary
    assert "南方科技大学" in profile_summary
    assert "相关院系" not in profile_summary
