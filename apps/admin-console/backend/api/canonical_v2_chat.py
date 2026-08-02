"""Thin FastAPI transport for one explicitly installed Canonical V2 chat adapter."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
import queue
import secrets
import threading
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

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
    idle_keepwarm = getattr(request.app.state, "canonical_v2_idle_keepwarm", None)
    mark_activity = getattr(idle_keepwarm, "mark_activity", None)
    if callable(mark_activity):
        mark_activity()
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


@router.post("/chat/stream", response_class=StreamingResponse)
def chat_stream(
    payload: ChatRequest,
    response: Response,
    request: Request,
    miroflow_chat_session: str | None = Cookie(default=None),
    adapter: CanonicalV2ChatAdapter = Depends(get_canonical_v2_chat_adapter),
) -> StreamingResponse:
    """Server-sent events for one chat turn.

    Events (``event:`` / ``data:`` JSON): ``stage`` (planning / retrieval /
    synthesis), ``plan_done`` (lanes, domains, web views), ``retrieval_done``
    (per-lane status and candidate counts), ``answer`` (the full ChatResponse
    JSON), ``done``, or ``error``.  Only stage summaries and counts are
    streamed — never raw evidence, internal ids, or snapshots.
    """
    from backend.services.canonical_v2_admin import (
        CanonicalV2ConsumerIntegrityError,
    )

    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query must be non-empty")
    idle_keepwarm = getattr(request.app.state, "canonical_v2_idle_keepwarm", None)
    mark_activity = getattr(idle_keepwarm, "mark_activity", None)
    if callable(mark_activity):
        mark_activity()
    session_id = miroflow_chat_session or _new_session_id()
    set_session_cookie = miroflow_chat_session is None

    events: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()

    def emit(name: str, data: dict[str, Any]) -> None:
        events.put((name, data))

    def run_turn() -> None:
        try:
            chat_response = adapter.answer_stream(
                query=query,
                session_id=session_id,
                option_id=payload.entity_id_hint,
                as_of=_utc_now(),
                progress=emit,
            )
            events.put(
                (
                    "answer",
                    chat_response.model_dump(mode="json"),
                )
            )
            events.put(("done", {}))
        except CanonicalV2InvalidOption as exc:
            events.put(("error", {"detail": _INVALID_OPTION_DETAIL}))
        except (CanonicalV2ReleaseMismatch, CanonicalV2ConsumerIntegrityError):
            events.put(("error", {"detail": _RELEASE_MISMATCH_DETAIL}))
        except KnowledgeReadIntegrityError:
            events.put(("error", {"detail": _RELEASE_MISMATCH_DETAIL}))
        except CanonicalV2MappingError:
            events.put(("error", {"detail": "canonical_v2_consumer_integrity_error"}))
        except Exception as exc:  # noqa: BLE001 - the stream must not hang
            logger.warning("canonical v2 stream turn failed: %s", exc)
            events.put(("error", {"detail": "internal_error"}))

    def render(name: str, data: dict[str, Any]) -> str:
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return f"event: {name}\ndata: {body}\n\n"

    def generate() -> Any:
        worker = threading.Thread(target=run_turn, daemon=True)
        worker.start()
        while True:
            name, data = events.get()
            yield render(name, data)
            if name in ("done", "error"):
                break

    stream = StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    if set_session_cookie:
        # The injected Response parameter's cookies are dropped when the
        # route returns a fresh StreamingResponse; set the session cookie on
        # the stream itself so multi-turn referents survive across events.
        stream.set_cookie(
            _SESSION_COOKIE,
            session_id,
            max_age=_SESSION_TTL_SECONDS,
            httponly=True,
            samesite="lax",
        )
    return stream


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
