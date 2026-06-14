from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.company.models import CompanyImportRecord

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_company_enrichment_e2e.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_company_enrichment_e2e", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_e2e_report_covers_release_key_people_yiou_and_product_fixtures():
    cli = _import_cli()
    records = [
        CompanyImportRecord(
            name="深圳示例科技有限公司",
            normalized_name="示例科技",
            credit_code="91440300MA5EXAMPLE",
            industry="人工智能",
            legal_representative="张三",
            registered_capital="100万人民币",
            website="https://example.com",
            team_raw=(
                "张三，职务：CEO，介绍：张三，本科毕业于斯坦福大学，"
                "曾任谷歌算法负责人。"
            ),
            patent_count=3,
            source_row_numbers=(2,),
        )
    ]

    report = cli._build_e2e_report(
        records=records,
        source_file=Path("docs/专辑项目导出1768807339.xlsx"),
        now=datetime(2026, 5, 27, tzinfo=timezone.utc),
        live=False,
    )

    assert report["deterministic_status"] == "passed"
    assert report["import"]["company_rows_parsed"] == 1
    assert report["release"]["released_record_count"] == 1
    assert report["optional_field_coverage"]["credit_code"] == 1
    assert report["key_person_coverage"]["with_description"] == 1
    assert report["key_person_coverage"]["with_education"] == 1
    assert report["key_person_coverage"]["with_work_experience"] == 1
    assert report["fixture_checks"]["iyiou_adapter"]["records"] == 1
    assert report["fixture_checks"]["official_product_capture"]["products"] == 1
    assert report["live_checks"]["status"] == "skipped"


def test_parse_args_defaults_to_real_xlsx():
    cli = _import_cli()

    args = cli._parse_args([])

    assert args.input.name == "专辑项目导出1768807339.xlsx"
    assert args.live is False
    assert args.live_limit == 20


def test_parse_args_accepts_live_limit():
    cli = _import_cli()

    args = cli._parse_args(["--live", "--live-limit", "5"])

    assert args.live is True
    assert args.live_limit == 5


def test_build_live_yiou_context_uses_xlsx_description_team_and_project():
    cli = _import_cli()
    record = CompanyImportRecord(
        name="深圳市示例机器人有限公司",
        normalized_name="示例机器人",
        project_name="ExampleBot",
        description="公司简称ExampleBot，专注具身智能机器人。",
        team_raw="张三，职务：创始人，介绍：曾负责机器人产品研发。",
    )

    context = cli._build_yiou_live_context(record)

    assert context.company_name == "深圳市示例机器人有限公司"
    assert context.normalized_name == "示例机器人"
    assert context.project_name == "ExampleBot"
    assert context.description == "公司简称ExampleBot，专注具身智能机器人。"
    assert context.team_raw == "张三，职务：创始人，介绍：曾负责机器人产品研发。"


def test_main_runs_live_checks_once_with_requested_limit(tmp_path, monkeypatch, capsys):
    cli = _import_cli()
    input_path = tmp_path / "companies.xlsx"
    input_path.write_bytes(b"placeholder")
    output_path = tmp_path / "report.json"
    calls: list[int] = []

    class _Report:
        sheet_name = "sheet1"
        rows_read = 1
        company_rows_parsed = 1
        deduped_records = 1

    class _ImportResult:
        records = [
            CompanyImportRecord(
                name="深圳示例科技有限公司",
                normalized_name="示例科技",
                industry="人工智能",
            )
        ]
        report = _Report()

    monkeypatch.setattr(cli, "import_company_xlsx", lambda *_args, **_kwargs: _ImportResult())
    monkeypatch.setattr(
        cli,
        "_run_live_checks",
        lambda _records, *, limit: calls.append(limit) or {"status": "passed"},
    )

    exit_code = cli.main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--live",
            "--live-limit",
            "2",
        ]
    )

    assert exit_code == 0
    assert calls == [2]
    assert output_path.exists()
    assert not capsys.readouterr().err
