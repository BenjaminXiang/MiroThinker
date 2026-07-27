"""Thin FastAPI transport for one explicitly installed Canonical V2 chat adapter."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

from backend.api.chat_contracts import (
    ChatFeedbackRequest,
    ChatFeedbackResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionResetResponse,
)
from backend.canonical_v2_deps import (
    get_canonical_v2_admin_runtime,
    get_canonical_v2_chat_adapter,
)
from backend.services.canonical_v2_chat import (
    CanonicalV2ChatAdapter,
    CanonicalV2InvalidOption,
    CanonicalV2MappingError,
    CanonicalV2ReleaseMismatch,
)
from src.data_agents.canonical_v2.knowledge_read import KnowledgeReadIntegrityError


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_SESSION_COOKIE = "miroflow_chat_session"
_SESSION_TTL_SECONDS = 30 * 60
_INVALID_OPTION_DETAIL = "canonical_v2_invalid_option"
_RELEASE_MISMATCH_DETAIL = "canonical_v2_release_mismatch"


def _new_session_id() -> str:
    return "session:chat:" + secrets.token_urlsafe(24)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        _SESSION_COOKIE,
        session_id,
        max_age=_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )


@router.post("/chat/session/reset", response_model=ChatSessionResetResponse)
def reset_chat_session(response: Response) -> ChatSessionResetResponse:
    session_id = _new_session_id()
    _set_session_cookie(response, session_id)
    return ChatSessionResetResponse(session_id=session_id)


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    response: Response,
    request: Request,
    miroflow_chat_session: str | None = Cookie(default=None),
    adapter: CanonicalV2ChatAdapter = Depends(get_canonical_v2_chat_adapter),
) -> ChatResponse:
    from backend.services.canonical_v2_admin import (
        CanonicalV2ConsumerIntegrityError,
    )

    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query must be non-empty")
    session_id = miroflow_chat_session or _new_session_id()
    if miroflow_chat_session is None:
        _set_session_cookie(response, session_id)
    try:
        return adapter.answer(
            query=query,
            session_id=session_id,
            option_id=payload.entity_id_hint,
            as_of=_utc_now(),
        )
    except CanonicalV2InvalidOption as exc:
        raise HTTPException(
            status_code=400,
            detail=_INVALID_OPTION_DETAIL,
        ) from exc
    except CanonicalV2ReleaseMismatch as exc:
        raise HTTPException(
            status_code=409,
            detail=_RELEASE_MISMATCH_DETAIL,
        ) from exc
    except CanonicalV2ConsumerIntegrityError as exc:
        logger.warning(
            "Canonical V2 consumer integrity rejection: %s: %s",
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=409,
            detail="canonical_v2_consumer_integrity_error",
        ) from exc
    except KnowledgeReadIntegrityError as exc:
        logger.warning(
            "Canonical V2 knowledge-read integrity rejection: %s: %s",
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=409,
            detail="canonical_v2_consumer_integrity_error",
        ) from exc
    except CanonicalV2MappingError as exc:
        if not hasattr(request.app.state, "canonical_v2_consumer_runtime"):
            raise
        logger.warning(
            "Canonical V2 response mapping rejection: %s: %s",
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=409,
            detail="canonical_v2_consumer_integrity_error",
        ) from exc


@router.post("/chat/feedback", response_model=ChatFeedbackResponse)
def record_chat_feedback(
    payload: ChatFeedbackRequest,
    miroflow_chat_session: str | None = Cookie(default=None),
    runtime: Any = Depends(get_canonical_v2_admin_runtime),
) -> ChatFeedbackResponse:
    from backend.services.canonical_v2_admin import (
        CanonicalV2ConsumerIntegrityError,
    )

    if miroflow_chat_session is None:
        raise HTTPException(
            status_code=409,
            detail="canonical_v2_feedback_checkpoint_required",
        )
    try:
        gap = runtime.record_chat_feedback(
            session_id=miroflow_chat_session,
            feedback_type=payload.feedback_type,
            note=payload.note,
        )
    except CanonicalV2ConsumerIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="canonical_v2_feedback_checkpoint_required",
        ) from exc
    return ChatFeedbackResponse(
        issue_id=gap.gap_id,
        status="filed",
        reported_at=gap.created_at,
    )


__all__ = ["router"]
