from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_paper_summary_zh_backfill.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_paper_summary_zh_backfill", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_help(capsys):
    with _patch_argv(["run_paper_summary_zh_backfill.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--limit" in captured.out
    assert "--only-missing" in captured.out
    assert "--all" in captured.out
    assert "--dry-run" in captured.out


def test_build_select_sql_only_missing_default():
    cli = _import_cli()
    args = cli._parse_args([])
    sql, params = cli._build_select_sql(only_missing=args.only_missing, limit=5)

    assert args.only_missing is True
    assert "p.abstract_clean IS NOT NULL" in sql
    assert "p.summary_zh IS NULL" in sql
    assert params == (5,)


def test_build_select_sql_all_disables_summary_filter():
    cli = _import_cli()
    args = cli._parse_args(["--all"])
    sql, _params = cli._build_select_sql(
        only_missing=args.only_missing,
        limit=None,
    )

    assert "p.summary_zh IS NULL" not in sql


def test_cli_dry_run_dispatches_without_paper_update(monkeypatch, tmp_path, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-1",
            "title_clean": "A paper",
            "title_raw": None,
            "abstract_clean": "This paper proposes a robust model for scientific discovery.",
            "summary_zh": None,
        }
    ]
    conn.execute.return_value = select_cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: tmp_path / "run.jsonl"
    )
    monkeypatch.setattr(cli, "translate_abstract_to_zh", lambda *_a, **_kw: "中" * 220)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_paper_summary_zh_backfill.py", "--dry-run", "--limit", "1"]):
        cli.main()

    sqls = [call.args[0] for call in conn.execute.call_args_list if call.args]
    assert not any(isinstance(sql, str) and "UPDATE paper" in sql for sql in sqls)
    report = json.loads(capsys.readouterr().out)
    assert report["summaries_written"] == 1
    assert report["dry_run"] is True


def test_cli_skips_already_chinese_abstract(monkeypatch, tmp_path):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-1",
            "title_clean": "中文论文",
            "title_raw": None,
            "abstract_clean": "本文提出一种用于智能制造质量检测的深度学习方法，能够提升缺陷识别准确率。",
            "summary_zh": None,
        }
    ]
    conn.execute.return_value = select_cursor
    translator = MagicMock()
    checkpoint = tmp_path / "run.jsonl"

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        cli, "_resolve_checkpoint_path", lambda _resume, _run_id: checkpoint
    )
    monkeypatch.setattr(cli, "translate_abstract_to_zh", translator)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_paper_summary_zh_backfill.py", "--dry-run", "--limit", "1"]):
        cli.main()

    translator.assert_not_called()
    rows = [
        json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [{"paper_id": "PAPER-1", "status": "skipped_already_zh"}]


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    with _patch_argv(["run_paper_summary_zh_backfill.py", "--limit", "1"]):
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
