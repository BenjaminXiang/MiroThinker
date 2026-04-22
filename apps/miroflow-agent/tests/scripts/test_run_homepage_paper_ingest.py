"""RED-phase tests for M2.4 Unit 7 — CLI entrypoint.

Thin argparse shell over run_homepage_paper_ingest. Tests cover flag parsing,
dispatch to orchestrator, and DATABASE_URL env handling.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the script as a module — scripts/ needs to be importable.
_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_homepage_paper_ingest.py"
)


def _import_cli_module():
    """Load scripts/run_homepage_paper_ingest.py as a module for testing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_homepage_paper_ingest", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_help_exits_zero(capsys):
    """--help emits usage and exits 0."""
    with patch.object(sys, "argv", ["run_homepage_paper_ingest.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli_module()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--dry-run" in captured.out
    assert "--limit" in captured.out


def test_cli_dispatches_dry_run_flag(monkeypatch, tmp_path):
    """--dry-run parses and dispatches with dry_run=True."""
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--dry-run",
            "--limit",
            "5",
        ],
    )
    cli.main()
    assert called_kwargs.get("dry_run") is True
    assert called_kwargs.get("limit") == 5


def test_cli_dispatches_institution_filter(monkeypatch, tmp_path):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--institution",
            "南方科技大学",
            "--dry-run",
        ],
    )
    cli.main()
    assert called_kwargs.get("institution") == "南方科技大学"


def test_cli_dispatches_resume_flag_with_explicit_path(monkeypatch, tmp_path):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_run(conn, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=0,
            profs_processed=0,
            profs_skipped=0,
            papers_linked_total=0,
            full_text_fetched_total=0,
            pipeline_issues_filed=0,
            run_duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    explicit = tmp_path / "my_checkpoint.jsonl"
    explicit.write_text("")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_homepage_paper_ingest.py",
            "--dry-run",
            "--resume",
            str(explicit),
        ],
    )
    cli.main()
    assert called_kwargs.get("resume_checkpoint_path") == explicit


def test_cli_missing_database_url_exits_nonzero(monkeypatch, capsys):
    """No DATABASE_URL env in non-dry-run → exit 1 with clear message."""
    cli = _import_cli_module()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_homepage_paper_ingest.py", "--limit", "1"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code != 0


def test_cli_prints_ingest_report_as_json(monkeypatch, capsys, tmp_path):
    cli = _import_cli_module()

    def _fake_run(conn, **kwargs):
        from src.data_agents.paper.homepage_ingest import IngestReport
        from uuid import UUID

        return IngestReport(
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            profs_total=10,
            profs_processed=8,
            profs_skipped=2,
            papers_linked_total=42,
            full_text_fetched_total=30,
            pipeline_issues_filed=1,
            run_duration_seconds=99.5,
        )

    monkeypatch.setattr(cli, "run_homepage_paper_ingest", _fake_run)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(sys, "argv", ["run_homepage_paper_ingest.py", "--dry-run"])
    cli.main()
    captured = capsys.readouterr()
    import json

    # Script output must include a JSON blob with the report fields.
    found_json = False
    for line in captured.out.splitlines():
        try:
            payload = json.loads(line)
            if isinstance(payload, dict) and payload.get("papers_linked_total") == 42:
                found_json = True
                assert payload["profs_processed"] == 8
                assert payload["pipeline_issues_filed"] == 1
                break
        except (json.JSONDecodeError, TypeError):
            continue
    assert found_json, f"expected JSON report in output, got: {captured.out!r}"
