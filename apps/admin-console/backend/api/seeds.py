"""Admin endpoints for the professor_seed registry."""

from __future__ import annotations

import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from functools import lru_cache
from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.deps import get_pg_conn
from backend.storage.seeds import (
    Seed,
    SeedCreate,
    SeedUpdate,
    claim_seed_for_trigger,
    create_seed,
    delete_seed,
    get_seed,
    list_seeds,
    update_seed,
)
from src.data_agents.professor.adapter_resolution import resolve_seed_adapter_name
from src.data_agents.professor.models import ProfessorRosterSeed
from src.data_agents.storage.postgres.pipeline_run import open_pipeline_run

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_DEFAULT_SEED_CONCURRENCY = 4


class SeedTriggerResponse(BaseModel):
    run_id: str
    seed_id: int
    status: str


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


@router.post(
    "/seeds/{seed_id}/trigger",
    response_model=SeedTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_seed_endpoint(
    seed_id: int,
    conn: Any = Depends(get_pg_conn),
) -> SeedTriggerResponse | JSONResponse:
    outcome = trigger_seed_run(conn, seed_id)
    if outcome["status_code"] == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail=f"seed {seed_id} not found")
    if outcome["status_code"] != status.HTTP_202_ACCEPTED:
        return JSONResponse(
            status_code=outcome["status_code"],
            content=outcome["content"],
        )
    return SeedTriggerResponse.model_validate(outcome["content"])


def trigger_seed_run(
    conn: Any,
    seed_id: int,
    *,
    schedule_seed_run: Any | None = None,
) -> dict[str, Any]:
    existing = get_seed(conn, seed_id)
    if existing is None:
        return {"status_code": status.HTTP_404_NOT_FOUND, "content": None}
    allow_adapter_missing = (
        existing.last_run_status == "adapter_missing"
        and _seed_has_registered_adapter(existing)
    )
    seed = claim_seed_for_trigger(
        conn,
        seed_id,
        allow_adapter_missing=allow_adapter_missing,
    )
    if seed is None:
        return {"status_code": status.HTTP_404_NOT_FOUND, "content": None}
    if not seed.trigger_claimed and seed.last_run_status == "in_progress":
        return {
            "status_code": status.HTTP_409_CONFLICT,
            "content": {"error": "already_in_progress", "seed_id": seed_id},
        }
    if not seed.trigger_claimed and seed.last_run_status == "adapter_missing":
        return {
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "content": {
                "error": "adapter_missing",
                "seed_id": seed_id,
                "school": seed.school,
                "department": seed.department,
            },
        }

    run_id = open_pipeline_run(
        conn,
        run_kind="roster_crawl",
        run_scope={
            "source": "admin-console",
            "domain": "professor",
            "action": "single_seed_trigger",
            "seed_id": seed.id,
            "school": seed.school,
            "department": seed.department,
            "seed_url": seed.seed_url,
        },
        triggered_by="admin-console",
    )
    conn.commit()
    scheduler = schedule_seed_run or _schedule_seed_run
    scheduler(seed_id=seed.id, run_id=run_id)
    return {
        "status_code": status.HTTP_202_ACCEPTED,
        "content": {
            "run_id": str(run_id),
            "seed_id": seed.id,
            "status": "in_progress",
        },
    }


def _seed_has_registered_adapter(seed: Seed) -> bool:
    return (
        resolve_seed_adapter_name(
            ProfessorRosterSeed(
                institution=seed.school,
                department=seed.department,
                roster_url=seed.seed_url,
            )
        )
        is not None
    )


def _schedule_seed_run(*, seed_id: int, run_id: UUID | str) -> None:
    future = _seed_run_executor().submit(
        _run_seed_task,
        seed_id=seed_id,
        run_id=str(run_id),
    )
    future.add_done_callback(_log_background_task_failure)


def _run_seed_task(*, seed_id: int, run_id: str) -> None:
    from src.data_agents.professor.seed_runner import run_single_seed
    from src.data_agents.storage.postgres.connection import resolve_dsn

    raw_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    dsn = resolve_dsn(raw_dsn)
    run_single_seed(seed_id, dsn=dsn, run_id=run_id)


@lru_cache(maxsize=1)
def _seed_run_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(
        max_workers=_seed_concurrency_cap(),
        thread_name_prefix="professor-seed-runner",
    )


def _seed_concurrency_cap() -> int:
    raw = os.environ.get("ADMIN_PROFESSOR_SEED_CONCURRENCY")
    if raw is None:
        return _DEFAULT_SEED_CONCURRENCY
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "Invalid ADMIN_PROFESSOR_SEED_CONCURRENCY=%r; using %d",
            raw,
            _DEFAULT_SEED_CONCURRENCY,
        )
        return _DEFAULT_SEED_CONCURRENCY
    return max(1, value)


def shutdown_seed_run_executor() -> None:
    if _seed_run_executor.cache_info().currsize:
        _seed_run_executor().shutdown(wait=False, cancel_futures=False)
        _seed_run_executor.cache_clear()


def _log_background_task_failure(task: Future[Any]) -> None:
    try:
        task.result()
    except Exception:
        logger.exception("Unhandled professor seed background task failure")
