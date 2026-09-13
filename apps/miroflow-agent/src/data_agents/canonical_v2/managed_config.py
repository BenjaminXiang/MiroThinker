"""Managed, non-sensitive operator configuration for the serving line.

One file (`config/managed/settings.json` by default) carries the values an
operator may change from the admin page. The file is a whitelist schema: any key
outside it is rejected, and credential material is structurally excluded. A
missing file, a missing key, or an unreadable file resolves to documented
defaults — never to an error.

Precedence is ``env > file > default`` for every field that already has an
environment variable, so this file can never become a second source of truth for
a behavior the environment pins. Every read reports which source won.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


DEFAULT_SETTINGS_DIRNAME = "config/managed"
DEFAULT_SETTINGS_FILENAME = "settings.json"
DEFAULT_AUDIT_FILENAME = "audit.jsonl"
SETTINGS_PATH_ENV = "CANONICAL_V2_MANAGED_SETTINGS"
SCHEMA_VERSION = 1

PUBLIC_DOMAINS: tuple[str, ...] = ("company", "paper", "patent", "professor")

# Field path -> (environment variable, renderer). Only fields listed here can be
# shadowed by the environment; anything else is file/default owned.
_FIELD_ENV_VARS: dict[str, str] = {
    "collection.max_web_searches_per_run": "WEB_LANE_DAILY_QUOTA",
    "collection.window_start_hour_utc": "CANONICAL_V2_COLLECTION_WINDOW_START_HOUR_UTC",
    "collection.window_end_hour_utc": "CANONICAL_V2_COLLECTION_WINDOW_END_HOUR_UTC",
    "extraction_endpoints.llm_base_url": "LOCAL_LLM_BASE_URL",
    "extraction_endpoints.llm_model": "LOCAL_LLM_MODEL",
    "extraction_endpoints.embedding_base_url": "CANONICAL_V2_EMBEDDING_BASE_URL",
    "extraction_endpoints.embedding_model": "CANONICAL_V2_EMBEDDING_MODEL",
    "extraction_endpoints.rerank_base_url": "CANONICAL_V2_RERANK_BASE_URL",
    "extraction_endpoints.rerank_model": "CANONICAL_V2_RERANK_MODEL",
    "paths.serving_pack_dir": "CANONICAL_V2_SERVING_PACK",
    "paths.access_log_retention_days": "CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS",
}

# Credential-shaped names are rejected even if a future schema mistake would
# otherwise let them through: never persist, never echo, never audit a secret.
_SECRET_NAME_FRAGMENTS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "passwd",
    "credential",
    "database_url",
    "dsn",
    "webhook",
)


class ManagedSettingsError(ValueError):
    """The managed settings request or file is not acceptable."""


class ManagedSettingsUnsupportedError(ManagedSettingsError):
    """A field outside the whitelist (or credential-shaped) was requested."""


class CollectionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    enabled: dict[str, bool] = Field(default_factory=lambda: {d: True for d in PUBLIC_DOMAINS})
    max_web_searches_per_run: int = Field(default=200, ge=0, le=10_000)
    max_llm_calls_per_run: int = Field(default=500, ge=0, le=100_000)
    window_start_hour_utc: int = Field(default=17, ge=0, le=23)
    window_end_hour_utc: int = Field(default=22, ge=0, le=23)

    @field_validator("enabled")
    @classmethod
    def _exact_domains(cls, value: dict[str, bool]) -> dict[str, bool]:
        unknown = sorted(set(value) - set(PUBLIC_DOMAINS))
        if unknown:
            raise ValueError(
                "collection.enabled only accepts the four public domains: "
                + ", ".join(unknown)
            )
        return {domain: bool(value.get(domain, True)) for domain in PUBLIC_DOMAINS}

    @model_validator(mode="after")
    def _ordered_window(self) -> CollectionSettings:
        if self.window_end_hour_utc <= self.window_start_hour_utc:
            raise ValueError(
                "collection.window_end_hour_utc must be greater than "
                "collection.window_start_hour_utc (no overnight wrap)"
            )
        return self


class ExtractionEndpoints(BaseModel):
    """Collection-time endpoints. Credentials are env/key-file owned, never here."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    llm_base_url: str | None = None
    llm_model: str | None = Field(default=None, max_length=200)
    embedding_base_url: str | None = None
    embedding_model: str | None = Field(default=None, max_length=200)
    rerank_base_url: str | None = None
    rerank_model: str | None = Field(default=None, max_length=200)

    @field_validator("*")
    @classmethod
    def _bounded_url_or_name(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if info.field_name.endswith("_base_url"):
            parsed = urlsplit(text)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"{info.field_name} must be an absolute http(s) URL")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError(f"{info.field_name} must not embed credentials")
            return text.rstrip("/")
        if len(text) > 200:
            raise ValueError(f"{info.field_name} must be at most 200 characters")
        return text


class PathSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    serving_pack_dir: str | None = None
    access_log_retention_days: int = Field(default=90, ge=1, le=3650)

    @field_validator("serving_pack_dir")
    @classmethod
    def _absolute_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if not text.startswith("/"):
            raise ValueError("paths.serving_pack_dir must be an absolute path")
        return text


class ManagedSettings(BaseModel):
    """The complete, validated managed configuration document."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1, le=SCHEMA_VERSION)
    collection: CollectionSettings = Field(default_factory=CollectionSettings)
    extraction_endpoints: ExtractionEndpoints = Field(
        default_factory=ExtractionEndpoints
    )
    paths: PathSettings = Field(default_factory=PathSettings)


def assert_non_secret_payload(value: object, *, where: str = "settings") -> None:
    """Refuse any credential-shaped key anywhere in a settings payload."""

    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            if key == "schema_version":
                continue
            folded = key.casefold()
            if any(fragment in folded for fragment in _SECRET_NAME_FRAGMENTS):
                raise ManagedSettingsUnsupportedError(
                    f"{where}.{key} looks like credential material and is not "
                    "allowed in the managed settings file"
                )
            assert_non_secret_payload(child, where=f"{where}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_non_secret_payload(child, where=f"{where}[{index}]")


def _flatten(payload: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


def _dig(payload: Mapping[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _coerce(raw: str, template: Any) -> Any:
    """Coerce an environment string into the type of the field it shadows."""

    text = raw.strip()
    if isinstance(template, bool):
        return text.casefold() in {"1", "true", "yes", "on"}
    if isinstance(template, int) and not isinstance(template, bool):
        return int(text)
    if isinstance(template, float):
        return float(text)
    return text


@dataclass(frozen=True, slots=True)
class EffectiveField:
    path: str
    value: Any
    source: Literal["env", "file", "default"]
    env_var: str | None
    editable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "value": self.value,
            "source": self.source,
            "env_var": self.env_var,
            "editable": self.editable,
        }


class ManagedSettingsStore:
    """Read, validate, atomically write, and audit the managed settings file."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        repo_root: Path | str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._environ = dict(os.environ if environ is None else environ)
        self._repo_root = (
            Path(repo_root) if repo_root is not None else default_repo_root()
        )
        self._path = (
            Path(path) if path is not None else default_settings_path(self._environ)
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def path(self) -> Path:
        return self._path

    @property
    def audit_path(self) -> Path:
        return self._path.with_name(DEFAULT_AUDIT_FILENAME)

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    # -- reads ---------------------------------------------------------------

    def exists(self) -> bool:
        return self._path.is_file()

    def raw(self) -> dict[str, Any]:
        """Return the validated on-disk document, or defaults when unusable."""

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ManagedSettings().model_dump(mode="json")
        if not isinstance(payload, Mapping):
            return ManagedSettings().model_dump(mode="json")
        try:
            assert_non_secret_payload(payload)
            return ManagedSettings.model_validate(payload).model_dump(mode="json")
        except (ManagedSettingsError, ValidationError):
            return ManagedSettings().model_dump(mode="json")

    def effective(self) -> tuple[ManagedSettings, tuple[EffectiveField, ...]]:
        """Resolve ``env > file > default`` and report the winning source."""

        document = ManagedSettings.model_validate(self.raw())
        file_values = _flatten(document.model_dump(mode="json"))
        resolved: dict[str, Any] = dict(file_values)
        sources: dict[str, Literal["env", "file", "default"]] = {}
        defaults = _flatten(ManagedSettings().model_dump(mode="json"))
        for path, value in file_values.items():
            sources[path] = "default" if value == defaults.get(path) else "file"
        for path, env_var in _FIELD_ENV_VARS.items():
            raw = self._environ.get(env_var)
            if raw is None or not raw.strip():
                continue
            try:
                resolved[path] = _coerce(raw, file_values.get(path))
            except (TypeError, ValueError):
                raise ManagedSettingsError(
                    f"environment variable {env_var} does not match the type of {path}"
                ) from None
            sources[path] = "env"
        try:
            effective_document = ManagedSettings.model_validate(
                _unflatten(resolved)
            )
        except ValidationError as exc:
            raise ManagedSettingsError(
                "effective configuration is invalid once environment overrides "
                "are applied"
            ) from exc
        effective_values = _flatten(effective_document.model_dump(mode="json"))
        fields = tuple(
            EffectiveField(
                path=path,
                value=effective_values.get(path),
                source=sources.get(path, "default"),
                env_var=_FIELD_ENV_VARS.get(path),
                editable=sources.get(path, "default") != "env",
            )
            for path in sorted(file_values)
        )
        return effective_document, fields

    def field_map(self) -> dict[str, dict[str, Any]]:
        _, fields = self.effective()
        return {field.path: field.as_dict() for field in fields}

    # -- writes --------------------------------------------------------------

    def patch(
        self,
        updates: Mapping[str, Any],
        *,
        operator: str | None = None,
    ) -> dict[str, Any]:
        """Validate, atomically persist, and audit one whitelist-only patch."""

        if not isinstance(updates, Mapping) or not updates:
            raise ManagedSettingsError("patch body must be a non-empty object")
        assert_non_secret_payload(updates, where="patch")
        allowed = set(_flatten(ManagedSettings().model_dump(mode="json")))
        submitted = _flatten(updates)
        unknown = sorted(set(submitted) - allowed)
        if unknown:
            raise ManagedSettingsUnsupportedError(
                "field is not in the managed settings whitelist: "
                + ", ".join(unknown)
            )
        before = self.raw()
        merged = _deep_merge(before, updates)
        try:
            document = ManagedSettings.model_validate(merged)
        except ValidationError as exc:
            raise ManagedSettingsError(
                "managed settings validation failed: "
                + "; ".join(
                    f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                    for error in exc.errors()
                )
            ) from exc
        serialized = document.model_dump(mode="json")
        before_flat = _flatten(before)
        after_flat = _flatten(serialized)
        changed = sorted(
            path
            for path in after_flat
            if before_flat.get(path) != after_flat.get(path)
        )
        if not changed:
            return {
                "settings": serialized,
                "changed": [],
                "audit_written": False,
            }
        self._atomic_write(serialized)
        self._append_audit(
            {
                "action": "patch",
                "operator": (operator or "anonymous").strip() or "anonymous",
                "before": before,
                "after": serialized,
                "changed": changed,
            }
        )
        return {"settings": serialized, "changed": changed, "audit_written": True}

    def _atomic_write(self, document: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        )
        descriptor, temp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix=".settings-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self._path)
        except BaseException:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def _append_audit(self, record: Mapping[str, Any]) -> None:
        entry = {"at": self._clock().isoformat(), **record}
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True, allow_nan=False)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.audit_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            os.write(descriptor, (line + "\n").encode("utf-8"))
            os.fsync(descriptor)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def audit_records(self) -> tuple[dict[str, Any], ...]:
        try:
            raw = self.audit_path.read_text(encoding="utf-8")
        except OSError:
            return ()
        records: list[dict[str, Any]] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, Mapping):
                records.append(dict(value))
        return tuple(records)


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = {key: value for key, value in base.items()}
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _unflatten(flat: Mapping[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for path, value in flat.items():
        parts = path.split(".")
        cursor = document
        for part in parts[:-1]:
            node = cursor.get(part)
            if not isinstance(node, dict):
                node = {}
                cursor[part] = node
            cursor = node
        cursor[parts[-1]] = value
    return document


def default_repo_root() -> Path:
    """Return the checkout root that contains this app (worktree aware)."""

    here = Path(__file__).resolve()
    # apps/miroflow-agent/src/data_agents/canonical_v2/managed_config.py
    return here.parents[5]


def default_settings_path(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    override = values.get(SETTINGS_PATH_ENV, "").strip()
    if override:
        return Path(override)
    return default_repo_root() / DEFAULT_SETTINGS_DIRNAME / DEFAULT_SETTINGS_FILENAME


def store_from_environment(
    *, environ: Mapping[str, str] | None = None, path: Path | str | None = None
) -> ManagedSettingsStore:
    return ManagedSettingsStore(path=path, environ=environ)


__all__ = [
    "CollectionSettings",
    "DEFAULT_AUDIT_FILENAME",
    "DEFAULT_SETTINGS_DIRNAME",
    "DEFAULT_SETTINGS_FILENAME",
    "EffectiveField",
    "ExtractionEndpoints",
    "ManagedSettings",
    "ManagedSettingsError",
    "ManagedSettingsStore",
    "ManagedSettingsUnsupportedError",
    "PUBLIC_DOMAINS",
    "PathSettings",
    "SCHEMA_VERSION",
    "SETTINGS_PATH_ENV",
    "assert_non_secret_payload",
    "default_repo_root",
    "default_settings_path",
    "store_from_environment",
]
