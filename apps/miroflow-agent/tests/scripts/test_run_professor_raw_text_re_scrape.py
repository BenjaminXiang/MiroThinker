from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_professor_raw_text_re_scrape.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_professor_raw_text_re_scrape", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_help(capsys):
    with _patch_argv(["run_professor_raw_text_re_scrape.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--limit" in captured.out
    assert "--resume" in captured.out
    assert "--dry-run" in captured.out


def test_build_select_sql_limits_professors():
    cli = _import_cli()
    sql, params = cli._build_select_sql(limit=3)

    assert "primary_official_profile_page_id" in sql
    assert "p.identity_status = 'resolved'" in sql
    assert "LIMIT %s" in sql
    assert params == (3,)


def test_build_select_sql_can_filter_missing_raw_text():
    cli = _import_cli()
    sql, params = cli._build_select_sql(limit=3, missing_raw_only=True)

    assert "p.profile_raw_text IS NULL" in sql
    assert "length(trim(p.profile_raw_text)) = 0" in sql
    assert params == (3,)


def test_should_process_row_filters_summary_valid_rows():
    cli = _import_cli()
    valid_summary = (
        "张三现任深圳大学教授，主要从事人工智能、机器学习与医学影像分析研究，"
        "关注算法可靠性、临床场景验证和多模态数据建模。其工作围绕智能诊断、"
        "影像分割和疾病风险评估展开，结合公开发表论文与团队项目积累，形成面向"
        "医疗应用的技术路线。相关研究强调模型解释性、数据质量和跨学科合作，"
        "为医学人工智能系统落地提供方法支持。近年来还参与科研项目和学生培养，"
        "持续推动算法在真实临床数据中的评估、优化与转化，并重视与医院、工程团队"
        "之间的协同验证。"
    )

    assert cli._should_process_row(
        {"profile_summary": valid_summary}, summary_invalid_only=True
    ) is False
    assert cli._should_process_row(
        {"profile_summary": "Too short"}, summary_invalid_only=True
    ) is True


def test_raw_text_quality_guard_requires_person_name_anchor():
    cli = _import_cli()
    assert (
        cli._raw_text_passes_quality_guard(
            {
                "canonical_name": "张三",
                "profile_url": "https://faculty.example.edu/zhangsan",
            },
            "这是张三教授的个人主页，研究方向包括人工智能。" * 10,
            min_length=120,
            identity_guard=True,
        )
        is True
    )
    assert (
        cli._raw_text_passes_quality_guard(
            {
                "canonical_name": "张三",
                "profile_url": "https://faculty.example.edu/zhangsan",
            },
            "这是学院新闻页面，主要介绍科研平台和通知公告。" * 10,
            min_length=120,
            identity_guard=True,
        )
        is False
    )
    assert (
        cli._raw_text_passes_quality_guard(
            {
                "canonical_name": "科研方向",
                "profile_url": "https://faculty.example.edu/research",
            },
            "科研方向栏目介绍学院平台。" * 20,
            min_length=120,
            identity_guard=True,
        )
        is False
    )


def test_scrape_raw_text_combines_primary_and_supplementary(monkeypatch):
    cli = _import_cli()
    html = "<html><body><h1>张三</h1><p>Primary bio text.</p></body></html>"
    monkeypatch.setattr(cli, "_fetch_html", lambda _url, _timeout: html)
    monkeypatch.setattr(
        cli,
        "follow_supplementary_links",
        lambda *_a, **_kw: ["Source: https://lab.example.edu\nSupplementary lab text."],
    )

    raw_text, supplementary_count = cli._scrape_raw_text(
        {
            "professor_id": "PROF-1",
            "canonical_name": "张三",
            "profile_url": "https://faculty.example.edu/prof.html",
        }
    )

    assert "Primary bio text" in raw_text
    assert "Supplementary lab text" in raw_text
    assert supplementary_count == 1


def test_cli_dry_run_dispatches_without_update(monkeypatch, tmp_path, capsys):
    cli = _import_cli()
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "professor_id": "PROF-1",
            "canonical_name": "张三",
            "profile_raw_text": None,
            "profile_url": "https://faculty.example.edu/prof.html",
        }
    ]
    conn.execute.return_value = cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: tmp_path / "run.jsonl"
    )
    monkeypatch.setattr(cli, "_scrape_raw_text", lambda _row: ("raw text", 1))
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(
        ["run_professor_raw_text_re_scrape.py", "--dry-run", "--limit", "1"]
    ):
        cli.main()

    sqls = [call.args[0] for call in conn.execute.call_args_list if call.args]
    assert not any(isinstance(sql, str) and "UPDATE professor" in sql for sql in sqls)
    report = json.loads(capsys.readouterr().out)
    assert report["raw_text_written"] == 1
    assert report["supplementary_segments"] == 1


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    with _patch_argv(["run_professor_raw_text_re_scrape.py", "--limit", "1"]):
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code != 0


class _patch_argv:
    def __init__(self, argv):
        self.argv = argv
        self._saved = None

    def __enter__(self):
        self._saved = sys.argv
        sys.argv = self.argv
        return self

    def __exit__(self, *exc):
        sys.argv = self._saved
