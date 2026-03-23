from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

from company_data_agent.ingest import MasterListParser


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_xlsx(path: Path, headers: list[str], rows: list[list[str | None]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_parser_accepts_csv_and_preserves_extra_columns(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_csv(
        source,
        [
            {
                "企业名称": "深圳未来机器人有限公司",
                "统一社会信用代码": "91440300MA5FUTURE1",
                "注册地址": "深圳市南山区",
                "行业分类": "机器人",
                "企业状态": "存续",
            },
            {
                "企业名称": "深圳智算科技有限公司",
                "统一社会信用代码": "91440300MA5INTELAI",
                "注册地址": "深圳市福田区",
                "行业分类": "人工智能",
                "企业状态": "存续",
            },
        ],
    )

    result = MasterListParser().parse(source)

    assert len(result.rows) == 2
    assert not result.errors
    assert result.rows[0].name == "深圳未来机器人有限公司"
    assert result.rows[0].credit_code == "91440300MA5FUTURE1"
    assert result.rows[0].registered_address == "深圳市南山区"
    assert result.rows[0].industry == "机器人"
    assert result.rows[0].extra_columns == {"企业状态": "存续"}


def test_parser_accepts_xlsx_and_skips_blank_rows(tmp_path: Path) -> None:
    source = tmp_path / "companies.xlsx"
    write_xlsx(
        source,
        ["公司名称", "信用代码", "地址", "行业"],
        [
            ["深圳未来机器人有限公司", "91440300MA5FUTURE1", "深圳市南山区", "机器人"],
            [None, None, None, None],
            ["深圳智算科技有限公司", "91440300MA5INTELAI", "深圳市福田区", "人工智能"],
        ],
    )

    result = MasterListParser().parse(source)

    assert len(result.rows) == 2
    assert result.rows[0].row_number == 2
    assert result.rows[1].row_number == 4
    assert not result.errors


def test_parser_surfaces_row_level_errors_without_aborting_valid_rows(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_csv(
        source,
        [
            {
                "企业名称": "深圳未来机器人有限公司",
                "统一社会信用代码": "91440300MA5FUTURE1",
                "注册地址": "深圳市南山区",
                "行业分类": "机器人",
            },
            {
                "企业名称": "",
                "统一社会信用代码": "91440300MA5BROKEN01",
                "注册地址": "深圳市宝安区",
                "行业分类": "制造业",
            },
            {
                "企业名称": "深圳智算科技有限公司",
                "统一社会信用代码": "91440300MA5INTELAI",
                "注册地址": "深圳市福田区",
                "行业分类": "人工智能",
            },
        ],
    )

    result = MasterListParser().parse(source)

    assert [row.name for row in result.rows] == [
        "深圳未来机器人有限公司",
        "深圳智算科技有限公司",
    ]
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 3
    assert "missing required columns: name" == result.errors[0].message


def test_parser_produces_stable_normalized_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_csv(
        source,
        [
            {
                "name": "Shenzhen Future Robotics Co., Ltd.",
                "credit_code": "91440300MA5FUTURE1",
                "registered_address": "Nanshan, Shenzhen",
                "industry": "Robotics",
                "notes": "priority",
            }
        ],
    )

    result = MasterListParser().parse(source)

    snapshot = [
        {
            "row_number": row.row_number,
            "name": row.name,
            "credit_code": row.credit_code,
            "registered_address": row.registered_address,
            "industry": row.industry,
            "extra_columns": row.extra_columns,
        }
        for row in result.rows
    ]

    assert snapshot == [
        {
            "row_number": 2,
            "name": "Shenzhen Future Robotics Co., Ltd.",
            "credit_code": "91440300MA5FUTURE1",
            "registered_address": "Nanshan, Shenzhen",
            "industry": "Robotics",
            "extra_columns": {"notes": "priority"},
        }
    ]


def test_parser_rejects_unsupported_file_format(tmp_path: Path) -> None:
    source = tmp_path / "companies.json"
    source.write_text("[]", encoding="utf-8")

    try:
        MasterListParser().parse(source)
    except ValueError as exc:
        assert "unsupported master list format" in str(exc)
    else:
        raise AssertionError("expected unsupported format to raise ValueError")
