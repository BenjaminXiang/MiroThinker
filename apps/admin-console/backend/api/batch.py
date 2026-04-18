from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.deps import get_store
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

router = APIRouter(prefix="/api/batch")


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
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> BatchQualityResponse:
    updated = 0
    for obj_id in body.ids:
        # We don't know the domain, so query across all domains
        for domain in ("professor", "company", "paper", "patent"):
            obj = store.get_object(domain, obj_id)
            if obj is not None:
                patched = obj.model_copy(update={"quality_status": body.quality_status})
                if store.update_object(patched):
                    updated += 1
                break
    return BatchQualityResponse(updated=updated)


@router.post("/delete", response_model=BatchDeleteResponse)
def batch_delete(
    body: BatchDeleteRequest,
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> BatchDeleteResponse:
    deleted = store.delete_objects(body.ids)
    return BatchDeleteResponse(deleted=deleted)
