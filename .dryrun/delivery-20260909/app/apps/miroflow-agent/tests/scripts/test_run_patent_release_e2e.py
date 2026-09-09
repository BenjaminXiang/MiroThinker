from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from openpyxl import Workbook


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_patent_release_e2e.py"
)


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
    ws.append(["1", "深圳市测试科技有限公司", "先进制造"])
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
        ]
    )
    ws.append(
        [
            "1",
            "测试专利",
            "深圳市测试科技有限公司",
            "CN100000001A",
            "2026-06-01",
            "2026-05-01",
            "发明",
            "测试摘要",
        ]
    )
    wb.save(path)


def test_run_patent_release_e2e_emits_jsonl_without_postgres(
    tmp_path: Path,
    monkeypatch,
):
    cli = _import_cli()
    company_path = tmp_path / "companies.xlsx"
    patent_path = tmp_path / "patents.xlsx"
    report_path = tmp_path / "report.json"
    patent_output = tmp_path / "patent_records.jsonl"
    released_output = tmp_path / "released_objects.jsonl"
    _write_company_workbook(company_path)
    _write_patent_workbook(patent_path)
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
            "--skip-postgres",
            "--skip-llm",
        ]
    )

    assert result == 0
    assert len(patent_output.read_text(encoding="utf-8").splitlines()) == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["postgres_write_summary"]["status"] == "skipped"
