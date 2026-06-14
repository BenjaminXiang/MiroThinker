"""Tests for patent.homepage_ingest helpers (T4.3 / T4.4).

These tests exercise the pure helpers and the orchestration loop with a
hand-rolled fake `conn` object so we can verify SQL-shape decisions
(which statements run, in what order, for which inputs) without booting
Postgres. Full E2E ingest belongs to T8.3.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from src.data_agents.patent.homepage_ingest import (
    _IngestOutcome,
    _build_patent_row,
    _ingest_patents_for_professor,
)
from src.data_agents.professor.homepage_patents import PatentEntry


_RUN_ID = UUID("11111111-1111-1111-1111-111111111111")


class _FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]] | None = None) -> None:
        self._rows = rows or []

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None


class _FakeConn:
    """Captures `.execute(sql, params)` calls so tests can assert
    statement order and parameter shape."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.patent_id_rows: list[str] = ["PAT-FAKE-001"]

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _FakeCursor:
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        if normalized.startswith("INSERT INTO patent ("):
            return _FakeCursor([(self.patent_id_rows.pop(0),)])
        return _FakeCursor()

    def transaction(self):  # pragma: no cover - unused in the helper tests
        raise NotImplementedError


# ---------------------------------------------------------------------------
# _build_patent_row
# ---------------------------------------------------------------------------


def test_build_patent_row_full_entry():
    entry = PatentEntry(
        title="一种基于深度学习的图像分类方法",
        patent_id="ZL202310012345.6",
        application_date=None,
        grant_date=date(2024, 6, 15),
        inventors=("张三", "李四"),
        source_url="https://prof.test/page",
        source_anchor=None,
    )
    row = _build_patent_row(entry, canonical_name="王教授", run_id=_RUN_ID)
    assert row["patent_number"] == "ZL202310012345.6"
    assert row["patent_id"].startswith("PAT-")
    assert row["title_clean"] == "一种基于深度学习的图像分类方法"
    assert row["inventors_parsed"] == ["张三", "李四"]
    assert row["inventors_raw"] == "张三；李四"
    assert row["grant_date"] == date(2024, 6, 15)
    assert row["quality_status"] == "needs_enrichment"
    assert row["identity_status"] == "unverified"
    assert row["ipc_codes"] == []


def test_build_patent_row_uses_canonical_name_when_no_inventors():
    entry = PatentEntry(
        title="一种处理X的方法",
        patent_id="CN202410999999",
        inventors=(),
        source_url="https://prof.test/page",
    )
    row = _build_patent_row(entry, canonical_name="王教授", run_id=_RUN_ID)
    assert row["inventors_parsed"] == ["王教授"]
    assert row["inventors_raw"] == "王教授"


def test_build_patent_row_synthesizes_page_only_id_without_patent_number():
    entry = PatentEntry(
        title="一种未授权的方法",
        patent_id=None,
        source_url="https://prof.test/page",
    )
    row = _build_patent_row(
        entry,
        canonical_name="王教授",
        professor_id="PROF-1",
        run_id=_RUN_ID,
    )
    assert row["patent_id"].startswith("PAT-PAGE-")
    assert row["patent_number"] is None
    assert row["title_clean"] == "一种未授权的方法"
    assert row["inventors_parsed"] == ["王教授"]
    assert row["identity_status"] == "unverified"
    assert row["quality_status"] == "needs_enrichment"


# ---------------------------------------------------------------------------
# _ingest_patents_for_professor — the routing decisions per scenario
# ---------------------------------------------------------------------------


def test_zero_patents_emits_no_sql_and_no_issue():
    conn = _FakeConn()
    outcome = _ingest_patents_for_professor(
        conn,
        entries=[],
        professor_id="PROF-1",
        canonical_name="王教授",
        run_id=_RUN_ID,
        dry_run=False,
    )
    assert outcome == _IngestOutcome(
        upserted=0,
        skipped_no_id=0,
        links_written=0,
        issues_filed=0,
    )
    assert conn.calls == []


def test_title_only_candidate_inserts_canonical_and_link():
    conn = _FakeConn()
    entries = [
        PatentEntry(
            title="一种未授权的方法示例",
            patent_id=None,
            source_url="https://prof.test/page",
        )
    ]
    outcome = _ingest_patents_for_professor(
        conn,
        entries=entries,
        professor_id="PROF-1",
        canonical_name="王教授",
        run_id=_RUN_ID,
        dry_run=False,
    )
    assert outcome == _IngestOutcome(
        upserted=1,
        skipped_no_id=0,
        links_written=1,
        issues_filed=0,
    )
    sql_statements = [call[0] for call in conn.calls]
    assert any(sql.startswith("INSERT INTO patent (") for sql in sql_statements)
    assert any(
        sql.startswith("INSERT INTO professor_patent_link (")
        for sql in sql_statements
    )
    assert not any(
        sql.startswith("INSERT INTO pipeline_issue") for sql in sql_statements
    )
    link_sql, link_params = next(
        call
        for call in conn.calls
        if call[0].startswith("INSERT INTO professor_patent_link (")
    )
    assert "evidence_url" in link_sql
    assert "evidence_anchor" in link_sql
    assert link_params[5] == "https://prof.test/page"
    assert link_params[6] is None
    patent_params = next(
        params for sql, params in conn.calls if sql.startswith("INSERT INTO patent (")
    )
    assert patent_params[0].startswith("PAT-PAGE-")
    assert patent_params[1] is None
    assert patent_params[2] == "一种未授权的方法示例"
    assert patent_params[19] == "unverified"
    assert patent_params[20] == "needs_enrichment"


def test_full_patent_id_inserts_canonical_and_link():
    conn = _FakeConn()
    entries = [
        PatentEntry(
            title="一种基于深度学习的图像分类方法",
            patent_id="ZL202310012345.6",
            grant_date=date(2024, 6, 15),
            inventors=("张三", "李四"),
            source_url="https://prof.test/page",
        )
    ]
    outcome = _ingest_patents_for_professor(
        conn,
        entries=entries,
        professor_id="PROF-1",
        canonical_name="王教授",
        run_id=_RUN_ID,
        dry_run=False,
    )
    assert outcome == _IngestOutcome(
        upserted=1,
        skipped_no_id=0,
        links_written=1,
        issues_filed=0,
    )
    sql_statements = [call[0] for call in conn.calls]
    assert any(sql.startswith("INSERT INTO patent (") for sql in sql_statements)
    assert any(
        sql.startswith("INSERT INTO professor_patent_link (")
        for sql in sql_statements
    )
    # No pipeline_issue should have been filed.
    assert not any(
        sql.startswith("INSERT INTO pipeline_issue") for sql in sql_statements
    )


def test_conflict_with_existing_patent_id_uses_on_conflict_clause():
    """The upsert SQL must rely on patent_number conflict resolution so
    re-discovering the same real-world patent merges into the existing
    canonical row instead of inserting a duplicate (Acceptance §5)."""
    conn = _FakeConn()
    entries = [
        PatentEntry(
            title="一种处理X的方法",
            patent_id="ZL202310012345.6",
            grant_date=date(2024, 6, 15),
            source_url="https://prof.test/page",
        )
    ]
    _ingest_patents_for_professor(
        conn,
        entries=entries,
        professor_id="PROF-1",
        canonical_name="王教授",
        run_id=_RUN_ID,
        dry_run=False,
    )
    patent_insert_sql = next(
        call[0] for call in conn.calls if call[0].startswith("INSERT INTO patent (")
    )
    assert "ON CONFLICT (patent_number) DO UPDATE" in patent_insert_sql
    # The UPDATE clause must NOT touch quality_status (forward-monotonic
    # invariant; see design.md §12 + spec Requirement "Quality status
    # promotion logic").
    update_clause = patent_insert_sql.split("DO UPDATE", maxsplit=1)[1]
    assert "quality_status" not in update_clause


def test_title_only_candidate_uses_patent_id_conflict_for_idempotency():
    conn = _FakeConn()
    entries = [
        PatentEntry(
            title="一种无编号但应保留的方法",
            patent_id=None,
            source_url="https://prof.test/page",
        )
    ]
    _ingest_patents_for_professor(
        conn,
        entries=entries,
        professor_id="PROF-1",
        canonical_name="王教授",
        run_id=_RUN_ID,
        dry_run=False,
    )
    patent_insert_sql = next(
        call[0] for call in conn.calls if call[0].startswith("INSERT INTO patent (")
    )
    assert "ON CONFLICT (patent_id) DO UPDATE" in patent_insert_sql
    assert "patent_number = COALESCE" in patent_insert_sql


def test_blank_title_candidate_files_issue_and_skips_canonical():
    conn = _FakeConn()
    entries = [
        PatentEntry(
            title="   ",
            patent_id=None,
            source_url="https://prof.test/page",
        )
    ]
    outcome = _ingest_patents_for_professor(
        conn,
        entries=entries,
        professor_id="PROF-1",
        canonical_name="王教授",
        run_id=_RUN_ID,
        dry_run=False,
    )
    assert outcome == _IngestOutcome(
        upserted=0,
        skipped_no_id=1,
        links_written=0,
        issues_filed=1,
    )
    sql_statements = [call[0] for call in conn.calls]
    assert any(sql.startswith("INSERT INTO pipeline_issue") for sql in sql_statements)
    assert not any(sql.startswith("INSERT INTO patent (") for sql in sql_statements)


def test_mixed_batch_routes_each_candidate_independently():
    conn = _FakeConn()
    conn.patent_id_rows = ["PAT-A", "PAT-B", "PAT-C"]
    entries = [
        PatentEntry(title="一种A方法的实现", patent_id="ZL202310011111"),
        PatentEntry(title="一种B方法没有编号示例", patent_id=None),
        PatentEntry(title="一种C方法的实现", patent_id="ZL202310022222"),
    ]
    outcome = _ingest_patents_for_professor(
        conn,
        entries=entries,
        professor_id="PROF-1",
        canonical_name="王教授",
        run_id=_RUN_ID,
        dry_run=False,
    )
    assert outcome == _IngestOutcome(
        upserted=3,
        skipped_no_id=0,
        links_written=3,
        issues_filed=0,
    )


def test_dry_run_skips_all_writes_but_keeps_counters():
    conn = _FakeConn()
    entries = [
        PatentEntry(title="一种基于X的方法", patent_id="ZL202310044444"),
        PatentEntry(title="一种未授权的方法示例", patent_id=None),
    ]
    outcome = _ingest_patents_for_professor(
        conn,
        entries=entries,
        professor_id="PROF-1",
        canonical_name="王教授",
        run_id=_RUN_ID,
        dry_run=True,
    )
    assert outcome == _IngestOutcome(
        upserted=2,
        skipped_no_id=0,
        links_written=0,
        issues_filed=0,
    )
    assert conn.calls == []
