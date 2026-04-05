from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.deps import get_store
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

router = APIRouter(prefix="/api")


class DomainEnum(str, Enum):
    professor = "professor"
    company = "company"
    paper = "paper"
    patent = "patent"


class PaginatedResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


@router.get("/{domain}", response_model=PaginatedResponse)
def list_domain(
    domain: DomainEnum,
    q: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = "display_name",
    sort_order: Literal["asc", "desc"] = "asc",
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> PaginatedResponse:
    offset = (page - 1) * page_size
    try:
        items, total = store.list_domain_paginated(
            domain.value,
            query=q,
            offset=offset,
            limit=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid sort_by. Allowed: id, display_name",
        )
    return PaginatedResponse(
        items=[item.model_dump(mode="json") for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{domain}/{object_id}")
def get_domain_object(
    domain: DomainEnum,
    object_id: str,
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> dict[str, Any]:
    obj = store.get_object(domain.value, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return obj.model_dump(mode="json")
