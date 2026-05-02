from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.api.domains import (
    UpdateRecordRequest,
    _apply_update,
    _finish_admin_run,
    _get_released_object,
    _open_admin_run,
    _soft_delete,
)
from backend.deps import get_pg_conn

router = APIRouter(prefix="/api/batch")
_DOMAINS = ("professor", "company", "paper", "patent")


class BatchQualityRequest(BaseModel):
    ids: list[str] = Field(min_length=1)
    quality_status: Literal["ready", "needs_review", "low_confidence", "needs_enrichment"]


class BatchQualityResponse(BaseModel):
    updated: int


class BatchDeleteRequest(BaseModel):
    ids: list[str] = Field(min_length=1)


class BatchDeleteResponse(BaseModel):
    deleted: int


@router.patch("/quality", response_model=BatchQualityResponse)
def batch_update_quality(
    body: BatchQualityRequest,
    conn: Any = Depends(get_pg_conn),
) -> BatchQualityResponse:
    updated = 0
    for obj_id in body.ids:
        for domain in _DOMAINS:
            obj = _get_released_object(conn, domain, obj_id, include_evidence=False)
            if obj is None:
                continue

            run_id = _open_admin_run(
                conn,
                domain=domain,
                object_id=obj_id,
                action="batch_quality",
            )
            try:
                _apply_update(
                    conn,
                    domain,
                    obj_id,
                    UpdateRecordRequest(quality_status=body.quality_status),
                    run_id,
                )
                _finish_admin_run(conn, run_id, status="succeeded")
            except Exception as exc:
                _finish_admin_run(
                    conn,
                    run_id,
                    status="failed",
                    error_summary={"message": str(exc)},
                )
                raise
            updated += 1
            break
    return BatchQualityResponse(updated=updated)


@router.post("/delete", response_model=BatchDeleteResponse)
def batch_delete(
    body: BatchDeleteRequest,
    conn: Any = Depends(get_pg_conn),
) -> BatchDeleteResponse:
    deleted = 0
    for obj_id in body.ids:
        for domain in _DOMAINS:
            obj = _get_released_object(conn, domain, obj_id, include_evidence=False)
            if obj is None:
                continue

            run_id = _open_admin_run(
                conn,
                domain=domain,
                object_id=obj_id,
                action="batch_delete",
            )
            try:
                _soft_delete(conn, domain, obj_id, run_id)
                _finish_admin_run(conn, run_id, status="succeeded")
            except Exception as exc:
                _finish_admin_run(
                    conn,
                    run_id,
                    status="failed",
                    error_summary={"message": str(exc)},
                )
                raise
            deleted += 1
            break
    return BatchDeleteResponse(deleted=deleted)
