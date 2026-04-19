from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.batch import router as batch_router
from backend.api.chat import router as chat_router
from backend.api.data import router as data_router
from backend.api.dashboard import router as dashboard_router
from backend.api.export import router as export_router
from backend.api.pipeline import router as pipeline_router
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
app.include_router(domains_router)
app.include_router(chat_router)


# Lightweight built-in data browser (no React build required).
# Visit /browse to inspect companies/professors/papers/patents through the
# Postgres-backed /api/data/* endpoints. Works the moment Round 8a lands
# professor/paper/patent endpoints without any frontend rebuild.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if (_STATIC_DIR / "browse.html").is_file():
    app.mount(
        "/static", StaticFiles(directory=_STATIC_DIR), name="static-files"
    )

    @app.get("/browse")
    def serve_browse() -> FileResponse:
        return FileResponse(_STATIC_DIR / "browse.html")


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
