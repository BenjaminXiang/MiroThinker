"""Bounded admin configuration, system-status, and provider-health HTTP surface."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.services.admin_session import current_operator
from backend.services.canonical_v2_admin_status import (
    collect_system_status,
    probe_http,
    provider_status,
)
from backend.services.canonical_v2_runtime_sources import (
    chat_llm_profile,
    resolve_connections,
    resolve_embedding,
)
from backend.services.canonical_v2_connection_tests import (
    CONNECTIONS,
    PROVIDER_PRESETS,
    SPEC_BY_KEY,
    ConnectionTestRateLimiter,
    UnsafeEndpointError,
    fetch_model_list,
    llm_profile_options,
    normalize_base_url,
    test_connection,
)
from backend.services.canonical_v2_embedding_identity import (
    EmbeddingIdentityReport,
    verify_embedding_identity,
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
        result = store.patch(body, operator=current_operator(request))
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
    store: ManagedSecretsStore,
    *,
    environ: Mapping[str, str] | None = None,
    settings_store: ManagedSettingsStore | None = None,
) -> dict[str, Any]:
    values = dict(os.environ) if environ is None else dict(environ)
    states = store.describe(environ=values, applied_env=applied_env_names(values))
    runtime = resolve_connections(
        environ=values, settings_store=settings_store, secrets_store=store
    )
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
                "runtime": runtime[spec.key].as_public_dict(),
            }
            for spec in CONNECTIONS
        ],
    }


@router.get("/secrets")
def get_admin_secrets(
    store: ManagedSecretsStore = Depends(get_managed_secrets_store),
    settings_store: ManagedSettingsStore = Depends(get_managed_settings_store),
) -> object:
    """Masks, origins and runtime state only: no credential is ever returned."""

    return _secrets_payload(store, settings_store=settings_store)


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
        result = store.patch(values, operator=current_operator(request))
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
        **_secrets_payload(store, settings_store=get_managed_settings_store(request)),
        "changed": result["changed"],
        "audit_written": result["audit_written"],
    }


def _runtime_connections(
    *,
    settings_store: ManagedSettingsStore,
    secrets_store: ManagedSecretsStore,
) -> dict[str, Any]:
    """Resolve every connection the way the serving process would (file:line in the module)."""

    return resolve_connections(
        environ=dict(os.environ),
        settings_store=settings_store,
        secrets_store=secrets_store,
        key_file_roots=secrets_store.key_file_roots,
    )


def _resolve_connection_request(
    request: Request,
    body: Mapping[str, Any],
    *,
    settings_store: ManagedSettingsStore,
    secrets_store: ManagedSecretsStore,
) -> dict[str, Any]:
    """Request values win over runtime values; both are reported so the page can tell them apart.

    The endpoint/credential chain is the runtime chain
    (:mod:`backend.services.canonical_v2_runtime_sources`), not a page-local guess:
    a connection the runtime has disabled is reported as disabled instead of being
    probed against an invented default.
    """

    connection = str(body.get("connection", "")).strip()
    spec = SPEC_BY_KEY.get(connection)
    if spec is None:
        raise _unprocessable(
            "connection must be one of: " + ", ".join(sorted(SPEC_BY_KEY))
        )
    runtime = _runtime_connections(
        settings_store=settings_store, secrets_store=secrets_store
    )[spec.key]

    submitted_key = body.get("api_key")
    if submitted_key is None:
        # Probing the value the operator just saved is the useful reading of
        # "test before/after save"; the response labels it as pending so nobody
        # mistakes it for what the running process uses today.
        pending = secrets_store.raw().get(spec.secret_field, "")
        if pending and runtime.pending_restart:
            api_key, key_source = pending, "managed-file(pending-restart)"
        else:
            api_key, key_source = runtime.api_key, runtime.api_key_origin
    elif isinstance(submitted_key, str) and submitted_key.strip():
        api_key, key_source = submitted_key.strip(), "request"
    else:
        raise _unprocessable("api_key must be a string when present")

    submitted_base = body.get("base_url")
    if isinstance(submitted_base, str) and submitted_base.strip():
        try:
            base_url = normalize_base_url(submitted_base)
        except UnsafeEndpointError as exc:
            raise _unprocessable(str(exc)) from exc
        endpoint_source = "request"
    else:
        base_url, endpoint_source = runtime.base_url, runtime.endpoint_origin
        if base_url is not None:
            try:
                base_url = normalize_base_url(base_url)
            except UnsafeEndpointError as exc:
                raise _unprocessable(str(exc)) from exc

    submitted_model = body.get("model")
    if isinstance(submitted_model, str) and submitted_model.strip():
        model = submitted_model.strip()
    else:
        model = runtime.model or spec.default_model

    return {
        "spec": spec,
        "runtime": runtime,
        "api_key": api_key,
        "key_source": key_source or "none",
        "base_url": base_url,
        "endpoint_source": endpoint_source,
        "model": model,
    }


@router.post("/connections/test")
def test_admin_connection(
    request: Request,
    body: dict[str, Any],
    settings_store: ManagedSettingsStore = Depends(get_managed_settings_store),
    secrets_store: ManagedSecretsStore = Depends(get_managed_secrets_store),
) -> object:
    """One minimal call per invocation. Unsaved values are allowed and never stored."""

    resolved = _resolve_connection_request(
        request,
        body,
        settings_store=settings_store,
        secrets_store=secrets_store,
    )
    spec = resolved["spec"]
    runtime = resolved["runtime"]
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
    submitted_endpoint = isinstance(body.get("base_url"), str) and bool(
        str(body.get("base_url")).strip()
    )
    disabled_reason = (
        None if runtime.enabled or submitted_endpoint else runtime.runtime_note
    )
    result = test_connection(
        spec,
        api_key=resolved["api_key"],
        base_url=resolved["base_url"],
        model=resolved["model"],
        disabled_reason=disabled_reason,
    )
    return {
        "connection": spec.key,
        "label": spec.label,
        "ok": result["ok"],
        "latency_ms": result["latency_ms"],
        "http_status": result["http_status"],
        "detail": result["detail"],
        "called": result["called"],
        "runtime": runtime.as_public_dict(),
        "used": {
            "api_key_source": resolved["key_source"],
            "effective_api_key_source": runtime.api_key_origin or "none",
            "endpoint_source": resolved["endpoint_source"],
            "base_url": resolved["base_url"] if spec.base_url_editable else None,
            "model": resolved["model"]
            if spec.kind in {"rerank", "embedding", "llm"}
            else None,
        },
        "rate": {
            "per_minute_limit": _TEST_LIMITER.per_minute,
            "min_interval_seconds": _TEST_LIMITER.min_interval_seconds,
            "remaining": decision.remaining,
        },
        "identity": _embedding_identity(resolved, result, body),
        "restart_required": _RESTART_NOTICE if runtime.pending_restart else None,
    }


# -- embedding identity (the check that stops a silent model switch) ---------
# The connection test itself stays one bounded call per invocation; the
# embedding card additionally asks for the identity probe, which measures
# whether the endpoint answers in the space the index was built in. A wrong
# space does not fail any transport check — it only produces wrong rankings —
# so "answers 200 with 4096 floats" is not evidence of anything.
def _embedding_identity(
    resolved: Mapping[str, Any],
    result: Mapping[str, Any],
    body: Mapping[str, Any],
) -> dict[str, Any] | None:
    if resolved["spec"].kind != "embedding":
        return None
    if not bool(body.get("identity_check")):
        return None
    if not result.get("ok"):
        return EmbeddingIdentityReport(
            arm=None,
            passed=None,
            cosine=None,
            detail="端点未通过连通性检查，跳过向量身份校验",
        ).as_dict()
    try:
        return verify_embedding_identity(
            configured_base_url=resolved["base_url"],
            api_key=resolved["api_key"],
            model=resolved["model"],
        ).as_dict()
    except Exception as exc:  # noqa: BLE001 - an advisory check never 5xxs
        # The probe reads the mounted pack and numpy files; a failure to read
        # them is reported as "not verified", never as a broken connection.
        return EmbeddingIdentityReport(
            arm=None,
            passed=None,
            cosine=None,
            detail=f"未校验：身份探针不可用（{type(exc).__name__}）",
        ).as_dict()


# -- model configuration (I2/I3: provider presets + model discovery) ---------


@router.get("/connections/presets")
def get_connection_presets() -> object:
    """The provider presets and chat profiles the model-config page renders.

    Read-only and deployment-agnostic: the preset table is static code
    (:data:`~backend.services.canonical_v2_connection_tests.PROVIDER_PRESETS`), so
    no customer host is baked into any installation; the profile list comes from
    the same table the serving line resolves through ``CHAT_LLM_PROFILE``, with
    each profile's *local* endpoint (the one the answer/rewrite path uses);
    ``chat_profile`` is what a process with this environment would actually run;
    and ``embedding_endpoint`` reports the *effective* embedding address and
    model — the operator's managed address over the bundle-recorded one, exactly
    what the serving process resolves — with the endpoint source named. No
    outbound call is made and nothing is read from the collection database.
    """

    environ = dict(os.environ)
    embedding = resolve_embedding(environ=environ, secrets_store=None)
    return {
        "presets": [preset.as_dict() for preset in PROVIDER_PRESETS],
        "llm_profiles": llm_profile_options(),
        "chat_profile": chat_llm_profile(environ).profile,
        "embedding_frozen": (
            {
                "base_url": embedding.base_url,
                "model": embedding.model,
                "note": (
                    f"运行期生效地址（来源 {embedding.endpoint_origin}）；"
                    "模型身份仍由发布包冻结（取自服务包记录，页面不可改），"
                    "地址可在受管配置里设置"
                ),
            }
            if embedding.base_url
            else None
        ),
    }


@router.post("/connections/{key}/models")
def list_connection_models(
    key: str,
    request: Request,
    body: dict[str, Any],
    settings_store: ManagedSettingsStore = Depends(get_managed_settings_store),
    secrets_store: ManagedSecretsStore = Depends(get_managed_secrets_store),
) -> object:
    """Fetch one connection's model list from ``{base_url}/v1/models``.

    Needs **no console database**: nothing on this path reads the collection DSN,
    so the model picker keeps working on an installation whose console has no
    Postgres at all — the only dependency is the model endpoint itself. The body
    takes the same unsaved ``base_url`` / ``api_key`` as ``/connections/test`` and
    resolves its defaults the same way (request value, then the runtime-effective
    endpoint and credential); nothing is stored. One bounded GET with a 3 s
    timeout, the same rate limiter as the connection test, and a structured
    result for every outcome — including a failed one, which is never a 5xx. The
    credential is never logged or echoed back (an upstream body that repeats it is
    redacted before it becomes an excerpt).
    """

    resolved = _resolve_connection_request(
        request,
        {**body, "connection": key},
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
    result = fetch_model_list(
        base_url=resolved["base_url"], api_key=resolved["api_key"]
    )
    return {"connection": spec.key, **result}


__all__ = [
    "get_managed_secrets_store",
    "get_managed_settings_store",
    "router",
]
