from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_paper_abstract_clean_quality_cleanup.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_paper_abstract_clean_quality_cleanup", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_process_rows_clears_unusable_abstract_and_demotes_ready() -> None:
    cli = _import_cli()
    conn = MagicMock()

    report = cli._process_rows(
        conn,
        rows=[
            {
                "paper_id": "PAPER-BAD",
                "title_clean": "Bad abstract",
                "abstract_clean": "International audience",
                "summary_zh": "已有中文摘要",
                "quality_status": "ready",
                "canonical_source": "openalex",
            }
        ],
        run_id="11111111-1111-1111-1111-111111111111",
        dry_run=False,
    )

    assert report["rows_scanned"] == 1
    assert report["abstracts_cleared"] == 1
    assert report["ready_demoted"] == 1
    sql, params = conn.execute.call_args.args
    assert "abstract_clean = NULL" in sql
    assert params == ("partial", "11111111-1111-1111-1111-111111111111", "PAPER-BAD")
    conn.commit.assert_called_once()


def test_process_rows_keeps_usable_abstract() -> None:
    cli = _import_cli()
    conn = MagicMock()

    report = cli._process_rows(
        conn,
        rows=[
            {
                "paper_id": "PAPER-GOOD",
                "title_clean": "Good abstract",
                "abstract_clean": (
                    "This paper proposes a source-grounded method and evaluates "
                    "its performance on representative benchmark datasets."
                ),
                "summary_zh": None,
                "quality_status": "partial",
                "canonical_source": "openalex",
            }
        ],
        run_id="11111111-1111-1111-1111-111111111111",
        dry_run=False,
    )

    assert report["rows_scanned"] == 1
    assert report["abstracts_cleared"] == 0
    conn.execute.assert_not_called()
    conn.commit.assert_called_once()


def test_main_dry_run_does_not_open_pipeline_run(monkeypatch, capsys) -> None:
    cli = _import_cli()
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "paper_id": "PAPER-BAD",
            "title_clean": "Bad abstract",
            "abstract_clean": "International audience",
            "summary_zh": None,
            "quality_status": "partial",
            "canonical_source": "openalex",
        }
    ]
    conn.execute.return_value = cursor
    opened: list[object] = []
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "open_pipeline_run", lambda *_a, **_kw: opened.append(True))
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", ["run_paper_abstract_clean_quality_cleanup.py", "--dry-run"])
        cli.main()

    assert opened == []
    report = json.loads(capsys.readouterr().out)
    assert report["abstracts_cleared"] == 1
