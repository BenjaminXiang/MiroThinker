"""CLI tests for scripts/run_homepage_patent_ingest.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_homepage_patent_ingest.py"
)


def _import_cli_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_homepage_patent_ingest", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(**overrides):
    from src.data_agents.patent.homepage_ingest import PatentIngestReport

    values = {
        "run_id": UUID("00000000-0000-0000-0000-000000000000"),
        "profs_total": 1,
        "profs_processed": 1,
        "profs_skipped": 0,
        "patents_upserted_total": 0,
        "patents_skipped_no_id_total": 0,
        "links_written_total": 0,
        "pipeline_issues_filed": 0,
        "run_duration_seconds": 0.0,
    }
    values.update(overrides)
    return PatentIngestReport(**values)


def test_cli_help_exits_zero(capsys):
    with _patch_argv(["run_homepage_patent_ingest.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli_module()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--dry-run" in captured.out
    assert "--prof-id" in captured.out
    assert "--institution" in captured.out


def test_cli_dispatches_dry_run_and_prof_id(monkeypatch):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        return _report()

    monkeypatch.setattr(cli, "run_homepage_patent_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(
        [
            "run_homepage_patent_ingest.py",
            "--dry-run",
            "--prof-id",
            "PROF-1",
            "--limit",
            "1",
        ]
    ):
        assert cli.main() == 0

    assert called_kwargs["dry_run"] is True
    assert called_kwargs["prof_id"] == "PROF-1"
    assert called_kwargs["limit"] == 1


def test_cli_commits_after_successful_non_dry_run(monkeypatch):
    cli = _import_cli_module()
    conn = MagicMock()

    monkeypatch.setattr(cli, "run_homepage_patent_ingest", lambda conn, **kw: _report())
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: conn)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_homepage_patent_ingest.py", "--limit", "1"]):
        assert cli.main() == 0

    conn.commit.assert_called_once()


def test_cli_prints_report_as_json(monkeypatch, capsys):
    cli = _import_cli_module()

    monkeypatch.setattr(
        cli,
        "run_homepage_patent_ingest",
        lambda conn, **kw: _report(patents_upserted_total=2, links_written_total=2),
    )
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_homepage_patent_ingest.py", "--dry-run"]):
        assert cli.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["patents_upserted_total"] == 2
    assert payload["links_written_total"] == 2


def test_cli_missing_database_url_exits_nonzero(monkeypatch, capsys):
    cli = _import_cli_module()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with _patch_argv(["run_homepage_patent_ingest.py", "--limit", "1"]):
        with pytest.raises(SystemExit) as exc:
            cli.main()

    assert exc.value.code != 0
    assert "DATABASE_URL is required" in capsys.readouterr().err


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
