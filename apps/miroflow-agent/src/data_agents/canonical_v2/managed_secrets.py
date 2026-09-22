"""Managed connection credentials for the serving line.

Credentials cannot live in ``managed_settings.json``: that file's schema rejects
credential-shaped keys by construction, and the rejection is what keeps the
settings file safe to read, print, diff and audit. This module adds the sibling
carrier — ``config/managed/secrets.json`` — with the same lifecycle:

* whitelist of connection fields only, nothing free-form;
* atomic write (tmp file + ``os.replace``) with mode ``0600``;
* append-only audit that records field names, actions and four-character tails —
  never plaintext;
* a missing, unreadable or malformed file resolves to "not configured", never to
  an error.

Nothing here reads the file on a request path. The operator's value becomes
effective when the process starts and :meth:`ManagedSecretsStore.apply_to_environ`
projects it into the environment (requirement R16: one uniform "read at service
startup", no hot reload). An existing environment variable always wins, so the
service unit stays the authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any

DEFAULT_SECRETS_FILENAME = "secrets.json"
DEFAULT_SECRETS_AUDIT_FILENAME = "secrets-audit.jsonl"
SECRETS_PATH_ENV = "CANONICAL_V2_MANAGED_SECRETS"
SECRETS_SCHEMA_VERSION = 1

MAX_SECRET_LENGTH = 512
_MASK_HEAD = 3
_MASK_TAIL = 4

_KEY_ROOT_ENV_NAMES = ("CANONICAL_V2_KEY_ROOTS", "CANONICAL_V2_KEY_ROOT")


class ManagedSecretsError(ValueError):
    """The managed secrets request or file is not acceptable."""


class ManagedSecretsUnsupportedError(ManagedSecretsError):
    """A field outside the credential whitelist was requested."""


def chat_llm_key_env(environ: Mapping[str, str] | None = None) -> str:
    """The credential variable the **active chat profile** reads at runtime.

    Mirrors ``knowledge_serving_isolated.py:2087-2096`` (the serving answer/rewrite
    LLM) through ``professor/llm_profiles.py:273``: the profile's own
    ``api_key_env`` — ``DEEPSEEK_API_KEY`` for ``deepseekv4flash``, ``API_KEY`` for
    the local ``gemma4`` endpoint. Writing a key to the wrong variable would look
    saved on the page and change nothing at runtime, so the page follows the
    profile.
    """

    values = os.environ if environ is None else environ
    profile = (values.get("CHAT_LLM_PROFILE", "") or "").strip() or "gemma4"
    try:
        from src.data_agents.professor.llm_profiles import (
            _LLM_PROFILES,
            resolve_professor_llm_profile_name,
        )

        resolved = resolve_professor_llm_profile_name(profile_name=profile)
        return str(_LLM_PROFILES[resolved].local.api_key_env)
    except Exception:  # noqa: BLE001 - the table is optional for reporting
        return "LOCAL_LLM_API_KEY"


@dataclass(frozen=True, slots=True)
class SecretSpec:
    """One credential: the page field, its environment variable, legacy key file."""

    field: str
    connection: str
    label: str
    env_var: str | None
    legacy_files: tuple[str, ...] = ()
    #: Other variables this **same value** must also occupy when it is projected at
    #: startup. The read-side aliases above are for *reporting* an externally set
    #: value; these are writes, for a credential that two runtime authorities
    #: consume through **different** slots. The page cannot know which authority a
    #: site runs, and one credential must not starve the other line, so the field
    #: fills both.
    mirror_env_vars: tuple[str, ...] = ()
    extra_env_names: tuple[str, ...] = ()
    env_var_resolver: Callable[[Mapping[str, str]], str] | None = None

    def env_var_for(self, environ: Mapping[str, str] | None = None) -> str | None:
        """The variable this credential must occupy, resolved for the current process."""

        if self.env_var:
            return self.env_var
        if self.env_var_resolver is not None:
            try:
                return self.env_var_resolver(
                    environ if environ is not None else os.environ
                )
            except Exception:  # noqa: BLE001 - never fail a read over metadata
                return None
        return None

    def env_vars_to_fill(
        self, environ: Mapping[str, str] | None = None
    ) -> tuple[str, ...]:
        """Every variable a projected value must occupy, primary first."""

        primary = self.env_var_for(environ)
        names = [primary] if primary else []
        for name in self.mirror_env_vars:
            if name not in names:
                names.append(name)
        return tuple(names)


# The whitelist. Every entry is a credential some connection actually consumes;
# adding a field here is the only way to make it settable from the page.
SECRET_SPECS: tuple[SecretSpec, ...] = (
    SecretSpec(
        field="bocha.api_key",
        connection="bocha",
        label="Bocha 博查 Web 搜索",
        env_var="BOCHA_API_KEY",
        legacy_files=(".bocha_api_key",),
    ),
    SecretSpec(
        field="serper.api_key",
        connection="serper",
        label="Serper Web 搜索",
        env_var="SERPER_API_KEY",
        legacy_files=(".serper_api_key",),
    ),
    SecretSpec(
        field="rerank.api_key",
        connection="rerank",
        label="Rerank 模型端点",
        # rerank_client.py:33-38 — the serving reranker reads exactly this variable
        # (and its *_API_KEY_FILE sibling); rerank itself stays disabled until
        # CANONICAL_V2_RERANK_BASE_URL is configured.
        env_var="CANONICAL_V2_RERANK_API_KEY",
    ),
    SecretSpec(
        field="embedding.api_key",
        connection="embedding",
        label="Embedding 模型端点",
        # Two authorities consume this one credential, through two different slots,
        # and the page cannot know which one a site runs:
        #
        # * the recorded (self-hosted) authority reads ``load_local_api_key()``
        #   (providers/local_api_key.py:8-11, called at knowledge_build_isolated.py:6570):
        #   API_KEY -> OPENAI_API_KEY -> SGLANG_API_KEY -> .sglang_api_key. We write
        #   the least generic of those, and accept the siblings when reporting origins.
        # * the candidate (gateway) authority reads only the slot its bundle declares
        #   as ``api_key_source`` (knowledge_build_isolated._GATEWAY_EMBEDDING_API_KEY_ENV,
        #   "CANONICAL_V2_EMBEDDING_API_KEY"). That slot is deliberately *not* the
        #   local one, so that a bundle pointing at a third-party host can never be
        #   handed the self-hosted endpoint's key — the read side stays closed, and
        #   the page fills both slots instead.
        env_var="SGLANG_API_KEY",
        mirror_env_vars=("CANONICAL_V2_EMBEDDING_API_KEY",),
        legacy_files=(".sglang_api_key",),
        extra_env_names=("API_KEY", "OPENAI_API_KEY"),
    ),
    SecretSpec(
        field="llm.api_key",
        connection="llm",
        label="LLM 档位（chat profile）",
        # Profile-owned: the variable depends on CHAT_LLM_PROFILE (see chat_llm_key_env).
        env_var=None,
        legacy_files=(),
        env_var_resolver=lambda environ: (
            chat_llm_key_env(environ) or "LOCAL_LLM_API_KEY"
        ),
    ),
)

SPEC_BY_FIELD: dict[str, SecretSpec] = {spec.field: spec for spec in SECRET_SPECS}


def secret_specs_for_connection(connection: str) -> tuple[SecretSpec, ...]:
    return tuple(spec for spec in SECRET_SPECS if spec.connection == connection)


def mask_secret(value: str) -> str:
    """Render a credential for display: at most 3 leading + 4 trailing characters."""

    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    if len(text) <= _MASK_TAIL:
        return "•" * 3
    if len(text) < 12:
        return "•" * 3 + text[-_MASK_TAIL:]
    return text[:_MASK_HEAD] + "…" + text[-_MASK_TAIL:]


def suffix4(value: str) -> str | None:
    text = "" if value is None else str(value).strip()
    return text[-_MASK_TAIL:] if text else None


def _validate_secret(field: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ManagedSecretsError(f"{field} must be a string")
    text = value.strip()
    if not text:
        raise ManagedSecretsError(f"{field} must not be blank (use null to clear it)")
    if len(text) > MAX_SECRET_LENGTH:
        raise ManagedSecretsError(
            f"{field} must be at most {MAX_SECRET_LENGTH} characters"
        )
    if any(character in text for character in ("\n", "\r", "\x00")):
        raise ManagedSecretsError(f"{field} must be a single line without NUL bytes")
    return text


def default_key_file_roots(
    environ: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Mirror the providers' key-file lookup: env roots, then ancestors of the checkout."""

    values = os.environ if environ is None else environ
    roots: list[Path] = []
    for env_name in _KEY_ROOT_ENV_NAMES:
        raw = values.get(env_name, "").strip()
        if raw:
            roots.extend(Path(part) for part in raw.split(os.pathsep) if part)
    here = Path(__file__).resolve()
    roots.extend(here.parents)
    roots.append(Path.cwd())
    roots.extend(Path.cwd().parents)
    seen: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.append(root)
    return tuple(seen)


@dataclass(frozen=True, slots=True)
class SecretState:
    """One credential's display state. Never carries plaintext."""

    field: str
    connection: str
    label: str
    env_var: str
    configured: bool
    mask: str | None
    suffix4: str | None
    origin: str | None
    applied_to_process_env: bool
    legacy_files: tuple[str, ...]
    #: Variables this credential *also* fills when projected (empty for most
    #: fields). The page names them so "restart and the service reads it" is not
    #: silently half true.
    mirror_env_vars: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "connection": self.connection,
            "label": self.label,
            "env_var": self.env_var,
            "configured": self.configured,
            "mask": self.mask,
            "suffix4": self.suffix4,
            "origin": self.origin,
            "applied_to_process_env": self.applied_to_process_env,
            "legacy_files": list(self.legacy_files),
            "mirror_env_vars": list(self.mirror_env_vars),
        }


class ManagedSecretsStore:
    """Read, validate, atomically write, and audit the managed credential file."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        key_file_roots: Sequence[Path] | None = None,
        clock: Callable[[], datetime] | None = None,
        repo_root: Path | str | None = None,
    ) -> None:
        self._environ = dict(os.environ if environ is None else environ)
        self._path = (
            Path(path)
            if path is not None
            else default_secrets_path(self._environ, repo_root=repo_root)
        )
        self._key_file_roots = (
            tuple(key_file_roots)
            if key_file_roots is not None
            else default_key_file_roots(self._environ)
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def path(self) -> Path:
        return self._path

    @property
    def audit_path(self) -> Path:
        return self._path.with_name(DEFAULT_SECRETS_AUDIT_FILENAME)

    @property
    def key_file_roots(self) -> tuple[Path, ...]:
        """Roots searched for legacy key files (same order the providers use)."""

        return self._key_file_roots

    # -- reads ---------------------------------------------------------------

    def exists(self) -> bool:
        return self._path.is_file()

    def permissions_ok(self) -> bool:
        """True when the file is absent or readable only by its owner."""

        try:
            mode = self._path.stat().st_mode
        except OSError:
            return True
        return (mode & 0o077) == 0

    def raw(self) -> dict[str, str]:
        """Return the whitelisted on-disk credentials, or ``{}`` when unusable."""

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, Mapping):
            return {}
        values = payload.get("secrets")
        if not isinstance(values, Mapping):
            return {}
        resolved: dict[str, str] = {}
        for field, value in values.items():
            spec = SPEC_BY_FIELD.get(str(field))
            if spec is None or not isinstance(value, str) or not value.strip():
                continue
            resolved[spec.field] = value.strip()
        return resolved

    def resolve(
        self, spec: SecretSpec, *, environ: Mapping[str, str] | None = None
    ) -> tuple[str, str | None]:
        """Return ``(material, origin)`` for one credential without echoing it."""

        values = self._environ if environ is None else environ
        return self._resolve(spec, values, frozenset())

    def resolve_field(
        self,
        field: str,
        *,
        environ: Mapping[str, str] | None = None,
        applied_env: frozenset[str] | None = None,
    ) -> tuple[str, str | None]:
        """Resolve one whitelisted field name to ``(material, origin)``.

        Callers that only know the page field name (the connectivity-test route)
        use this instead of reaching into the spec table themselves.
        """

        spec = SPEC_BY_FIELD.get(field)
        if spec is None:
            raise ManagedSecretsUnsupportedError(
                f"field is not in the managed credential whitelist: {field}"
            )
        values = self._environ if environ is None else environ
        return self._resolve(
            spec, values, applied_env if applied_env is not None else frozenset()
        )

    def _resolve(
        self,
        spec: SecretSpec,
        environ: Mapping[str, str],
        applied_env: frozenset[str],
    ) -> tuple[str, str | None]:
        file_value = self.raw().get(spec.field, "")
        env_var = spec.env_var_for(environ)
        env_value = environ.get(env_var, "").strip() if env_var else ""
        if env_value and env_var not in applied_env:
            return env_value, f"env:{env_var}"
        if file_value:
            return file_value, "managed-file"
        if env_value:
            return env_value, f"env:{env_var}"
        for alias in spec.extra_env_names:
            alias_value = environ.get(alias, "").strip()
            if alias_value:
                return alias_value, f"env:{alias}"
        for root in self._key_file_roots:
            for filename in spec.legacy_files:
                candidate = root / filename
                try:
                    if not candidate.is_file():
                        continue
                    value = candidate.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                if value:
                    return value, f"legacy-file:{filename}"
        return "", None

    def describe(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        applied_env: frozenset[str] | None = None,
    ) -> tuple[SecretState, ...]:
        """Per-credential display state: configured, mask, origin. No plaintext."""

        values = self._environ if environ is None else environ
        applied = applied_env if applied_env is not None else frozenset()
        states: list[SecretState] = []
        for spec in SECRET_SPECS:
            material, origin = self._resolve(spec, values, applied)
            states.append(
                SecretState(
                    field=spec.field,
                    connection=spec.connection,
                    label=spec.label,
                    env_var=spec.env_var_for(values) or "",
                    configured=bool(material),
                    mask=mask_secret(material) or None,
                    suffix4=suffix4(material),
                    origin=origin,
                    applied_to_process_env=bool(material) and spec.env_var in applied,
                    legacy_files=spec.legacy_files,
                    mirror_env_vars=spec.mirror_env_vars,
                )
            )
        return tuple(states)

    # -- writes --------------------------------------------------------------

    def patch(
        self,
        values: Mapping[str, Any],
        *,
        operator: str | None = None,
    ) -> dict[str, Any]:
        """Set (string) or clear (``None``/blank) the named credentials.

        Both the file and the audit record are value-free on the audit side: the
        audit stores the field name, the action and the four-character tail.
        """

        if not isinstance(values, Mapping) or not values:
            raise ManagedSecretsError("secrets body must be a non-empty object")
        unknown = sorted(set(str(field) for field in values) - set(SPEC_BY_FIELD))
        if unknown:
            raise ManagedSecretsUnsupportedError(
                "field is not in the managed credential whitelist: "
                + ", ".join(unknown)
            )
        before = self.raw()
        after = dict(before)
        changes: list[dict[str, Any]] = []
        for raw_field, raw_value in values.items():
            field = str(raw_field)
            spec = SPEC_BY_FIELD[field]
            if raw_value is None or (
                isinstance(raw_value, str) and not raw_value.strip()
            ):
                if field in after:
                    after.pop(field)
                    changes.append({"field": field, "action": "clear", "suffix4": None})
                continue
            text = _validate_secret(field, raw_value)
            if before.get(field) == text:
                continue
            after[field] = text
            changes.append(
                {
                    "field": field,
                    "action": "set",
                    "suffix4": suffix4(text),
                    "env_var": spec.env_var,
                }
            )
        if not changes:
            return {"changed": [], "audit_written": False}
        self._atomic_write({"schema_version": SECRETS_SCHEMA_VERSION, "secrets": after})
        self._append_audit(
            {
                "action": "secrets-patch",
                "operator": (operator or "anonymous").strip() or "anonymous",
                "changes": changes,
                "stored_fields": sorted(after),
            }
        )
        return {
            "changed": [entry["field"] for entry in changes],
            "audit_written": True,
        }

    def clear_all(self, *, operator: str | None = None) -> dict[str, Any]:
        """Remove every stored credential (used by the page's clear-all action)."""

        before = self.raw()
        if not before:
            return {"changed": [], "audit_written": False}
        self._atomic_write({"schema_version": SECRETS_SCHEMA_VERSION, "secrets": {}})
        self._append_audit(
            {
                "action": "secrets-clear-all",
                "operator": (operator or "anonymous").strip() or "anonymous",
                "changes": [
                    {"field": field, "action": "clear", "suffix4": None}
                    for field in sorted(before)
                ],
                "stored_fields": [],
            }
        )
        return {"changed": sorted(before), "audit_written": True}

    def _atomic_write(self, document: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._path.parent, 0o700)
        except OSError:
            pass
        payload = json.dumps(
            document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        )
        descriptor, temp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix=".secrets-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self._path)
            os.chmod(self._path, 0o600)
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

    # -- startup projection --------------------------------------------------

    def apply_to_environ(
        self, environ: Mapping[str, str] | None = None
    ) -> dict[str, tuple[str, ...]]:
        """Project stored credentials into the environment. Existing values win.

        Returns the environment variable names applied and skipped — names only,
        never values — so the caller can log a receipt.
        """

        target: MutableMapping[str, str] = os.environ if environ is None else environ  # type: ignore[assignment]
        stored = self.raw()
        applied: list[str] = []
        skipped: list[str] = []
        for spec in SECRET_SPECS:
            file_value = stored.get(spec.field)
            if not file_value:
                continue
            for env_var in spec.env_vars_to_fill(target):
                # The same rule for the primary and its mirrors: an existing
                # value wins, so the service unit stays the authority.
                if target.get(env_var, "").strip():
                    skipped.append(env_var)
                    continue
                target[env_var] = file_value
                applied.append(env_var)
        return {"applied": tuple(applied), "skipped_env": tuple(skipped)}


def default_repo_root() -> Path:
    """Return the checkout root that contains this app (worktree aware)."""

    here = Path(__file__).resolve()
    # apps/miroflow-agent/src/data_agents/canonical_v2/managed_secrets.py
    return here.parents[5]


def default_secrets_path(
    environ: Mapping[str, str] | None = None,
    *,
    repo_root: Path | str | None = None,
) -> Path:
    values = os.environ if environ is None else environ
    override = values.get(SECRETS_PATH_ENV, "").strip()
    if override:
        return Path(override)
    root = Path(repo_root) if repo_root is not None else default_repo_root()
    return root / "config" / "managed" / DEFAULT_SECRETS_FILENAME


__all__ = [
    "DEFAULT_SECRETS_AUDIT_FILENAME",
    "DEFAULT_SECRETS_FILENAME",
    "MAX_SECRET_LENGTH",
    "ManagedSecretsError",
    "ManagedSecretsStore",
    "ManagedSecretsUnsupportedError",
    "SECRET_SPECS",
    "SECRETS_PATH_ENV",
    "SECRETS_SCHEMA_VERSION",
    "SPEC_BY_FIELD",
    "SecretSpec",
    "SecretState",
    "chat_llm_key_env",
    "default_key_file_roots",
    "default_repo_root",
    "default_secrets_path",
    "mask_secret",
    "secret_specs_for_connection",
    "suffix4",
]
