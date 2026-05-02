from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from openpyxl import Workbook


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_patent_release_e2e.py"
)
_RUN_ID = "11111111-1111-1111-1111-111111111111"


class _Cursor:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _RecordingConn:
    def __init__(self):
        self.patents: dict[str, tuple] = {}
        self.links: dict[tuple[str, str, str], tuple] = {}
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def execute(self, sql: str, params=()):
        if "INSERT INTO pipeline_run" in sql:
            return _Cursor({"run_id": _RUN_ID})
        if "UPDATE pipeline_run" in sql:
            return _Cursor()
        if "INSERT INTO company_patent_link" in sql:
            key = (params[0], params[1], params[2])
            self.links[key] = params
            return _Cursor({"link_id": f"link-{len(self.links)}"})
        if "INSERT INTO patent" in sql:
            self.patents[params[0]] = params
            return _Cursor({"patent_id": params[0]})
        raise AssertionError(f"unexpected SQL: {sql}")

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "run_patent_release_e2e", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_company_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "sheet1"
    ws.append(["序号", "公司名称", "行业领域"])
    for index in range(15):
        ws.append([str(index + 1), f"深圳市公司{index}有限公司", "先进制造"])
    wb.save(path)


def _write_patent_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(
        [
            "序号",
            "标题 (中文)",
            "申请人",
            "公开（公告）号",
            "公开（公告）日",
            "申请日",
            "专利类型",
            "摘要 (中文)",
            "技术功效句",
        ]
    )
    for index in range(10):
        if index < 5:
            applicants = f"深圳市公司{index}有限公司; 深圳市公司{index + 10}有限公司"
        else:
            applicants = f"深圳市公司{index}有限公司"
        ws.append(
            [
                str(index + 1),
                f"测试专利{index}",
                applicants,
                f"CN10000000{index}A",
                "2026-06-01",
                "2026-05-01",
                "发明",
                f"测试专利{index}摘要",
                "提升测试覆盖率",
            ]
        )
    wb.save(path)


def test_run_patent_release_e2e_writes_patents_and_company_links_with_mock_pg(
    tmp_path: Path,
    monkeypatch,
):
    cli = _import_cli()
    conn = _RecordingConn()
    company_path = tmp_path / "companies.xlsx"
    patent_path = tmp_path / "patents.xlsx"
    report_path = tmp_path / "report.json"
    patent_output = tmp_path / "patent_records.jsonl"
    released_output = tmp_path / "released_objects.jsonl"
    _write_company_workbook(company_path)
    _write_patent_workbook(patent_path)

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_default_supplement_patent_inputs", lambda: [])

    result = cli.main(
        [
            "--company-input",
            str(company_path),
            "--patent-input",
            str(patent_path),
            "--patent-output",
            str(patent_output),
            "--released-output",
            str(released_output),
            "--report-output",
            str(report_path),
            "--database-url",
            "postgresql://fake/test",
            "--skip-llm",
        ]
    )

    assert result == 0
    assert len(conn.patents) == 10
    assert len(conn.links) == 15
    assert conn.committed is True
    assert conn.closed is True
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["postgres_write_summary"]["patents_written"] == 10
    assert payload["postgres_write_summary"]["company_patent_links_written"] == 15
