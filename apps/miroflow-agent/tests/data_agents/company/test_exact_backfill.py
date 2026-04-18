from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook

from src.data_agents.company.exact_backfill import build_company_release_from_sources


TIMESTAMP = datetime(2026, 4, 16, tzinfo=timezone.utc)


def _write_workbook(path: Path, rows: list[list[object]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "sheet1"
    ws.append(["专辑项目导出"])
    ws.append(["序号", "行业领域", "公司名称", "网址", "团队", "简介"])
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_build_company_release_from_sources_merges_primary_and_supplement(tmp_path: Path):
    primary = tmp_path / "primary.xlsx"
    supplement = tmp_path / "supplement.xlsx"
    _write_workbook(
        primary,
        [["1", "机器人", "深圳市普渡科技有限公司", "https://www.pudurobotics.com", None, "配送机器人"]],
    )
    _write_workbook(
        supplement,
        [["1", "PCB", "深南电路股份有限公司", "https://www.scc.com.cn", None, "印制电路板"]],
    )

    result = build_company_release_from_sources(
        workbook_paths=[primary, supplement],
        now=TIMESTAMP,
    )

    assert result.report.input_record_count == 2
    assert result.report.released_record_count == 2
    names = {record.name for record in result.company_records}
    assert names == {"深圳市普渡科技有限公司", "深南电路股份有限公司"}


def test_build_company_release_from_sources_prefers_later_source_for_same_company(tmp_path: Path):
    primary = tmp_path / "primary.xlsx"
    supplement = tmp_path / "supplement.xlsx"
    _write_workbook(
        primary,
        [["1", "机器人", "深圳市普渡科技有限公司", None, None, "旧描述"]],
    )
    _write_workbook(
        supplement,
        [["1", "机器人", "普渡科技有限公司", "https://www.pudurobotics.com", None, "新描述"]],
    )

    result = build_company_release_from_sources(
        workbook_paths=[primary, supplement],
        now=TIMESTAMP,
    )

    assert result.report.input_record_count == 2
    assert result.report.released_record_count == 1
    record = result.company_records[0]
    assert record.name == "普渡科技有限公司"
    assert record.website == "https://www.pudurobotics.com"
    assert "新描述" in record.profile_summary
