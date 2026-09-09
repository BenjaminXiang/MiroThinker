"""Admin endpoints for the professor_seed registry."""

from __future__ import annotations

import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from functools import lru_cache
from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from psycopg.rows import dict_row

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
_MAX_SEED_TRIGGER_LIMIT = 1000

SeedTriggerMode = Literal["full", "sample", "preview"]


class SeedTriggerRequest(BaseModel):
    mode: SeedTriggerMode = "full"
    limit: int | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_mode_limit(self) -> "SeedTriggerRequest":
        if self.limit is not None and (
            self.limit <= 0 or self.limit > _MAX_SEED_TRIGGER_LIMIT
        ):
            raise ValueError(
                f"limit must be between 1 and {_MAX_SEED_TRIGGER_LIMIT}"
            )
        if self.mode == "sample" and self.limit is None:
            raise ValueError("sample mode requires limit")
        return self


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
    payload: SeedTriggerRequest | None = Body(default=None),
    conn: Any = Depends(get_pg_conn),
) -> SeedTriggerResponse | JSONResponse:
    request = payload or SeedTriggerRequest()
    outcome = trigger_seed_run(
        conn,
        seed_id,
        trigger_mode=request.mode,
        limit=request.limit,
    )
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
    trigger_mode: SeedTriggerMode = "full",
    limit: int | None = None,
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
            "trigger_mode": trigger_mode,
            "limit": limit,
        },
        triggered_by="admin-console",
    )
    conn.commit()
    scheduler = schedule_seed_run or _schedule_seed_run
    scheduler(
        seed_id=seed.id,
        run_id=run_id,
        trigger_mode=trigger_mode,
        limit=limit,
    )
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


def _schedule_seed_run(
    *,
    seed_id: int,
    run_id: UUID | str,
    trigger_mode: SeedTriggerMode = "full",
    limit: int | None = None,
) -> None:
    future = _seed_run_executor().submit(
        _run_seed_task,
        seed_id=seed_id,
        run_id=str(run_id),
        trigger_mode=trigger_mode,
        limit=limit,
    )
    future.add_done_callback(_log_background_task_failure)


def _run_seed_task(
    *,
    seed_id: int,
    run_id: str,
    trigger_mode: SeedTriggerMode = "full",
    limit: int | None = None,
) -> None:
    from src.data_agents.professor.seed_runner import run_single_seed
    from src.data_agents.storage.postgres.connection import resolve_dsn

    raw_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    dsn = resolve_dsn(raw_dsn)
    result = run_single_seed(
        seed_id=seed_id,
        dsn=dsn,
        run_id=run_id,
        trigger_mode=trigger_mode,
        limit=limit,
    )
    if not _should_run_quality_closure_after_seed(
        result,
        trigger_mode=trigger_mode,
        limit=limit,
    ):
        return
    try:
        _run_seed_quality_closure_for_seed(
            dsn=dsn,
            seed_id=seed_id,
            run_id=run_id,
            trigger_mode=trigger_mode,
            limit=limit,
        )
    except Exception:
        logger.exception(
            "Professor core profile-paper quality closure failed after "
            "successful seed run %s",
            seed_id,
        )


def _should_run_quality_closure_after_seed(
    result: Any,
    *,
    trigger_mode: SeedTriggerMode,
    limit: int | None,
) -> bool:
    from src.data_agents.professor.core_profile_paper_quality_closure import (
        should_run_seed_quality_closure,
    )

    return should_run_seed_quality_closure(
        seed_status=getattr(result, "status", None),
        trigger_mode=trigger_mode,
        limit=limit,
    )


def _run_seed_quality_closure_for_seed(
    *,
    dsn: str,
    seed_id: int,
    run_id: str,
    trigger_mode: SeedTriggerMode,
    limit: int | None,
) -> None:
    from src.data_agents.professor import core_profile_paper_quality_closure

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        report = core_profile_paper_quality_closure.run_seed_quality_closure(
            conn=conn,
            seed_id=seed_id,
            run_id=run_id,
            trigger_mode=trigger_mode,
            limit=limit,
            dsn=dsn,
            publication_extractor=_build_seed_followup_publication_extractor(),
            commit_after_stage=True,
        )
        conn.commit()
    logger.info(
        "Professor core profile-paper quality closure for seed %s finished "
        "with status=%s stage_counts=%s",
        seed_id,
        report.status,
        report.stage_counts,
    )


def _build_seed_followup_publication_extractor():
    if _env_flag_disabled("ADMIN_SEED_LLM_PUBLICATION_EXTRACTION"):
        return None

    from src.data_agents.paper.llm_publication_extractor import (
        build_llm_publication_extractor,
    )

    profile_name = os.environ.get("ADMIN_SEED_LLM_PUBLICATION_PROFILE", "gemma4")
    force_llm = _env_flag_enabled("ADMIN_SEED_FORCE_LLM_PUBLICATION_EXTRACTION")
    try:
        return build_llm_publication_extractor(profile_name, force_llm=force_llm)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LLM publication extractor unavailable for seed follow-up; "
            "falling back to rule extraction (%s: %s)",
            exc.__class__.__name__,
            exc,
        )
        return None


def _env_flag_disabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"0", "false", "no", "off"}


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


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
