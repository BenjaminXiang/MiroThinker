from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_professor_metrics_backfill.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "run_professor_metrics_backfill", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeConn:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql: str, params: tuple[object, ...] = ()):
        self.execute_calls.append((sql, params))
        return SimpleNamespace(rowcount=1)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _row(professor_id: str, *, orcid: str | None = "0000-0001-2345-6789") -> dict:
    return {
        "professor_id": professor_id,
        "canonical_name": "张三",
        "institution": "南方科技大学",
        "orcid": orcid,
    }


def _args(**overrides):
    defaults = {
        "database_url": "postgresql://fake/test",
        "dry_run": False,
        "limit": None,
        "resume": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_backfill_happy_path_writes_openalex_metrics(tmp_path, monkeypatch):
    cli = _import_cli()
    conn = FakeConn()
    upsert = MagicMock()
    monkeypatch.setattr(cli, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_fetch_professors", lambda *_a, **_kw: [_row("PROF-1")])
    monkeypatch.setattr(
        cli,
        "fetch_metrics",
        lambda **_kw: SimpleNamespace(
            source="openalex",
            h_index=12,
            citation_count=345,
        ),
    )
    monkeypatch.setattr(cli, "upsert_professor_metrics", upsert)

    stats = cli.run_backfill(_args())

    assert stats.profs_successful == 1
    assert stats.openalex == 1
    upsert.assert_called_once()
    assert upsert.call_args.kwargs["h_index"] == 12
    assert upsert.call_args.kwargs["citation_count"] == 345
    assert upsert.call_args.kwargs["metrics_source"] == "openalex"
    assert conn.commits == 1
    assert "metrics_source" in next(tmp_path.glob("*.jsonl")).read_text()


def test_backfill_no_orcid_writes_verified_link_only(tmp_path, monkeypatch):
    cli = _import_cli()
    conn = FakeConn()
    upsert = MagicMock()
    fetch = MagicMock()
    monkeypatch.setattr(cli, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli, "_fetch_professors", lambda *_a, **_kw: [_row("PROF-2", orcid=None)]
    )
    monkeypatch.setattr(cli, "fetch_metrics", fetch)
    monkeypatch.setattr(cli, "upsert_professor_metrics", upsert)

    stats = cli.run_backfill(_args())

    fetch.assert_not_called()
    assert stats.verified_link_only == 1
    assert upsert.call_args.kwargs["h_index"] is None
    assert upsert.call_args.kwargs["citation_count"] is None
    assert upsert.call_args.kwargs["metrics_source"] == "verified_link_only"


def test_backfill_fetch_failure_files_pipeline_issue(tmp_path, monkeypatch):
    cli = _import_cli()
    conn = FakeConn()
    upsert = MagicMock()
    monkeypatch.setattr(cli, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_fetch_professors", lambda *_a, **_kw: [_row("PROF-3")])
    monkeypatch.setattr(
        cli,
        "fetch_metrics",
        MagicMock(side_effect=RuntimeError("openalex 503")),
    )
    monkeypatch.setattr(cli, "upsert_professor_metrics", upsert)

    stats = cli.run_backfill(_args())

    upsert.assert_not_called()
    assert stats.fetch_failed == 1
    assert stats.pipeline_issues_inserted == 1
    assert any("INSERT INTO pipeline_issue" in sql for sql, _ in conn.execute_calls)
    assert "fetch_failed" in next(tmp_path.glob("*.jsonl")).read_text()


def test_resume_selects_only_uncomputed_metrics():
    cli = _import_cli()

    sql, params = cli._build_select_sql(limit=10, resume=True)

    assert "p.identity_status = 'resolved'" in sql
    assert "p.metrics_computed_at IS NULL" in sql
    assert "LIMIT %s" in sql
    assert params == (10,)


def test_backfill_commits_every_50_professors(tmp_path, monkeypatch):
    cli = _import_cli()
    conn = FakeConn()
    monkeypatch.setattr(cli, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_fetch_professors",
        lambda *_a, **_kw: [_row(f"PROF-{i}", orcid=None) for i in range(51)],
    )
    monkeypatch.setattr(cli, "upsert_professor_metrics", MagicMock())

    stats = cli.run_backfill(_args())

    assert stats.profs_successful == 51
    assert conn.commits == 2
    assert conn.rollbacks == 0
