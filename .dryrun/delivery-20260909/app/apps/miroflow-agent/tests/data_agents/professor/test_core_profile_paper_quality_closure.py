from __future__ import annotations

from typing import Any

from src.data_agents.professor.core_profile_paper_quality_closure import (
    CLOSURE_STAGE_ORDER,
    ClosureContext,
    ClosureIssue,
    ClosureStageResult,
    _run_professor_output_summaries_stage,
    run_seed_quality_closure,
    should_run_seed_quality_closure,
    upsert_closure_stage_issue,
)


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _IssueConn:
    def __init__(self) -> None:
        self.issue_exists = False
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Cursor:
        self.statements.append((sql, params))
        compact = " ".join(sql.split())
        if compact.startswith("SELECT issue_id"):
            rows = [{"issue_id": "ISSUE-1"}] if self.issue_exists else []
            return _Cursor(rows=rows)
        if compact.startswith("INSERT INTO pipeline_issue"):
            self.issue_exists = True
            return _Cursor(rowcount=1)
        if compact.startswith("UPDATE pipeline_issue"):
            return _Cursor(rowcount=1)
        return _Cursor()


class _NoProfessorConn:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Cursor:
        self.statements.append((sql, params))
        return _Cursor(rows=[])


def test_successful_full_seed_closure_runs_stages_in_contract_order() -> None:
    calls: list[str] = []

    def _runner(stage: str):
        def run(_context):
            calls.append(stage)
            return ClosureStageResult(
                stage=stage,
                status="success",
                counts={f"{stage}_count": 1},
                professor_ids=("PROF-1",),
                paper_ids=("PAPER-1",),
            )

        return run

    report = run_seed_quality_closure(
        conn=object(),
        seed_id=8,
        run_id="run-8",
        trigger_mode="full",
        limit=None,
        professor_ids=("PROF-1",),
        stage_runners={stage: _runner(stage) for stage in CLOSURE_STAGE_ORDER},
    )

    assert calls == list(CLOSURE_STAGE_ORDER)
    assert report.status == "success"
    assert report.ready_promotion_allowed is True
    assert report.stage_counts["homepage_paper_ingest"] == {
        "homepage_paper_ingest_count": 1
    }
    assert report.stage_counts["index_refresh_selection"] == {
        "index_refresh_selection_count": 1
    }
    assert report.index_refresh_professor_ids == ("PROF-1",)
    assert report.index_refresh_paper_ids == ("PAPER-1",)


def test_sample_or_limited_seed_closure_skips_without_running_stages() -> None:
    def _raise_if_called(_context):
        raise AssertionError("sample or limited runs must not run closure stages")

    assert (
        should_run_seed_quality_closure(
            seed_status="success",
            trigger_mode="sample",
            limit=3,
        )
        is False
    )
    assert (
        should_run_seed_quality_closure(
            seed_status="success",
            trigger_mode="full",
            limit=3,
        )
        is False
    )

    report = run_seed_quality_closure(
        conn=object(),
        seed_id=8,
        run_id="sample-run-8",
        trigger_mode="sample",
        limit=3,
        professor_ids=("PROF-1",),
        stage_runners={stage: _raise_if_called for stage in CLOSURE_STAGE_ORDER},
    )

    assert report.status == "skipped"
    assert report.skip_reason == "sample_or_limited_seed_run"
    assert report.ready_promotion_allowed is False
    assert report.stages == ()
    assert report.issues == ()


def test_failed_stage_records_visible_issue_and_blocks_ready_promotion() -> None:
    calls: list[str] = []
    issues: list[ClosureIssue] = []

    def homepage(_context):
        calls.append("homepage_paper_ingest")
        return ClosureStageResult(
            stage="homepage_paper_ingest",
            status="success",
            counts={"papers_linked_total": 2},
            professor_ids=("PROF-FAIL",),
        )

    def paper_enrichment(_context):
        calls.append("paper_enrichment")
        raise RuntimeError("provider timeout")

    def must_not_run(_context):
        raise AssertionError("later stages must not run after a closure stage fails")

    report = run_seed_quality_closure(
        conn=object(),
        seed_id=8,
        run_id="run-8",
        trigger_mode="full",
        limit=None,
        professor_ids=("PROF-FAIL",),
        stage_runners={
            "homepage_paper_ingest": homepage,
            "title_enrichment_merge": lambda _context: ClosureStageResult(
                stage="title_enrichment_merge",
                status="success",
            ),
            "paper_enrichment": paper_enrichment,
            "paper_quality_promotion": must_not_run,
            "professor_output_summaries": must_not_run,
            "professor_quality_re_evaluation": must_not_run,
            "index_refresh_selection": must_not_run,
        },
        issue_writer=lambda _conn, issue: issues.append(issue),
    )

    assert calls == ["homepage_paper_ingest", "paper_enrichment"]
    assert report.status == "failed"
    assert report.ready_promotion_allowed is False
    assert len(issues) == 1
    assert issues[0].seed_id == 8
    assert issues[0].professor_id == "PROF-FAIL"
    assert issues[0].stage == "paper_enrichment"
    assert "provider timeout" in issues[0].reason
    assert report.issues == tuple(issues)


def test_closure_issue_upsert_is_idempotent_for_same_seed_professor_stage_reason() -> None:
    conn = _IssueConn()

    first = upsert_closure_stage_issue(
        conn,
        seed_id=8,
        run_id="run-8",
        professor_id="PROF-1",
        stage="paper_enrichment",
        reason="provider timeout",
    )
    second = upsert_closure_stage_issue(
        conn,
        seed_id=8,
        run_id="run-8",
        professor_id="PROF-1",
        stage="paper_enrichment",
        reason="provider timeout",
    )

    inserts = [
        sql for sql, _params in conn.statements if "INSERT INTO pipeline_issue" in sql
    ]
    updates = [
        sql for sql, _params in conn.statements if "UPDATE pipeline_issue" in sql
    ]

    assert first.inserted is True
    assert second.inserted is False
    assert len(inserts) == 1
    assert len(updates) == 1


def test_output_summary_stage_fails_before_llm_when_seed_scope_has_no_professors(
    monkeypatch,
) -> None:
    from src.data_agents.professor import core_profile_paper_quality_closure as closure

    monkeypatch.setattr(
        closure,
        "_open_professor_output_summary_llm",
        lambda: (_ for _ in ()).throw(AssertionError("must not open LLM")),
    )

    result = _run_professor_output_summaries_stage(
        ClosureContext(
            conn=_NoProfessorConn(),
            seed_id=8,
            run_id="run-8",
            trigger_mode="full",
            limit=None,
        )
    )

    assert result.status == "failed"
    assert result.reason == "no professor ids resolved for seed-scoped output summaries"
