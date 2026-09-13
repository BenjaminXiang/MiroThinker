"""Bounded read-only HTTP surface for the Canonical V2 access log."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import csv
import io
import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field

from backend.services.canonical_v2_access_log import (
    AccessLogExport,
    AccessLogStore,
    AccessLogTurnStatus,
)


router = APIRouter(prefix="/api/canonical-v2/admin/access-logs")

_STATUSES = frozenset({"completed", "error", "interrupted"})
_STATE_NAME = "canonical_v2_access_log_store"
_QUERY_TYPE_MAX = 120
_IDENTITY_MAX = 120
_STATS_DEFAULT_WINDOW_DAYS = 30
_EXPORT_FORMATS = frozenset({"csv", "jsonl"})
_EXPORT_MAX_TURNS = 20000
_EXPORT_DEFAULT_TURNS = 5000
_DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}")

_CSV_COLUMNS = (
    "session_id",
    "user_identity",
    "turn_id",
    "turn_count",
    "query_type",
    "status",
    "started_at",
    "finished_at",
    "latency_ms",
    "answer_style",
    "query",
    "answer_text",
    "error_detail",
    "citations",
    "suggested_followups",
)


class AccessLogSessionItem(BaseModel):
    session_id: str
    started_at: str
    last_active_at: str
    turn_count: int
    first_query: str
    statuses: list[str]
    identities: list[str]


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
    user_identity: str


class AccessLogSessionDetailResponse(BaseModel):
    session: AccessLogSessionItem
    turns: list[AccessLogTurnItem]


class AccessLogStatisticsWindow(BaseModel):
    since: str
    until: str
    since_defaulted: bool


class AccessLogStatisticsTotals(BaseModel):
    sessions: int
    turns: int
    errors: int
    interrupted: int
    error_rate: float


class AccessLogDayCountItem(BaseModel):
    day: str
    sessions: int
    turns: int


class AccessLogQueryTypeItem(BaseModel):
    query_type: str
    turns: int


class AccessLogIdentityItem(BaseModel):
    identity: str
    turns: int


class AccessLogQueryItem(BaseModel):
    query: str
    turns: int


class AccessLogStatisticsResponse(BaseModel):
    window: AccessLogStatisticsWindow
    totals: AccessLogStatisticsTotals
    daily: list[AccessLogDayCountItem]
    query_types: list[AccessLogQueryTypeItem]
    identities: list[AccessLogIdentityItem]
    top_queries: list[AccessLogQueryItem]


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


def _validated_query_type(value: str | None) -> str | None:
    """``query_type`` is matched exactly; an empty value selects the unrecorded bucket."""

    if value is None:
        return None
    if len(value) > _QUERY_TYPE_MAX:
        raise _unprocessable(
            f"query_type must be at most {_QUERY_TYPE_MAX} characters"
        )
    return value


def _validated_identity(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text or len(text) > _IDENTITY_MAX:
        raise _unprocessable(
            f"identity must contain 1..{_IDENTITY_MAX} characters when provided"
        )
    return text


def _validated_bound(value: str, *, end_of_day: bool, name: str) -> str:
    """Normalize one time bound to a fixed-width UTC ISO-8601 instant."""

    text = value.strip()
    if _DATE_ONLY.fullmatch(text):
        try:
            day = date.fromisoformat(text)
        except ValueError:
            raise _unprocessable(f"{name} must be a valid date") from None
        if end_of_day:
            moment = datetime(
                day.year, day.month, day.day, 23, 59, 59, 999999, tzinfo=UTC
            )
        else:
            moment = datetime(day.year, day.month, day.day, tzinfo=UTC)
    else:
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            raise _unprocessable(
                f"{name} must be a date (YYYY-MM-DD) or an ISO-8601 datetime"
            ) from None
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise _unprocessable(f"{name} must carry an explicit UTC offset")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _validated_time_range(
    since: str | None, until: str | None
) -> tuple[str | None, str | None]:
    start = (
        None
        if since is None
        else _validated_bound(since, end_of_day=False, name="since")
    )
    end = (
        None
        if until is None
        else _validated_bound(until, end_of_day=True, name="until")
    )
    if start is not None and end is not None and start > end:
        raise _unprocessable("since must not be later than until")
    return start, end


def _validated_turn_window(since: str | None, until: str | None) -> tuple[str, str]:
    """Resolve the statistics window, defaulting to the last 30 days."""

    now = datetime.now(UTC)
    if until is None:
        end = now.isoformat(timespec="microseconds")
    else:
        end = _validated_bound(until, end_of_day=True, name="until")
    if since is None:
        start = (now - timedelta(days=_STATS_DEFAULT_WINDOW_DAYS)).isoformat(
            timespec="microseconds"
        )
    else:
        start = _validated_bound(since, end_of_day=False, name="since")
    if start > end:
        raise _unprocessable("since must not be later than until")
    return start, end


def _validated_window(limit: int, offset: int) -> None:
    if offset + limit > 10000:
        raise _unprocessable("offset + limit must not exceed 10000")


def _session_item(summary: Any) -> AccessLogSessionItem:
    return AccessLogSessionItem(
        session_id=summary.session_id,
        started_at=summary.started_at,
        last_active_at=summary.last_active_at,
        turn_count=summary.turn_count,
        first_query=summary.first_query,
        statuses=list(summary.statuses),
        identities=list(summary.identities),
    )


def _turn_item(turn: Any) -> AccessLogTurnItem:
    return AccessLogTurnItem(
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
        user_identity=turn.user_identity,
    )


def _export_document(export: AccessLogExport, *, export_format: str) -> str:
    if export_format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(_CSV_COLUMNS)
        for turn in export.turns:
            writer.writerow(
                (
                    turn.session_id,
                    turn.user_identity,
                    turn.turn_id,
                    turn.turn_count,
                    turn.query_type,
                    turn.status,
                    turn.started_at,
                    turn.finished_at,
                    turn.latency_ms,
                    turn.answer_style,
                    turn.query,
                    turn.answer_text,
                    turn.error_detail or "",
                    json.dumps(list(turn.citations), ensure_ascii=False),
                    json.dumps(list(turn.suggested_followups), ensure_ascii=False),
                )
            )
        return buffer.getvalue()
    lines = []
    for turn in export.turns:
        lines.append(
            json.dumps(
                {
                    "session_id": turn.session_id,
                    "user_identity": turn.user_identity,
                    "turn_id": turn.turn_id,
                    "turn_count": turn.turn_count,
                    "query_type": turn.query_type,
                    "status": turn.status,
                    "started_at": turn.started_at,
                    "finished_at": turn.finished_at,
                    "latency_ms": turn.latency_ms,
                    "answer_style": turn.answer_style,
                    "query": turn.query,
                    "answer_text": turn.answer_text,
                    "error_detail": turn.error_detail,
                    "citations": list(turn.citations),
                    "suggested_followups": list(turn.suggested_followups),
                },
                ensure_ascii=False,
            )
        )
    return "".join(line + "\n" for line in lines)


@router.get("/sessions", response_model=AccessLogSessionPage)
def list_access_log_sessions(
    q: str | None = None,
    status: str | None = None,
    query_type: str | None = None,
    identity: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    store: AccessLogStore = Depends(_get_store),
) -> AccessLogSessionPage:
    query_text = _validated_q(q)
    status_filter = _validated_status(status)
    type_filter = _validated_query_type(query_type)
    identity_filter = _validated_identity(identity)
    start, end = _validated_time_range(since, until)
    _validated_window(limit, offset)
    sessions, total = store.list_sessions(
        query_text=query_text,
        status=status_filter,
        query_type=type_filter,
        identity=identity_filter,
        since=start,
        until=end,
        limit=limit,
        offset=offset,
    )
    return AccessLogSessionPage(
        sessions=[_session_item(item) for item in sessions],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=AccessLogStatisticsResponse)
def access_log_statistics(
    q: str | None = None,
    status: str | None = None,
    query_type: str | None = None,
    identity: str | None = None,
    since: str | None = None,
    until: str | None = None,
    top_limit: Annotated[int, Query(ge=1, le=50)] = 10,
    store: AccessLogStore = Depends(_get_store),
) -> AccessLogStatisticsResponse:
    query_text = _validated_q(q)
    status_filter = _validated_status(status)
    type_filter = _validated_query_type(query_type)
    identity_filter = _validated_identity(identity)
    start, end = _validated_turn_window(since, until)
    statistics = store.statistics(
        query_text=query_text,
        status=status_filter,
        query_type=type_filter,
        identity=identity_filter,
        since=start,
        until=end,
        top_limit=top_limit,
    )
    return AccessLogStatisticsResponse(
        window=AccessLogStatisticsWindow(
            since=statistics.since,
            until=statistics.until,
            since_defaulted=since is None,
        ),
        totals=AccessLogStatisticsTotals(
            sessions=statistics.sessions,
            turns=statistics.turns,
            errors=statistics.errors,
            interrupted=statistics.interrupted,
            error_rate=statistics.error_rate,
        ),
        daily=[
            AccessLogDayCountItem(
                day=item.day, sessions=item.sessions, turns=item.turns
            )
            for item in statistics.daily
        ],
        query_types=[
            AccessLogQueryTypeItem(query_type=item.key, turns=item.turns)
            for item in statistics.query_types
        ],
        identities=[
            AccessLogIdentityItem(identity=item.key, turns=item.turns)
            for item in statistics.identities
        ],
        top_queries=[
            AccessLogQueryItem(query=item.key, turns=item.turns)
            for item in statistics.top_queries
        ],
    )


@router.get("/export")
def export_access_log_turns(
    format: str = "csv",
    q: str | None = None,
    status: str | None = None,
    query_type: str | None = None,
    identity: str | None = None,
    since: str | None = None,
    until: str | None = None,
    max_turns: Annotated[int, Query(ge=1, le=_EXPORT_MAX_TURNS)] = (
        _EXPORT_DEFAULT_TURNS
    ),
    store: AccessLogStore = Depends(_get_store),
) -> Response:
    """Export the turns of the matching sessions; the same filters as the page."""

    if format not in _EXPORT_FORMATS:
        raise _unprocessable("format must be one of csv, jsonl")
    query_text = _validated_q(q)
    status_filter = _validated_status(status)
    type_filter = _validated_query_type(query_type)
    identity_filter = _validated_identity(identity)
    start, end = _validated_time_range(since, until)
    export = store.export_turns(
        query_text=query_text,
        status=status_filter,
        query_type=type_filter,
        identity=identity_filter,
        since=start,
        until=end,
        max_turns=max_turns,
    )
    body = _export_document(export, export_format=format)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    media_type = "text/csv; charset=utf-8" if format == "csv" else "application/x-ndjson"
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="access-logs-{stamp}.{format}"'
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Access-Log-Sessions": str(export.sessions),
            "X-Access-Log-Turns": str(len(export.turns)),
            "X-Access-Log-Truncated": "true" if export.truncated else "false",
        },
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
        session=_session_item(detail.session),
        turns=[_turn_item(turn) for turn in detail.turns],
    )


__all__ = ["router"]
