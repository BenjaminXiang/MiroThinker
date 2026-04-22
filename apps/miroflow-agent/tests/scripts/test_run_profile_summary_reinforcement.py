"""RED-phase tests for M6 Unit 2 — profile summary reinforcement CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_profile_summary_reinforcement.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_profile_summary_reinforcement", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_help(capsys):
    with _patch_argv(["run_profile_summary_reinforcement.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--limit" in captured.out
    assert "--dry-run" in captured.out
    assert "--only-missing" in captured.out or "--all" in captured.out


def test_cli_dry_run_dispatches_without_writes(monkeypatch):
    cli = _import_cli()

    # Two sample profs returned by SELECT.
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "professor_id": "prof-1",
            "canonical_name": "王教授",
            "institution": "南方科技大学",
            "research_directions": ["机器人"],
            "profile_summary": None,
            "profile_raw_text": "bio 1",
        },
    ]
    # Paper-context JOIN query returns empty.
    cursor.fetchall.side_effect = [
        [
            {
                "professor_id": "prof-1",
                "canonical_name": "王教授",
                "institution": "南方科技大学",
                "research_directions": ["机器人"],
                "profile_summary": None,
                "profile_raw_text": "bio 1",
            }
        ],
        [],  # paper contexts for prof-1 — empty
    ]
    conn.execute.return_value = cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda url: conn)

    llm = MagicMock()
    msg = MagicMock()
    msg.content = "教授研究机器人控制。" * 30
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    llm.chat.completions.create.return_value = resp
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (llm, "gemma-4-26b-a4b-it", {}))

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    with _patch_argv(
        [
            "run_profile_summary_reinforcement.py",
            "--dry-run",
            "--limit",
            "1",
        ]
    ):
        cli.main()

    # No UPDATE statement should have been executed in dry-run.
    sqls = [c.args[0] for c in conn.execute.call_args_list if c.args]
    update_sqls = [s for s in sqls if isinstance(s, str) and "UPDATE professor" in s.upper()]
    assert update_sqls == []


def test_cli_only_missing_filter_by_default(monkeypatch):
    cli = _import_cli()
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.execute.return_value = cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "model", {}))
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    with _patch_argv(
        ["run_profile_summary_reinforcement.py", "--dry-run", "--limit", "1"]
    ):
        cli.main()

    sqls = [c.args[0] for c in conn.execute.call_args_list if c.args and isinstance(c.args[0], str)]
    select_sqls = [s for s in sqls if "SELECT" in s.upper() and "professor" in s.lower()]
    # --only-missing default: filter clause should be in the SELECT.
    assert any(
        "profile_summary IS NULL" in s or "length(profile_summary)" in s.lower()
        for s in select_sqls
    )


def test_cli_all_disables_filter(monkeypatch):
    cli = _import_cli()
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn.execute.return_value = cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "model", {}))
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    with _patch_argv(
        ["run_profile_summary_reinforcement.py", "--dry-run", "--all", "--limit", "1"]
    ):
        cli.main()

    sqls = [c.args[0] for c in conn.execute.call_args_list if c.args and isinstance(c.args[0], str)]
    select_sqls = [s for s in sqls if "SELECT" in s.upper() and "professor" in s.lower()]
    # --all: filter clause must NOT appear.
    assert not any(
        "profile_summary IS NULL" in s or "length(profile_summary)" in s.lower()
        for s in select_sqls
    )


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    with _patch_argv(["run_profile_summary_reinforcement.py", "--limit", "1"]):
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
