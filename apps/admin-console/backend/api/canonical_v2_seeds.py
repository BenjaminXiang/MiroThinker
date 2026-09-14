"""Bounded HTTP surface for the W3 professor-seed registry.

The registry rows and their invariants stay in ``backend/storage/seeds.py`` (unique seed URL,
pipeline-managed last-run fields); this module only adds the V2 shell's conventions: a Postgres probe
so a thin deployment degrades instead of 500-ing, and a trigger that goes through the shared gate
rather than starting its own work.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, model_validator

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
from src.data_agents.canonical_v2.jobs import (
    MANUAL_TRIGGER,
    JobRunStore,
    JobRuntime,
    JobsError,
    JobsStorageUnavailableError,
    jobs_database_path,
)
from src.data_agents.canonical_v2.managed_config import (
    ManagedSettingsStore,
    default_settings_path,
)

import psycopg

router = APIRouter(prefix="/api/canonical-v2/admin")

_STATE_NAME = "canonical_v2_seed_gate"
_MAX_OPERATOR_LENGTH = 200

SeedTriggerMode = Literal["full", "sample", "preview"]
SAMPLE_TASK_ID = "admin-seed-refresh-sample"
REFRESH_TASK_MODES: dict[str, str] = {
    "preview": "admin-seed-refresh",
    "full": "admin-seed-refresh",
    "sample": SAMPLE_TASK_ID,
}
SAMPLE_LIMITS: tuple[str, ...] = ("5", "20", "50", "100")
POSTGRES_UNAVAILABLE = "seeds_require_postgres"


class SeedTriggerRequest(BaseModel):
    mode: SeedTriggerMode = "preview"
    limit: int | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_mode_limit(self) -> "SeedTriggerRequest":
        if self.mode == "sample" and self.limit is None:
            raise ValueError("sample mode requires limit")
        if self.limit is not None and str(self.limit) not in SAMPLE_LIMITS:
            raise ValueError(f"limit must be one of: {', '.join(SAMPLE_LIMITS)}")
        if self.mode not in {"sample", "preview"} and self.limit is not None:
            raise ValueError("limit is only accepted for sample and preview modes")
        return self


class SeedTriggerResponse(BaseModel):
    run_id: str
    seed_id: int
    status: str
    task_id: str
    mode: str
    skip_reason: str | None = None


def get_seed_gate(request: Request) -> JobRuntime:
    installed = getattr(request.app.state, _STATE_NAME, None)
    if isinstance(installed, JobRuntime):
        return installed
    values = dict(os.environ)
    try:
        runtime = JobRuntime(
            store=JobRunStore(jobs_database_path(values)),
            settings_store=ManagedSettingsStore(path=default_settings_path(values)),
            environ=values,
            lock_dir=jobs_database_path(values).parent / "locks",
        )
    except (JobsStorageUnavailableError, OSError) as exc:
        raise HTTPException(status_code=503, detail="jobs_storage_unavailable") from exc
    setattr(request.app.state, _STATE_NAME, runtime)
    return runtime


def require_postgres(gate: JobRuntime) -> None:
    if not gate.postgres_status().get("available"):
        raise HTTPException(status_code=503, detail=POSTGRES_UNAVAILABLE)


def _operator(request: Request) -> str:
    raw = request.headers.get("X-Remote-User", "").strip()
    return raw[:_MAX_OPERATOR_LENGTH] if raw else "anonymous"


def _seed_connection() -> Any:
    from src.data_agents.storage.postgres.connection import connect

    raw = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    from src.data_agents.storage.postgres.connection import resolve_dsn

    return connect(resolve_dsn(raw))


def _seed_exists(seed_id: int) -> bool:
    return _with_seed_connection(lambda conn: get_seed(conn, seed_id)) is not None


def _with_seed_connection(work: Any) -> Any:
    conn = _seed_connection()
    enter = getattr(conn, "__enter__", None)
    if callable(enter):
        with conn as live:
            return work(live)
    try:
        return work(conn)
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()


@router.get("/seeds", response_model=list[Seed])
def list_seeds_endpoint(gate: JobRuntime = Depends(get_seed_gate)) -> list[Seed]:
    require_postgres(gate)
    return _with_seed_connection(list_seeds)


@router.get("/seeds/{seed_id}", response_model=Seed)
def get_seed_endpoint(seed_id: int, gate: JobRuntime = Depends(get_seed_gate)) -> Seed:
    require_postgres(gate)
    seed = _with_seed_connection(lambda conn: get_seed(conn, seed_id))
    if seed is None:
        raise HTTPException(status_code=404, detail=f"seed {seed_id} not found")
    return seed


@router.post("/seeds", response_model=Seed, status_code=status.HTTP_201_CREATED)
def create_seed_endpoint(
    payload: SeedCreate, gate: JobRuntime = Depends(get_seed_gate)
) -> Seed:
    require_postgres(gate)
    try:
        return _with_seed_connection(lambda conn: create_seed(conn, payload))
    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail={"error": "seed_url_already_exists", "seed_url": str(payload.seed_url)},
        ) from None


@router.put("/seeds/{seed_id}", response_model=Seed)
def update_seed_endpoint(
    seed_id: int, payload: SeedUpdate, gate: JobRuntime = Depends(get_seed_gate)
) -> Seed:
    require_postgres(gate)
    try:
        seed = _with_seed_connection(lambda conn: update_seed(conn, seed_id, payload))
    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail={"error": "seed_url_already_exists", "seed_url": str(payload.seed_url)},
        ) from None
    if seed is None:
        raise HTTPException(status_code=404, detail=f"seed {seed_id} not found")
    return seed


@router.delete(
    "/seeds/{seed_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_seed_endpoint(seed_id: int, gate: JobRuntime = Depends(get_seed_gate)) -> Response:
    require_postgres(gate)
    deleted = _with_seed_connection(lambda conn: delete_seed(conn, seed_id))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"seed {seed_id} not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/seeds/{seed_id}/trigger",
    response_model=SeedTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_seed_endpoint(
    seed_id: int,
    request: Request,
    payload: SeedTriggerRequest | None = None,
    gate: JobRuntime = Depends(get_seed_gate),
) -> SeedTriggerResponse:
    require_postgres(gate)
    if not _seed_exists(seed_id):
        raise HTTPException(status_code=404, detail=f"seed {seed_id} not found")
    body = payload or SeedTriggerRequest()
    task_id = REFRESH_TASK_MODES[body.mode]
    # Each task declares only what its own argv uses: the sample task fixes the mode in its template
    # and takes the bound, the other one takes the mode. Passing both would be refused by the gate.
    params: dict[str, str] = {"seed_id": str(seed_id)}
    if task_id == SAMPLE_TASK_ID:
        params["limit"] = str(body.limit)
    else:
        params["mode"] = body.mode
    try:
        outcome = gate.trigger(
            task_id,
            params=params,
            operator=_operator(request),
            trigger_source=MANUAL_TRIGGER,
        )
    except JobsError as exc:
        http_status = 409 if exc.code in {"job_already_running", "job_breaker_open"} else 422
        if exc.code == "job_postgres_unavailable":
            http_status = 503
        raise HTTPException(status_code=http_status, detail=exc.code) from exc
    return SeedTriggerResponse(
        run_id=outcome.run_id,
        seed_id=seed_id,
        status=outcome.status,
        task_id=task_id,
        mode=body.mode,
        skip_reason=outcome.skip_reason,
    )


@router.get("/seeds/{seed_id}/runs")
def list_seed_runs(
    seed_id: int,
    limit: int = Query(default=20, ge=1, le=200),
    gate: JobRuntime = Depends(get_seed_gate),
) -> dict[str, Any]:
    """Run polling for one seed: the refresh runs this seed started, newest first."""

    require_postgres(gate)
    collected: list[dict[str, Any]] = []
    for task_id in sorted(set(REFRESH_TASK_MODES.values())):
        for run in gate.history(task_id, limit=limit):
            if _command_targets_seed(run.command, seed_id):
                collected.append(run.as_dict())
    collected.sort(key=lambda item: str(item.get("started_at") or ""), reverse=True)
    return {"seed_id": seed_id, "total": len(collected), "runs": collected[:limit]}


def _command_targets_seed(command: tuple[str, ...] | list[str], seed_id: int) -> bool:
    """A run belongs to a seed when the recorded argv names it — the run row is the source of truth."""

    tokens = list(command)
    for index, token in enumerate(tokens[:-1]):
        if token in {"--seed-id", "--seed_id"} and tokens[index + 1] == str(seed_id):
            return True
    return False


__all__ = [
    "REFRESH_TASK_MODES",
    "SeedTriggerRequest",
    "SeedTriggerResponse",
    "get_seed_gate",
    "require_postgres",
    "router",
]
