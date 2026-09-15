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
from backend.services.canonical_v2_connection_tests import (
    CONNECTIONS,
    SPEC_BY_KEY,
    ConnectionTestRateLimiter,
    UnsafeEndpointError,
    normalize_base_url,
    test_connection,
)
from src.data_agents.canonical_v2.managed_config import (
    ManagedSettingsError,
    ManagedSettingsStore,
    ManagedSettingsUnsupportedError,
    default_settings_path,
)
from src.data_agents.canonical_v2.managed_runtime import applied_env_names
from src.data_agents.canonical_v2.managed_secrets import (
    ManagedSecretsError,
    ManagedSecretsStore,
    ManagedSecretsUnsupportedError,
    default_secrets_path,
)


router = APIRouter(prefix="/api/canonical-v2/admin")

_STORE_STATE_NAME = "canonical_v2_managed_settings_store"
_SECRETS_STATE_NAME = "canonical_v2_managed_secrets_store"
_MAX_OPERATOR_LENGTH = 200
_RESTART_NOTICE = "修改后需重启服务生效（服务启动时读取受管文件，不做热加载）"

# One limiter per process: the page's test button must not become a provider bill.
_TEST_LIMITER = ConnectionTestRateLimiter(per_minute=6, min_interval_seconds=1.0)


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


def get_managed_secrets_store(request: Request) -> ManagedSecretsStore:
    """Return the installed secrets store, or the environment-resolved default."""

    installed = getattr(request.app.state, _SECRETS_STATE_NAME, None)
    if isinstance(installed, ManagedSecretsStore):
        return installed
    return ManagedSecretsStore(path=default_secrets_path())


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
            field.path: field.env_var for field in fields if field.env_var is not None
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


# -- managed credentials (R16: keys are settable from the page) --------------


def _secrets_payload(
    store: ManagedSecretsStore, *, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    values = dict(os.environ) if environ is None else dict(environ)
    states = store.describe(environ=values, applied_env=applied_env_names(values))
    return {
        "path": str(store.path),
        "exists": store.exists(),
        "permissions_ok": store.permissions_ok(),
        "restart_required": _RESTART_NOTICE,
        "secrets": [state.as_dict() for state in states],
        "connections": [
            {
                "key": spec.key,
                "label": spec.label,
                "kind": spec.kind,
                "secret_field": spec.secret_field,
                "requires_key": spec.requires_key,
                "base_url_editable": spec.base_url_editable,
            }
            for spec in CONNECTIONS
        ],
    }


@router.get("/secrets")
def get_admin_secrets(
    store: ManagedSecretsStore = Depends(get_managed_secrets_store),
) -> object:
    """Masks and origins only: a credential is never returned by this surface."""

    return _secrets_payload(store)


@router.patch("/secrets")
def patch_admin_secrets(
    request: Request,
    body: dict[str, Any],
    store: ManagedSecretsStore = Depends(get_managed_secrets_store),
) -> object:
    values = body.get("values") if isinstance(body, dict) else None
    if not isinstance(values, Mapping):
        raise _unprocessable("body must be {'values': {<field>: <secret|null>}}")
    try:
        result = store.patch(values, operator=_operator(request))
    except ManagedSecretsUnsupportedError as exc:
        raise _unprocessable(str(exc)) from exc
    except ManagedSecretsError as exc:
        raise _unprocessable(str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"managed secrets file is not writable ({type(exc).__name__})",
        ) from exc
    return {
        **_secrets_payload(store),
        "changed": result["changed"],
        "audit_written": result["audit_written"],
    }


def _effective_settings_value(
    request: Request, store: ManagedSettingsStore, path: str | None
) -> Any:
    if path is None:
        return None
    try:
        _document, fields = store.effective()
    except ManagedSettingsError:
        return None
    for field in fields:
        if field.path == path:
            return field.value
    return None


def _resolve_connection_credentials(
    request: Request,
    body: Mapping[str, Any],
    *,
    settings_store: ManagedSettingsStore,
    secrets_store: ManagedSecretsStore,
) -> dict[str, Any]:
    connection = str(body.get("connection", "")).strip()
    spec = SPEC_BY_KEY.get(connection)
    if spec is None:
        raise _unprocessable(
            "connection must be one of: " + ", ".join(sorted(SPEC_BY_KEY))
        )
    environ = dict(os.environ)
    submitted_key = body.get("api_key")
    key_source: str
    if isinstance(submitted_key, str) and submitted_key.strip():
        api_key = submitted_key.strip()
        key_source = "request"
    elif submitted_key is None:
        api_key, origin = secrets_store.resolve_field(
            spec.secret_field,
            environ=environ,
            applied_env=applied_env_names(environ),
        )
        key_source = origin or "none"
    else:
        raise _unprocessable("api_key must be a string when present")
    submitted_base = body.get("base_url")
    if spec.base_url_editable:
        try:
            base_url = normalize_base_url(
                submitted_base
                if isinstance(submitted_base, str) and submitted_base.strip()
                else _effective_settings_value(
                    request, settings_store, spec.base_url_field
                ),
                default=_normalized_default(spec),
            )
        except UnsafeEndpointError as exc:
            raise _unprocessable(str(exc)) from exc
    else:
        base_url = spec.default_base_url
    submitted_model = body.get("model")
    if isinstance(submitted_model, str) and submitted_model.strip():
        model = submitted_model.strip()
    else:
        model = _effective_settings_value(request, settings_store, spec.model_field)
    return {
        "spec": spec,
        "api_key": api_key,
        "key_source": key_source,
        "base_url": base_url,
        "model": model or spec.default_model,
    }


def _normalized_default(spec: Any) -> str | None:
    default = spec.default_base_url
    if default is None:
        return None
    try:
        return normalize_base_url(default)
    except UnsafeEndpointError:  # pragma: no cover - module constants are valid
        return default


@router.post("/connections/test")
def test_admin_connection(
    request: Request,
    body: dict[str, Any],
    settings_store: ManagedSettingsStore = Depends(get_managed_settings_store),
    secrets_store: ManagedSecretsStore = Depends(get_managed_secrets_store),
) -> object:
    """One minimal call per invocation. Unsaved values are allowed and never stored."""

    resolved = _resolve_connection_credentials(
        request,
        body,
        settings_store=settings_store,
        secrets_store=secrets_store,
    )
    spec = resolved["spec"]
    client = request.client.host if request.client is not None else "unknown"
    decision = _TEST_LIMITER.check([f"conn:{spec.key}", f"client:{client}"])
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limited",
                "connection": spec.key,
                "retry_after_seconds": decision.retry_after_seconds,
            },
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    result = test_connection(
        spec,
        api_key=resolved["api_key"],
        base_url=resolved["base_url"],
        model=resolved["model"],
    )
    return {
        "connection": spec.key,
        "label": spec.label,
        "ok": result["ok"],
        "latency_ms": result["latency_ms"],
        "http_status": result["http_status"],
        "detail": result["detail"],
        "used": {
            "api_key_source": resolved["key_source"],
            "base_url": resolved["base_url"] if spec.base_url_editable else None,
            "model": resolved["model"] if spec.model_field else None,
        },
        "rate": {
            "per_minute_limit": _TEST_LIMITER.per_minute,
            "min_interval_seconds": _TEST_LIMITER.min_interval_seconds,
            "remaining": decision.remaining,
        },
        "restart_required": None,
    }


__all__ = [
    "get_managed_secrets_store",
    "get_managed_settings_store",
    "router",
]
