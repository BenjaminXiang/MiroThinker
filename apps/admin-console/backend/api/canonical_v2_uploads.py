"""Bounded HTTP surface for the W3 XLSX upload front door.

Admission lives in ``src.data_agents.canonical_v2.uploads`` so the same rules apply whether an upload
arrives over HTTP or from a future operator CLI. This module translates: resolve the runtime, read the
multipart body with a hard size cap, and map typed refusals to stable HTTP codes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from backend.deps import resolve_console_dsn
from backend.services.admin_session import current_operator
from src.data_agents.canonical_v2.jobs import JobRunStore, JobRuntime, jobs_database_path
from src.data_agents.canonical_v2.managed_config import (
    ManagedSettingsStore,
    default_settings_path,
)
from src.data_agents.canonical_v2.uploads import (
    UPLOAD_DOMAINS,
    UploadDomainError,
    UploadDuplicateError,
    UploadError,
    UploadFileTypeError,
    UploadInProgressError,
    UploadNotFoundError,
    UploadRequiresPostgresError,
    UploadRuntime,
    UploadStore,
    UploadTooLargeError,
    UploadsStorageUnavailableError,
    max_upload_bytes,
    uploads_database_path,
)


router = APIRouter(prefix="/api/canonical-v2/admin/uploads")

_STATE_NAME = "canonical_v2_uploads_runtime"
_READ_CHUNK_BYTES = 1024 * 1024
CONSOLE_DATABASE_NOT_CONFIGURED = "console_database_not_configured"

_STATUS_BY_ERROR: tuple[tuple[type[UploadError], int], ...] = (
    (UploadNotFoundError, 404),
    (UploadDomainError, 422),
    (UploadFileTypeError, 400),
    (UploadTooLargeError, 413),
    (UploadDuplicateError, 409),
    (UploadInProgressError, 409),
    (UploadRequiresPostgresError, 503),
    (UploadsStorageUnavailableError, 503),
)


class UploadDetailResponse(BaseModel):
    upload: dict[str, Any]
    run: dict[str, Any] | None = None
    batch: dict[str, Any] | None = None


class UploadListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    domains: list[dict[str, Any]]
    postgres: dict[str, Any]
    uploads: list[dict[str, Any]]


def _postgres_preflight(domain: str, digest: str) -> dict[str, Any] | None:
    """Ask the legacy chain whether this content is already in flight (Postgres side)."""

    from backend.api.upload import _load_active_duplicate_upload, _resolve_upload_dsn
    from src.data_agents.storage.postgres.connection import connect

    with connect(_resolve_upload_dsn()) as conn:
        return _load_active_duplicate_upload(
            conn, domain=domain, file_content_hash=digest
        )


def _batch_progress(batch_id: str) -> dict[str, Any] | None:
    """Project the company enrichment batch the legacy chain created for this upload."""

    from backend.api.upload import _resolve_upload_dsn
    from src.data_agents.storage.postgres.connection import connect

    with connect(_resolve_upload_dsn()) as conn:
        batch = conn.execute(
            """
            SELECT batch_id, status, current_stage, companies_total, companies_selected,
                   companies_processed, companies_succeeded, companies_failed,
                   runner_pid, runner_log_path, started_at, finished_at
              FROM company_enrichment_batch
             WHERE batch_id = %s
            """,
            (batch_id,),
        ).fetchone()
        if batch is None:
            return {"available": False, "reason": "batch_not_found"}
        items = conn.execute(
            """
            SELECT status, count(*)::int AS total
              FROM company_enrichment_company_state
             WHERE batch_id = %s
             GROUP BY status
            """,
            (batch_id,),
        ).fetchall()
    return {
        "available": True,
        "batch": {key: (str(value) if value is not None else None) for key, value in dict(batch).items()},
        "items": {row["status"]: int(row["total"]) for row in items},
    }


def build_upload_runtime(
    *, environ: dict[str, str] | None = None
) -> UploadRuntime:  # pragma: no cover - exercised through the dependency
    values = dict(os.environ) if environ is None else dict(environ)
    gate = JobRuntime(
        store=JobRunStore(jobs_database_path(values)),
        settings_store=ManagedSettingsStore(path=default_settings_path(values)),
        environ=values,
        lock_dir=jobs_database_path(values).parent / "locks",
    )
    store = UploadStore(uploads_database_path(values))
    return UploadRuntime(
        store=store,
        gate=gate,
        repo_root=Path(__file__).resolve().parents[4],
        environ=values,
        preflight=_postgres_preflight,
        batch_reader=_batch_progress,
    )


def get_upload_runtime(request: Request) -> UploadRuntime:
    installed = getattr(request.app.state, _STATE_NAME, None)
    if isinstance(installed, UploadRuntime):
        return installed
    try:
        runtime = build_upload_runtime()
    except (UploadsStorageUnavailableError, OSError) as exc:
        raise HTTPException(status_code=503, detail="uploads_storage_unavailable") from exc
    setattr(request.app.state, _STATE_NAME, runtime)
    return runtime


def _console_dsn(request: Request) -> str | None:
    """The console database this app resolved at start (resolver as fallback)."""

    resolved = getattr(request.app.state, "console_dsn", None)
    return resolved or resolve_console_dsn()


def require_console_database(request: Request, runtime: UploadRuntime) -> None:
    """A commit needs the console database before `runtime.register` can preflight it.

    `register`'s preflight calls the legacy chain's `_resolve_upload_dsn()` outside any
    fail-soft wrapper, so with the console unconfigured the resolver's RuntimeError would
    surface as a 500. The missing configuration answers the same stable 503 as the seeds
    surface (`canonical_v2_seeds.require_postgres`); a database that is configured but
    unreachable keeps this surface's own code, which is the refusal `register` raises.
    """

    if _console_dsn(request) is not None:
        return
    if runtime.postgres_status().get("source") is None:
        raise HTTPException(status_code=503, detail=CONSOLE_DATABASE_NOT_CONFIGURED)
    raise HTTPException(status_code=503, detail=UploadRequiresPostgresError.code)


def _http_error(error: UploadError) -> HTTPException:
    for error_type, status_code in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            detail: Any = error.code
            if isinstance(error, UploadDuplicateError) and error.record is not None:
                detail = {
                    "code": error.code,
                    "upload_id": error.record.upload_id,
                    "status": error.record.status,
                    "created_at": error.record.created_at,
                }
            return HTTPException(status_code=status_code, detail=detail)
    return HTTPException(status_code=400, detail=error.code)


def _read_bounded(file: UploadFile, *, limit: int) -> bytes:
    content = bytearray()
    while True:
        chunk = file.file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > limit:
            raise UploadTooLargeError(f"uploaded file exceeds the {limit} byte limit")
    return bytes(content)


@router.get("", response_model=UploadListResponse)
def list_uploads(
    request: Request,
    domain: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    runtime: UploadRuntime = Depends(get_upload_runtime),
) -> UploadListResponse:
    if domain is not None and domain not in UPLOAD_DOMAINS:
        raise HTTPException(status_code=422, detail="upload_unknown_domain")
    records = runtime.store.list(domain=domain, limit=limit, offset=offset)
    return UploadListResponse(
        total=runtime.store.total(domain=domain),
        limit=limit,
        offset=offset,
        domains=runtime.domains(),
        postgres=runtime.postgres_status(),
        uploads=[record.as_dict() for record in records],
    )


@router.get("/{upload_id}", response_model=UploadDetailResponse)
def get_upload(
    upload_id: str, runtime: UploadRuntime = Depends(get_upload_runtime)
) -> UploadDetailResponse:
    try:
        payload = runtime.detail(upload_id)
    except UploadError as exc:
        raise _http_error(exc) from exc
    return UploadDetailResponse(**payload)


@router.post("/{domain}", status_code=202)
def upload_domain_file(
    domain: str,
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False),
    runtime: UploadRuntime = Depends(get_upload_runtime),
) -> dict[str, Any]:
    limit = max_upload_bytes(dict(os.environ))
    if not dry_run:
        require_console_database(request, runtime)
    try:
        content = _read_bounded(file, limit=limit)
        admission = runtime.register(
            domain=domain,
            filename=file.filename or "",
            content=content,
            operator=current_operator(request),
            dry_run=dry_run,
        )
    except UploadError as exc:
        raise _http_error(exc) from exc
    return {
        "upload": admission.record.as_dict(),
        "outcome": admission.outcome,
        "skip_reason": admission.skip_reason,
    }


__all__ = [
    "build_upload_runtime",
    "get_upload_runtime",
    "require_console_database",
    "router",
]
