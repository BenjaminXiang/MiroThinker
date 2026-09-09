from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from src.data_agents.company.models import CompanyImportRecord
from src.data_agents.company.release import build_company_release
from src.data_agents.patent.models import PatentImportRecord
from src.data_agents.patent.release import (
    build_patent_release,
    publish_patent_release,
)


TIMESTAMP = datetime(2026, 4, 2, tzinfo=timezone.utc)


def _patent_record() -> PatentImportRecord:
    return PatentImportRecord(
        source_row=2,
        sequence_number="10001",
        title="无人机的机臂锁紧组件、无人机机臂和无人机",
        title_en="UAV arm locking assembly, UAV arm and UAV",
        abstract="本申请公开了一种用于无人机机臂的锁紧组件，可提升锁定稳定性。",
        abstract_en=None,
        applicants=("深圳市飞米机器人科技有限公司",),
        patent_number="CN223200311U",
        publication_date=date(2025, 8, 8),
        filing_date=date(2024, 8, 8),
        patent_type="实用新型",
        technology_effect_sentence="使得锁紧件可以牢固锁定第一固定件和第二固定件",
        technology_effect_phrases=("第一固定件牢固锁定",),
        expected_expiry_date=date(2034, 8, 8),
    )


def _company_release() -> list[str]:
    result = build_company_release(
        records=[
            CompanyImportRecord(
                name="深圳市飞米机器人科技有限公司",
                normalized_name="飞米机器人科技",
                industry="先进制造",
            )
        ],
        source_file=Path("docs/专辑项目导出1768807339.xlsx"),
        now=TIMESTAMP,
    )
    return [result.company_records[0].id]


def test_build_patent_release_generates_summary_and_company_links():
    company_ids = _company_release()

    release_result = build_patent_release(
        records=[_patent_record()],
        source_file=Path("docs/2025-12-05 专利.xlsx"),
        company_name_to_id={"飞米机器人科技": company_ids[0]},
        now=TIMESTAMP,
    )

    assert len(release_result.patent_records) == 1
    record = release_result.patent_records[0]
    assert record.id.startswith("PAT-")
    assert record.patent_number == "CN223200311U"
    assert record.applicants == ["深圳市飞米机器人科技有限公司"]
    assert record.inventors == []
    assert record.summary_text
    assert record.company_ids == company_ids
    assert record.professor_ids == []
    assert any(item.source_type == "xlsx_import" for item in record.evidence)

    released = release_result.released_objects[0]
    assert released.object_type == "patent"
    assert released.summary_fields["summary_text"] == record.summary_text
    assert released.core_facts["company_ids"] == company_ids


def test_publish_patent_release_writes_jsonl_outputs(tmp_path: Path):
    release_result = build_patent_release(
        records=[_patent_record()],
        source_file=Path("docs/2025-12-05 专利.xlsx"),
        company_name_to_id={},
        now=TIMESTAMP,
    )
    patent_path = tmp_path / "patent_records.jsonl"
    released_path = tmp_path / "released_objects.jsonl"

    publish_patent_release(
        release_result,
        patent_records_path=patent_path,
        released_objects_path=released_path,
    )

    patent_lines = patent_path.read_text(encoding="utf-8").strip().splitlines()
    released_lines = released_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(patent_lines) == 1
    assert len(released_lines) == 1
    patent_payload = json.loads(patent_lines[0])
    released_payload = json.loads(released_lines[0])
    assert patent_payload["id"] == released_payload["id"]
    assert released_payload["object_type"] == "patent"
