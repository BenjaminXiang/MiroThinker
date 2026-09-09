"""Fail-closed admission for Canonical V2 rebuild writes.

The accepted S2B documents are executable evidence, not a mutable configuration. Every rebuild
writer must bind to their exact accepted bytes and relationships before opening a write target.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol


class _AlembicConfig(Protocol):
    def get_main_option(self, name: str, default: str | None = None) -> str | None: ...


class RebuildWriteGateError(RuntimeError):
    """Raised before a Canonical V2 writer can use unaccepted evidence."""


@dataclass(frozen=True, slots=True)
class BackupGateReceipt:
    """Identity of the exact accepted source-backup/restore checkpoint."""

    state: str
    source_count: int
    source_inventory_sha256: str
    backup_manifest_sha256: str
    restore_verification_sha256: str
    acceptance_record_sha256: str


_SOURCE_INVENTORY_SHA256 = (
    "83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09"
)
_BACKUP_MANIFEST_SHA256 = (
    "a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8"
)
_RESTORE_VERIFICATION_SHA256 = (
    "98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231"
)
_ACCEPTANCE_RECORD_SHA256 = (
    "3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b"
)
_REQUIRED_EXTRA_SOURCE_IDS = frozenset(
    {"original_postgresql_volume", "forensic_recovery_tree"}
)
_REQUIRED_PROBE_IDS = frozenset({"forensic", "milvus", "postgresql"})


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_exact_document(
    path: Path,
    *,
    label: str,
    expected_sha256: str,
) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RebuildWriteGateError(
            f"Required accepted {label} is missing or unreadable: {path}"
        ) from exc
    actual_sha256 = _sha256_bytes(payload)
    if actual_sha256 != expected_sha256:
        raise RebuildWriteGateError(
            f"Accepted {label} hash changed: expected {expected_sha256}, "
            f"got {actual_sha256}"
        )
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RebuildWriteGateError(
            f"Accepted {label} is not valid JSON: {path}"
        ) from exc
    if not isinstance(document, dict):
        raise RebuildWriteGateError(f"Accepted {label} must be a JSON object")
    return document


def _source_record_id(source: dict[str, Any]) -> str:
    compact = json.dumps(
        source,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"inventory:{_sha256_bytes(compact)}"


def _expected_source_ids(inventory: dict[str, Any]) -> set[str]:
    sources = inventory.get("sources")
    if not isinstance(sources, list) or not all(
        isinstance(source, dict) for source in sources
    ):
        raise RebuildWriteGateError("Accepted source inventory has invalid sources")
    return {_source_record_id(source) for source in sources} | set(
        _REQUIRED_EXTRA_SOURCE_IDS
    )


def _indexed_sources(
    document: dict[str, Any],
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    sources = document.get("sources")
    if not isinstance(sources, list):
        raise RebuildWriteGateError(f"Accepted {label} has invalid sources")
    indexed: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise RebuildWriteGateError(f"Accepted {label} has a non-object source")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise RebuildWriteGateError(
                f"Accepted {label} contains a source without source_id"
            )
        if source_id in indexed:
            raise RebuildWriteGateError(
                f"Accepted {label} contains duplicate source_id {source_id}"
            )
        indexed[source_id] = source
    return indexed


def _require_exact_coverage(
    actual: set[str],
    expected: set[str],
    *,
    label: str,
) -> None:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise RebuildWriteGateError(
            f"Accepted {label} source coverage mismatch: "
            f"missing={missing}, extra={extra}"
        )


def _require_distinct_roots(backup_manifest: dict[str, Any]) -> None:
    backup_value = backup_manifest.get("backup_root")
    restore_value = backup_manifest.get("restore_root")
    if not isinstance(backup_value, str) or not isinstance(restore_value, str):
        raise RebuildWriteGateError("Accepted backup/restore roots are missing")
    backup_root = Path(backup_value).resolve(strict=False)
    restore_root = Path(restore_value).resolve(strict=False)
    try:
        restore_root.relative_to(backup_root)
        overlaps = True
    except ValueError:
        try:
            backup_root.relative_to(restore_root)
            overlaps = True
        except ValueError:
            overlaps = False
    if overlaps:
        raise RebuildWriteGateError(
            "Accepted backup and restore roots must be distinct and non-overlapping"
        )


def require_accepted_backup_gate(evidence_root: Path) -> BackupGateReceipt:
    """Verify the exact Accepted S2B checkpoint before a rebuild writer connects."""
    if not evidence_root.is_absolute():
        raise RebuildWriteGateError(
            "Canonical V2 backup gate root must be an explicit absolute path"
        )
    root = evidence_root.resolve(strict=False)
    inventory = _load_exact_document(
        root / "s2" / "source-inventory.json",
        label="source inventory",
        expected_sha256=_SOURCE_INVENTORY_SHA256,
    )
    backup = _load_exact_document(
        root / "s2b" / "backup-manifest.json",
        label="backup manifest",
        expected_sha256=_BACKUP_MANIFEST_SHA256,
    )
    restore = _load_exact_document(
        root / "s2b" / "restore-verification.json",
        label="restore verification",
        expected_sha256=_RESTORE_VERIFICATION_SHA256,
    )
    acceptance = _load_exact_document(
        root / "s2b" / "acceptance-record.json",
        label="acceptance record",
        expected_sha256=_ACCEPTANCE_RECORD_SHA256,
    )

    if backup.get("source_inventory_sha256") != _SOURCE_INVENTORY_SHA256:
        raise RebuildWriteGateError(
            "Accepted backup manifest does not reference the exact source inventory"
        )
    _require_distinct_roots(backup)

    expected_sources = _expected_source_ids(inventory)
    backup_sources = _indexed_sources(backup, label="backup manifest")
    _require_exact_coverage(
        set(backup_sources),
        expected_sources,
        label="backup manifest",
    )
    for source_id, source in backup_sources.items():
        if source.get("copy_independent") is not True:
            raise RebuildWriteGateError(
                f"Accepted backup copy independence failed for {source_id}"
            )
        if source.get("hash_verified") is not True:
            raise RebuildWriteGateError(
                f"Accepted backup hash verification failed for {source_id}"
            )

    restore_sources = _indexed_sources(restore, label="restore verification")
    _require_exact_coverage(
        set(restore_sources),
        expected_sources,
        label="restore verification",
    )
    for source_id, source in restore_sources.items():
        if source.get("status") != "passed":
            raise RebuildWriteGateError(
                f"Accepted restore verification failed for {source_id}"
            )
    if restore.get("backup_manifest_sha256") != _BACKUP_MANIFEST_SHA256:
        raise RebuildWriteGateError(
            "Accepted restore verification does not reference the exact backup manifest"
        )
    probes = restore.get("required_probes")
    if not isinstance(probes, dict):
        raise RebuildWriteGateError("Accepted restore required probes are missing")
    missing_probes = sorted(_REQUIRED_PROBE_IDS - set(probes))
    failed_probes = sorted(
        probe_id
        for probe_id in _REQUIRED_PROBE_IDS & set(probes)
        if not isinstance(probes[probe_id], dict)
        or probes[probe_id].get("status") != "passed"
    )
    if missing_probes or failed_probes:
        raise RebuildWriteGateError(
            "Accepted restore required probes are incomplete: "
            f"missing={missing_probes}, failed={failed_probes}"
        )

    if acceptance.get("state") != "accepted":
        raise RebuildWriteGateError("Backup/restore gate is not accepted")
    if acceptance.get("backup_manifest_sha256") != _BACKUP_MANIFEST_SHA256:
        raise RebuildWriteGateError(
            "Acceptance record does not match the exact backup manifest"
        )
    if acceptance.get("restore_verification_sha256") != _RESTORE_VERIFICATION_SHA256:
        raise RebuildWriteGateError(
            "Acceptance record does not match the exact restore verification"
        )
    if len(expected_sources) != 50:
        raise RebuildWriteGateError(
            f"Accepted backup source count changed: {len(expected_sources)}"
        )

    return BackupGateReceipt(
        state="accepted",
        source_count=len(expected_sources),
        source_inventory_sha256=_SOURCE_INVENTORY_SHA256,
        backup_manifest_sha256=_BACKUP_MANIFEST_SHA256,
        restore_verification_sha256=_RESTORE_VERIFICATION_SHA256,
        acceptance_record_sha256=_ACCEPTANCE_RECORD_SHA256,
    )


def resolve_backup_gate_root(
    config: _AlembicConfig,
    environment: Mapping[str, str],
) -> Path:
    """Resolve one explicit evidence root without generic environment fallback."""
    configured = config.get_main_option("miroflow.backup_gate_root")
    configured = configured.strip() if configured and configured.strip() else None
    environment_value = environment.get("CANONICAL_V2_BACKUP_GATE_ROOT")
    environment_value = (
        environment_value.strip()
        if environment_value and environment_value.strip()
        else None
    )
    if configured and environment_value:
        if Path(configured).resolve(strict=False) != Path(environment_value).resolve(
            strict=False
        ):
            raise RebuildWriteGateError(
                "Ambiguous Canonical V2 backup gate root: config and dedicated "
                "environment values conflict"
            )
    selected = configured or environment_value
    if not selected:
        raise RebuildWriteGateError(
            "An explicit Canonical V2 backup gate root is required"
        )
    root = Path(selected)
    if not root.is_absolute():
        raise RebuildWriteGateError(
            "Canonical V2 backup gate root must be an explicit absolute path"
        )
    return root.resolve(strict=False)
