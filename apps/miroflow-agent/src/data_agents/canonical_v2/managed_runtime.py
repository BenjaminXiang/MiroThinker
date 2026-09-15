"""Startup projection of the managed files into the process environment.

Requirement R16 (2026-09-15): the admin page edits managed files, and services
read them **at startup** — one uniform mechanism, no hot reload. This module is
that one mechanism. It runs once per process, before anything can serve a
request, and it never wins against the environment:

* only values **explicitly present in a managed file** are projected (defaults
  are never projected, so a shipped default can never masquerade as an operator
  decision);
* an existing environment variable is always kept (the service unit stays the
  authority, and ``env > file`` matches the W1 precedence rule);
* the return value is a receipt of paths, field names and counts — never a value;
* any unreadable file is a no-op, so a broken managed file cannot fail a boot.

The environment variable :data:`APPLIED_ENV_VAR` records which variables this
process adopted from the managed files. It carries names only, and it is what
lets the admin page distinguish "set by the environment" from "set by the managed
file" without ever reading a credential back.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
import json
import logging
import os
from typing import Any

from .managed_config import (
    _FIELD_ENV_VARS,
    ManagedSettings,
    ManagedSettingsStore,
    assert_non_secret_payload,
    default_settings_path,
    flatten_settings,
)
from .managed_secrets import ManagedSecretsStore, default_secrets_path

_LOGGER = logging.getLogger(__name__)

APPLIED_ENV_VAR = "CANONICAL_V2_MANAGED_ENV_APPLIED"


def applied_env_names(environ: Mapping[str, str] | None = None) -> frozenset[str]:
    """Names of the environment variables this process adopted from managed files."""

    values = os.environ if environ is None else environ
    raw = values.get(APPLIED_ENV_VAR, "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _record_applied(names: frozenset[str], environ: MutableMapping[str, str]) -> None:
    if not names:
        return
    environ[APPLIED_ENV_VAR] = ",".join(sorted(names))


def render_env_value(value: Any) -> str | None:
    """Render a managed value the way the consuming code parses it."""

    if value is None:
        return None
    if isinstance(value, bool):
        # Flag readers accept "1"/"true" for on and "0"/"false" for off.
        return "1" if value else "0"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _file_owned_values(store: ManagedSettingsStore) -> dict[str, Any]:
    """Operator-chosen values in the managed file, keyed by field path.

    Read from the on-disk payload rather than the resolved document, and keep only
    values that **differ from the schema default**: the settings store writes the
    complete document on every save, so "present in the file" alone would project
    a shipped default into the environment as if an operator had chosen it.
    """

    try:
        payload = json.loads(store.path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    except ValueError as exc:
        _LOGGER.warning(
            "managed settings file is not valid JSON (%s); leaving the environment "
            "untouched",
            type(exc).__name__,
        )
        return {}
    if not isinstance(payload, Mapping):
        return {}
    try:
        assert_non_secret_payload(payload)
        ManagedSettings.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - a broken file must not fail a boot
        _LOGGER.warning(
            "managed settings are invalid (%s); leaving the environment untouched",
            type(exc).__name__,
        )
        return {}
    defaults = flatten_settings(ManagedSettings().model_dump(mode="json"))
    return {
        path: value
        for path, value in flatten_settings(payload).items()
        if path in _FIELD_ENV_VARS and value is not None and value != defaults.get(path)
    }


def apply_managed_runtime_config(
    *,
    environ: MutableMapping[str, str] | None = None,
    settings_store: ManagedSettingsStore | None = None,
    secrets_store: ManagedSecretsStore | None = None,
) -> dict[str, Any]:
    """Project file-owned settings and credentials into the process environment."""

    target: MutableMapping[str, str] = os.environ if environ is None else environ

    settings_path = default_settings_path(target)
    store = settings_store or ManagedSettingsStore(path=settings_path, environ=target)
    applied_fields: list[str] = []
    applied_env_vars: list[str] = []
    skipped_env_vars: list[str] = []
    for path, file_value in sorted(_file_owned_values(store).items()):
        env_var = _FIELD_ENV_VARS[path]
        rendered = render_env_value(file_value)
        if rendered is None:
            continue
        if target.get(env_var, "").strip():
            skipped_env_vars.append(env_var)
            continue
        target[env_var] = rendered
        applied_fields.append(path)
        applied_env_vars.append(env_var)

    secrets = secrets_store or ManagedSecretsStore(path=default_secrets_path(target))
    try:
        secret_receipt = secrets.apply_to_environ(target)
    except Exception as exc:  # noqa: BLE001 - same fail-open contract
        _LOGGER.warning(
            "managed secrets are unreadable (%s); leaving the environment untouched",
            type(exc).__name__,
        )
        secret_receipt = {"applied": (), "skipped_env": ()}

    adopted = applied_env_names(target)
    _record_applied(
        adopted | frozenset(applied_env_vars) | frozenset(secret_receipt["applied"]),
        target,
    )

    receipt = {
        "settings_path": str(store.path),
        "settings_applied": tuple(applied_fields),
        "settings_skipped_env": tuple(skipped_env_vars),
        "secrets_path": str(secrets.path),
        "secrets_applied_env": tuple(secret_receipt["applied"]),
        "secrets_skipped_env": tuple(secret_receipt["skipped_env"]),
        "applied_env_var": APPLIED_ENV_VAR,
    }
    if (
        receipt["settings_applied"]
        or receipt["secrets_applied_env"]
        or receipt["settings_skipped_env"]
        or receipt["secrets_skipped_env"]
    ):
        _LOGGER.info(
            "managed configuration adopted at startup: settings=%d secrets=%d "
            "skipped=%d (names only; no values logged)",
            len(receipt["settings_applied"]),
            len(receipt["secrets_applied_env"]),
            len(receipt["settings_skipped_env"]) + len(receipt["secrets_skipped_env"]),
        )
    return receipt


__all__ = [
    "APPLIED_ENV_VAR",
    "ManagedSettings",
    "apply_managed_runtime_config",
    "applied_env_names",
    "render_env_value",
]
