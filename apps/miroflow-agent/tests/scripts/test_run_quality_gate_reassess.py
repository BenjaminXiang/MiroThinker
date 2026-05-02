from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_quality_gate_reassess.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_quality_gate_reassess", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_help(capsys):
    with _patch_argv(["run_quality_gate_reassess.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--limit" in captured.out
    assert "--dry-run" in captured.out


def test_build_select_sql_scans_ready_professors():
    cli = _import_cli()
    sql, params = cli._build_select_sql(limit=5)

    assert "p.quality_status = 'ready'" in sql
    assert "LIMIT %s" in sql
    assert params == (5,)


def test_decide_reassess_demotes_short_summary():
    cli = _import_cli()
    decision = cli._decide_reassess(
        {
            "professor_id": "PROF-1",
            "canonical_name": "张三",
            "institution": "南方科技大学",
            "profile_url": "https://faculty.sustech.edu.cn/zhangsan",
            "profile_summary": "张三是教授。",
        }
    )

    assert decision.should_demote is True
    assert decision.failure_code == "profile_summary_too_short"


def test_cli_dry_run_reports_demotions_without_writes(monkeypatch, capsys):
    cli = _import_cli()
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "professor_id": "PROF-1",
            "canonical_name": "张三",
            "institution": "南方科技大学",
            "profile_url": "https://faculty.sustech.edu.cn/zhangsan",
            "profile_summary": "张三是教授。",
        }
    ]
    conn.execute.return_value = cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_quality_gate_reassess.py", "--dry-run", "--limit", "1"]):
        cli.main()

    sqls = [call.args[0] for call in conn.execute.call_args_list if call.args]
    assert not any(isinstance(sql, str) and "UPDATE professor" in sql for sql in sqls)
    report = json.loads(capsys.readouterr().out)
    assert report["profs_demoted"] == 1
    assert report["dry_run"] is True


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    with _patch_argv(["run_quality_gate_reassess.py", "--limit", "1"]):
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
