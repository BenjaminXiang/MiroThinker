from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

# admin-console serves real users; ensure Milvus uses real client (not in-memory mock).
# The mock is intentional for unit tests but unsafe for production retrieval.
# See .agents/specs/2026-05-02-w13-9-milvus-real-client-explicit.md.
os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api.batch import router as batch_router
from backend.api.chat import router as chat_router
from backend.api.data import router as data_router
from backend.api.dashboard import router as dashboard_router
from backend.api.export import router as export_router
from backend.api.pipeline import router as pipeline_router
from backend.api.pipeline_issues import router as pipeline_issues_router
from backend.api.review import router as review_router
from backend.api.upload import router as upload_router
from backend.api.domains import router as domains_router

app = FastAPI(title="深圳科创数据管理平台 - Admin Console")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Register specific-prefix routers BEFORE the domain catch-all
app.include_router(dashboard_router)
app.include_router(upload_router)
app.include_router(export_router)
app.include_router(batch_router)
app.include_router(data_router)
app.include_router(pipeline_router)
app.include_router(review_router)
app.include_router(chat_router)
app.include_router(pipeline_issues_router)
app.include_router(domains_router)


# Lightweight built-in data browser (no React build required).
# Visit /browse to inspect companies/professors/papers/patents through the
# Legacy /api/data/* endpoints now redirect to the Postgres-backed /api/{domain}
# API. The React SPA at /assets/* is the legacy dashboard (now fed real Postgres
# numbers from /api/dashboard per Round 9). The `/` root redirects to /browse
# because that's the primary operator surface; the SPA is still reachable at the
# filename paths it serves from /assets.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if (_STATIC_DIR / "browse.html").is_file():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static-files")

    @app.get("/", include_in_schema=False)
    def redirect_root_to_browse() -> RedirectResponse:
        return RedirectResponse(url="/browse", status_code=302)

    @app.get("/browse")
    def serve_browse() -> FileResponse:
        return FileResponse(_STATIC_DIR / "browse.html")

    if (_STATIC_DIR / "chat.html").is_file():

        @app.get("/chat")
        def serve_chat() -> FileResponse:
            return FileResponse(_STATIC_DIR / "chat.html")


# Serve React SPA static files
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount(
        "/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets"
    )

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str) -> FileResponse:
        """Serve index.html for all non-API routes (React Router client-side routing)."""
        return FileResponse(_FRONTEND_DIST / "index.html")


_LOGGER = logging.getLogger(__name__)
_FRONTEND_STALENESS_GRACE_SECONDS = 5.0


def _check_frontend_dist_freshness() -> None:
    try:
        dist_index = _FRONTEND_DIST / "index.html"
        if not dist_index.is_file():
            _LOGGER.warning(
                "ADMIN_CONSOLE_FRONTEND_MISSING: dist/index.html not found at %s. "
                "SPA routes will 404. Run `just frontend-fresh` to build.",
                dist_index,
            )
            return

        dist_mtime = dist_index.stat().st_mtime

        frontend_root = _FRONTEND_DIST.parent
        src_root = frontend_root / "src"
        candidates: list[Path] = []
        if src_root.is_dir():
            for ext in ("ts", "tsx", "js", "jsx", "css", "html"):
                candidates.extend(src_root.rglob(f"*.{ext}"))
        for extra in ("index.html", "package.json", "vite.config.ts"):
            p = frontend_root / extra
            if p.is_file():
                candidates.append(p)

        if not candidates:
            return

        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        latest_mtime = latest.stat().st_mtime

        if latest_mtime > dist_mtime + _FRONTEND_STALENESS_GRACE_SECONDS:
            _LOGGER.warning(
                "ADMIN_CONSOLE_FRONTEND_STALE: dist/index.html built at %s, "
                "but src has newer file (%s at %s). Browser will see stale "
                "React SPA. Run `just frontend-fresh` to rebuild, or "
                "`just frontend-dev` for HMR on http://localhost:5180.",
                datetime.fromtimestamp(dist_mtime).isoformat(timespec="seconds"),
                latest.relative_to(frontend_root.parent),
                datetime.fromtimestamp(latest_mtime).isoformat(timespec="seconds"),
            )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("frontend dist freshness check skipped: %s", exc)


_check_frontend_dist_freshness()
