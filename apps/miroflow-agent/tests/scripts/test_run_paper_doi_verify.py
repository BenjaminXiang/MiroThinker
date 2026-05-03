from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import scripts.run_paper_doi_verify as doi_verify
from src.data_agents.paper.doi_verifier import DoiVerification
from src.data_agents.paper.title_resolver import ResolvedPaper


class FakeCursor:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        self.statements.append((sql, params))
        compact_sql = " ".join(sql.split())
        if " FROM paper p " in compact_sql:
            return FakeCursor(rows=self.rows)
        if compact_sql.startswith("UPDATE paper"):
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("INSERT INTO paper_title_resolution_cache"):
            return FakeCursor(rowcount=1)
        if compact_sql.startswith("INSERT INTO pipeline_issue"):
            return FakeCursor(rowcount=1)
        return FakeCursor()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class FakeHttpClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _paper_row() -> dict[str, Any]:
    return {
        "paper_id": "PAPER-1",
        "title_clean": "Graph Neural Networks for Shenzhen Innovation",
        "title_raw": None,
        "authors_display": "Alice Smith, Bob Li",
        "authors_raw": None,
        "doi": None,
        "arxiv_id": None,
        "openalex_id": None,
        "year": 2024,
    }


def _resolved() -> ResolvedPaper:
    return ResolvedPaper(
        title="Graph Neural Networks for Shenzhen Innovation",
        doi="10.1234/example",
        openalex_id="W123",
        arxiv_id=None,
        abstract=None,
        pdf_url=None,
        authors=("Alice Smith", "Carol Zhang"),
        year=2024,
        venue="TestConf",
        match_confidence=0.93,
        match_source="openalex",
    )


def _decision(source: str = "openalex") -> DoiVerification:
    return DoiVerification(
        status="confirmed",
        source=source,  # type: ignore[arg-type]
        resolved=_resolved(),
        title_score=98.0,
        author_jaccard=0.42,
    )


def _install_pipeline_run_mocks(monkeypatch: Any) -> list[tuple[UUID, dict[str, Any]]]:
    run_id = UUID("11111111-1111-1111-1111-111111111111")
    closed: list[tuple[UUID, dict[str, Any]]] = []
    monkeypatch.setattr(doi_verify, "open_pipeline_run", lambda conn, **kwargs: run_id)
    monkeypatch.setattr(
        doi_verify,
        "close_pipeline_run",
        lambda conn, value, **kwargs: closed.append((value, kwargs)),
    )
    return closed


def test_dry_run_summary_uses_no_per_paper_writes(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    conn = FakeConnection([_paper_row()])
    http_client = FakeHttpClient()
    _install_pipeline_run_mocks(monkeypatch)
    monkeypatch.setenv("DATABASE_URL_TEST", "postgresql://example/test")
    monkeypatch.setattr(doi_verify, "_open_database_connection", lambda dsn: conn)
    monkeypatch.setattr(doi_verify, "_open_http_client", lambda: http_client)
    monkeypatch.setattr(
        doi_verify,
        "_verify_row",
        lambda row, *, cache, http_client: doi_verify.RowVerification(
            decision=_decision(),
            cache_key="0" * 40,
        ),
    )

    doi_verify.main(["--dry-run", "--limit", "1"])

    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert report["papers_total"] == 1
    assert report["papers_confirmed"] == 1
    assert report["paper_updates"] == 0
    assert report["cache_writes"] == 0
    assert not any("UPDATE paper" in sql for sql, _params in conn.statements)
    assert not any(
        "INSERT INTO paper_title_resolution_cache" in sql
        for sql, _params in conn.statements
    )
    assert not any("INSERT INTO pipeline_issue" in sql for sql, _params in conn.statements)
    assert conn.closed is True
    assert http_client.closed is True


def test_actual_run_updates_identity_status_and_cache(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    conn = FakeConnection([_paper_row()])
    closed = _install_pipeline_run_mocks(monkeypatch)
    monkeypatch.setenv("DATABASE_URL_TEST", "postgresql://example/test")
    monkeypatch.setattr(doi_verify, "_open_database_connection", lambda dsn: conn)
    monkeypatch.setattr(doi_verify, "_open_http_client", FakeHttpClient)
    monkeypatch.setattr(
        doi_verify,
        "_verify_row",
        lambda row, *, cache, http_client: doi_verify.RowVerification(
            decision=_decision(),
            cache_key="0" * 40,
        ),
    )

    doi_verify.main(["--limit", "1"])

    report = json.loads(capsys.readouterr().out)
    assert report["paper_updates"] == 1
    assert report["cache_writes"] == 1
    update_statements = [
        (sql, params) for sql, params in conn.statements if "UPDATE paper" in sql
    ]
    assert len(update_statements) == 1
    assert update_statements[0][1] == (
        UUID("11111111-1111-1111-1111-111111111111"),
        "PAPER-1",
    )
    cache_statements = [
        (sql, params)
        for sql, params in conn.statements
        if "INSERT INTO paper_title_resolution_cache" in sql
    ]
    assert len(cache_statements) == 1
    cache_payload = json.loads(cache_statements[0][1][2])
    assert cache_payload["doi"] == "10.1234/example"
    assert closed[0][1]["status"] == "succeeded"


def test_failed_verify_writes_pipeline_issue(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    conn = FakeConnection([_paper_row()])
    _install_pipeline_run_mocks(monkeypatch)
    monkeypatch.setenv("DATABASE_URL_TEST", "postgresql://example/test")
    monkeypatch.setattr(doi_verify, "_open_database_connection", lambda dsn: conn)
    monkeypatch.setattr(doi_verify, "_open_http_client", FakeHttpClient)
    monkeypatch.setattr(
        doi_verify,
        "_verify_row",
        lambda row, *, cache, http_client: doi_verify.RowVerification(
            decision=None,
            cache_key="0" * 40,
        ),
    )

    doi_verify.main(["--limit", "1"])

    report = json.loads(capsys.readouterr().out)
    assert report["papers_unverified"] == 1
    assert report["pipeline_issues_inserted"] == 1
    assert not any("UPDATE paper" in sql for sql, _params in conn.statements)
    issue_statements = [
        (sql, params)
        for sql, params in conn.statements
        if "INSERT INTO pipeline_issue" in sql
    ]
    assert len(issue_statements) == 1
    assert issue_statements[0][1][0] == "paper:PAPER-1"
    assert "paper_doi_verify_failed" in issue_statements[0][1][1]
    snapshot = json.loads(issue_statements[0][1][2])
    assert snapshot["issue_code"] == "paper_doi_verify_failed"
    assert snapshot["paper_id"] == "PAPER-1"
