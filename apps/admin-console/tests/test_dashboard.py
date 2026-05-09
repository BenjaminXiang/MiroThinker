from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.api import dashboard


NOW = datetime(2026, 5, 6, 13, 30, tzinfo=timezone.utc)


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _OpsConn:
    def __init__(
        self,
        *,
        run_rows: list[dict[str, Any]],
        issue_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.run_rows = run_rows
        self.issue_rows = issue_rows or []

    def execute(self, query: str, params: dict[str, Any] | None = None) -> _Result:
        del params
        compact = " ".join(query.lower().split())
        if "from pipeline_run" in compact:
            return _Result(self.run_rows)
        if "from pipeline_issue" in compact:
            return _Result(self.issue_rows)
        raise AssertionError(f"unexpected query: {query}")


def _run(
    run_id: str,
    *,
    run_kind: str,
    status: str,
    scope: dict[str, Any],
    items_processed: int | None = None,
    items_failed: int | None = None,
    error_summary: dict[str, Any] | None = None,
    started_at: datetime = NOW,
    finished_at: datetime | None = NOW,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "run_kind": run_kind,
        "status": status,
        "run_scope": scope,
        "started_at": started_at,
        "finished_at": finished_at,
        "items_processed": items_processed,
        "items_failed": items_failed,
        "error_summary": error_summary,
    }


def test_pipeline_ops_summarizes_progress_failures_issues_and_actions() -> None:
    conn = _OpsConn(
        run_rows=[
            _run(
                "11111111-1111-1111-1111-111111111111",
                run_kind="import_xlsx",
                status="succeeded",
                scope={
                    "domain": "company",
                    "result_summary": {"milvus_backfill_required": True},
                },
                items_processed=1025,
                items_failed=0,
            ),
            _run(
                "22222222-2222-2222-2222-222222222222",
                run_kind="professor_v3",
                status="running",
                scope={"domain": "professor"},
                started_at=NOW.replace(minute=20),
                finished_at=None,
            ),
            _run(
                "33333333-3333-3333-3333-333333333333",
                run_kind="professor_v3",
                status="failed",
                scope={"domain": "professor"},
                items_processed=2,
                items_failed=1,
                error_summary={"message": "paper stage timed out"},
                started_at=NOW.replace(minute=10),
            ),
        ],
        issue_rows=[
            {
                "issue_id": "44444444-4444-4444-4444-444444444444",
                "severity": "high",
                "description": "missing company_name rows",
                "evidence_snapshot": {
                    "domain": "company",
                    "issue_type": "missing_company_name",
                    "task_id": "11111111-1111-1111-1111-111111111111",
                    "source_rows": [1620, "1621"],
                    "recommended_action": "Fill company_name before import.",
                },
                "reported_at": NOW,
                "total_count": 2,
            }
        ],
    )

    ops = dashboard._pipeline_ops(conn)

    assert ops.active_runs == 1
    assert ops.recent_failed_runs == 1
    assert ops.open_issue_count == 2
    assert [(stage.stage, stage.total) for stage in ops.stages] == [
        ("import_xlsx", 1),
        ("professor_v3", 2),
    ]
    assert ops.failure_samples[0].run_id == "33333333-3333-3333-3333-333333333333"
    assert ops.failure_samples[0].error_summary == {"message": "paper stage timed out"}
    assert ops.issue_samples[0].source_rows == [1620, 1621]
    assert [action.action for action in ops.actions] == [
        "review_issues",
        "retrieval_validation",
        "milvus_backfill",
    ]


def test_pipeline_ops_suppresses_completed_child_actions() -> None:
    parent_run_id = "11111111-1111-1111-1111-111111111111"
    conn = _OpsConn(
        run_rows=[
            _run(
                parent_run_id,
                run_kind="import_xlsx",
                status="succeeded",
                scope={
                    "domain": "company",
                    "result_summary": {"milvus_backfill_required": True},
                },
            ),
            _run(
                "22222222-2222-2222-2222-222222222222",
                run_kind="answer_readiness_eval",
                status="succeeded",
                scope={
                    "domain": "company",
                    "action": "retrieval_validation",
                    "parent_run_id": parent_run_id,
                },
            ),
            _run(
                "33333333-3333-3333-3333-333333333333",
                run_kind="backfill_real",
                status="succeeded",
                scope={
                    "domain": "company",
                    "action": "milvus_backfill",
                    "parent_run_id": parent_run_id,
                },
            ),
        ]
    )

    ops = dashboard._pipeline_ops(conn)

    assert ops.actions == []


def test_pipeline_ops_does_not_prompt_retrieval_validation_for_dry_run() -> None:
    conn = _OpsConn(
        run_rows=[
            _run(
                "11111111-1111-1111-1111-111111111111",
                run_kind="import_xlsx",
                status="succeeded",
                scope={
                    "domain": "company",
                    "dry_run": True,
                    "result_summary": {"rows_read": 1617},
                },
            ),
        ]
    )

    ops = dashboard._pipeline_ops(conn)

    assert ops.actions == []
