"""Admin endpoints for the professor_seed registry.

Per OpenSpec change `prof-seed-admin-console` Phase A. Implements 5 CRUD
endpoints under /api/seeds. The trigger endpoint (POST /api/seeds/{id}/trigger)
is deliberately NOT in this slice — it belongs to Phase B.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.deps import get_pg_conn
from backend.storage.seeds import (
    Seed,
    SeedCreate,
    SeedUpdate,
    create_seed,
    delete_seed,
    get_seed,
    list_seeds,
    update_seed,
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/seeds", response_model=list[Seed])
def list_seeds_endpoint(conn: Any = Depends(get_pg_conn)) -> list[Seed]:
    """List every seed, sorted by (school, department NULLS FIRST, id)."""
    return list_seeds(conn)


@router.get("/seeds/{seed_id}", response_model=Seed)
def get_seed_endpoint(
    seed_id: int, conn: Any = Depends(get_pg_conn)
) -> Seed:
    seed = get_seed(conn, seed_id)
    if seed is None:
        raise HTTPException(status_code=404, detail=f"seed {seed_id} not found")
    return seed


@router.post("/seeds", response_model=Seed, status_code=status.HTTP_201_CREATED)
def create_seed_endpoint(
    payload: SeedCreate, conn: Any = Depends(get_pg_conn)
) -> Seed:
    try:
        return create_seed(conn, payload)
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "error": "seed_url_already_exists",
                "seed_url": str(payload.seed_url),
            },
        )


@router.put("/seeds/{seed_id}", response_model=Seed)
def update_seed_endpoint(
    seed_id: int,
    payload: SeedUpdate,
    conn: Any = Depends(get_pg_conn),
) -> Seed:
    """Update mutable fields. last_run_at and last_run_status are
    pipeline-managed and silently ignored if present in the request body
    (Pydantic strips them automatically since they are not declared on
    SeedUpdate)."""
    try:
        seed = update_seed(conn, seed_id, payload)
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "error": "seed_url_already_exists",
                "seed_url": str(payload.seed_url),
            },
        )
    if seed is None:
        raise HTTPException(status_code=404, detail=f"seed {seed_id} not found")
    return seed


@router.delete(
    "/seeds/{seed_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_seed_endpoint(
    seed_id: int, conn: Any = Depends(get_pg_conn)
) -> Response:
    deleted = delete_seed(conn, seed_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"seed {seed_id} not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
