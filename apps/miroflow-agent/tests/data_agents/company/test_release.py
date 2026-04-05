from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.company.models import CompanyImportRecord, FinancingEvent
from src.data_agents.company.release import (
    build_company_release,
    publish_company_release,
)


TIMESTAMP = datetime(2026, 4, 2, tzinfo=timezone.utc)


def _company_record() -> CompanyImportRecord:
    return CompanyImportRecord(
        name="深圳旭宏医疗科技有限公司",
        normalized_name="旭宏医疗科技",
        industry="医疗健康",
        sub_industry="心脏治疗及急救装置",
        business="人工智能慢病预防与管理企业",
        website="https://www.semacare.com/",
        legal_representative="WANG BO YANG ALEXANDER",
        description=(
            "Semacare专注创新心电系统开发，拥有自主核心算法，运用AI自动诊断技术，"
            "覆盖临床和运动医学两大市场。"
        ),
        team_raw=(
            "王博洋，职务：CEO&联合创始人，介绍：王博洋，旭宏医疗CEO&联合创始人。\n"
            "杨馥诚，职务：董事长，介绍：杨馥诚，旭宏医疗董事长。"
        ),
        patent_count=62,
        financing_events=(
            FinancingEvent(
                round="A轮",
                time="2020.7.7",
                amount="数千万人民币",
                amount_cny_wan="1100",
                investor="力合科创",
            ),
        ),
        investors=("力合科创",),
        source_row_numbers=(4, 5),
    )


def test_build_company_release_generates_contract_records_and_released_objects():
    release_result = build_company_release(
        records=[_company_record()],
        source_file=Path("docs/专辑项目导出1768807339.xlsx"),
        now=TIMESTAMP,
    )

    assert len(release_result.company_records) == 1
    record = release_result.company_records[0]
    assert record.id.startswith("COMP-")
    assert record.name == "深圳旭宏医疗科技有限公司"
    assert record.normalized_name == "旭宏医疗科技"
    assert record.industry == "医疗健康"
    assert len(record.key_personnel) == 2
    assert record.key_personnel[0].name == "王博洋"
    assert record.key_personnel[0].role == "CEO&联合创始人"
    assert record.profile_summary
    assert record.evaluation_summary
    assert record.technology_route_summary
    assert any(item.source_type == "xlsx_import" for item in record.evidence)

    released = release_result.released_objects[0]
    assert released.object_type == "company"
    assert released.id == record.id
    assert released.core_facts["key_personnel"] == [
        {"name": "王博洋", "role": "CEO&联合创始人"},
        {"name": "杨馥诚", "role": "董事长"},
    ]
    assert released.summary_fields["profile_summary"] == record.profile_summary
    assert released.summary_fields["evaluation_summary"] == record.evaluation_summary
    assert (
        released.summary_fields["technology_route_summary"]
        == record.technology_route_summary
    )


def test_publish_company_release_writes_jsonl_outputs(tmp_path: Path):
    release_result = build_company_release(
        records=[_company_record()],
        source_file=Path("docs/专辑项目导出1768807339.xlsx"),
        now=TIMESTAMP,
    )
    company_path = tmp_path / "company_records.jsonl"
    released_path = tmp_path / "released_objects.jsonl"

    publish_company_release(
        release_result,
        company_records_path=company_path,
        released_objects_path=released_path,
    )

    company_lines = company_path.read_text(encoding="utf-8").strip().splitlines()
    released_lines = released_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(company_lines) == 1
    assert len(released_lines) == 1
    company_payload = json.loads(company_lines[0])
    released_payload = json.loads(released_lines[0])
    assert company_payload["id"] == released_payload["id"]
    assert released_payload["object_type"] == "company"
