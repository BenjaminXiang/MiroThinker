from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.deps import get_pg_conn

router = APIRouter(prefix="/api")


class DomainStats(BaseModel):
    name: str
    count: int
    quality: dict[str, int]
    last_updated: str | None


class DashboardResponse(BaseModel):
    domains: list[DomainStats]
    ops: "DashboardOps" = Field(default_factory=lambda: DashboardOps())


class PipelineStageSummary(BaseModel):
    stage: str
    total: int
    running: int = 0
    succeeded: int = 0
    partial: int = 0
    failed: int = 0
    latest_run_id: str | None = None
    latest_domain: str | None = None
    latest_started_at: datetime | None = None
    latest_finished_at: datetime | None = None


class PipelineFailureSample(BaseModel):
    run_id: str
    run_kind: str
    domain: str | None = None
    status: str
    items_processed: int | None = None
    items_failed: int | None = None
    error_summary: dict[str, Any] | None = None
    started_at: datetime
    finished_at: datetime | None = None


class PipelineIssueSample(BaseModel):
    issue_id: str
    domain: str | None = None
    issue_type: str | None = None
    severity: str
    description: str
    task_id: str | None = None
    source_rows: list[int] = Field(default_factory=list)
    recommended_action: str | None = None
    reported_at: datetime


class PipelineAction(BaseModel):
    action: str
    label: str
    run_id: str | None = None
    domain: str | None = None
    reason: str


class DashboardOps(BaseModel):
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    active_runs: int = 0
    recent_failed_runs: int = 0
    open_issue_count: int = 0
    stages: list[PipelineStageSummary] = Field(default_factory=list)
    failure_samples: list[PipelineFailureSample] = Field(default_factory=list)
    issue_samples: list[PipelineIssueSample] = Field(default_factory=list)
    actions: list[PipelineAction] = Field(default_factory=list)


# Round 9 — read from Postgres canonical tables, not the legacy
# `released_objects.db` snapshot. The SQLite store was frozen several
# rounds ago and showed stale counts (19 profs / 1037 companies / 208
# papers / 1931 patents) even though Postgres has the current truth
# (783 resolved profs / 1024 companies / 7297 papers / 0 patents).


def _professor_stats(conn: Any) -> DomainStats:
    row = conn.execute(
        """
        SELECT count(*) FILTER (WHERE identity_status = 'resolved')::int AS ready,
               count(*) FILTER (WHERE identity_status = 'needs_review')::int AS needs_review,
               count(*) FILTER (WHERE identity_status = 'inactive')::int AS inactive,
               count(*) FILTER (WHERE identity_status = 'merged_into')::int AS merged,
               max(updated_at) AS last_updated
          FROM professor
        """
    ).fetchone()
    count = (row["ready"] or 0)
    quality = {
        "ready": row["ready"] or 0,
        "needs_review": row["needs_review"] or 0,
    }
    if row["inactive"]:
        quality["inactive"] = row["inactive"]
    if row["merged"]:
        quality["merged"] = row["merged"]
    return DomainStats(
        name="professor",
        count=count,
        quality=quality,
        last_updated=row["last_updated"].isoformat() if row["last_updated"] else None,
    )


def _company_stats(conn: Any) -> DomainStats:
    row = conn.execute(
        """
        SELECT count(*)::int AS total,
               count(*) FILTER (WHERE is_shenzhen = true)::int AS shenzhen,
               max(updated_at) AS last_updated
          FROM company
        """
    ).fetchone()
    return DomainStats(
        name="company",
        count=row["total"] or 0,
        quality={
            "ready": row["total"] or 0,
            "shenzhen": row["shenzhen"] or 0,
        },
        last_updated=row["last_updated"].isoformat() if row["last_updated"] else None,
    )


def _paper_stats(conn: Any) -> DomainStats:
    row = conn.execute(
        """
        SELECT count(*)::int AS total,
               count(*) FILTER (WHERE title_clean IS NOT NULL)::int AS with_title,
               count(*) FILTER (WHERE title_clean IS NULL)::int AS missing_title,
               max(updated_at) AS last_updated
          FROM paper
        """
    ).fetchone()
    quality = {"ready": row["with_title"] or 0}
    if row["missing_title"]:
        quality["missing_title"] = row["missing_title"]
    return DomainStats(
        name="paper",
        count=row["total"] or 0,
        quality=quality,
        last_updated=row["last_updated"].isoformat() if row["last_updated"] else None,
    )


def _patent_stats(conn: Any) -> DomainStats:
    row = conn.execute(
        """
        SELECT count(*)::int AS total, max(updated_at) AS last_updated
          FROM patent
        """
    ).fetchone()
    return DomainStats(
        name="patent",
        count=row["total"] or 0,
        quality={"ready": row["total"] or 0},
        last_updated=row["last_updated"].isoformat() if row["last_updated"] else None,
    )


def _pipeline_ops(conn: Any) -> DashboardOps:
    run_rows = conn.execute(
        """
        SELECT
            run_id,
            run_kind,
            status,
            run_scope,
            started_at,
            finished_at,
            items_processed,
            items_failed,
            error_summary
          FROM pipeline_run
         ORDER BY started_at DESC
         LIMIT 100
        """
    ).fetchall()
    issue_rows = conn.execute(
        """
        SELECT
            issue_id::text AS issue_id,
            severity,
            description,
            evidence_snapshot,
            reported_at,
            count(*) OVER()::int AS total_count
          FROM pipeline_issue
         WHERE resolved = false
         ORDER BY reported_at DESC
         LIMIT 5
        """
    ).fetchall()

    stages = _stage_summaries(run_rows)
    failure_samples = _failure_samples(run_rows)
    issue_samples = [_issue_sample(row) for row in issue_rows]
    open_issue_count = int(_row_value(issue_rows[0], "total_count", 5)) if issue_rows else 0
    return DashboardOps(
        active_runs=sum(1 for row in run_rows if _row_value(row, "status", 2) == "running"),
        recent_failed_runs=sum(
            1 for row in run_rows if _row_value(row, "status", 2) in {"failed", "partial"}
        ),
        open_issue_count=open_issue_count,
        stages=stages,
        failure_samples=failure_samples,
        issue_samples=issue_samples,
        actions=_pipeline_actions(run_rows, open_issue_count),
    )


def _stage_summaries(rows: list[Any]) -> list[PipelineStageSummary]:
    by_stage: dict[str, dict[str, Any]] = {}
    for row in rows:
        stage = str(_row_value(row, "run_kind", 1))
        status = str(_row_value(row, "status", 2))
        scope = _json_object(_row_value(row, "run_scope", 3))
        bucket = by_stage.setdefault(
            stage,
            {
                "stage": stage,
                "total": 0,
                "running": 0,
                "succeeded": 0,
                "partial": 0,
                "failed": 0,
                "latest_run_id": None,
                "latest_domain": None,
                "latest_started_at": None,
                "latest_finished_at": None,
            },
        )
        bucket["total"] += 1
        if status in {"running", "succeeded", "partial", "failed"}:
            bucket[status] += 1
        started_at = _row_value(row, "started_at", 4)
        if bucket["latest_started_at"] is None or started_at > bucket["latest_started_at"]:
            bucket["latest_run_id"] = str(_row_value(row, "run_id", 0))
            bucket["latest_domain"] = _optional_text(scope.get("domain"))
            bucket["latest_started_at"] = started_at
            bucket["latest_finished_at"] = _row_value(row, "finished_at", 5)
    return [
        PipelineStageSummary.model_validate(bucket)
        for bucket in sorted(
            by_stage.values(),
            key=lambda item: item["latest_started_at"] or datetime.min,
            reverse=True,
        )
    ]


def _failure_samples(rows: list[Any]) -> list[PipelineFailureSample]:
    samples: list[PipelineFailureSample] = []
    for row in rows:
        status = str(_row_value(row, "status", 2))
        if status not in {"failed", "partial"}:
            continue
        scope = _json_object(_row_value(row, "run_scope", 3))
        samples.append(
            PipelineFailureSample(
                run_id=str(_row_value(row, "run_id", 0)),
                run_kind=str(_row_value(row, "run_kind", 1)),
                domain=_optional_text(scope.get("domain")),
                status=status,
                items_processed=_optional_int(_row_value(row, "items_processed", 6)),
                items_failed=_optional_int(_row_value(row, "items_failed", 7)),
                error_summary=_optional_json_object(_row_value(row, "error_summary", 8)),
                started_at=_row_value(row, "started_at", 4),
                finished_at=_row_value(row, "finished_at", 5),
            )
        )
        if len(samples) >= 5:
            break
    return samples


def _issue_sample(row: Any) -> PipelineIssueSample:
    evidence = _json_object(_row_value(row, "evidence_snapshot", 3))
    return PipelineIssueSample(
        issue_id=str(_row_value(row, "issue_id", 0)),
        severity=str(_row_value(row, "severity", 1)),
        description=str(_row_value(row, "description", 2)),
        domain=_optional_text(evidence.get("domain")),
        issue_type=_optional_text(evidence.get("issue_type")),
        task_id=_optional_text(evidence.get("task_id")),
        source_rows=_int_list(evidence.get("source_rows")),
        recommended_action=_optional_text(evidence.get("recommended_action")),
        reported_at=_row_value(row, "reported_at", 4),
    )


def _pipeline_actions(rows: list[Any], open_issue_count: int) -> list[PipelineAction]:
    actions: list[PipelineAction] = []
    if open_issue_count:
        actions.append(
            PipelineAction(
                action="review_issues",
                label=f"处理 {open_issue_count} 个开放质量问题",
                reason="pipeline_issue 中仍有未关闭记录",
            )
        )

    for row in rows:
        if len(actions) >= 6:
            break
        status = str(_row_value(row, "status", 2))
        if status != "succeeded":
            continue
        run_id = str(_row_value(row, "run_id", 0))
        run_kind = str(_row_value(row, "run_kind", 1))
        scope = _json_object(_row_value(row, "run_scope", 3))
        domain = _optional_text(scope.get("domain"))
        summary = _json_object(scope.get("result_summary"))
        if (
            run_kind == "import_xlsx"
            and domain in {"company", "patent", "paper", "professor"}
            and scope.get("dry_run") is not True
            and "retrieval_validation_report" not in summary
            and not _has_successful_child(rows, run_id, "retrieval_validation")
        ):
            actions.append(
                PipelineAction(
                    action="retrieval_validation",
                    label=f"{domain} 导入后检索验收",
                    run_id=run_id,
                    domain=domain,
                    reason="该导入任务尚未写回 retrieval_validation_report",
                )
            )
        if (
            domain in {"company", "patent", "paper", "professor"}
            and summary.get("milvus_backfill_required") is True
            and not _has_successful_child(rows, run_id, "milvus_backfill")
        ):
            actions.append(
                PipelineAction(
                    action="milvus_backfill",
                    label=f"{domain} Milvus dry-run",
                    run_id=run_id,
                    domain=domain,
                    reason="导入摘要标记需要 Milvus 回填验证",
                )
            )
    return actions[:6]


def _has_successful_child(rows: list[Any], parent_run_id: str, action: str) -> bool:
    for row in rows:
        scope = _json_object(_row_value(row, "run_scope", 3))
        if (
            str(scope.get("parent_run_id") or "") == parent_run_id
            and scope.get("action") == action
            and _row_value(row, "status", 2) == "succeeded"
        ):
            return True
    return False


def _row_value(row: Any, key: str, index: int) -> Any:
    return row[key] if isinstance(row, dict) else row[index]


def _json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_json_object(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    output: list[int] = []
    for item in value:
        parsed = _optional_int(item)
        if parsed is not None:
            output.append(parsed)
    return output


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(conn: Any = Depends(get_pg_conn)) -> DashboardResponse:
    return DashboardResponse(
        domains=[
            _professor_stats(conn),
            _company_stats(conn),
            _paper_stats(conn),
            _patent_stats(conn),
        ],
        ops=_pipeline_ops(conn),
    )
