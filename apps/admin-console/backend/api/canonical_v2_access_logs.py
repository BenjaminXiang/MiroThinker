"""Bounded read-only HTTP surface for the Canonical V2 access log."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field

from backend.services.canonical_v2_access_log import (
    AccessLogStore,
    AccessLogTurnStatus,
)


router = APIRouter(prefix="/api/canonical-v2/admin/access-logs")

_STATUSES = frozenset({"completed", "error", "interrupted"})
_STATE_NAME = "canonical_v2_access_log_store"


class AccessLogSessionItem(BaseModel):
    session_id: str
    started_at: str
    last_active_at: str
    turn_count: int
    first_query: str
    statuses: list[str]


class AccessLogSessionPage(BaseModel):
    sessions: list[AccessLogSessionItem]
    total: int
    limit: int
    offset: int


class AccessLogTurnItem(BaseModel):
    turn_id: str
    session_id: str
    turn_count: int
    query: str
    query_type: str
    answer_text: str
    answer_style: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    status: str
    error_detail: str | None = None
    started_at: str
    finished_at: str
    latency_ms: int


class AccessLogSessionDetailResponse(BaseModel):
    session: AccessLogSessionItem
    turns: list[AccessLogTurnItem]


def _get_store(request: Request) -> AccessLogStore:
    store = getattr(request.app.state, _STATE_NAME, None)
    if not isinstance(store, AccessLogStore):
        raise HTTPException(
            status_code=503,
            detail="canonical_v2_access_log_unavailable",
        )
    return store


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _validated_status(value: str | None) -> AccessLogTurnStatus | None:
    if value is None:
        return None
    if value not in _STATUSES:
        raise _unprocessable(
            "status must be one of completed, error, interrupted"
        )
    return value  # type: ignore[return-value]


def _validated_q(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip() or len(value) > 200:
        raise _unprocessable("q must contain 1..200 characters when provided")
    return value


def _validated_window(limit: int, offset: int) -> None:
    if offset + limit > 10000:
        raise _unprocessable("offset + limit must not exceed 10000")


@router.get("/sessions", response_model=AccessLogSessionPage)
def list_access_log_sessions(
    q: str | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    store: AccessLogStore = Depends(_get_store),
) -> AccessLogSessionPage:
    query_text = _validated_q(q)
    status_filter = _validated_status(status)
    _validated_window(limit, offset)
    sessions, total = store.list_sessions(
        query_text=query_text,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return AccessLogSessionPage(
        sessions=[
            AccessLogSessionItem(
                session_id=item.session_id,
                started_at=item.started_at,
                last_active_at=item.last_active_at,
                turn_count=item.turn_count,
                first_query=item.first_query,
                statuses=list(item.statuses),
            )
            for item in sessions
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{session_id}", response_model=AccessLogSessionDetailResponse)
def get_access_log_session(
    session_id: Annotated[
        str, Path(min_length=1, max_length=200)
    ],
    store: AccessLogStore = Depends(_get_store),
) -> AccessLogSessionDetailResponse:
    detail = store.get_session(session_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail="canonical_v2_access_log_session_not_found",
        )
    return AccessLogSessionDetailResponse(
        session=AccessLogSessionItem(
            session_id=detail.session.session_id,
            started_at=detail.session.started_at,
            last_active_at=detail.session.last_active_at,
            turn_count=detail.session.turn_count,
            first_query=detail.session.first_query,
            statuses=list(detail.session.statuses),
        ),
        turns=[
            AccessLogTurnItem(
                turn_id=turn.turn_id,
                session_id=turn.session_id,
                turn_count=turn.turn_count,
                query=turn.query,
                query_type=turn.query_type,
                answer_text=turn.answer_text,
                answer_style=turn.answer_style,
                citations=list(turn.citations),
                suggested_followups=list(turn.suggested_followups),
                status=turn.status,
                error_detail=turn.error_detail,
                started_at=turn.started_at,
                finished_at=turn.finished_at,
                latency_ms=turn.latency_ms,
            )
            for turn in detail.turns
        ],
    )


__all__ = ["router"]
