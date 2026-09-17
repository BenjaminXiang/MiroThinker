"""The admin-console gate: which paths need a session, and from where.

One ASGI middleware for the serving shell. The acting identity is taken from the
signed session cookie only — a client-supplied ``X-Remote-User`` header is never
read here — and state-changing gated requests additionally have to look
same-origin, which is the whole CSRF story for this console (no tokens).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
import logging
import sqlite3
from typing import Any

from fastapi import Request
from starlette.responses import JSONResponse, RedirectResponse

from backend.services.admin_session import (
    SESSION_COOKIE,
    SessionCodec,
    SessionTicket,
    render_session_cookie,
    request_is_https,
    request_origin,
    session_ticket,
)

logger = logging.getLogger(__name__)

GATED_PAGE_PATHS = frozenset({"/admin", "/logs", "/browse", "/jobs", "/upload", "/seeds"})
GATED_API_PREFIX = "/api/canonical-v2"
SESSION_API_PREFIX = "/api/auth"
PUBLIC_SESSION_PATHS = frozenset({"/api/auth/login"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

PAGE = "page"
API = "api"

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def gated_target(path: str) -> str | None:
    """Classify one request path: a gated page, a gated API, or nothing."""

    if path in GATED_PAGE_PATHS:
        return PAGE
    if path.startswith(GATED_API_PREFIX):
        return API
    if path.startswith(SESSION_API_PREFIX) and path not in PUBLIC_SESSION_PATHS:
        return API
    return None


def same_origin(request: Request) -> bool:
    """Reject a write that a browser tells us came from another site."""

    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != request_origin(request):
        return False
    fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    return fetch_site not in {"cross-site", "same-site"}


def _refusal(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(
        {"detail": detail}, status_code=status_code, headers={"cache-control": "no-store"}
    )


def _resolve_ticket(request: Request) -> SessionTicket | None:
    """Resolve the session, treating an unreadable store as "not signed in"."""

    if SESSION_COOKIE not in request.cookies:
        return None
    try:
        return session_ticket(request)
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        logger.warning("admin session lookup failed (%s)", type(exc).__name__)
        return None


def _refresh_cookie(request: Request, ticket: SessionTicket) -> str | None:
    try:
        token, expires_at = SessionCodec.from_environment().refresh(ticket)
    except (OSError, RuntimeError) as exc:
        logger.warning("admin session refresh failed (%s)", type(exc).__name__)
        return None
    return render_session_cookie(
        token, secure=request_is_https(request), expires_at=expires_at
    )


def _cookies_in(message: Message) -> list[bytes]:
    return [
        value
        for key, value in message.get("headers", [])
        if key.lower() == b"set-cookie"
    ]


def _send_with_cookie(send: Send, cookie: str) -> Send:
    """Append the refreshed session cookie unless the route set one itself."""

    marker = f"{SESSION_COOKIE}=".encode("latin-1")

    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start":
            if not any(marker in value for value in _cookies_in(message)):
                message.setdefault("headers", []).append(
                    (b"set-cookie", cookie.encode("latin-1"))
                )
        await send(message)

    return wrapped


class AdminSessionGate:
    """One middleware: session identity in, 302/401/403 out."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        request = Request(scope, receive)
        target = gated_target(path)
        is_session_api = path.startswith(SESSION_API_PREFIX)
        if (target is not None or is_session_api) and request.method in WRITE_METHODS:
            if not same_origin(request):
                await _refusal(403, "cross_site_request_refused")(scope, receive, send)
                return
        ticket = _resolve_ticket(request)
        if target is not None and ticket is None:
            if target == PAGE:
                redirect = RedirectResponse(url="/main", status_code=302)
                redirect.headers["cache-control"] = "no-store"
                await redirect(scope, receive, send)
            else:
                await _refusal(401, "authentication_required")(scope, receive, send)
            return
        if ticket is None:
            await self.app(scope, receive, send)
            return
        request.state.admin_user = ticket.username
        refreshed = _refresh_cookie(request, ticket)
        await self.app(scope, receive, _send_with_cookie(send, refreshed) if refreshed else send)


__all__ = [
    "API",
    "AdminSessionGate",
    "GATED_API_PREFIX",
    "GATED_PAGE_PATHS",
    "PAGE",
    "gated_target",
    "same_origin",
]
