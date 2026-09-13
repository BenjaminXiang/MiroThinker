"""Bounded admin configuration, system-status, and provider-health HTTP surface."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.services.canonical_v2_admin_status import (
    collect_system_status,
    probe_http,
    provider_status,
)
from src.data_agents.canonical_v2.managed_config import (
    ManagedSettingsError,
    ManagedSettingsStore,
    ManagedSettingsUnsupportedError,
    default_settings_path,
)


router = APIRouter(prefix="/api/canonical-v2/admin")

_STORE_STATE_NAME = "canonical_v2_managed_settings_store"
_MAX_OPERATOR_LENGTH = 200


class ProviderStatusItem(BaseModel):
    key: str
    label: str
    configured: bool
    suffix4: str | None
    origin: str | None
    reachable: bool | None
    detail: str | None


class ProviderHealthResponse(BaseModel):
    generated_at: str
    providers: list[ProviderStatusItem]


def get_managed_settings_store(request: Request) -> ManagedSettingsStore:
    """Return the installed store, or the environment-resolved default store."""

    installed = getattr(request.app.state, _STORE_STATE_NAME, None)
    if isinstance(installed, ManagedSettingsStore):
        return installed
    return ManagedSettingsStore(path=default_settings_path())


def _operator(request: Request) -> str:
    raw = request.headers.get("X-Remote-User", "").strip()
    if not raw:
        return "anonymous"
    return raw[:_MAX_OPERATOR_LENGTH]


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _runtime(request: Request) -> Any | None:
    return getattr(request.app.state, "canonical_v2_consumer_runtime", None)


def _runtime_manifest(request: Request) -> Any | None:
    service = _runtime(request)
    admin_runtime = getattr(service, "admin_runtime", None)
    return getattr(admin_runtime, "manifest", None)


def _runtime_as_of(request: Request) -> datetime | None:
    service = _runtime(request)
    admin_runtime = getattr(service, "admin_runtime", None)
    value = getattr(admin_runtime, "as_of", None)
    return value if isinstance(value, datetime) else None


def _config_payload(store: ManagedSettingsStore) -> dict[str, Any]:
    try:
        document, fields = store.effective()
    except ManagedSettingsError as exc:
        raise HTTPException(
            status_code=503,
            detail="managed configuration is unavailable",
        ) from exc
    return {
        "path": str(store.path),
        "exists": store.exists(),
        "schema_version": document.schema_version,
        "settings": document.model_dump(mode="json"),
        "fields": [field.as_dict() for field in fields],
        "env_vars": {
            field.path: field.env_var
            for field in fields
            if field.env_var is not None
        },
    }


@router.get("/config")
def get_admin_config(
    store: ManagedSettingsStore = Depends(get_managed_settings_store),
) -> object:
    return _config_payload(store)


@router.patch("/config")
def patch_admin_config(
    request: Request,
    body: dict[str, Any],
    store: ManagedSettingsStore = Depends(get_managed_settings_store),
) -> object:
    try:
        result = store.patch(body, operator=_operator(request))
    except ManagedSettingsUnsupportedError as exc:
        raise _unprocessable(str(exc)) from exc
    except ManagedSettingsError as exc:
        raise _unprocessable(str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"managed configuration is not writable ({type(exc).__name__})",
        ) from exc
    return {**_config_payload(store), "changed": result["changed"]}


@router.get("/system-status")
def get_admin_system_status(
    request: Request,
    store: ManagedSettingsStore = Depends(get_managed_settings_store),
) -> object:
    environ: Mapping[str, str] = dict(os.environ)
    return collect_system_status(
        store=store,
        environ=environ,
        manifest=_runtime_manifest(request),
        as_of=_runtime_as_of(request),
    )


@router.post("/providers/health-check", response_model=ProviderHealthResponse)
def check_provider_health() -> ProviderHealthResponse:
    results = provider_status(environ=dict(os.environ), probe=probe_http)
    return ProviderHealthResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        providers=[ProviderStatusItem(**item) for item in results],
    )


__all__ = [
    "get_managed_settings_store",
    "router",
]
