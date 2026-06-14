from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.data_agents.professor.quality_gate import ProfessorQualityEvaluation

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_professor_quality_re_eval.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "run_professor_quality_re_eval", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeConn:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _args(**overrides):
    defaults = {
        "database_url": "postgresql://fake/test",
        "dry_run": True,
        "professor_id": ["PROF-1"],
        "limit": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _eval(professor_id: str, status: str) -> ProfessorQualityEvaluation:
    return ProfessorQualityEvaluation(
        professor_id=professor_id,
        quality_status=status,
        reasons=(),
    )


def test_parse_args_supports_dry_run_and_selected_professor() -> None:
    cli = _import_cli()

    args = cli._parse_args(["--dry-run", "--id", "PROF-1", "--id", "PROF-2"])

    assert args.dry_run is True
    assert args.professor_id == ["PROF-1", "PROF-2"]


def test_dry_run_reports_distribution_without_persisting(monkeypatch) -> None:
    cli = _import_cli()
    conn = FakeConn()
    persist = MagicMock()
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "load_professor_canonical_states",
        lambda _conn, professor_ids=None: ["STATE-1", "STATE-2"],
    )
    monkeypatch.setattr(
        cli,
        "evaluate_professor_quality",
        MagicMock(side_effect=[_eval("PROF-1", "ready"), _eval("PROF-2", "low_confidence")]),
    )
    monkeypatch.setattr(cli, "persist_professor_quality_evaluation", persist)
    monkeypatch.setattr(
        cli,
        "_fetch_quality_distribution",
        lambda _conn: {"needs_review": 2},
    )
    monkeypatch.setattr(
        cli,
        "_fetch_quality_gate_issue_counts",
        lambda _conn: {"professor_quality_gate:coverage": 1},
    )

    report = cli.run_re_eval(_args(dry_run=True))

    persist.assert_not_called()
    assert conn.commits == 0
    assert report["evaluated"] == 2
    assert report["before_distribution"] == {"needs_review": 2}
    assert report["after_distribution"] == {"ready": 1, "low_confidence": 1}
    assert report["dry_run"] is True


def test_write_mode_persists_each_evaluation_and_commits(monkeypatch) -> None:
    cli = _import_cli()
    conn = FakeConn()
    persist = MagicMock()
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli, "load_professor_canonical_states", lambda _conn, professor_ids=None: ["STATE-1"]
    )
    monkeypatch.setattr(
        cli, "evaluate_professor_quality", MagicMock(return_value=_eval("PROF-1", "ready"))
    )
    monkeypatch.setattr(cli, "persist_professor_quality_evaluation", persist)
    monkeypatch.setattr(
        cli,
        "_fetch_quality_distribution",
        MagicMock(side_effect=[{"needs_review": 1}, {"ready": 1}]),
    )
    monkeypatch.setattr(cli, "_fetch_quality_gate_issue_counts", lambda _conn: {})

    report = cli.run_re_eval(_args(dry_run=False))

    persist.assert_called_once()
    assert conn.commits == 1
    assert report["written"] == 1
    assert report["before_distribution"] == {"needs_review": 1}
    assert report["after_distribution"] == {"ready": 1}


def test_main_prints_json_report(monkeypatch, capsys) -> None:
    cli = _import_cli()
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(
        cli,
        "run_re_eval",
        lambda _args: {"dry_run": True, "evaluated": 1},
    )

    cli.main(["--dry-run", "--id", "PROF-1"])

    assert json.loads(capsys.readouterr().out) == {"dry_run": True, "evaluated": 1}
