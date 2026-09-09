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
        credit_code="91440300MA5EXAMPLE",
        industry="医疗健康",
        sub_industry="心脏治疗及急救装置",
        business="人工智能慢病预防与管理企业",
        website="https://www.semacare.com/",
        legal_representative="WANG BO YANG ALEXANDER",
        registered_capital="500万人民币",
        description=(
            "Semacare专注创新心电系统开发，拥有自主核心算法，运用AI自动诊断技术，"
            "覆盖临床和运动医学两大市场。"
        ),
        team_raw=(
            "王博洋，职务：CEO&联合创始人，介绍：王博洋，本科毕业于斯坦福大学，"
            "曾任谷歌算法负责人，旭宏医疗CEO&联合创始人。\n"
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
    assert record.credit_code == "91440300MA5EXAMPLE"
    assert record.legal_representative == "WANG BO YANG ALEXANDER"
    assert record.registered_capital == "500万人民币"
    assert record.patent_count == 62
    assert len(record.key_personnel) == 2
    assert record.key_personnel[0].name == "王博洋"
    assert record.key_personnel[0].role == "CEO&联合创始人"
    assert record.key_personnel[0].description == (
        "王博洋，本科毕业于斯坦福大学，曾任谷歌算法负责人，旭宏医疗CEO&联合创始人。"
    )
    assert record.key_personnel[0].education_structured[0].school == "斯坦福大学"
    assert record.key_personnel[0].education_structured[0].degree == "本科"
    assert record.key_personnel[0].work_experience[0].organization == "谷歌"
    assert record.key_personnel[0].work_experience[0].role == "算法负责人"
    assert record.profile_summary
    assert record.technology_route_summary
    assert any(item.source_type == "xlsx_import" for item in record.evidence)

    released = release_result.released_objects[0]
    assert released.object_type == "company"
    assert released.id == record.id
    assert released.core_facts["credit_code"] == "91440300MA5EXAMPLE"
    assert released.core_facts["legal_representative"] == "WANG BO YANG ALEXANDER"
    assert released.core_facts["registered_capital"] == "500万人民币"
    assert released.core_facts["patent_count"] == 62
    assert released.core_facts["key_personnel"] == [
        {
            "name": "王博洋",
            "role": "CEO&联合创始人",
            "description": (
                "王博洋，本科毕业于斯坦福大学，曾任谷歌算法负责人，旭宏医疗CEO&联合创始人。"
            ),
            "education_structured": [
                {
                    "school": "斯坦福大学",
                    "degree": "本科",
                    "field": None,
                    "start_year": None,
                    "end_year": None,
                }
            ],
            "work_experience": [
                {
                    "organization": "谷歌",
                    "role": "算法负责人",
                    "description": "曾任谷歌算法负责人",
                    "start_year": None,
                    "end_year": None,
                }
            ],
        },
        {
            "name": "杨馥诚",
            "role": "董事长",
            "description": "杨馥诚，旭宏医疗董事长。",
            "education_structured": [],
            "work_experience": [],
        },
    ]
    assert released.summary_fields["profile_summary"] == record.profile_summary
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


def test_company_release_optional_publish_fields_remain_optional():
    minimal = CompanyImportRecord(
        name="深圳示例科技有限公司",
        normalized_name="示例科技",
        industry="人工智能",
        business="机器人视觉方案",
        source_row_numbers=(7,),
    )

    release_result = build_company_release(
        records=[minimal],
        source_file=Path("docs/专辑项目导出1768807339.xlsx"),
        now=TIMESTAMP,
    )

    record = release_result.company_records[0]
    released = release_result.released_objects[0]
    assert record.credit_code is None
    assert record.legal_representative is None
    assert record.registered_capital is None
    assert record.patent_count is None
    assert released.core_facts["credit_code"] is None
    assert released.core_facts["legal_representative"] is None
    assert released.core_facts["registered_capital"] is None
    assert released.core_facts["patent_count"] is None


def test_company_release_prefers_synthesized_summaries_when_present():
    record = CompanyImportRecord(
        name="深圳示例科技有限公司",
        normalized_name="示例科技",
        industry="人工智能",
        business="原始 XLSX 业务描述",
        description="原始 XLSX 简介",
        profile_summary="合成后的公司简介，用于展示和检索。",
        technology_route_summary="合成后的技术路线，覆盖产品和研发方向。",
        source_row_numbers=(8,),
    )

    release_result = build_company_release(
        records=[record],
        source_file=Path("docs/专辑项目导出1768807339.xlsx"),
        now=TIMESTAMP,
    )

    released = release_result.released_objects[0]
    assert (
        released.summary_fields["profile_summary"]
        == "合成后的公司简介，用于展示和检索。"
    )
    assert (
        released.summary_fields["technology_route_summary"]
        == "合成后的技术路线，覆盖产品和研发方向。"
    )
