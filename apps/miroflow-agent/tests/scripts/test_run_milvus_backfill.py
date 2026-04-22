"""RED-phase tests for M3 Unit 3 — run_milvus_backfill.py CLI shell."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "run_milvus_backfill.py"


def _import_cli_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_milvus_backfill", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_help_exits_zero(capsys):
    with patch_argv(["run_milvus_backfill.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli_module()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--domain" in captured.out
    assert "--limit" in captured.out
    assert "--batch-size" in captured.out
    assert "--resume" in captured.out


def test_cli_dispatches_paper_domain(monkeypatch, tmp_path):
    cli = _import_cli_module()
    called_kwargs: dict = {}

    def _fake_backfill(conn, milvus, embed, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.milvus_backfill import BackfillReport

        return BackfillReport(
            papers_total=0,
            papers_processed=0,
            papers_skipped=0,
            chunks_inserted=0,
            papers_with_errors=0,
            duration_seconds=0.0,
        )

    monkeypatch.setattr(cli, "backfill_paper_chunks", _fake_backfill)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setattr(cli, "_open_milvus_client", lambda uri: MagicMock())
    monkeypatch.setattr(cli, "_open_embedding_client", lambda: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_milvus_backfill.py",
            "--domain",
            "paper",
            "--limit",
            "10",
            "--batch-size",
            "8",
            "--milvus-uri",
            ":memory:",
        ],
    )
    cli.main()
    assert called_kwargs.get("limit") == 10
    assert called_kwargs.get("batch_size") == 8


def test_cli_dispatches_professor_domain(monkeypatch):
    """--domain professor invokes professor backfill path (mocked)."""
    cli = _import_cli_module()
    # The professor backfill path is implementation-dependent. The test's contract
    # is merely that the CLI routes to a distinct handler for --domain professor
    # AND does not dispatch the paper backfill when domain=professor.
    paper_called = []

    def _fake_paper_backfill(*args, **kwargs):
        paper_called.append(1)
        from src.data_agents.paper.milvus_backfill import BackfillReport

        return BackfillReport(0, 0, 0, 0, 0, 0.0)

    monkeypatch.setattr(cli, "backfill_paper_chunks", _fake_paper_backfill)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setattr(cli, "_open_milvus_client", lambda uri: MagicMock())
    monkeypatch.setattr(cli, "_open_embedding_client", lambda: MagicMock())
    # Professor backfill dispatches to a function in the professor module;
    # patch a generic "_backfill_professor_domain" hook if present.
    if hasattr(cli, "_backfill_professor_domain"):
        prof_called = []

        def _fake_prof(*args, **kwargs):
            prof_called.append(1)
            from src.data_agents.paper.milvus_backfill import BackfillReport

            return BackfillReport(0, 0, 0, 0, 0, 0.0)

        monkeypatch.setattr(cli, "_backfill_professor_domain", _fake_prof)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_milvus_backfill.py",
            "--domain",
            "professor",
            "--milvus-uri",
            ":memory:",
        ],
    )
    cli.main()
    # Paper backfill must NOT have been called.
    assert paper_called == []


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli_module()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_milvus_backfill.py", "--domain", "paper", "--milvus-uri", ":memory:"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code != 0


def test_cli_resume_with_corrupt_line(monkeypatch, tmp_path):
    cli = _import_cli_module()
    ckpt = tmp_path / "resume.jsonl"
    ckpt.write_text(
        '{"paper_id": "p_ok"}\n'
        "not valid json\n"
        '{"paper_id": "p_ok2"}\n'
    )
    called_kwargs: dict = {}

    def _fake_backfill(conn, milvus, embed, **kwargs):
        called_kwargs.update(kwargs)
        from src.data_agents.paper.milvus_backfill import BackfillReport

        return BackfillReport(0, 0, 0, 0, 0, 0.0)

    monkeypatch.setattr(cli, "backfill_paper_chunks", _fake_backfill)
    monkeypatch.setattr(cli, "_open_database_connection", lambda url: MagicMock())
    monkeypatch.setattr(cli, "_open_milvus_client", lambda uri: MagicMock())
    monkeypatch.setattr(cli, "_open_embedding_client", lambda: MagicMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_milvus_backfill.py",
            "--domain",
            "paper",
            "--milvus-uri",
            ":memory:",
            "--resume",
            str(ckpt),
        ],
    )
    cli.main()
    resume_ids = called_kwargs.get("resume_ids")
    assert resume_ids is not None
    assert "p_ok" in resume_ids
    assert "p_ok2" in resume_ids


class patch_argv:
    """Tiny context manager for setting sys.argv inside a `with` block."""

    def __init__(self, argv):
        self.argv = argv
        self._saved = None

    def __enter__(self):
        self._saved = sys.argv
        sys.argv = self.argv
        return self

    def __exit__(self, *exc):
        sys.argv = self._saved
