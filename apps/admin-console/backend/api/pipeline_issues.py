"""P2.2 — pipeline_issue feed API.

Surfaces the `pipeline_issue` table for the dashboard. Supports filtering
by stage / severity / resolved / reported_by (the cleanup-round label)
and pagination. Also exposes a per-guard summary used by the dashboard
"数据质量动态" strip: last run time + 7-day counts per reported_by.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.deps import get_pg_conn

router = APIRouter(prefix="/api")


class PipelineIssueRow(BaseModel):
    issue_id: str
    professor_id: str | None
    link_id: str | None
    institution: str | None
    stage: str
    severity: str
    description: str
    evidence_snapshot: dict[str, Any] | None
    reported_by: str | None
    reported_at: datetime
    resolved: bool
    resolved_at: datetime | None
    resolution_notes: str | None
    resolution_round: str | None


class PipelineIssueListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PipelineIssueRow]


class GuardRunSummary(BaseModel):
    reported_by: str
    last_run_at: datetime
    rows_last_run: int
    rows_last_7_days: int
    severity_breakdown: dict[str, int]


@router.get("/pipeline-issues", response_model=PipelineIssueListResponse)
def list_pipeline_issues(
    stage: str | None = Query(default=None),
    severity: Literal["low", "medium", "high"] | None = Query(default=None),
    resolved: bool | None = Query(default=None),
    reported_by: str | None = Query(default=None),
    professor_id: str | None = Query(default=None),
    q: str | None = Query(default=None, description="ILIKE description"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    conn: Any = Depends(get_pg_conn),
) -> PipelineIssueListResponse:
    conditions: list[str] = []
    params: dict[str, Any] = {
        "offset": (page - 1) * page_size,
        "page_size": page_size,
    }
    if stage is not None:
        conditions.append("stage = %(stage)s")
        params["stage"] = stage
    if severity is not None:
        conditions.append("severity = %(severity)s")
        params["severity"] = severity
    if resolved is not None:
        conditions.append("resolved = %(resolved)s")
        params["resolved"] = resolved
    if reported_by is not None:
        conditions.append("reported_by = %(reported_by)s")
        params["reported_by"] = reported_by
    if professor_id is not None:
        conditions.append("professor_id = %(professor_id)s")
        params["professor_id"] = professor_id
    if q:
        conditions.append("description ILIKE %(q_like)s")
        params["q_like"] = f"%{q}%"

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    rows = conn.execute(
        f"""
        SELECT issue_id::text AS issue_id,
               professor_id,
               link_id::text AS link_id,
               institution,
               stage, severity,
               description,
               evidence_snapshot,
               reported_by,
               reported_at,
               resolved,
               resolved_at,
               resolution_notes,
               resolution_round,
               count(*) OVER ()::int AS total_count
          FROM pipeline_issue
          {where}
         ORDER BY reported_at DESC
         OFFSET %(offset)s LIMIT %(page_size)s
        """,
        params,
    ).fetchall()
    total = int(rows[0]["total_count"]) if rows else 0
    items = [
        PipelineIssueRow(
            issue_id=r["issue_id"],
            professor_id=r["professor_id"],
            link_id=r["link_id"],
            institution=r["institution"],
            stage=r["stage"],
            severity=r["severity"],
            description=r["description"],
            evidence_snapshot=r["evidence_snapshot"],
            reported_by=r["reported_by"],
            reported_at=r["reported_at"],
            resolved=r["resolved"],
            resolved_at=r["resolved_at"],
            resolution_notes=r["resolution_notes"],
            resolution_round=r["resolution_round"],
        )
        for r in rows
    ]
    return PipelineIssueListResponse(
        total=total, page=page, page_size=page_size, items=items
    )


@router.get(
    "/pipeline-issues/guard-runs",
    response_model=list[GuardRunSummary],
)
def list_guard_runs(
    conn: Any = Depends(get_pg_conn),
) -> list[GuardRunSummary]:
    """Per-reported_by summary for the dashboard 质量动态 strip.

    Excludes NULL reported_by (legacy rows without a guard label).
    Sorted by most recent run first.
    """
    rows = conn.execute(
        """
        WITH guard_summary AS (
          SELECT reported_by,
                 max(reported_at) AS last_run_at,
                 count(*) FILTER (
                   WHERE reported_at >= now() - interval '7 days'
                 )::int AS rows_last_7_days,
                 jsonb_object_agg(
                   severity, sev_count
                 ) AS severity_breakdown,
                 max(run_rows) AS rows_last_run
            FROM (
              SELECT reported_by,
                     reported_at,
                     severity,
                     count(*) OVER (
                       PARTITION BY reported_by, severity
                     )::int AS sev_count,
                     count(*) OVER (
                       PARTITION BY reported_by,
                       date_trunc('minute', reported_at)
                     )::int AS run_rows
                FROM pipeline_issue
               WHERE reported_by IS NOT NULL
            ) t
           GROUP BY reported_by
        )
        SELECT reported_by, last_run_at, rows_last_run,
               rows_last_7_days, severity_breakdown
          FROM guard_summary
         ORDER BY last_run_at DESC
        """,
    ).fetchall()
    return [
        GuardRunSummary(
            reported_by=r["reported_by"],
            last_run_at=r["last_run_at"],
            rows_last_run=r["rows_last_run"] or 0,
            rows_last_7_days=r["rows_last_7_days"],
            severity_breakdown=r["severity_breakdown"] or {},
        )
        for r in rows
    ]
