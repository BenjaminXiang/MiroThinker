"""Canonical V2-only candidate application shell and explicit factory."""

from __future__ import annotations

from collections.abc import Callable
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.canonical_v2_chat import router as canonical_v2_chat_router
from backend.api.canonical_v2_consumers import router as canonical_v2_consumers_router
from backend.api.canonical_v2_operations import router as canonical_v2_operations_router
from backend.api.canonical_v2_review import (
    review_error_response,
    review_http_exception_handler,
    review_origin_is_exact,
    review_validation_error_handler,
    review_workspace_error_handler,
    router as canonical_v2_review_router,
)
from backend.canonical_v2_deps import (
    get_canonical_v2_candidate_chat_adapter,
    get_canonical_v2_chat_adapter,
    get_canonical_v2_gap_operations,
    get_knowledge_gap_operations,
)
from backend.services.canonical_v2_admin import (
    CanonicalV2ConsumerRuntime,
    require_canonical_v2_consumer_runtime,
)
from backend.services.canonical_v2_review import ReviewWorkspace, ReviewWorkspaceError


_STATIC_DIR = Path(__file__).resolve().parent / "static"
_REVIEW_HTML = (_STATIC_DIR / "review.html").resolve()
_REJECT_METHODS = ("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE")


class _CandidateStaticFiles(StaticFiles):
    """Serve shared assets while keeping review HTML behind its guarded route."""

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        full_path, stat_result = super().lookup_path(path)
        if stat_result is not None and Path(full_path).resolve() == _REVIEW_HTML:
            return "", None
        return full_path, stat_result


def _create_route_shell(*, include_review: bool) -> FastAPI:
    """Create one fresh route graph, optionally with the isolated review surface."""

    shell = FastAPI(
        title="Canonical V2 Candidate",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    @shell.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    if include_review:
        shell.include_router(canonical_v2_review_router)
    shell.include_router(canonical_v2_chat_router)
    shell.include_router(canonical_v2_operations_router)
    shell.include_router(canonical_v2_consumers_router)

    @shell.api_route("/api/{path:path}", methods=list(_REJECT_METHODS))
    def reject_unknown_api(path: str) -> None:
        del path
        raise HTTPException(status_code=404, detail="canonical_v2_route_not_found")

    shell.mount(
        "/static",
        _CandidateStaticFiles(directory=_STATIC_DIR),
        name="static-files",
    )

    if include_review:

        @shell.get("/review", include_in_schema=False)
        def serve_review() -> FileResponse:
            return FileResponse(
                _STATIC_DIR / "review.html",
                headers={
                    "Content-Security-Policy": (
                        "default-src 'none'; script-src 'self'; style-src 'self'; "
                        "connect-src 'self'; base-uri 'none'; form-action 'self'; "
                        "frame-ancestors 'none'; object-src 'none'; "
                        "img-src 'self' data:"
                    ),
                    "Cache-Control": "no-store",
                    "Referrer-Policy": "no-referrer",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    @shell.get("/", include_in_schema=False)
    def redirect_root_to_browse() -> RedirectResponse:
        return RedirectResponse(url="/browse", status_code=302)

    @shell.get("/browse")
    def serve_browse() -> FileResponse:
        return FileResponse(_STATIC_DIR / "browse.html")

    @shell.get("/chat")
    def serve_chat() -> FileResponse:
        return FileResponse(_STATIC_DIR / "chat.html")

    return shell


def _create_canonical_v2_route_shell() -> FastAPI:
    """Create one fresh V2-only route graph with no installed runtime."""

    return _create_route_shell(include_review=False)


def _normalized_public_origin(value: str) -> tuple[str, bool]:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError("public_origin must be a canonical HTTP(S) origin")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("public_origin must be a canonical HTTP(S) origin")
    try:
        parsed.hostname.encode("ascii")
        port = parsed.port
    except (UnicodeEncodeError, ValueError) as exc:
        raise ValueError("public_origin must be a canonical HTTP(S) origin") from exc
    hostname = parsed.hostname.lower()
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 80 if parsed.scheme == "http" else 443
    rendered_port = "" if port in {None, default_port} else f":{port}"
    normalized = f"{parsed.scheme}://{rendered_host}{rendered_port}"
    if value != normalized:
        raise ValueError("public_origin must be a canonical HTTP(S) origin")
    try:
        loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        loopback = hostname == "localhost" or hostname.endswith(".localhost")
    if parsed.scheme != "https" and not loopback:
        raise ValueError("HTTPS is required for a non-loopback public_origin")
    return normalized, parsed.scheme == "https"


def create_canonical_v2_candidate_app(
    *,
    runtime: CanonicalV2ConsumerRuntime,
    idle_keepwarm_cycle: Callable[[], None] | None = None,
) -> FastAPI:
    """Install one exact aggregate and its two predecessor dependency overrides."""

    exact_runtime = require_canonical_v2_consumer_runtime(runtime)
    candidate = _create_canonical_v2_route_shell()
    candidate.state.canonical_v2_consumer_runtime = exact_runtime
    if idle_keepwarm_cycle is not None:
        from backend.services.canonical_v2_keepwarm import AdaptiveIdleKeepwarm

        idle_keepwarm = AdaptiveIdleKeepwarm(
            cycle=idle_keepwarm_cycle,
            idle_seconds=300.0,
        )
        candidate.state.canonical_v2_idle_keepwarm = idle_keepwarm
        candidate.router.add_event_handler("startup", idle_keepwarm.start)
        candidate.router.add_event_handler("shutdown", idle_keepwarm.stop)
    candidate.dependency_overrides[get_canonical_v2_chat_adapter] = (
        get_canonical_v2_candidate_chat_adapter
    )
    candidate.dependency_overrides[get_knowledge_gap_operations] = (
        get_canonical_v2_gap_operations
    )
    return candidate


def create_canonical_v2_review_app(
    *,
    review_workspace: ReviewWorkspace,
    public_origin: str,
) -> FastAPI:
    """Create the separate same-origin review-enabled Candidate shell."""

    normalized_origin, secure_cookie = _normalized_public_origin(public_origin)
    candidate = _create_route_shell(include_review=True)
    candidate.state.canonical_v2_review_workspace = review_workspace
    candidate.state.canonical_v2_review_public_origin = normalized_origin
    candidate.state.canonical_v2_review_secure_cookie = secure_cookie

    @candidate.middleware("http")
    async def enforce_review_origin(request: Request, call_next):
        is_review_api = request.url.path.startswith("/api/review/")
        if is_review_api and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not review_origin_is_exact(request, expected_origin=normalized_origin):
                response = review_error_response(status_code=403, code="origin_rejected")
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)
        if is_review_api:
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    candidate.add_exception_handler(
        ReviewWorkspaceError,
        review_workspace_error_handler,
    )
    candidate.add_exception_handler(
        RequestValidationError,
        review_validation_error_handler,
    )
    candidate.add_exception_handler(
        StarletteHTTPException,
        review_http_exception_handler,
    )
    return candidate


app = _create_canonical_v2_route_shell()


__all__ = [
    "_create_canonical_v2_route_shell",
    "app",
    "create_canonical_v2_candidate_app",
    "create_canonical_v2_review_app",
]
