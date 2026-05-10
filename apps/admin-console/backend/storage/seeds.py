"""Postgres-backed storage for the professor_seed admin registry.

Per OpenSpec change `prof-seed-admin-console` Phase A. Owns the Pydantic
models for the seed table plus thin SQL helpers consumed by
`backend/api/seeds.py`. Keeps `last_run_status` enum semantics aligned with
Alembic migration V022.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

logger = logging.getLogger(__name__)

# MUST stay in sync with V022_professor_seed.PROFESSOR_SEED_LAST_RUN_STATUSES.
# Phase A only writes `never_run`; the other four values come into use during
# Phase B (pipeline integration).
SeedLastRunStatus = Literal[
    "success",
    "failure",
    "in_progress",
    "never_run",
    "adapter_missing",
]

VALID_LAST_RUN_STATUSES: tuple[str, ...] = (
    "success",
    "failure",
    "in_progress",
    "never_run",
    "adapter_missing",
)


def _normalize_optional_str(value: str | None) -> str | None:
    """Normalize empty / whitespace-only strings to None for nullable columns."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class SeedCreate(BaseModel):
    """Body shape for POST /api/seeds."""

    school: str = Field(..., min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    seed_url: HttpUrl

    @field_validator("school")
    @classmethod
    def _strip_school(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("school must not be blank")
        return stripped

    @field_validator("department", mode="before")
    @classmethod
    def _normalize_department(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _normalize_optional_str(value)
        return value


class SeedUpdate(BaseModel):
    """Body shape for PUT /api/seeds/{id}.

    `last_run_at` and `last_run_status` are intentionally absent: admins may
    not mutate run-status fields. Status is pipeline-managed (Phase B).
    """

    school: str = Field(..., min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    seed_url: HttpUrl

    @field_validator("school")
    @classmethod
    def _strip_school(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("school must not be blank")
        return stripped

    @field_validator("department", mode="before")
    @classmethod
    def _normalize_department(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _normalize_optional_str(value)
        return value


class Seed(BaseModel):
    """Response shape for GET /api/seeds and GET /api/seeds/{id}."""

    id: int
    school: str
    department: str | None
    seed_url: str
    last_run_at: datetime | None
    last_run_status: SeedLastRunStatus
    created_at: datetime
    updated_at: datetime


# --- DB helpers --------------------------------------------------------------
#
# The `conn` parameter is a psycopg.Connection obtained via FastAPI's
# Depends(get_pg_conn). The pool sets `row_factory=dict_row`, so cur.fetchone()
# / fetchall() return dicts directly. Helpers commit explicitly because the
# connection is pool-managed (no implicit autocommit at the pool boundary).
#
# The smoke-test path used by the OpenSpec change sanity script runs through
# psycopg.connect() (default tuple_row); a dict_row override is set on the
# cursor so both call sites see the same shape.


_SELECT_COLUMNS = (
    "id, school, department, seed_url, last_run_at, last_run_status, "
    "created_at, updated_at"
)


def _seed_cursor(conn: Any) -> Any:
    """Open a cursor that always yields dict rows, regardless of conn default."""
    from psycopg.rows import dict_row

    return conn.cursor(row_factory=dict_row)


def list_seeds(conn: Any) -> list[Seed]:
    """List seeds ordered by (school, department NULLS FIRST, id)."""
    sql = (
        f"SELECT {_SELECT_COLUMNS} FROM professor_seed "
        "ORDER BY school ASC, department ASC NULLS FIRST, id ASC"
    )
    with _seed_cursor(conn) as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [Seed.model_validate(r) for r in rows]


def get_seed(conn: Any, seed_id: int) -> Seed | None:
    sql = f"SELECT {_SELECT_COLUMNS} FROM professor_seed WHERE id = %s"
    with _seed_cursor(conn) as cur:
        cur.execute(sql, (seed_id,))
        row = cur.fetchone()
    return Seed.model_validate(row) if row else None


def get_seed_by_url(conn: Any, seed_url: str) -> Seed | None:
    sql = f"SELECT {_SELECT_COLUMNS} FROM professor_seed WHERE seed_url = %s"
    with _seed_cursor(conn) as cur:
        cur.execute(sql, (seed_url,))
        row = cur.fetchone()
    return Seed.model_validate(row) if row else None


def create_seed(conn: Any, payload: SeedCreate) -> Seed:
    sql = (
        "INSERT INTO professor_seed (school, department, seed_url) "
        "VALUES (%s, %s, %s) "
        f"RETURNING {_SELECT_COLUMNS}"
    )
    with _seed_cursor(conn) as cur:
        cur.execute(
            sql,
            (payload.school, payload.department, str(payload.seed_url)),
        )
        row = cur.fetchone()
    conn.commit()
    return Seed.model_validate(row)


def update_seed(conn: Any, seed_id: int, payload: SeedUpdate) -> Seed | None:
    sql = (
        "UPDATE professor_seed "
        "SET school = %s, department = %s, seed_url = %s, updated_at = now() "
        "WHERE id = %s "
        f"RETURNING {_SELECT_COLUMNS}"
    )
    with _seed_cursor(conn) as cur:
        cur.execute(
            sql,
            (payload.school, payload.department, str(payload.seed_url), seed_id),
        )
        row = cur.fetchone()
    if row is None:
        conn.rollback()
        return None
    conn.commit()
    return Seed.model_validate(row)


def delete_seed(conn: Any, seed_id: int) -> bool:
    sql = "DELETE FROM professor_seed WHERE id = %s"
    with conn.cursor() as cur:
        cur.execute(sql, (seed_id,))
        deleted = cur.rowcount > 0
    conn.commit()
    return deleted
