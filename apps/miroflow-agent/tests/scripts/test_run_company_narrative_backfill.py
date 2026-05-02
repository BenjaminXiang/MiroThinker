from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_company_narrative_backfill.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_company_narrative_backfill", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_help(capsys):
    with _patch_argv(["run_company_narrative_backfill.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--limit" in captured.out
    assert "--only-missing" in captured.out
    assert "--all" in captured.out


def test_build_select_sql_only_missing_default():
    cli = _import_cli()
    args = cli._parse_args([])
    sql, params = cli._build_select_sql(only_missing=args.only_missing, limit=5)

    assert args.only_missing is True
    assert "c.profile_summary IS NULL" in sql
    assert "c.technology_route_summary IS NULL" in sql
    assert "LEFT JOIN LATERAL" in sql
    assert params == (5,)


def test_build_select_sql_all_disables_filter():
    cli = _import_cli()
    args = cli._parse_args(["--all"])
    sql, _params = cli._build_select_sql(only_missing=args.only_missing, limit=None)

    assert "c.profile_summary IS NULL" not in sql
    assert "c.technology_route_summary IS NULL" not in sql


def test_cli_dry_run_dispatches_without_company_update(monkeypatch, tmp_path):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "company_id": "COMP-1",
            "canonical_name": "深圳示例科技",
            "industry": "机器人",
            "hq_city": "深圳",
            "description": "深圳示例科技专注智能机器人和行业自动化解决方案。" * 4,
        }
    ]
    conn.execute.return_value = select_cursor

    result = cli.NarrativeResult(
        profile_summary="企" * 220,
        technology_route_summary="技" * 360,
        error=None,
    )

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(cli, "generate_company_narrative", lambda **_kwargs: result)
    monkeypatch.setattr(cli, "open_pipeline_run", lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, "_resolve_checkpoint_path", lambda _resume, _run_id: tmp_path / "run.jsonl")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_company_narrative_backfill.py", "--dry-run", "--limit", "1"]):
        cli.main()

    sqls = [call.args[0] for call in conn.execute.call_args_list if call.args]
    assert not any(isinstance(sql, str) and "UPDATE company" in sql for sql in sqls)


def test_cli_skips_short_description(monkeypatch, tmp_path):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "company_id": "COMP-1",
            "canonical_name": "深圳示例科技",
            "industry": "机器人",
            "hq_city": "深圳",
            "description": "太短",
        }
    ]
    conn.execute.return_value = select_cursor
    generator = MagicMock()

    checkpoint = tmp_path / "run.jsonl"
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(cli, "generate_company_narrative", generator)
    monkeypatch.setattr(cli, "open_pipeline_run", lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, "_resolve_checkpoint_path", lambda _resume, _run_id: checkpoint)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_company_narrative_backfill.py", "--dry-run", "--limit", "1"]):
        cli.main()

    generator.assert_not_called()
    rows = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"company_id": "COMP-1", "status": "skipped_short_input"}]


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    with _patch_argv(["run_company_narrative_backfill.py", "--limit", "1"]):
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
