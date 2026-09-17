"""Bounded HTTP surface for the Canonical V2 task-run console (W2).

The heavy lifting (white list, gate, run history) lives in
``src.data_agents.canonical_v2.jobs`` so the same gate can be used by the scheduled entry point.
This module only translates: it resolves the runtime (installed on application state, or built from
the environment), validates query/body shape, and maps typed refusals to stable HTTP codes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.services.admin_session import current_operator
from src.data_agents.canonical_v2.jobs import (
    MANUAL_TRIGGER,
    RUN_STATUSES,
    JobAlreadyRunningError,
    JobBreakerOpenError,
    JobParameterError,
    JobPostgresUnavailableError,
    JobRunStore,
    JobRuntime,
    JobTaskUnknownError,
    JobsConfigurationError,
    JobsError,
    JobsStorageUnavailableError,
    jobs_database_path,
)
from src.data_agents.canonical_v2.managed_config import (
    ManagedSettingsStore,
    default_settings_path,
)


router = APIRouter(prefix="/api/canonical-v2/admin/jobs")

_STATE_NAME = "canonical_v2_jobs_runtime"

_STATUS_BY_ERROR: tuple[tuple[type[JobsError], int], ...] = (
    (JobTaskUnknownError, 404),
    (JobParameterError, 422),
    (JobAlreadyRunningError, 409),
    (JobBreakerOpenError, 409),
    (JobPostgresUnavailableError, 503),
    (JobsStorageUnavailableError, 503),
    (JobsConfigurationError, 503),
)


class JobTriggerRequest(BaseModel):
    """The only caller input accepted: values for declared, closed parameters."""

    params: dict[str, Any] = Field(default_factory=dict)


class JobTriggerResponse(BaseModel):
    task_id: str
    run_id: str
    status: str
    skip_reason: str | None
    started_at: str
    command: list[str]


class JobRunListResponse(BaseModel):
    task_id: str
    total: int
    limit: int
    offset: int
    runs: list[dict[str, Any]]


class JobBreakerResetResponse(BaseModel):
    task_id: str
    breaker_open: bool
    consecutive_failures: int
    reset_run_id: str


def build_job_runtime(
    *,
    environ: dict[str, str] | None = None,
    settings_store: ManagedSettingsStore | None = None,
) -> JobRuntime:
    """Build the environment-resolved runtime; raises when storage cannot be resolved."""

    values = dict(os.environ) if environ is None else dict(environ)
    database_path = jobs_database_path(values)
    try:
        store = JobRunStore(database_path)
    except (OSError, sqlite3.Error) as exc:
        raise JobsStorageUnavailableError(
            f"jobs database is not usable at {database_path} ({type(exc).__name__})"
        ) from exc
    settings = settings_store or ManagedSettingsStore(
        path=default_settings_path(values)
    )
    return JobRuntime(
        store=store,
        settings_store=settings,
        environ=values,
        lock_dir=database_path.parent / "locks",
    )


def get_job_runtime(request: Request) -> JobRuntime:
    """Return the installed runtime, or the one this process resolves from its environment."""

    installed = getattr(request.app.state, _STATE_NAME, None)
    if isinstance(installed, JobRuntime):
        return installed
    try:
        runtime = build_job_runtime()
    except JobsStorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    setattr(request.app.state, _STATE_NAME, runtime)
    return runtime



def _http_error(error: JobsError) -> HTTPException:
    for error_type, status_code in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return HTTPException(status_code=status_code, detail=error.code)
    return HTTPException(status_code=400, detail=error.code)


@router.get("/runs/{run_id}")
def get_job_run(run_id: str, runtime: JobRuntime = Depends(get_job_runtime)) -> object:
    detail = runtime.run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="job_run_not_found")
    return detail


@router.get("")
def list_jobs(runtime: JobRuntime = Depends(get_job_runtime)) -> object:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "storage": runtime.storage_status(),
        "config": runtime.config_status(),
        "postgres": runtime.postgres_status(),
        "tasks": runtime.task_views(),
    }


@router.get("/{task_id}/runs", response_model=JobRunListResponse)
def list_job_runs(
    task_id: str,
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    runtime: JobRuntime = Depends(get_job_runtime),
) -> JobRunListResponse:
    if status is not None and status not in RUN_STATUSES:
        raise HTTPException(status_code=422, detail="job_invalid_status")
    try:
        runs = runtime.history(task_id, status=status, limit=limit, offset=offset)
        total = runtime.history_total(task_id, status=status)
    except JobsError as exc:
        raise _http_error(exc) from exc
    return JobRunListResponse(
        task_id=task_id,
        total=total,
        limit=limit,
        offset=offset,
        runs=[row.as_dict() for row in runs],
    )


@router.post("/{task_id}/run", status_code=202, response_model=JobTriggerResponse)
def trigger_job(
    task_id: str,
    request: Request,
    body: JobTriggerRequest | None = None,
    runtime: JobRuntime = Depends(get_job_runtime),
) -> JobTriggerResponse:
    try:
        outcome = runtime.trigger(
            task_id,
            params=body.params if body is not None else {},
            operator=current_operator(request),
            trigger_source=MANUAL_TRIGGER,
        )
    except JobsError as exc:
        raise _http_error(exc) from exc
    return JobTriggerResponse(**outcome.as_dict())


@router.post("/{task_id}/reset", response_model=JobBreakerResetResponse)
def reset_job_breaker(
    task_id: str,
    request: Request,
    runtime: JobRuntime = Depends(get_job_runtime),
) -> JobBreakerResetResponse:
    try:
        result = runtime.reset_breaker(task_id, operator=current_operator(request))
    except JobsError as exc:
        raise _http_error(exc) from exc
    return JobBreakerResetResponse(**result)


__all__ = [
    "build_job_runtime",
    "get_job_runtime",
    "router",
]
