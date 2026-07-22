"""Ingest exactly one accepted S2B restore member into EvidenceLanding."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Literal

from pydantic import model_validator

from src.data_agents.canonical_v2.contracts import (
    CanonicalDatetime,
    ContractModel,
    NonEmptyStr,
    Sha256,
)
from src.data_agents.canonical_v2.evidence_landing import (
    IngestEvidenceRequest,
    LandingReceipt,
    ParserReference,
)
from src.data_agents.canonical_v2.evidence_landing_postgres import (
    create_postgres_evidence_landing,
)
from src.data_agents.canonical_v2.rebuild_write_gate import (
    require_accepted_backup_gate,
)


class EvidenceIngestContractError(RuntimeError):
    """Explicit target or accepted restore-member evidence failed closed."""


class _IngestMetadata(ContractModel):
    run_id: NonEmptyStr
    source_batch_id: NonEmptyStr
    source_kind: NonEmptyStr
    source_locator: NonEmptyStr
    observed_at: CanonicalDatetime
    expected_content_sha256: Sha256
    parser: ParserReference = ParserReference(
        parser_name="historical_jsonl",
        parser_version="v1",
        schema_version="historical-record-v1",
    )
    parent_artifact_id: NonEmptyStr | None = None
    parent_content_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def validate_parent_pair(self) -> _IngestMetadata:
        if (self.parent_artifact_id is None) != (self.parent_content_sha256 is None):
            raise ValueError("parent evidence identity must be complete")
        return self


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_document(path: Path, *, label: str) -> tuple[dict[str, object], str]:
    if path.is_symlink() or not path.is_file():
        raise EvidenceIngestContractError(f"accepted {label} is unavailable")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceIngestContractError(f"accepted {label} is invalid") from exc
    if not isinstance(value, dict):
        raise EvidenceIngestContractError(f"accepted {label} must be an object")
    return value, _sha256(raw)


def _safe_relative(value: str, *, label: str) -> PurePosixPath:
    if (
        not value
        or "\0" in value
        or "\\" in value
        or "//" in value
        or any(marker in value for marker in "*?[]{}")
    ):
        raise EvidenceIngestContractError(f"{label} is not canonical")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise EvidenceIngestContractError(f"{label} is not repository-relative")
    return path


def _resolved_regular(root: Path, relative: PurePosixPath, *, label: str) -> Path:
    exact_root = root.resolve(strict=True)
    current = exact_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise EvidenceIngestContractError(f"{label} traverses a symlink")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(exact_root)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise EvidenceIngestContractError(f"{label} escapes its accepted root") from exc
    mode = resolved.lstat().st_mode
    if not stat.S_ISREG(mode):
        raise EvidenceIngestContractError(f"{label} is not a regular file")
    return resolved


def _one_source(
    document: dict[str, object], *, source_id: str, label: str
) -> dict[str, object]:
    sources = document.get("sources")
    if not isinstance(sources, list):
        raise EvidenceIngestContractError(f"accepted {label} sources are invalid")
    matches = [
        item
        for item in sources
        if isinstance(item, dict) and item.get("source_id") == source_id
    ]
    if len(matches) != 1:
        raise EvidenceIngestContractError(
            f"accepted {label} must contain exactly one requested source"
        )
    return matches[0]


def _member_rows(path: Path, *, expected_sha256: object) -> list[dict[str, object]]:
    raw = path.read_bytes()
    if not isinstance(expected_sha256, str) or _sha256(raw) != expected_sha256:
        raise EvidenceIngestContractError("accepted member manifest hash drifted")
    rows: list[dict[str, object]] = []
    try:
        for line in raw.decode("utf-8").splitlines():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("member row is not an object")
            rows.append(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise EvidenceIngestContractError(
            "accepted member manifest is invalid"
        ) from exc
    return rows


def _identity(path: Path, *, label: str) -> tuple[int, int]:
    if path.is_symlink() or not path.is_file():
        raise EvidenceIngestContractError(f"accepted {label} is not a regular file")
    value = path.stat()
    return value.st_dev, value.st_ino


def _read_member_once(path: Path) -> bytes:
    return path.read_bytes()


def _load_metadata(path: Path) -> _IngestMetadata:
    if path.is_symlink() or not path.is_file():
        raise EvidenceIngestContractError("request JSON must be one explicit file")
    try:
        raw = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceIngestContractError("request JSON is invalid") from exc
    if not isinstance(raw, dict) or "content" in raw:
        raise EvidenceIngestContractError("request JSON must contain metadata only")
    try:
        return _IngestMetadata.model_validate(raw)
    except ValueError as exc:
        raise EvidenceIngestContractError("request metadata is invalid") from exc


def run_ingest(
    *,
    database_url: str,
    expected_database: str,
    target_kind: Literal["disposable", "isolated-candidate"],
    backup_gate_root: Path,
    request_json: Path,
    source_id: str,
    member_namespace: str,
    member_relative_path: str,
) -> LandingReceipt:
    """Validate metadata, compose once, admit one member, and ingest once."""

    if (
        not database_url.strip()
        or not expected_database.strip()
        or not source_id.strip()
    ):
        raise EvidenceIngestContractError(
            "explicit target and source values are required"
        )
    if target_kind not in {"disposable", "isolated-candidate"}:
        raise EvidenceIngestContractError("target kind is not an isolated candidate")
    if not backup_gate_root.is_absolute():
        raise EvidenceIngestContractError(
            "backup gate root must be explicit and absolute"
        )
    namespace = _safe_relative(member_namespace, label="member namespace")
    if len(namespace.parts) != 1:
        raise EvidenceIngestContractError("member namespace must be one exact segment")
    relative = _safe_relative(member_relative_path, label="member relative path")
    metadata = _load_metadata(request_json)

    landing = create_postgres_evidence_landing(
        database_url=database_url,
        expected_database=expected_database,
        target_kind=target_kind,
        backup_gate_root=backup_gate_root,
    )
    gate = require_accepted_backup_gate(backup_gate_root)

    backup_path = backup_gate_root / "s2b/backup-manifest.json"
    restore_path = backup_gate_root / "s2b/restore-verification.json"
    acceptance_path = backup_gate_root / "s2b/acceptance-record.json"
    backup, backup_sha = _read_document(backup_path, label="backup manifest")
    restore, restore_sha = _read_document(restore_path, label="restore verification")
    acceptance, acceptance_sha = _read_document(
        acceptance_path, label="acceptance record"
    )
    if (
        gate.backup_manifest_sha256 != backup_sha
        or gate.restore_verification_sha256 != restore_sha
        or gate.acceptance_record_sha256 != acceptance_sha
        or restore.get("backup_manifest_sha256") != backup_sha
        or acceptance.get("backup_manifest_sha256") != backup_sha
        or acceptance.get("restore_verification_sha256") != restore_sha
        or acceptance.get("state") != "accepted"
        or backup.get("run_id") != restore.get("run_id")
    ):
        raise EvidenceIngestContractError("accepted S2B document graph drifted")

    backup_source = _one_source(backup, source_id=source_id, label="backup")
    restore_source = _one_source(restore, source_id=source_id, label="restore")
    if (
        backup_source.get("copy_independent") is not True
        or backup_source.get("hash_verified") is not True
        or restore_source.get("status") != "passed"
        or restore_source.get("hash_verified") is not True
        or restore_source.get("copy_independent") is not True
    ):
        raise EvidenceIngestContractError("requested restore source is not accepted")

    backup_root_value = backup.get("backup_root")
    restore_root_value = backup.get("restore_root")
    if (
        not isinstance(backup_root_value, str)
        or not isinstance(restore_root_value, str)
        or restore.get("backup_root") != backup_root_value
        or restore.get("restore_root") != restore_root_value
    ):
        raise EvidenceIngestContractError("accepted backup/restore roots drifted")
    backup_root = Path(backup_root_value)
    restore_root = Path(restore_root_value)
    manifest_value = backup_source.get("backup_member_manifest_path")
    if not isinstance(manifest_value, str):
        raise EvidenceIngestContractError("accepted member manifest path is absent")
    manifest_path = _resolved_regular(
        backup_root,
        _safe_relative(manifest_value, label="member manifest path"),
        label="member manifest",
    )
    rows = _member_rows(
        manifest_path,
        expected_sha256=backup_source.get("backup_member_manifest_sha256"),
    )
    matches = [
        row
        for row in rows
        if row.get("namespace") == member_namespace
        and row.get("relative_path") == member_relative_path
    ]
    if len(matches) != 1:
        raise EvidenceIngestContractError(
            "accepted manifest must contain exactly one requested member"
        )
    member = matches[0]
    accepted_run_id = backup.get("run_id")
    expected_locator = (
        f"s2b-restore://{accepted_run_id}/{member_namespace}/{member_relative_path}"
    )
    if metadata.source_locator != expected_locator:
        raise EvidenceIngestContractError(
            "request locator is not the accepted restore member"
        )
    if (
        member.get("copy_independent") is not True
        or member.get("source_bytes") != member.get("backup_bytes")
        or member.get("source_sha256") != member.get("backup_sha256")
        or member.get("backup_sha256") != metadata.expected_content_sha256
    ):
        raise EvidenceIngestContractError("accepted member identity drifted")

    restored = _resolved_regular(
        restore_root,
        PurePosixPath(member_namespace) / relative,
        label="restore member",
    )
    before = restored.lstat()
    if before.st_size != member.get("backup_bytes"):
        raise EvidenceIngestContractError("restore member size drifted")
    original_value = member.get("source_path")
    object_value = member.get("object_path")
    if not isinstance(original_value, str) or not isinstance(object_value, str):
        raise EvidenceIngestContractError("accepted member protected paths are absent")
    protected = {
        _identity(Path(original_value), label="original source"),
        _identity(
            _resolved_regular(
                backup_root,
                _safe_relative(object_value, label="backup object path"),
                label="backup object",
            ),
            label="backup object",
        ),
        _identity(manifest_path, label="member manifest"),
    }
    if (before.st_dev, before.st_ino) in protected:
        raise EvidenceIngestContractError("restore member is not an independent copy")
    content = _read_member_once(restored)
    after = restored.lstat()
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or _sha256(content) != member.get("backup_sha256")
        or _sha256(content) != metadata.expected_content_sha256
    ):
        raise EvidenceIngestContractError(
            "restore member changed or failed hash binding"
        )

    request = IngestEvidenceRequest(
        **metadata.model_dump(mode="python"),
        content=content,
    )
    receipt = landing.ingest(request)
    if type(receipt) is not LandingReceipt:
        raise EvidenceIngestContractError("landing returned an invalid receipt type")
    exact_receipt = LandingReceipt.model_validate(receipt.model_dump(mode="json"))
    if exact_receipt != receipt:
        raise EvidenceIngestContractError("landing receipt failed exact validation")
    return exact_receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest one exact accepted S2B restore member."
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument(
        "--target-kind",
        choices=("disposable", "isolated-candidate"),
        required=True,
    )
    parser.add_argument("--backup-gate-root", required=True, type=Path)
    parser.add_argument("--request-json", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--member-namespace", required=True)
    parser.add_argument("--member-relative-path", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = run_ingest(
            database_url=args.database_url,
            expected_database=args.expected_database,
            target_kind=args.target_kind,
            backup_gate_root=args.backup_gate_root,
            request_json=args.request_json,
            source_id=args.source_id,
            member_namespace=args.member_namespace,
            member_relative_path=args.member_relative_path,
        )
    except Exception:
        raise SystemExit("Canonical V2 evidence ingestion rejected") from None
    print(receipt.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
