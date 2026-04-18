# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.contracts import Evidence, ReleasedObject
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_script():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "run_workbook_coverage_audit.py"
    )
    return _load_module("run_workbook_coverage_audit", script_path)


def _evidence() -> list[Evidence]:
    return [
        Evidence(
            source_type="official_site",
            source_url="https://example.edu.cn/profile",
            fetched_at=datetime.now(timezone.utc),
        )
    ]


def _released_object(
    *,
    object_id: str,
    object_type: str,
    display_name: str,
    core_facts: dict,
    summary_fields: dict | None = None,
) -> ReleasedObject:
    return ReleasedObject(
        id=object_id,
        object_type=object_type,
        display_name=display_name,
        core_facts=core_facts,
        summary_fields=summary_fields or {"profile_summary": f"{display_name} summary"},
        evidence=_evidence(),
        last_updated=datetime.now(timezone.utc),
        quality_status="ready",
    )


def test_audit_workbook_coverage_marks_q1_pass_with_professor_company_link(tmp_path: Path):
    module = _load_script()
    db_path = tmp_path / "released_objects.db"
    store = SqliteReleasedObjectStore(db_path)
    store.upsert_released_objects(
        [
            _released_object(
                object_id="PROF-1",
                object_type="professor",
                display_name="丁文伯",
                core_facts={
                    "name": "丁文伯",
                    "institution": "清华大学深圳国际研究生院",
                    "company_roles": [
                        {
                            "company_name": "深圳无界智航科技有限公司",
                            "role": "founder",
                        }
                    ],
                    "top_papers": [],
                    "patent_ids": [],
                },
            ),
            _released_object(
                object_id="COMP-1",
                object_type="company",
                display_name="深圳无界智航科技有限公司",
                core_facts={"name": "深圳无界智航科技有限公司"},
                summary_fields={
                    "profile_summary": "深圳无界智航科技有限公司画像",
                    "evaluation_summary": "评价",
                    "technology_route_summary": "技术路线",
                },
            ),
        ]
    )

    report = module.build_workbook_coverage_report(db_path)
    question = next(item for item in report["questions"] if item["id"] == "q1")

    assert question["status"] == "pass"
    assert question["passed_checks"] == 3
    assert question["failed_checks"] == 0


def test_audit_workbook_coverage_treats_patent_applicants_as_company_match(tmp_path: Path):
    module = _load_script()
    db_path = tmp_path / "released_objects.db"
    store = SqliteReleasedObjectStore(db_path)
    store.upsert_released_objects(
        [
            _released_object(
                object_id="PAT-APPLICANT",
                object_type="patent",
                display_name="一种人形机器人控制装置",
                core_facts={
                    "title": "一种人形机器人控制装置",
                    "patent_number": "CN000000002A",
                    "applicants": ["深圳市优必选科技股份有限公司"],
                },
                summary_fields={
                    "summary_text": "专利摘要",
                    "summary_zh": "专利摘要",
                },
            )
        ]
    )

    report = module.build_workbook_coverage_report(db_path)
    question = next(item for item in report["questions"] if item["id"] == "q17")
    ubtech_check = next(item for item in question["checks"] if item["id"] == "ubtech_patents_exist")

    assert ubtech_check["passed"] is True
    assert question["status"] == "partial"


def test_audit_workbook_coverage_marks_q17_partial_without_exact_patent(tmp_path: Path):
    module = _load_script()
    db_path = tmp_path / "released_objects.db"
    store = SqliteReleasedObjectStore(db_path)
    store.upsert_released_objects(
        [
            _released_object(
                object_id="PAT-1",
                object_type="patent",
                display_name="一种机器人控制系统",
                core_facts={
                    "title": "一种机器人控制系统",
                    "patent_number": "CN000000001A",
                    "assignees": ["深圳市优必选科技股份有限公司"],
                },
                summary_fields={
                    "summary_text": "专利摘要",
                    "summary_zh": "专利摘要",
                },
            )
        ]
    )

    report = module.build_workbook_coverage_report(db_path)
    question = next(item for item in report["questions"] if item["id"] == "q17")

    assert question["status"] == "partial"
    assert question["passed_checks"] == 1
    assert question["failed_checks"] == 1


def test_object_exists_ignores_irrelevant_url_substrings(tmp_path: Path):
    module = _load_script()
    db_path = tmp_path / "released_objects.db"
    store = SqliteReleasedObjectStore(db_path)
    store.upsert_released_objects(
        [
            _released_object(
                object_id="COMP-URL",
                object_type="company",
                display_name="示例公司",
                core_facts={
                    "name": "示例公司",
                    "website": "https://example.com/jiuhao",
                    "industry": "机器人",
                    "key_personnel": [],
                },
                summary_fields={
                    "profile_summary": "示例公司画像",
                    "evaluation_summary": "评价",
                    "technology_route_summary": "技术路线",
                },
            )
        ]
    )

    objects_by_domain, _ = module._load_objects_by_domain(db_path)

    assert (
        module._object_exists(
            objects_by_domain,
            domain="company",
            query="九号",
        )
        is False
    )


def test_object_exists_ignores_unrelated_summary_mentions(tmp_path: Path):
    module = _load_script()
    db_path = tmp_path / "released_objects.db"
    store = SqliteReleasedObjectStore(db_path)
    store.upsert_released_objects(
        [
            _released_object(
                object_id="COMP-SUMMARY",
                object_type="company",
                display_name="示例公司",
                core_facts={
                    "name": "示例公司",
                    "website": "https://example.com",
                    "industry": "机器人",
                    "key_personnel": [],
                },
                summary_fields={
                    "profile_summary": "示例公司曾与九号机器人合作举办活动",
                    "evaluation_summary": "评价",
                    "technology_route_summary": "技术路线",
                },
            )
        ]
    )

    objects_by_domain, _ = module._load_objects_by_domain(db_path)

    assert (
        module._object_exists(
            objects_by_domain,
            domain="company",
            query="九号",
        )
        is False
    )


def test_object_exists_rejects_partial_company_identity_matches(tmp_path: Path):
    module = _load_script()
    db_path = tmp_path / "released_objects.db"
    store = SqliteReleasedObjectStore(db_path)
    store.upsert_released_objects(
        [
            _released_object(
                object_id="COMP-PUDU",
                object_type="company",
                display_name="普渡大学科技有限公司",
                core_facts={
                    "name": "普渡大学科技有限公司",
                    "website": "https://example.com",
                    "industry": "机器人",
                    "key_personnel": [],
                },
                summary_fields={
                    "profile_summary": "示例公司画像",
                    "evaluation_summary": "评价",
                    "technology_route_summary": "技术路线",
                },
            )
        ]
    )

    objects_by_domain, _ = module._load_objects_by_domain(db_path)

    assert (
        module._object_exists(
            objects_by_domain,
            domain="company",
            query="普渡科技",
        )
        is False
    )


def test_audit_workbook_coverage_keeps_q1_fail_without_professor_company_link(tmp_path: Path):
    module = _load_script()
    db_path = tmp_path / "released_objects.db"
    store = SqliteReleasedObjectStore(db_path)
    store.upsert_released_objects(
        [
            _released_object(
                object_id="PROF-2",
                object_type="professor",
                display_name="丁文伯",
                core_facts={
                    "name": "丁文伯",
                    "institution": "清华大学深圳国际研究生院",
                    "company_roles": [],
                    "top_papers": [],
                    "patent_ids": [],
                },
            ),
            _released_object(
                object_id="COMP-2",
                object_type="company",
                display_name="深圳无界智航科技有限公司",
                core_facts={"name": "深圳无界智航科技有限公司"},
                summary_fields={
                    "profile_summary": "深圳无界智航科技有限公司画像",
                    "evaluation_summary": "评价",
                    "technology_route_summary": "技术路线",
                },
            ),
        ]
    )

    report = module.build_workbook_coverage_report(db_path)
    question = next(item for item in report["questions"] if item["id"] == "q1")

    assert question["status"] == "fail"
    assert question["passed_checks"] == 2
    assert question["failed_checks"] == 1


def test_audit_workbook_coverage_marks_q11_pass_with_real_and_synthetic_routes(tmp_path: Path):
    module = _load_script()
    db_path = tmp_path / "released_objects.db"
    store = SqliteReleasedObjectStore(db_path)
    store.upsert_released_objects(
        [
            _released_object(
                object_id="COMP-R1",
                object_type="company",
                display_name="自变量机器人科技（深圳）有限公司",
                core_facts={
                    "name": "自变量机器人科技（深圳）有限公司",
                    "data_route_types": ["real_data"],
                    "real_data_methods": ["teleoperation", "motion_capture"],
                },
                summary_fields={
                    "profile_summary": "公司画像",
                    "evaluation_summary": "评价",
                    "technology_route_summary": "技术路线",
                },
            ),
            _released_object(
                object_id="COMP-S1",
                object_type="company",
                display_name="深圳无界智航科技有限公司",
                core_facts={
                    "name": "深圳无界智航科技有限公司",
                    "data_route_types": ["synthetic_data"],
                    "synthetic_data_methods": ["physics_simulation", "generative_model"],
                },
                summary_fields={
                    "profile_summary": "公司画像",
                    "evaluation_summary": "评价",
                    "technology_route_summary": "技术路线",
                },
            ),
        ]
    )

    report = module.build_workbook_coverage_report(db_path)
    question = next(item for item in report["questions"] if item["id"] == "q11")

    assert question["status"] == "pass"
    assert question["passed_checks"] == 2


def test_object_exists_rejects_unrelated_prefix_collision(tmp_path: Path):
    module = _load_script()
    db_path = tmp_path / "released_objects.db"
    store = SqliteReleasedObjectStore(db_path)
    store.upsert_released_objects(
        [
            _released_object(
                object_id="COMP-PREFIX",
                object_type="company",
                display_name="云迹科技传媒有限公司",
                core_facts={
                    "name": "云迹科技传媒有限公司",
                    "industry": "传媒",
                    "key_personnel": [],
                },
                summary_fields={
                    "profile_summary": "公司画像",
                    "evaluation_summary": "评价",
                    "technology_route_summary": "技术路线",
                },
            )
        ]
    )

    objects_by_domain, _ = module._load_objects_by_domain(db_path)

    assert module._object_exists(objects_by_domain, domain="company", query="云迹科技") is False
