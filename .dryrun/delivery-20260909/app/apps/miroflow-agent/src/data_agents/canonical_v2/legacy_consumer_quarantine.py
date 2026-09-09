"""Canonical, content-addressed policy for quarantined legacy consumers.

The inventory is static acceptance evidence.  Loading it can only reject malformed or
non-canonical policy bytes; it never enables, imports, or dispatches an entrypoint.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


_SCHEMA_VERSION = "canonical-v2-legacy-consumer-inventory-v1"
_CATEGORIES = (
    "retired_http_routers",
    "retired_frontend_routes",
    "legacy_modules",
    "legacy_scripts",
    "sanctioned_entrypoints",
)
_TOP_LEVEL_KEYS = frozenset({"schema_version", *_CATEGORIES})
_RETIRED_DISPOSITIONS = frozenset({"reference_only", "replaced", "s11c_disposition"})
_MODULE_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\Z")
_GLOB_MARKERS = frozenset("*?[]{}")


class LegacyConsumerInventoryError(ValueError):
    """Inventory bytes or identities are not canonical and fail closed."""


@dataclass(frozen=True, slots=True)
class LegacyConsumerInventory:
    """Immutable-value view over one exact inventory and its content receipt."""

    _payload: dict[str, Any]
    _receipt: dict[str, Any]

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        if mode not in {"python", "json"}:
            raise ValueError("inventory supports only python/json model dumps")
        return deepcopy(self._payload)

    @property
    def receipt(self) -> dict[str, Any]:
        return deepcopy(self._receipt)


def _canonical_bytes(payload: object) -> bytes:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LegacyConsumerInventoryError(
            "legacy inventory is not canonical JSON"
        ) from exc
    return encoded + b"\n"


def _load_json(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise LegacyConsumerInventoryError(
            "legacy inventory must be exact UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise LegacyConsumerInventoryError("legacy inventory must be a JSON object")
    if raw != _canonical_bytes(value):
        raise LegacyConsumerInventoryError(
            "legacy inventory bytes are not in canonical form"
        )
    return value


def _require_repository_path(value: object, repository_root: Path) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise LegacyConsumerInventoryError("inventory path must be non-empty text")
    if (
        "\\" in value
        or "//" in value
        or any(marker in value for marker in _GLOB_MARKERS)
    ):
        raise LegacyConsumerInventoryError("inventory path is not an exact POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value:
        raise LegacyConsumerInventoryError("inventory path must be repository-relative")
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise LegacyConsumerInventoryError("inventory path contains an unsafe segment")

    root = repository_root.resolve(strict=True)
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise LegacyConsumerInventoryError(
                "inventory path cannot traverse a symlink"
            )
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise LegacyConsumerInventoryError(
            "inventory path does not identify one repository file"
        ) from exc
    if not resolved.is_file():
        raise LegacyConsumerInventoryError(
            "inventory path must identify a regular file"
        )
    return value


def _require_module(value: object) -> str:
    if not isinstance(value, str) or _MODULE_RE.fullmatch(value) is None:
        raise LegacyConsumerInventoryError(
            "inventory module must be dot-separated Python identifiers"
        )
    return value


def _validate_entry(
    raw_entry: object,
    *,
    category: str,
    repository_root: Path,
) -> tuple[dict[str, Any], str]:
    if not isinstance(raw_entry, dict):
        raise LegacyConsumerInventoryError("inventory entry must be a JSON object")
    has_path = "path" in raw_entry
    has_module = "module" in raw_entry
    if has_path == has_module:
        raise LegacyConsumerInventoryError(
            "inventory entry requires exactly one path or module"
        )
    expected_keys = {"reason", "replacement", "path" if has_path else "module"}
    if category != "sanctioned_entrypoints":
        expected_keys.add("disposition")
    if set(raw_entry) != expected_keys:
        raise LegacyConsumerInventoryError(
            "inventory entry has unknown or missing fields"
        )

    key = "path" if has_path else "module"
    value = (
        _require_repository_path(raw_entry[key], repository_root)
        if has_path
        else _require_module(raw_entry[key])
    )
    reason = raw_entry["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise LegacyConsumerInventoryError("inventory reason must be non-empty")
    replacement = raw_entry["replacement"]
    if replacement is not None and (
        not isinstance(replacement, str) or not replacement.strip()
    ):
        raise LegacyConsumerInventoryError(
            "inventory replacement must be null or non-empty text"
        )
    if category != "sanctioned_entrypoints":
        if raw_entry["disposition"] not in _RETIRED_DISPOSITIONS:
            raise LegacyConsumerInventoryError("inventory disposition is not allowed")
    return raw_entry, f"{key}:{value}"


def load_legacy_consumer_inventory(
    inventory_path: Path,
    *,
    repository_root: Path,
) -> LegacyConsumerInventory:
    """Load one exact policy file and return its immutable content receipt."""

    if inventory_path.is_symlink() or not inventory_path.is_file():
        raise LegacyConsumerInventoryError(
            "legacy inventory must be one explicit regular file"
        )
    raw = inventory_path.read_bytes()
    payload = _load_json(raw)
    if set(payload) != _TOP_LEVEL_KEYS:
        raise LegacyConsumerInventoryError(
            "legacy inventory top-level schema is not exact"
        )
    if payload["schema_version"] != _SCHEMA_VERSION:
        raise LegacyConsumerInventoryError("legacy inventory schema version is unknown")

    identities: set[str] = set()
    disposition_counts: dict[str, int] = {}
    s11c_entries: list[dict[str, str]] = []
    for category in _CATEGORIES:
        entries = payload[category]
        if not isinstance(entries, list):
            raise LegacyConsumerInventoryError(
                "legacy inventory categories must be arrays"
            )
        category_identities: list[str] = []
        for raw_entry in entries:
            entry, identity = _validate_entry(
                raw_entry,
                category=category,
                repository_root=repository_root,
            )
            if identity in identities:
                raise LegacyConsumerInventoryError(
                    "legacy inventory identity is duplicated across categories"
                )
            identities.add(identity)
            category_identities.append(identity)
            if category != "sanctioned_entrypoints":
                disposition = entry["disposition"]
                disposition_counts[disposition] = (
                    disposition_counts.get(disposition, 0) + 1
                )
                if disposition == "s11c_disposition":
                    inventory_value = entry.get("path", entry.get("module"))
                    if not isinstance(inventory_value, str):
                        raise LegacyConsumerInventoryError(
                            "S11C disposition identity is invalid"
                        )
                    s11c_entries.append(
                        {
                            "inventory_category": category,
                            "inventory_path": inventory_value,
                        }
                    )
        if category_identities != sorted(category_identities):
            raise LegacyConsumerInventoryError(
                "legacy inventory category entries are not canonically ordered"
            )

    sanctioned_identities = {
        f"{'path' if 'path' in entry else 'module'}:"
        f"{entry.get('path', entry.get('module'))}"
        for entry in payload["sanctioned_entrypoints"]
    }
    for category in _CATEGORIES[:-1]:
        for entry in payload[category]:
            disposition = entry["disposition"]
            replacement = entry["replacement"]
            if (disposition == "replaced") != (replacement is not None):
                raise LegacyConsumerInventoryError(
                    "replacement presence does not match its disposition"
                )
            if replacement is not None and replacement not in sanctioned_identities:
                raise LegacyConsumerInventoryError(
                    "retired replacement is not an exact sanctioned entrypoint"
                )

    try:
        receipt_path = (
            inventory_path.resolve(strict=True)
            .relative_to(repository_root.resolve(strict=True))
            .as_posix()
        )
    except ValueError:
        receipt_path = inventory_path.resolve(strict=True).as_posix()
    s11c_entries.sort(
        key=lambda item: (item["inventory_category"], item["inventory_path"])
    )
    receipt = {
        "path": receipt_path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "category_counts": {
            category: len(payload[category]) for category in _CATEGORIES
        },
        "disposition_counts": disposition_counts,
        "s11c_disposition_entries": s11c_entries,
        "s11c_disposition_count": len(s11c_entries),
    }
    return LegacyConsumerInventory(
        _payload=deepcopy(payload),
        _receipt=receipt,
    )


__all__ = [
    "LegacyConsumerInventory",
    "LegacyConsumerInventoryError",
    "load_legacy_consumer_inventory",
]
