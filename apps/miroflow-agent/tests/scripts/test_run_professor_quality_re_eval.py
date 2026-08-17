from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

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


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, *, distributions, issue_counts, professor_rows):
        self._distributions = list(distributions)
        self._issue_counts = list(issue_counts)
        self._professor_rows = professor_rows
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()):
        compact_sql = " ".join(sql.split())
        self.statements.append((compact_sql, params))
        if compact_sql.startswith("SELECT quality_status, count(*)::int AS count"):
            return _Rows(self._distributions.pop(0))
        if compact_sql.startswith("SELECT reported_by, stage, count(*)::int AS count"):
            return _Rows(self._issue_counts.pop(0))
        if compact_sql.startswith("SELECT professor_id, quality_status FROM professor"):
            return _Rows(self._professor_rows)
        raise AssertionError(f"Unexpected SQL: {compact_sql}")

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


def test_cli_help(capsys):
    cli = _import_cli()
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--dry-run" in captured.out
    assert "--professor-id" in captured.out


def test_build_professor_select_sql_supports_ids_and_limit():
    cli = _import_cli()
    sql, params = cli._build_professor_select_sql(
        professor_ids=["PROF-1", "PROF-2"],
        limit=10,
    )

    assert "professor_id = ANY(%s)" in sql
    assert "LIMIT %s" in sql
    assert params == (["PROF-1", "PROF-2"], 10)


def test_normalize_psycopg_dsn_accepts_sqlalchemy_url():
    cli = _import_cli()

    assert cli._normalize_psycopg_dsn(
        "postgresql+psycopg://u:p@localhost:5432/miroflow_real"
    ) == "postgresql://u:p@localhost:5432/miroflow_real"


def test_run_re_eval_dry_run_projects_distribution_without_writes(monkeypatch):
    cli = _import_cli()
    conn = _FakeConn(
        distributions=[
            [
                {"quality_status": "needs_review", "count": 1},
                {"quality_status": "ready", "count": 1},
            ],
        ],
        issue_counts=[[{"reported_by": "manual", "stage": "identity_gate", "count": 1}]],
        professor_rows=[{"professor_id": "PROF-1", "quality_status": "needs_review"}],
    )
    monkeypatch.setattr(cli, "load_professor_canonical_state", lambda _conn, pid: pid)
    monkeypatch.setattr(
        cli,
        "evaluate_professor_quality",
        lambda _state: SimpleNamespace(quality_status="needs_enrichment"),
    )
    monkeypatch.setattr(
        cli,
        "persist_professor_quality_evaluation",
        lambda *_args, **_kwargs: pytest.fail("dry-run must not persist"),
    )

    report = cli.run_re_eval(
        conn,
        SimpleNamespace(dry_run=True, professor_id=[], limit=None),
    )

    assert report["professors_scanned"] == 1
    assert report["statuses_changed"] == 1
    assert report["after_distribution"]["needs_review"] == 0
    assert report["after_distribution"]["needs_enrichment"] == 1
    assert conn.commit_count == 0


def test_run_re_eval_write_persists_and_commits(monkeypatch):
    cli = _import_cli()
    conn = _FakeConn(
        distributions=[
            [{"quality_status": "needs_review", "count": 1}],
            [{"quality_status": "needs_enrichment", "count": 1}],
        ],
        issue_counts=[
            [],
            [
                {
                    "reported_by": "professor_quality_gate",
                    "stage": "coverage",
                    "count": 1,
                }
            ],
        ],
        professor_rows=[{"professor_id": "PROF-1", "quality_status": "needs_review"}],
    )
    monkeypatch.setattr(cli, "load_professor_canonical_state", lambda _conn, pid: pid)
    monkeypatch.setattr(
        cli,
        "evaluate_professor_quality",
        lambda _state: SimpleNamespace(quality_status="needs_enrichment"),
    )
    monkeypatch.setattr(
        cli,
        "persist_professor_quality_evaluation",
        lambda *_args, **_kwargs: SimpleNamespace(issues_inserted=1, issues_resolved=2),
    )

    report = cli.run_re_eval(
        conn,
        SimpleNamespace(dry_run=False, professor_id=[], limit=None),
    )

    assert report["issues_inserted"] == 1
    assert report["issues_resolved"] == 2
    assert report["after_distribution"] == {"needs_enrichment": 1}
    assert conn.commit_count == 1
