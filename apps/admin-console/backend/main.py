"""Canonical V2-only candidate application shell and explicit factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api.canonical_v2_chat import router as canonical_v2_chat_router
from backend.api.canonical_v2_consumers import router as canonical_v2_consumers_router
from backend.api.canonical_v2_operations import router as canonical_v2_operations_router
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


_STATIC_DIR = Path(__file__).resolve().parent / "static"
_REJECT_METHODS = ("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE")


def _create_canonical_v2_route_shell() -> FastAPI:
    """Create one fresh V2-only route graph with no installed runtime."""

    shell = FastAPI(
        title="Canonical V2 Candidate",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    @shell.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    shell.include_router(canonical_v2_chat_router)
    shell.include_router(canonical_v2_operations_router)
    shell.include_router(canonical_v2_consumers_router)

    @shell.api_route("/api/{path:path}", methods=list(_REJECT_METHODS))
    def reject_unknown_api(path: str) -> None:
        del path
        raise HTTPException(status_code=404, detail="canonical_v2_route_not_found")

    shell.mount(
        "/static",
        StaticFiles(directory=_STATIC_DIR),
        name="static-files",
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


def create_canonical_v2_candidate_app(
    *,
    runtime: CanonicalV2ConsumerRuntime,
) -> FastAPI:
    """Install one exact aggregate and its two predecessor dependency overrides."""

    exact_runtime = require_canonical_v2_consumer_runtime(runtime)
    candidate = _create_canonical_v2_route_shell()
    candidate.state.canonical_v2_consumer_runtime = exact_runtime
    candidate.dependency_overrides[get_canonical_v2_chat_adapter] = (
        get_canonical_v2_candidate_chat_adapter
    )
    candidate.dependency_overrides[get_knowledge_gap_operations] = (
        get_canonical_v2_gap_operations
    )
    return candidate


app = _create_canonical_v2_route_shell()


__all__ = [
    "_create_canonical_v2_route_shell",
    "app",
    "create_canonical_v2_candidate_app",
]
