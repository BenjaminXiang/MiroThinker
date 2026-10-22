from __future__ import annotations

import io

from openpyxl import Workbook

from backend.services.excel_structure import analyze_workbook, iter_structured_rows


def _workbook(headers: list[str], rows: list[list[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_detects_company_columns_and_rows() -> None:
    data = _workbook(
        ["公司名称", "统一社会信用代码", "网址", "简介"],
        [["深圳测试科技有限公司", "91440300TEST", "https://a.example.com", "机器人"]],
    )

    analysis = analyze_workbook(data)

    assert analysis.best.domain == "company"
    assert analysis.best.confidence == "high"
    fields = {item.field for item in analysis.best.mapping}
    assert {"company_name", "credit_code", "website", "description"} <= fields
    row = next(iter(iter_structured_rows(analysis.best, data)))
    assert row["company_name"] == "深圳测试科技有限公司"
    assert row["website"] == "https://a.example.com"


def test_detects_professor_patent_and_paper() -> None:
    professor = analyze_workbook(
        _workbook(
            ["姓名", "学校", "院系", "邮箱", "研究方向"],
            [["张三", "南方科技大学", "计算机系", "z@example.com", "机器人"]],
        )
    )
    patent = analyze_workbook(
        _workbook(
            ["专利名称", "专利号", "申请人", "申请日"],
            [["一种关节", "CN20240001", "深圳测试科技有限公司", "2024-01-02"]],
        )
    )
    paper = analyze_workbook(
        _workbook(
            ["论文标题", "DOI", "年份", "作者"],
            [["Robot Learning", "10.1000/xyz", "2024", "张三, 李四"]],
        )
    )

    assert professor.best.domain == "professor"
    assert patent.best.domain == "patent"
    assert paper.best.domain == "paper"


def test_unmatched_columns_do_not_shift_values() -> None:
    data = _workbook(
        ["序号", "公司名称", "备注", "网址"],
        [[1, "深圳测试科技有限公司", "x", "https://a.example.com"]],
    )

    analysis = analyze_workbook(data)
    row = next(iter(iter_structured_rows(analysis.best, data)))

    assert row["company_name"] == "深圳测试科技有限公司"
    assert row["website"] == "https://a.example.com"
