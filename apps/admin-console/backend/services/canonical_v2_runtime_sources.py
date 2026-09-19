"""What each connection actually uses **at runtime**, resolved from the live code paths.

The admin page's connectivity test must not invent a source. Every endpoint and
credential below is resolved by calling (or mirroring, with a file:line pointer)
the exact function the serving process calls:

* Bocha / Serper — ``src/data_agents/providers/bocha_search.py:61`` (env, then the
  repository key file) and the Serper provider's identical pattern.
* Embedding — ``src/data_agents/company/vectorizer.py:22,40-53``: base URL is the
  frozen release-bundle authority (``knowledge_build_isolated.py:6720-6728``,
  ``http://100.64.0.27:18005/v1``) and the credential is
  ``load_local_api_key()`` (``providers/local_api_key.py:8-31``: ``API_KEY`` →
  ``OPENAI_API_KEY`` → ``SGLANG_API_KEY`` → ``.sglang_api_key``), *not* an
  ``EMBEDDING_API_KEY`` variable (nothing at runtime reads one).
* Rerank — ``canonical_v2/rerank_client.py:224-236``: ``configured_reranker()``
  returns ``None`` unless ``CANONICAL_V2_RERANK_BASE_URL`` is set, i.e. the live
  line has rerank **disabled**; there is no default endpoint.
* LLM — ``knowledge_serving_isolated.py:2087-2096`` (also 5972, 6070;
  ``llm_judgments.py:304``): the active chat profile
  (``CHAT_LLM_PROFILE``, default ``gemma4``) resolved through
  ``resolve_professor_llm_settings(..., apply_endpoint_env_overrides=False)``
  (``professor/llm_profiles.py:244-288``), whose credential comes from the
  profile's own ``api_key_env`` and key file (``llm_profiles.py:14-20,55-66``).

Values are resolved here and never returned outward: the response carries origins
("env:BOCHA_API_KEY", "legacy-file:.sglang_api_key", "profile:deepseekv4flash").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from src.data_agents.canonical_v2.managed_runtime import applied_env_names
from src.data_agents.canonical_v2.managed_secrets import (
    SECRET_SPECS,
    ManagedSecretsStore,
)

# Endpoint authorities that the runtime pins: a page must never move a credential
# to another host, so these are reported as origins, not as editable fields.
BOCHA_ENDPOINT = "https://api.bochaai.com/v1/web-search"
SERPER_ENDPOINT = "https://google.serper.dev/search"

_CHAT_PROFILE_ENV = "CHAT_LLM_PROFILE"
_DEFAULT_CHAT_PROFILE = "gemma4"

_LOCAL_KEY_ENV_NAMES = ("API_KEY", "OPENAI_API_KEY", "SGLANG_API_KEY")
_LOCAL_KEY_FILENAME = ".sglang_api_key"


@dataclass(frozen=True, slots=True)
class RuntimeConnection:
    """The runtime-resolved endpoint + credential state of one connection."""

    key: str
    label: str
    kind: str
    enabled: bool
    base_url: str | None
    model: str | None
    api_key: str
    api_key_origin: str | None
    endpoint_origin: str | None
    runtime_note: str
    pending_restart: bool = False

    def as_public_dict(self) -> dict[str, Any]:
        """The value-free view the page/API may show."""

        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "enabled": self.enabled,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_origin": self.api_key_origin,
            "endpoint_origin": self.endpoint_origin,
            "runtime_note": self.runtime_note,
            "pending_restart": self.pending_restart,
        }


def _first_env(
    environ: Mapping[str, str],
    names: Sequence[str],
    *,
    applied_env: frozenset[str] = frozenset(),
) -> tuple[str, str | None]:
    for name in names:
        value = environ.get(name, "").strip()
        if value:
            origin = (
                f"managed-file(env:{name})" if name in applied_env else f"env:{name}"
            )
            return value, origin
    return "", None


def _walk_key_file(filename: str, roots: Sequence[Path]) -> tuple[str, str | None]:
    for root in roots:
        candidate = root / filename
        try:
            value = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value, f"legacy-file:{filename}"
    return "", None


def _key_file_roots() -> tuple[Path, ...]:
    """Mirror ``providers/local_api_key.py`` and ``llm_profiles._candidate_key_roots``."""

    here = Path(__file__).resolve()
    roots = [Path.cwd(), *Path.cwd().parents, *here.parents]
    seen: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.append(root)
    return tuple(seen)


def _managed_value(
    store: ManagedSecretsStore | None, field: str, environ: Mapping[str, str]
) -> str:
    if store is None:
        return ""
    try:
        values = store.raw()
    except Exception:  # noqa: BLE001 - a broken managed file must not break status
        return ""
    return values.get(field, "")


def _pending_restart(
    store: ManagedSecretsStore | None,
    field: str,
    effective: str,
    environ: Mapping[str, str],
) -> bool:
    """True when the managed file holds a value the running process has not adopted.

    The managed file reaches the runtime through the environment at startup
    (``managed_runtime.apply_managed_runtime_config``), so until that restart the
    effective credential is still the environment or the legacy key file. Reporting
    the file's value as "effective" here would be exactly the misalignment this
    module exists to remove.
    """

    managed = _managed_value(store, field, environ)
    if not managed:
        return False
    return effective != managed


def _local_key(
    environ: Mapping[str, str], roots: Sequence[Path] | None = None
) -> tuple[str, str | None]:
    value, origin = _first_env(
        environ, _LOCAL_KEY_ENV_NAMES, applied_env=applied_env_names(environ)
    )
    if value:
        return value, origin
    return _walk_key_file(_LOCAL_KEY_FILENAME, roots or _key_file_roots())


@dataclass(frozen=True, slots=True)
class ChatLLMProfile:
    """The active chat LLM endpoint, read from the same table the serving path uses."""

    profile: str
    base_url: str
    model: str
    api_key_env: str
    key_file: str | None


def chat_llm_profile(environ: Mapping[str, str]) -> ChatLLMProfile:
    """Resolve the active chat profile against *this* environment.

    ``knowledge_serving_isolated.py:2087-2096`` calls
    ``resolve_professor_llm_settings(profile, apply_endpoint_env_overrides=False)``,
    which reads ``os.environ`` directly. Resolution here is deliberately pure with
    respect to the passed mapping (same table, same profile name rules, no ambient
    read) so the page can report what a process with *this* environment would use —
    and so status calls can never silently pick up an unrelated ambient variable.
    """

    requested = environ.get(_CHAT_PROFILE_ENV, "").strip() or _DEFAULT_CHAT_PROFILE
    from src.data_agents.professor.llm_profiles import (
        _KEY_FILE_BY_ENV,
        _LLM_PROFILES,
        resolve_professor_llm_profile_name,
    )

    resolved = resolve_professor_llm_profile_name(profile_name=requested)
    endpoint = _LLM_PROFILES[resolved].local
    return ChatLLMProfile(
        profile=resolved,
        base_url=endpoint.base_url,
        model=endpoint.model,
        api_key_env=endpoint.api_key_env,
        key_file=_KEY_FILE_BY_ENV.get(endpoint.api_key_env),
    )


def _profile_key(
    profile: ChatLLMProfile,
    environ: Mapping[str, str],
    roots: Sequence[Path] | None = None,
) -> tuple[str, str | None]:
    """The profile credential, resolved the way llm_profiles.py:55-66 resolves it."""

    value = environ.get(profile.api_key_env, "").strip()
    if value:
        origin = (
            f"managed-file(env:{profile.api_key_env})"
            if profile.api_key_env in applied_env_names(environ)
            else f"env:{profile.api_key_env}"
        )
        return value, origin
    if profile.key_file:
        return _walk_key_file(profile.key_file, roots or _key_file_roots())
    return "", None


def _managed_origin(
    store: ManagedSecretsStore | None, field: str, environ: Mapping[str, str]
) -> str | None:
    if _managed_value(store, field, environ):
        return "managed-file"
    return None


def resolve_bocha_or_serper(
    key: str,
    *,
    environ: Mapping[str, str],
    secrets_store: ManagedSecretsStore | None,
    key_file_roots: Sequence[Path] | None = None,
) -> RuntimeConnection:
    field = f"{key}.api_key"
    roots = tuple(key_file_roots) if key_file_roots is not None else _key_file_roots()
    spec = next((item for item in SECRET_SPECS if item.field == field), None)
    endpoint = BOCHA_ENDPOINT if key == "bocha" else SERPER_ENDPOINT
    env_names = (spec.env_var,) if spec is not None else ()
    applied = applied_env_names(environ)
    value, origin = _first_env(environ, env_names, applied_env=applied)
    if not value:
        for filename in spec.legacy_files if spec is not None else ():
            value, origin = _walk_key_file(filename, roots)
            if value:
                break
    enabled = bool(value)
    if enabled:
        note = f"运行期使用 provider 固定主机（{endpoint}）；凭据来源 {origin}"
    else:
        note = f"运行期不可用：{spec.env_var if spec else field} 与旧 key 文件均缺失"
    if _pending_restart(secrets_store, field, value, environ):
        note += "；受管文件已保存新值，重启服务后生效"
    return RuntimeConnection(
        key=key,
        label=spec.label if spec is not None else key,
        kind="web_search",
        enabled=enabled,
        base_url=endpoint,
        model=None,
        api_key=value,
        api_key_origin=origin,
        endpoint_origin="pinned-provider-host",
        runtime_note=note,
        pending_restart=_pending_restart(secrets_store, field, value, environ),
    )


def resolve_embedding(
    *,
    environ: Mapping[str, str],
    secrets_store: ManagedSecretsStore | None,
    key_file_roots: Sequence[Path] | None = None,
) -> RuntimeConnection:
    """Base URL/model from the frozen bundle; credential from ``load_local_api_key()``."""

    from src.data_agents.company.vectorizer import EmbeddingClient

    client = EmbeddingClient()
    base_url = client.base_url
    model = "Qwen/Qwen3-Embedding-8B"
    roots = tuple(key_file_roots) if key_file_roots is not None else _key_file_roots()
    value, origin = _local_key(environ, roots)
    enabled = bool(value) and bool(base_url)
    if enabled:
        note = (
            f"运行期 base_url 由 release embedding bundle 冻结（{base_url}）；"
            f"凭据来源 {origin}"
        )
    else:
        note = "运行期不可用：本地凭据缺失（API_KEY/OPENAI_API_KEY/SGLANG_API_KEY/.sglang_api_key 全空）"
    if _pending_restart(secrets_store, "embedding.api_key", value, environ):
        note += "；受管文件已保存新值，重启服务后生效"
    return RuntimeConnection(
        key="embedding",
        label="Embedding 模型端点",
        kind="embedding",
        enabled=enabled,
        base_url=base_url,
        model=model,
        api_key=value,
        api_key_origin=origin,
        endpoint_origin="release-bundle-frozen",
        runtime_note=note,
        pending_restart=_pending_restart(
            secrets_store, "embedding.api_key", value, environ
        ),
    )


def resolve_rerank(
    *,
    environ: Mapping[str, str],
    settings_store: Any | None,
    secrets_store: ManagedSecretsStore | None,
    key_file_roots: Sequence[Path] | None = None,
) -> RuntimeConnection:
    """Rerank is enabled only when its base URL is configured (rerank_client.py:224-236)."""

    from src.data_agents.canonical_v2.rerank_client import (
        DEFAULT_MODEL,
        ENV_API_KEY,
        ENV_API_KEY_FILE,
        ENV_BASE_URL,
        ENV_MODEL,
    )

    applied = applied_env_names(environ)
    base_url = environ.get(ENV_BASE_URL, "").strip()
    endpoint_origin: str | None = None
    if base_url:
        # The bootstrap projects the managed file's rerank_base_url into exactly
        # this variable, so a bare "env:" would tell the operator someone pinned
        # an environment variable — when it is the value they typed on this page.
        endpoint_origin = (
            f"managed-file(env:{ENV_BASE_URL})"
            if ENV_BASE_URL in applied
            else f"env:{ENV_BASE_URL}"
        )
    if not base_url and settings_store is not None:
        managed_base, managed_origin = _managed_setting(
            settings_store, "extraction_endpoints.rerank_base_url"
        )
        base_url, endpoint_origin = managed_base, managed_origin
    model = environ.get(ENV_MODEL, "").strip() or DEFAULT_MODEL
    roots = tuple(key_file_roots) if key_file_roots is not None else _key_file_roots()
    value, origin = _first_env(environ, (ENV_API_KEY,), applied_env=applied)
    if not value:
        key_file = environ.get(ENV_API_KEY_FILE, "").strip()
        if key_file:
            try:
                material = Path(key_file).read_text(encoding="utf-8").strip()
            except OSError:
                material = ""
            if material:
                value, origin = material, f"file:{ENV_API_KEY_FILE}"
    if not value:
        # The offline reranker (providers/rerank.py:35) and the LAN box share the
        # local credential; report it as such instead of claiming "no key".
        local_value, local_origin = _local_key(environ, roots)
        if local_value:
            value, origin = local_value, f"local-key:{local_origin}"
    enabled = bool(base_url)
    note = (
        f"运行期已启用 rerank（base_url 来源 {endpoint_origin}）；凭据来源 {origin or '未配置'}"
        if enabled
        else f"运行期未启用：未配置 {ENV_BASE_URL}（configured_reranker() 返回 None，"
        "服务不会调用 rerank）"
    )
    return RuntimeConnection(
        key="rerank",
        label="Rerank 模型端点",
        kind="rerank",
        enabled=enabled,
        base_url=base_url or None,
        model=model,
        api_key=value,
        api_key_origin=origin,
        endpoint_origin=endpoint_origin,
        runtime_note=(
            note if enabled else note + "；如需启用请在页面填写端点并重启服务"
        )
        + (
            "；受管文件已保存新值，重启服务后生效"
            if _pending_restart(secrets_store, "rerank.api_key", value, environ)
            else ""
        ),
        pending_restart=_pending_restart(
            secrets_store, "rerank.api_key", value, environ
        ),
    )


def resolve_llm(
    *,
    environ: Mapping[str, str],
    secrets_store: ManagedSecretsStore | None,
    key_file_roots: Sequence[Path] | None = None,
) -> RuntimeConnection:
    """The active chat profile — the LLM the serving line answers and rewrites with."""

    roots = tuple(key_file_roots) if key_file_roots is not None else _key_file_roots()
    profile = chat_llm_profile(environ)
    base_url = profile.base_url.strip()
    model = profile.model or None
    value, origin = _profile_key(profile, environ, roots)
    enabled = bool(base_url and value)
    if not base_url:
        note = f"运行期未配置：chat profile {profile.profile} 的 base_url 为空"
    elif not value:
        note = (
            f"运行期不可用：chat profile {profile.profile} 的凭据缺失"
            f"（{profile.api_key_env} 与 key 文件均未命中）"
        )
    else:
        note = (
            f"运行期使用 chat profile {profile.profile}（CHAT_LLM_PROFILE）；"
            f"base_url {base_url}；凭据来源 {origin}"
        )
    return RuntimeConnection(
        key="llm",
        label=f"LLM 档位（{profile.profile}）",
        kind="llm",
        enabled=enabled,
        base_url=base_url or None,
        model=model,
        api_key=value,
        api_key_origin=origin,
        endpoint_origin=f"chat-profile:{profile.profile}",
        runtime_note=(
            note + "；受管文件已保存新值，重启服务后生效"
            if _pending_restart(secrets_store, "llm.api_key", value, environ)
            else note
        ),
        pending_restart=_pending_restart(secrets_store, "llm.api_key", value, environ),
    )


def _managed_setting(store: Any, path: str) -> tuple[str, str | None]:
    try:
        _document, fields = store.effective()
    except Exception:  # noqa: BLE001 - a broken managed file must not break status
        return "", None
    for field in fields:
        if field.path == path:
            value = field.value
            if value in (None, ""):
                return "", None
            origin = (
                "managed-file"
                if field.source == "file"
                else f"{field.source}:{field.env_var}"
            )
            return str(value), origin
    return "", None


def resolve_connections(
    *,
    environ: Mapping[str, str] | None = None,
    settings_store: Any | None = None,
    secrets_store: ManagedSecretsStore | None = None,
    key_file_roots: Sequence[Path] | None = None,
) -> dict[str, RuntimeConnection]:
    """Resolve every connection the page can test, in the page's order."""

    values = dict(os.environ) if environ is None else dict(environ)
    roots = tuple(key_file_roots) if key_file_roots is not None else _key_file_roots()
    return {
        "bocha": resolve_bocha_or_serper(
            "bocha", environ=values, secrets_store=secrets_store, key_file_roots=roots
        ),
        "serper": resolve_bocha_or_serper(
            "serper", environ=values, secrets_store=secrets_store, key_file_roots=roots
        ),
        "rerank": resolve_rerank(
            environ=values,
            settings_store=settings_store,
            secrets_store=secrets_store,
            key_file_roots=roots,
        ),
        "embedding": resolve_embedding(
            environ=values, secrets_store=secrets_store, key_file_roots=roots
        ),
        "llm": resolve_llm(
            environ=values, secrets_store=secrets_store, key_file_roots=roots
        ),
    }


__all__ = [
    "BOCHA_ENDPOINT",
    "ChatLLMProfile",
    "SERPER_ENDPOINT",
    "RuntimeConnection",
    "chat_llm_profile",
    "resolve_bocha_or_serper",
    "resolve_connections",
    "resolve_embedding",
    "resolve_llm",
    "resolve_rerank",
]
