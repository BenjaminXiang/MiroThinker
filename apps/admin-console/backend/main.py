"""Canonical V2-only candidate application shell and explicit factory."""

from __future__ import annotations

from collections.abc import Callable
from html import escape as _escape_html
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api.admin_auth import router as admin_auth_router
from backend.api.canonical_v2_access_logs import (
    router as canonical_v2_access_logs_router,
)
from backend.api.canonical_v2_admin_config import (
    router as canonical_v2_admin_config_router,
)
from backend.api.canonical_v2_chat import router as canonical_v2_chat_router
from backend.api.canonical_v2_consumers import router as canonical_v2_consumers_router
from backend.api.canonical_v2_corrections import (
    router as canonical_v2_corrections_router,
)
from backend.api.canonical_v2_jobs import router as canonical_v2_jobs_router
from backend.api.canonical_v2_manual_recall import (
    router as canonical_v2_manual_recall_router,
)
from backend.api.canonical_v2_operations import router as canonical_v2_operations_router
from backend.api.canonical_v2_seeds import router as canonical_v2_seeds_router
from backend.api.canonical_v2_uploads import router as canonical_v2_uploads_router
from backend.canonical_v2_deps import (
    get_canonical_v2_candidate_chat_adapter,
    get_canonical_v2_chat_adapter,
    get_canonical_v2_gap_operations,
    get_knowledge_gap_operations,
)
from backend.deps import resolve_console_dsn
from backend.services.admin_auth import store_from_environment
from backend.services.admin_gate import AdminSessionGate
from backend.services.canonical_v2_admin import (
    CanonicalV2ConsumerRuntime,
    require_canonical_v2_consumer_runtime,
)


_STATIC_DIR = Path(__file__).resolve().parent / "static"
_MAIN_HTML = _STATIC_DIR / "main.html"
_REJECT_METHODS = ("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE")
_ANONYMOUS_MARKER = 'data-admin-user=""'


def _adopt_managed_configuration() -> None:
    """R16: one startup read of the managed files (never a request-path read).

    Projecting the operator's managed configuration into the environment is what
    makes "save on the page → restart → effective" true. A missing or unreadable
    file is a no-op, and an existing environment variable always wins.
    """

    try:
        from src.data_agents.canonical_v2.managed_runtime import (
            apply_managed_runtime_config,
        )

        receipt = apply_managed_runtime_config()
    except Exception as exc:  # noqa: BLE001 - a broken managed file must not block boot
        logging.getLogger(__name__).warning(
            "managed configuration was not adopted at startup (%s)",
            type(exc).__name__,
        )
        return
    logging.getLogger(__name__).info(
        "managed configuration adopted: settings=%d secrets=%d skipped=%d",
        len(receipt["settings_applied"]),
        len(receipt["secrets_applied_env"]),
        len(receipt["settings_skipped_env"]) + len(receipt["secrets_skipped_env"]),
    )


def _seed_admin_credentials() -> None:
    """First boot creates the single administrator; later boots are a no-op."""

    try:
        store = store_from_environment()
        store.seed_initial_admin()
    except Exception as exc:  # noqa: BLE001 - a broken auth store must not block boot
        logging.getLogger(__name__).warning(
            "admin credential seeding skipped (%s)", type(exc).__name__
        )


def _resolve_console_database(app: FastAPI) -> str | None:
    """Resolve the console database once, carry it on the app, and log only its state.

    Both factories in this module build through `_create_route_shell`, so this is
    the one place the value is read; every console surface reads it from
    ``app.state`` afterwards. The DSN itself is never logged.
    """

    console_dsn = resolve_console_dsn()
    app.state.console_dsn = console_dsn
    state = "configured" if console_dsn else "unconfigured"
    logging.getLogger(__name__).info("console_database=%s", state)
    # The serving process's logging configuration does not surface this logger, and the
    # state is the first thing an operator reading the boot log needs (the first-boot
    # admin password is announced the same way). The state only — never the DSN.
    print(f"[canonical-v2] console_database={state}", flush=True)
    return console_dsn


def _create_route_shell() -> FastAPI:
    """Create one fresh route graph for the isolated Canonical V2 shell."""

    shell = FastAPI(
        title="Canonical V2 Candidate",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    shell.add_middleware(AdminSessionGate)
    shell.router.add_event_handler("startup", _adopt_managed_configuration)
    shell.router.add_event_handler("startup", _seed_admin_credentials)
    _resolve_console_database(shell)

    @shell.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    shell.include_router(admin_auth_router)
    shell.include_router(canonical_v2_chat_router)
    shell.include_router(canonical_v2_operations_router)
    shell.include_router(canonical_v2_consumers_router)
    shell.include_router(canonical_v2_corrections_router)
    shell.include_router(canonical_v2_manual_recall_router)
    shell.include_router(canonical_v2_access_logs_router)
    shell.include_router(canonical_v2_admin_config_router)
    shell.include_router(canonical_v2_jobs_router)
    shell.include_router(canonical_v2_uploads_router)
    shell.include_router(canonical_v2_seeds_router)

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
    def redirect_root_to_chat() -> RedirectResponse:
        return RedirectResponse(url="/chat", status_code=302)

    @shell.get("/main", include_in_schema=False)
    def serve_main(request: Request) -> HTMLResponse:
        """One URL for both the login form and the dashboard.

        The page decides with its own CSS which half is visible, so the shell
        only has to stamp the authenticated username into the document.
        """

        document = _MAIN_HTML.read_text(encoding="utf-8")
        username = str(getattr(request.state, "admin_user", "") or "")
        if username:
            document = document.replace(
                _ANONYMOUS_MARKER,
                f'data-admin-user="{_escape_html(username, quote=True)}"',
                1,
            )
        return HTMLResponse(document, headers={"cache-control": "no-store"})

    @shell.get("/browse")
    def serve_browse() -> FileResponse:
        return FileResponse(_STATIC_DIR / "browse.html")

    @shell.get("/logs")
    def serve_logs() -> FileResponse:
        return FileResponse(_STATIC_DIR / "logs.html")

    @shell.get("/admin")
    def serve_admin() -> FileResponse:
        return FileResponse(_STATIC_DIR / "admin.html")

    @shell.get("/jobs")
    def serve_jobs() -> FileResponse:
        return FileResponse(_STATIC_DIR / "jobs.html")

    @shell.get("/upload")
    def serve_upload() -> FileResponse:
        return FileResponse(_STATIC_DIR / "upload.html")

    @shell.get("/seeds")
    def serve_seeds() -> FileResponse:
        return FileResponse(_STATIC_DIR / "seeds.html")

    @shell.get("/chat")
    def serve_chat() -> FileResponse:
        return FileResponse(_STATIC_DIR / "chat.html")

    return shell


def _create_canonical_v2_route_shell() -> FastAPI:
    """Create one fresh V2-only route graph with no installed runtime."""

    return _create_route_shell()


def create_canonical_v2_candidate_app(
    *,
    runtime: CanonicalV2ConsumerRuntime,
    idle_keepwarm_cycle: Callable[[], None] | None = None,
) -> FastAPI:
    """Install one exact aggregate and its two predecessor dependency overrides."""

    exact_runtime = require_canonical_v2_consumer_runtime(runtime)
    # Single choke point for every serving composition (admin compose AND the
    # pack-mode mirror in the candidate runner): attach the turn-trace journal
    # here so every path serves traced turns. Fail-open by construction.
    candidate_chat_adapter = getattr(exact_runtime, "chat_adapter", None)
    candidate_attach = getattr(candidate_chat_adapter, "attach_turn_trace", None)
    if (
        callable(candidate_attach)
        and getattr(candidate_chat_adapter, "_turn_trace", None) is None
    ):
        from backend.services.canonical_v2_turn_trace import TurnTraceJournalStore

        candidate_attach(TurnTraceJournalStore())
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


app = _create_canonical_v2_route_shell()


__all__ = [
    "_create_canonical_v2_route_shell",
    "app",
    "create_canonical_v2_candidate_app",
]
