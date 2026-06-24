from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_paper_source_gap_audit.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_paper_source_gap_audit", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_help(capsys) -> None:
    cli = _import_cli()

    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--database-url" in captured.out
    assert "--sample-limit" in captured.out
    assert "--limit" in captured.out
    assert "--output" in captured.out


def test_cli_outputs_read_only_source_gap_report(monkeypatch, capsys) -> None:
    cli = _import_cli()
    closed = []

    class _Conn:
        def close(self):
            closed.append(True)

        def commit(self):  # pragma: no cover - should never be called
            raise AssertionError("source-gap audit must not commit")

    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: _Conn())
    monkeypatch.setattr(
        cli,
        "load_source_gap_rows",
        lambda _conn, limit=None: [
            {
                "paper_id": "PAPER-A",
                "canonical_source": "crossref",
                "identity_status": "unverified",
                "quality_status": "needs_enrichment",
                "summary_zh": None,
                "abstract_clean": (
                    "This paper studies trustworthy artificial intelligence for "
                    "medical imaging and evaluates robust diagnosis models."
                ),
            },
            {
                "paper_id": "PAPER-B",
                "canonical_source": "prof_page_only",
                "identity_status": "unverified",
                "quality_status": "needs_enrichment",
                "summary_zh": None,
                "abstract_clean": None,
            },
        ],
    )

    cli.main(["--sample-limit", "1"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["database_url_label"] == "env:DATABASE_URL"
    assert payload["total_rows"] == 2
    assert payload["lane_counts"] == {
        "existing_source_summary_fast_path": 1,
        "prof_page_only_title_parser_cleanup": 1,
    }
    assert payload["lanes"]["existing_source_summary_fast_path"]["sample_paper_ids"] == [
        "PAPER-A"
    ]
    assert "rows" not in payload
    assert closed == [True]
