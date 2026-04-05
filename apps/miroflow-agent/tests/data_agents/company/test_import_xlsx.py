from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from src.data_agents.company.import_xlsx import import_company_xlsx


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def test_import_company_xlsx_detects_real_header_and_merges_continuation_rows():
    workbook_path = _repo_root() / "docs" / "专辑项目导出1768807339.xlsx"

    result = import_company_xlsx(workbook_path, sheet_name="sheet1")

    assert result.report.header_row_index == 2
    assert result.report.continuation_rows_merged >= 1

    xuhong = next(
        record for record in result.records if record.name == "深圳旭宏医疗科技有限公司"
    )
    assert xuhong.source_row_numbers == (4, 5)
    assert [event.round for event in xuhong.financing_events] == ["A轮", "Pre-A轮"]
    assert xuhong.investors == ("力合科创", "元真价值投资")


def test_import_company_xlsx_dedupes_on_normalized_name_and_keeps_most_complete_record(
    tmp_path: Path,
):
    workbook_path = tmp_path / "company_fixture.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "sheet1"

    ws.append(["专辑项目导出"])
    ws.append(["序号", "项目名称", "行业领域", "投资轮次", "投资时间", "投资金额", "投资方", "简介", "公司名称", "网址", "法人代表"])
    ws.append(
        [
            "1",
            "优必选",
            "机器人",
            "A轮",
            "2020.01.01",
            "1亿人民币",
            "投资方甲",
            "做人形机器人",
            "深圳市优必选科技股份有限公司",
            "https://www.ubtrobot.com",
            "周剑",
        ]
    )
    ws.append(
        [
            None,
            None,
            None,
            "Pre-A轮",
            "2019.01.01",
            "5000万人民币",
            "投资方乙",
            None,
            None,
            None,
            None,
        ]
    )
    ws.append(
        [
            "2",
            "优必选（重复）",
            None,
            None,
            None,
            None,
            None,
            None,
            "优必选科技股份有限公司",
            None,
            None,
        ]
    )
    wb.save(workbook_path)

    result = import_company_xlsx(workbook_path, sheet_name="sheet1")

    assert len(result.records) == 1
    record = result.records[0]
    assert record.name == "深圳市优必选科技股份有限公司"
    assert record.normalized_name == "优必选科技"
    assert record.source_row_numbers == (3, 4)
    assert record.investors == ("投资方甲", "投资方乙")
    assert [event.round for event in record.financing_events] == ["A轮", "Pre-A轮"]

    assert result.report.rows_read == 3
    assert result.report.company_rows_parsed == 2
    assert result.report.continuation_rows_merged == 1
    assert result.report.deduped_records == 1
    assert result.report.duplicate_groups == 1
    assert result.report.duplicate_records_discarded == 1


def test_import_company_xlsx_report_counts_are_consistent(tmp_path: Path):
    workbook_path = tmp_path / "report_fixture.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "sheet1"
    ws.append(["专辑项目导出"])
    ws.append(["序号", "行业领域", "公司名称"])
    ws.append(["1", "先进制造", "深圳市星火半导体科技有限公司"])
    ws.append(["2", "先进制造", "星火半导体科技有限公司"])
    wb.save(workbook_path)

    result = import_company_xlsx(workbook_path)

    assert result.report.company_rows_parsed == 2
    assert result.report.deduped_records == 1
    assert result.report.duplicate_records_discarded == (
        result.report.company_rows_parsed - result.report.deduped_records
    )
