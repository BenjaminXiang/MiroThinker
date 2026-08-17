from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.quality_gate import (
    ProfessorCanonicalState,
    ProfessorQualityEvaluation,
    ProfessorQualityReason,
)

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_professor_quality_re_eval.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_professor_quality_re_eval", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_help(capsys):
    with _patch_argv(["run_professor_quality_re_eval.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli = _import_cli()
            cli.main()
        assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--dry-run" in captured.out
    assert "--professor-id" in captured.out
    assert "--limit" in captured.out


def test_dry_run_reports_distribution_without_persisting(monkeypatch, capsys):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {"professor_id": "PROF-1", "quality_status": "needs_review"},
        {"professor_id": "PROF-2", "quality_status": "needs_review"},
    ]
    states = {
        "PROF-1": ProfessorCanonicalState(
            professor_id="PROF-1",
            canonical_name="张三",
            identity_status="resolved",
            current_institution="南方科技大学",
            title="教授",
            department=None,
            has_official_source=True,
        ),
        "PROF-2": ProfessorCanonicalState(
            professor_id="PROF-2",
            canonical_name="李四",
            identity_status="resolved",
            current_institution="南方科技大学",
            title="教授",
            department=None,
            research_topics=("机器学习",),
            profile_summary="李四教授研究机器学习。",
            has_official_source=True,
        ),
    }
    persisted: list[str] = []

    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: conn)
    monkeypatch.setattr(
        cli, "load_professor_canonical_state", lambda _conn, pid: states[pid]
    )
    monkeypatch.setattr(
        cli,
        "persist_professor_quality_evaluation",
        lambda _conn, professor_id, evaluation: persisted.append(professor_id),
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(["run_professor_quality_re_eval.py", "--dry-run"]):
        cli.main()

    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert report["professors_total"] == 2
    assert report["before_distribution"] == {"needs_review": 2}
    assert report["after_distribution"] == {"needs_enrichment": 1, "ready": 1}
    assert persisted == []


def test_selected_professor_write_persists_and_reports_issue_counts(monkeypatch, capsys):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {"professor_id": "PROF-1", "quality_status": "needs_review"},
    ]
    state = ProfessorCanonicalState(
        professor_id="PROF-1",
        canonical_name="张三",
        identity_status="resolved",
        current_institution="南方科技大学",
        title=None,
        department=None,
        has_official_source=True,
    )
    evaluation = ProfessorQualityEvaluation(
        quality_status="needs_enrichment",
        reasons=(
            ProfessorQualityReason(
                rule_id="missing_title_or_department",
                stage="affiliation",
                message="title or department missing",
            ),
        ),
    )
    persisted: list[tuple[str, str]] = []

    monkeypatch.setattr(cli, "_open_database_connection", lambda _dsn: conn)
    monkeypatch.setattr(cli, "load_professor_canonical_state", lambda _conn, pid: state)
    monkeypatch.setattr(cli, "evaluate_professor_quality", lambda _state: evaluation)
    monkeypatch.setattr(
        cli,
        "persist_professor_quality_evaluation",
        lambda _conn, professor_id, evaluation: persisted.append(
            (professor_id, evaluation.quality_status)
        )
        or {"issues_upserted": 1, "stale_issues_reconciled": 1},
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    with _patch_argv(
        ["run_professor_quality_re_eval.py", "--professor-id", "PROF-1"]
    ):
        cli.main()

    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is False
    assert report["selected_professor_ids"] == ["PROF-1"]
    assert report["issues_upserted"] == 1
    assert report["stale_issues_reconciled"] == 1
    assert persisted == [("PROF-1", "needs_enrichment")]
    assert conn.commit.called


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
