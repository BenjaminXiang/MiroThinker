"""Bounded read-only HTTP surface for Canonical V2 knowledge gaps."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.canonical_v2_deps import get_knowledge_gap_operations
from src.data_agents.canonical_v2.contracts import GapClass, GapSeverity, GapStatus
from src.data_agents.canonical_v2.knowledge_gap_postgres import (
    GapAdminDetail,
    GapAdminPage,
    GapAdminQuery,
    KnowledgeGapConfigurationError,
    KnowledgeGapIntegrityError,
    KnowledgeGapPersistenceError,
)


router = APIRouter(prefix="/api/canonical-v2/operations")


@router.get("/gaps", response_model=GapAdminPage)
def list_knowledge_gaps(
    statuses: Annotated[list[GapStatus] | None, Query()] = None,
    gap_classes: Annotated[list[GapClass] | None, Query()] = None,
    severities: Annotated[list[GapSeverity] | None, Query()] = None,
    domain: str | None = None,
    path: str | None = None,
    release_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    operations: Any = Depends(get_knowledge_gap_operations),
) -> GapAdminPage:
    query = GapAdminQuery(
        statuses=tuple(statuses or ()),
        gap_classes=tuple(gap_classes or ()),
        severities=tuple(severities or ()),
        domain=domain,
        path=path,
        release_id=release_id,
        limit=limit,
        offset=offset,
    )
    try:
        return operations.list_for_admin(query)
    except KnowledgeGapIntegrityError as exc:
        raise HTTPException(
            status_code=500, detail="Canonical V2 gap data failed validation"
        ) from exc
    except (KnowledgeGapConfigurationError, KnowledgeGapPersistenceError) as exc:
        raise HTTPException(
            status_code=503, detail="Canonical V2 operations are unavailable"
        ) from exc


@router.get("/gaps/{gap_id}", response_model=GapAdminDetail)
def get_knowledge_gap(
    gap_id: str,
    operations: Any = Depends(get_knowledge_gap_operations),
) -> GapAdminDetail:
    try:
        detail = operations.get_for_admin(gap_id)
    except KnowledgeGapIntegrityError as exc:
        raise HTTPException(
            status_code=500, detail="Canonical V2 gap data failed validation"
        ) from exc
    except (KnowledgeGapConfigurationError, KnowledgeGapPersistenceError) as exc:
        raise HTTPException(
            status_code=503, detail="Canonical V2 operations are unavailable"
        ) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Canonical V2 gap not found")
    return detail


__all__ = ["router"]
