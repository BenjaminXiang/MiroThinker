"""Task 4.4 bounded landing-matrix replay tool."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any
import warnings


class MatrixReplayError(RuntimeError):
    """The frozen matrix cannot be replayed without weakening its evidence contract."""


class _StrictJsonError(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _StrictJsonError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise _StrictJsonError(f"non-standard JSON number {value!r}")


def _strict_json_loads(value: str | bytes) -> Any:
    return json.loads(
        value,
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )


@dataclass(frozen=True, slots=True)
class VerifiedMember:
    source_id: str
    member_relative_path: str
    backup_path: Path
    restore_path: Path
    content_sha256: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class PreparedEntry:
    entry_id: str
    source_batch_id: str
    source_kind: str
    source_locator: str
    parser_name: str
    parser_version: str
    schema_version: str
    parser_options: dict[str, Any]
    content: bytes
    source: VerifiedMember
    derived: bool


@dataclass(frozen=True, slots=True)
class MatrixSpec:
    matrix_id: str
    observed_at: datetime
    entries: tuple[dict[str, Any], ...]
    expected_by_entry: dict[str, dict[str, Any]]


@dataclass(frozen=True, slots=True)
class PreparedMatrix:
    spec: MatrixSpec
    entries: tuple[PreparedEntry, ...]
    gate: Any


_FAMILY_CONTRACT = {
    "wal_fpi_partial": ("wal_fpi", True),
    "sqlite": ("direct", False),
    "jsonl": ("direct", False),
    "xlsx": ("direct", False),
    "milvus_copy": ("milvus", True),
    "recorded_response": ("recorded_response", True),
}


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = _strict_json_loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, _StrictJsonError) as exc:
        raise MatrixReplayError(
            f"{label} is missing or invalid JSON: {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise MatrixReplayError(f"{label} must be a JSON object")
    return value


def _non_empty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MatrixReplayError(f"{label} must be a non-empty string")
    return value


def load_matrix(path: Path) -> MatrixSpec:
    document = _load_json_object(path, label="landing matrix")
    if document.get("schema_version") != "canonical-v2-landing-matrix-v1":
        raise MatrixReplayError("landing matrix schema version is not supported")
    matrix_id = _non_empty_string(document.get("matrix_id"), label="matrix_id")
    observed_value = _non_empty_string(document.get("observed_at"), label="observed_at")
    normalized_time = (
        f"{observed_value[:-1]}+00:00"
        if observed_value.endswith("Z")
        else observed_value
    )
    try:
        observed_at = datetime.fromisoformat(normalized_time)
    except ValueError as exc:
        raise MatrixReplayError("landing matrix observed_at is invalid") from exc
    if observed_at.utcoffset() is None:
        raise MatrixReplayError("landing matrix observed_at requires a timezone")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list) or not all(
        isinstance(entry, dict) for entry in raw_entries
    ):
        raise MatrixReplayError("landing matrix entries must be objects")
    entries = tuple(raw_entries)
    families = [entry.get("family") for entry in entries]
    if len(entries) != len(_FAMILY_CONTRACT) or set(families) != set(_FAMILY_CONTRACT):
        raise MatrixReplayError(
            "landing matrix families must exactly cover "
            + ", ".join(sorted(_FAMILY_CONTRACT))
        )
    entry_ids: list[str] = []
    batch_ids: list[str] = []
    expected_by_entry: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_id = _non_empty_string(entry.get("entry_id"), label="entry_id")
        batch_id = _non_empty_string(
            entry.get("source_batch_id"), label=f"{entry_id}.source_batch_id"
        )
        entry_ids.append(entry_id)
        batch_ids.append(batch_id)
        for field in (
            "accepted_source_kind",
            "member_relative_path",
            "restore_relative_path",
            "source_id",
            "source_kind",
            "source_locator",
        ):
            _non_empty_string(entry.get(field), label=f"{entry_id}.{field}")
        expected_sha256 = entry.get("expected_source_sha256")
        if (
            not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise MatrixReplayError(f"{entry_id}.expected_source_sha256 is invalid")
        expected_bytes = entry.get("expected_source_bytes")
        if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int):
            raise MatrixReplayError(f"{entry_id}.expected_source_bytes is invalid")
        if expected_bytes < 0:
            raise MatrixReplayError(f"{entry_id}.expected_source_bytes is invalid")
        family = str(entry["family"])
        materializer = entry.get("materializer")
        parser = entry.get("parser")
        expected = entry.get("expected")
        if not isinstance(materializer, dict) or not isinstance(parser, dict):
            raise MatrixReplayError(f"{entry_id} parser/materializer must be objects")
        expected_kind, expected_derived = _FAMILY_CONTRACT[family]
        if materializer.get("kind") != expected_kind:
            raise MatrixReplayError(f"{entry_id} materializer violates family contract")
        if entry.get("derived") is not expected_derived:
            raise MatrixReplayError(f"{entry_id} derived flag violates family contract")
        for field in ("name", "version", "schema_version"):
            _non_empty_string(parser.get(field), label=f"{entry_id}.parser.{field}")
        if not isinstance(parser.get("options"), dict):
            raise MatrixReplayError(f"{entry_id}.parser.options must be an object")
        if not isinstance(expected, dict):
            raise MatrixReplayError(f"{entry_id}.expected must be an object")
        expected_by_entry[entry_id] = expected
    if len(entry_ids) != len(set(entry_ids)) or len(batch_ids) != len(set(batch_ids)):
        raise MatrixReplayError("landing matrix entry and batch IDs must be unique")
    return MatrixSpec(
        matrix_id=matrix_id,
        observed_at=observed_at,
        entries=entries,
        expected_by_entry=expected_by_entry,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_beneath(root: Path, relative_path: str, *, label: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise MatrixReplayError(f"{label} must be a non-empty relative path")
    resolved_root = root.resolve(strict=True)
    try:
        resolved = (resolved_root / relative_path).resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise MatrixReplayError(
            f"{label} escapes or is absent from its accepted root"
        ) from exc
    if not resolved.is_file():
        raise MatrixReplayError(f"{label} is not a regular file")
    return resolved


def _jsonl_objects(path: Path) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                value = _strict_json_loads(line)
                if not isinstance(value, dict):
                    raise MatrixReplayError(
                        f"manifest line {line_number} is not an object"
                    )
                records.append(value)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        _StrictJsonError,
    ) as exc:
        raise MatrixReplayError(
            f"manifest is missing or invalid: {path}: {exc}"
        ) from exc
    return tuple(records)


def _indexed_sources(
    document: dict[str, Any], *, label: str
) -> dict[str, dict[str, Any]]:
    sources = document.get("sources")
    if not isinstance(sources, list):
        raise MatrixReplayError(f"{label} has no source list")
    indexed: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise MatrixReplayError(f"{label} contains a non-object source")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise MatrixReplayError(f"{label} contains a source without identity")
        if source_id in indexed:
            raise MatrixReplayError(f"{label} contains duplicate source {source_id}")
        indexed[source_id] = source
    return indexed


def verify_member(
    *,
    source_id: str,
    member_relative_path: str,
    restore_relative_path: str,
    backup_root: Path,
    restore_root: Path,
    member_manifest_path: Path,
    restore_source: dict[str, Any],
    expected_sha256: str,
    expected_byte_size: int,
) -> VerifiedMember:
    resolved_backup_root = backup_root.resolve(strict=True)
    try:
        resolved_manifest = member_manifest_path.resolve(strict=True)
        resolved_manifest.relative_to(resolved_backup_root)
    except (OSError, ValueError) as exc:
        raise MatrixReplayError(
            "member manifest escapes or is absent from the accepted backup root"
        ) from exc
    matches = tuple(
        record
        for record in _jsonl_objects(resolved_manifest)
        if record.get("relative_path") == member_relative_path
    )
    if len(matches) != 1:
        raise MatrixReplayError(
            "member manifest must contain exactly one selected relative path"
        )
    member = matches[0]
    if (
        restore_source.get("source_id") != source_id
        or restore_source.get("status") != "passed"
        or restore_source.get("hash_verified") is not True
        or restore_source.get("copy_independent") is not True
    ):
        raise MatrixReplayError("selected source lacks an accepted restore result")
    probes = restore_source.get("probes")
    if not isinstance(probes, list) or not any(
        isinstance(probe, dict)
        and probe.get("restore_path") == restore_relative_path
        and probe.get("status") == "passed"
        for probe in probes
    ):
        raise MatrixReplayError("selected restore probe is absent or did not pass")
    expected_fields = {
        "backup_bytes": expected_byte_size,
        "backup_sha256": expected_sha256,
        "copy_independent": True,
        "source_bytes": expected_byte_size,
        "source_sha256": expected_sha256,
    }
    mismatched_fields = sorted(
        key for key, expected in expected_fields.items() if member.get(key) != expected
    )
    if mismatched_fields:
        raise MatrixReplayError(
            f"selected member manifest identity mismatch: {mismatched_fields}"
        )
    object_path = member.get("object_path")
    if not isinstance(object_path, str):
        raise MatrixReplayError("selected member has no backup object path")
    backup_path = _resolve_beneath(
        resolved_backup_root, object_path, label="backup object path"
    )
    restore_path = _resolve_beneath(
        restore_root, restore_relative_path, label="restore probe path"
    )
    for label, path in (("backup", backup_path), ("restore", restore_path)):
        actual_size = path.stat().st_size
        if actual_size != expected_byte_size:
            raise MatrixReplayError(
                f"{label} size mismatch: expected {expected_byte_size}, got {actual_size}"
            )
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise MatrixReplayError(
                f"{label} hash mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
    backup_stat = backup_path.stat()
    restore_stat = restore_path.stat()
    if (backup_stat.st_dev, backup_stat.st_ino) == (
        restore_stat.st_dev,
        restore_stat.st_ino,
    ):
        raise MatrixReplayError("backup and restore member must be independent files")
    return VerifiedMember(
        source_id=source_id,
        member_relative_path=member_relative_path,
        backup_path=backup_path,
        restore_path=restore_path,
        content_sha256=expected_sha256,
        byte_size=expected_byte_size,
    )


def parse_pg_copy_rows(
    lines: Iterable[str],
    *,
    expected_table: str,
    selected_field: str | None = None,
    selected_values: frozenset[str] | None = None,
) -> tuple[dict[str, str | None], ...]:
    if (selected_field is None) != (selected_values is None):
        raise MatrixReplayError(
            "PostgreSQL COPY selected field and values must be provided together"
        )
    if selected_values is not None and not selected_values:
        raise MatrixReplayError("PostgreSQL COPY selected values cannot be empty")
    copy_pattern = re.compile(r"^COPY ([^ ]+) \((.*)\) FROM stdin;$")
    columns: tuple[str, ...] | None = None
    selected_index: int | None = None
    records: list[dict[str, str | None]] = []
    terminated = False
    for raw_line in lines:
        line = raw_line.removesuffix("\n").removesuffix("\r")
        if columns is None:
            match = copy_pattern.match(line)
            if match is None:
                continue
            if match.group(1) != expected_table:
                continue
            columns = tuple(column.strip() for column in match.group(2).split(","))
            if not columns or any(not column for column in columns):
                raise MatrixReplayError("PostgreSQL COPY header has invalid columns")
            if selected_field is not None:
                try:
                    selected_index = columns.index(selected_field)
                except ValueError as exc:
                    raise MatrixReplayError(
                        f"PostgreSQL COPY selected field {selected_field} is absent"
                    ) from exc
            continue
        if line == r"\.":
            terminated = True
            break
        raw_values = line.split("\t")
        if len(raw_values) != len(columns):
            raise MatrixReplayError(
                "PostgreSQL COPY row does not match the declared column count"
            )
        if selected_index is not None:
            assert selected_values is not None
            selected_value = _decode_pg_copy_value(raw_values[selected_index])
            if selected_value not in selected_values:
                continue
        records.append(
            {
                column: _decode_pg_copy_value(raw_value)
                for column, raw_value in zip(columns, raw_values, strict=True)
            }
        )
    if columns is None:
        raise MatrixReplayError(f"PostgreSQL COPY table {expected_table} is absent")
    if not terminated:
        raise MatrixReplayError(f"PostgreSQL COPY table {expected_table} is truncated")
    return tuple(records)


def _decode_pg_copy_value(value: str) -> str | None:
    if value == r"\N":
        return None
    decoded: list[str] = []
    index = 0
    escapes = {
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "\\": "\\",
    }
    while index < len(value):
        if value[index] != "\\":
            decoded.append(value[index])
            index += 1
            continue
        index += 1
        if index >= len(value):
            raise MatrixReplayError("PostgreSQL COPY value ends with an escape")
        escaped = value[index]
        if escaped in escapes:
            decoded.append(escapes[escaped])
            index += 1
            continue
        if escaped in "01234567":
            end = index + 1
            while end < min(index + 3, len(value)) and value[end] in "01234567":
                end += 1
            decoded.append(chr(int(value[index:end], 8)))
            index = end
            continue
        if escaped == "x":
            end = index + 1
            while end < min(index + 3, len(value)) and value[end] in (
                "0123456789abcdefABCDEF"
            ):
                end += 1
            if end == index + 1:
                raise MatrixReplayError("PostgreSQL COPY hex escape has no digits")
            decoded.append(chr(int(value[index + 1 : end], 16)))
            index = end
            continue
        decoded.append(escaped)
        index += 1
    return "".join(decoded)


def materialize_wal_fpi(
    paper_rows: Iterable[dict[str, str | None]],
    error_rows: Iterable[dict[str, str | None]],
    *,
    record_keys: tuple[str, ...],
) -> bytes:
    if not record_keys or len(record_keys) != len(set(record_keys)):
        raise MatrixReplayError("WAL/FPI selector requires unique record keys")
    papers: dict[str, dict[str, str | None]] = {}
    for row in paper_rows:
        paper_id = row.get("paper_id")
        if not isinstance(paper_id, str) or not paper_id:
            raise MatrixReplayError("WAL/FPI paper row has no paper_id")
        if paper_id in papers:
            raise MatrixReplayError(f"duplicate WAL/FPI paper key {paper_id}")
        papers[paper_id] = row
    errors_by_key: dict[str, list[dict[str, str | None]]] = {}
    for row in error_rows:
        record_key = row.get("record_key")
        if row.get("table_name") != "paper" or not isinstance(record_key, str):
            continue
        errors_by_key.setdefault(record_key, []).append(row)
    missing = sorted(set(record_keys) - set(papers))
    if missing:
        raise MatrixReplayError(f"missing WAL/FPI paper records: {missing}")
    envelopes: list[dict[str, Any]] = []
    for record_key in record_keys:
        readable_fields = {
            key: _paper_field_value(key, value)
            for key, value in papers[record_key].items()
            if value is not None
        }
        field_errors = []
        for error in sorted(
            errors_by_key.get(record_key, ()),
            key=lambda item: str(item.get("column_name")),
        ):
            column_name = error.get("column_name")
            sqlstate = error.get("sqlstate")
            message = error.get("error_message")
            if not all(
                isinstance(item, str) and item
                for item in (column_name, sqlstate, message)
            ):
                raise MatrixReplayError(
                    f"WAL/FPI field error is incomplete for {record_key}"
                )
            field_errors.append(
                {
                    "error_code": f"salvage_{sqlstate}",
                    "error_kind": "missing_external_content",
                    "field_path": column_name,
                    "message": message,
                    "recoverable": False,
                }
            )
        envelopes.append(
            {
                "record_locator": f"salvage.paper:{record_key}",
                "readable_fields": readable_fields,
                "field_errors": field_errors,
            }
        )
    return _json_lines(envelopes)


def _paper_field_value(field: str, value: str) -> Any:
    if field in {"year", "citation_count", "recovery_source_xmin"}:
        try:
            return int(value)
        except ValueError as exc:
            raise MatrixReplayError(
                f"WAL/FPI integer field {field} has invalid value"
            ) from exc
    if field == "authors_raw":
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise MatrixReplayError("WAL/FPI authors_raw is invalid JSON") from exc
    return value


def _json_lines(values: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
        for value in values
    )


def materialize_milvus(
    rows: Iterable[dict[str, Any]],
    *,
    collection: str,
    primary_key_field: str,
    primary_keys: tuple[str, ...],
    copy_sha256: str,
) -> bytes:
    if not collection or not primary_key_field:
        raise MatrixReplayError("Milvus collection and primary-key field are required")
    if not primary_keys or len(primary_keys) != len(set(primary_keys)):
        raise MatrixReplayError("Milvus selector requires unique primary keys")
    if re.fullmatch(r"[0-9a-f]{64}", copy_sha256) is None:
        raise MatrixReplayError("Milvus source copy hash is invalid")
    by_primary_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        primary_key = row.get(primary_key_field)
        if not isinstance(primary_key, str) or not primary_key:
            raise MatrixReplayError("Milvus row has no string primary key")
        if primary_key in by_primary_key:
            raise MatrixReplayError(f"duplicate Milvus primary key {primary_key}")
        by_primary_key[primary_key] = row
    if set(by_primary_key) != set(primary_keys):
        raise MatrixReplayError(
            "Milvus rows do not match the frozen primary keys: "
            f"expected={sorted(primary_keys)}, actual={sorted(by_primary_key)}"
        )
    return _json_lines(
        {
            "collection": collection,
            "primary_key": primary_key,
            "payload": by_primary_key[primary_key],
            "projection": {"source_copy_sha256": copy_sha256},
        }
        for primary_key in primary_keys
    )


def materialize_recorded_response(
    cache_content: bytes,
    *,
    source_sha256: str,
    relative_path: str,
) -> bytes:
    if hashlib.sha256(cache_content).hexdigest() != source_sha256:
        raise MatrixReplayError("recorded response cache hash mismatch")
    relative = Path(relative_path)
    if not relative_path or relative.is_absolute() or ".." in relative.parts:
        raise MatrixReplayError("recorded response cache path is invalid")
    try:
        cache = _strict_json_loads(cache_content)
    except (UnicodeDecodeError, json.JSONDecodeError, _StrictJsonError) as exc:
        raise MatrixReplayError(
            f"recorded response cache is invalid JSON: {exc}"
        ) from exc
    if not isinstance(cache, dict):
        raise MatrixReplayError("recorded response cache must be an object")
    source_url = cache.get("url")
    body = cache.get("content")
    if not isinstance(source_url, str) or not source_url.strip():
        raise MatrixReplayError("recorded response cache has no source URL")
    if not isinstance(body, (str, dict, list)):
        raise MatrixReplayError("recorded response cache has no retained body")
    return json.dumps(
        {
            "body": body,
            "source_cache": {
                "content_sha256": source_sha256,
                "relative_path": relative_path,
            },
            "source_url": source_url,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def replay_prepared_entry(
    landing: Any,
    entry: PreparedEntry,
    *,
    observed_at: datetime,
) -> dict[str, Any]:
    from src.data_agents.canonical_v2.evidence_landing import (
        IngestEvidenceRequest,
        ParserReference,
        RegisterArtifactRequest,
    )

    backup = landing.register_artifact(
        RegisterArtifactRequest(
            run_id=f"s4d:{entry.entry_id}:backup",
            source_kind="verified_backup_copy",
            source_locator=(
                f"s2b-backup://{entry.source.source_id}/"
                f"{entry.source.member_relative_path}"
            ),
            content_path=entry.source.backup_path,
            observed_at=observed_at,
            expected_content_sha256=entry.source.content_sha256,
            expected_byte_size=entry.source.byte_size,
        )
    )
    parent = backup
    parent_kind = "verified_backup_copy"
    if entry.derived:
        parent = landing.register_artifact(
            RegisterArtifactRequest(
                run_id=f"s4d:{entry.entry_id}:restore",
                source_kind="verified_restore_copy",
                source_locator=(
                    f"s2b-restore://{entry.source.source_id}/"
                    f"{entry.source.member_relative_path}"
                ),
                content_path=entry.source.restore_path,
                observed_at=observed_at,
                expected_content_sha256=entry.source.content_sha256,
                expected_byte_size=entry.source.byte_size,
                parent_artifact_id=backup.artifact_id,
                parent_content_sha256=backup.content_sha256,
            )
        )
        parent_kind = "verified_restore_copy"
    elif hashlib.sha256(entry.content).hexdigest() != entry.source.content_sha256:
        raise MatrixReplayError("direct replay bytes differ from the verified restore")
    receipt = landing.ingest(
        IngestEvidenceRequest(
            run_id=f"s4d:{entry.entry_id}:parse:{entry.parser_version}",
            source_batch_id=entry.source_batch_id,
            source_kind=entry.source_kind,
            source_locator=entry.source_locator,
            content=entry.content,
            observed_at=observed_at,
            expected_content_sha256=hashlib.sha256(entry.content).hexdigest(),
            parser=ParserReference(
                parser_name=entry.parser_name,
                parser_version=entry.parser_version,
                schema_version=entry.schema_version,
                options=entry.parser_options,
            ),
            parent_artifact_id=parent.artifact_id,
            parent_content_sha256=parent.content_sha256,
        )
    )
    records = landing.stream(entry.source_batch_id)
    record_set = [
        {
            "errors": [error.model_dump(mode="json") for error in record.errors],
            "parse_status": record.parse_status.value,
            "payload": record.payload,
            "record_locator": record.record_locator,
        }
        for record in records
    ]
    record_set_bytes = json.dumps(
        record_set,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    parse_status_counts: dict[str, int] = {}
    error_kind_counts: dict[str, int] = {}
    for record in records:
        parse_status_counts[record.parse_status.value] = (
            parse_status_counts.get(record.parse_status.value, 0) + 1
        )
        for error in record.errors:
            error_kind_counts[error.error_kind.value] = (
                error_kind_counts.get(error.error_kind.value, 0) + 1
            )
    return {
        "artifact_id": receipt.artifact_id,
        "entry_id": entry.entry_id,
        "error_count": sum(error_kind_counts.values()),
        "error_kind_counts": dict(sorted(error_kind_counts.items())),
        "landing_status": receipt.status.value,
        "parent_artifact_id": receipt.parent_artifact_id,
        "parent_content_sha256": receipt.parent_content_sha256,
        "parent_kind": parent_kind,
        "parse_status_counts": dict(sorted(parse_status_counts.items())),
        "record_count": len(records),
        "record_set_sha256": hashlib.sha256(record_set_bytes).hexdigest(),
        "replay_bytes": len(entry.content),
        "replay_content_sha256": hashlib.sha256(entry.content).hexdigest(),
        "source_bytes": entry.source.byte_size,
        "source_id": entry.source.source_id,
        "source_sha256": entry.source.content_sha256,
    }


def require_expected_summary(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    mismatches = {
        key: {"expected": value, "actual": actual.get(key)}
        for key, value in expected.items()
        if actual.get(key) != value
    }
    if mismatches:
        raise MatrixReplayError(
            "landing replay summary mismatch: "
            + json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
        )


def execute_prepared_matrix(
    entries: tuple[PreparedEntry, ...],
    *,
    observed_at: datetime,
    expected_by_entry: dict[str, dict[str, Any]],
    landing_factory: Callable[[], Any] | None,
) -> dict[str, Any]:
    from src.data_agents.canonical_v2.evidence_landing import (
        create_ephemeral_evidence_landing,
    )

    entry_ids = tuple(entry.entry_id for entry in entries)
    if not entries or len(entry_ids) != len(set(entry_ids)):
        raise MatrixReplayError("landing matrix requires unique entries")
    expected_ids = set(expected_by_entry)
    if expected_ids and expected_ids != set(entry_ids):
        raise MatrixReplayError(
            "frozen summary coverage differs from the prepared matrix: "
            f"expected={sorted(expected_ids)}, entries={sorted(entry_ids)}"
        )
    if landing_factory is not None and (
        not expected_by_entry
        or any(not expected for expected in expected_by_entry.values())
    ):
        raise MatrixReplayError(
            "destination replay requires a frozen expected summary for every entry"
        )

    preflight_landing = create_ephemeral_evidence_landing()
    preflight_summaries = tuple(
        replay_prepared_entry(preflight_landing, entry, observed_at=observed_at)
        for entry in entries
    )
    if expected_by_entry:
        for summary in preflight_summaries:
            require_expected_summary(
                summary,
                expected_by_entry[summary["entry_id"]],
            )
    document = _matrix_summary(preflight_summaries)
    if landing_factory is None:
        return document

    destination = landing_factory()
    destination_summaries = tuple(
        replay_prepared_entry(destination, entry, observed_at=observed_at)
        for entry in entries
    )
    for summary in destination_summaries:
        require_expected_summary(summary, expected_by_entry[summary["entry_id"]])
    destination_document = _matrix_summary(destination_summaries)
    if destination_document != document:
        raise MatrixReplayError(
            "destination replay differs from the fully validated preflight summary"
        )
    return document


def _matrix_summary(summaries: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    entries = list(summaries)
    entry_bytes = json.dumps(
        entries,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "entries": entries,
        "entry_count": len(entries),
        "error_count": sum(int(entry["error_count"]) for entry in entries),
        "matrix_entries_sha256": hashlib.sha256(entry_bytes).hexdigest(),
        "record_count": sum(int(entry["record_count"]) for entry in entries),
        "replay_bytes": sum(int(entry["replay_bytes"]) for entry in entries),
        "source_bytes": sum(int(entry["source_bytes"]) for entry in entries),
    }


def _selected_strings(
    value: Any,
    *,
    label: str,
    maximum: int,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise MatrixReplayError(f"{label} must contain 1 through {maximum} values")
    result = tuple(_non_empty_string(item, label=label) for item in value)
    if len(result) != len(set(result)):
        raise MatrixReplayError(f"{label} must contain unique values")
    return result


def _docker_volume_set_sha256() -> str:
    result = subprocess.run(
        ["docker", "volume", "ls", "-q"],
        check=True,
        capture_output=True,
        text=True,
    )
    names = "\n".join(sorted(line for line in result.stdout.splitlines() if line))
    return hashlib.sha256(names.encode()).hexdigest()


def _pg_restore_selected_rows(
    dump_path: Path,
    *,
    table: str,
    expected_table: str,
    selected_field: str,
    selected_values: frozenset[str],
) -> tuple[dict[str, str | None], ...]:
    if re.fullmatch(r"[a-z_]+", table) is None:
        raise MatrixReplayError("pg_restore table selector is invalid")
    before_volumes = _docker_volume_set_sha256()
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m",
        "--tmpfs",
        "/var/lib/postgresql/data:rw,noexec,nosuid,size=1m",
        "--mount",
        f"type=bind,src={dump_path},dst=/input.dump,readonly",
        "--entrypoint",
        "pg_restore",
        "pgvector/pgvector:pg16",
        "--data-only",
        f"--table={table}",
        "--file=-",
        "/input.dump",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert process.stdout is not None and process.stderr is not None
    try:
        rows = parse_pg_copy_rows(
            process.stdout,
            expected_table=expected_table,
            selected_field=selected_field,
            selected_values=selected_values,
        )
        stderr = process.stderr.read()
        return_code = process.wait()
    except BaseException as exc:
        process.terminate()
        process.wait()
        if _docker_volume_set_sha256() != before_volumes:
            raise MatrixReplayError(
                "failed isolated pg_restore changed the Docker volume set"
            ) from exc
        raise
    after_volumes = _docker_volume_set_sha256()
    if after_volumes != before_volumes:
        raise MatrixReplayError("isolated pg_restore changed the Docker volume set")
    if return_code != 0:
        raise MatrixReplayError(
            f"isolated pg_restore failed for {table}: {stderr.strip()}"
        )
    return rows


def _query_milvus_copy(
    source_path: Path,
    *,
    materializer: dict[str, Any],
    expected_sha256: str,
    work_root: Path,
) -> tuple[dict[str, Any], ...]:
    collection = _non_empty_string(
        materializer.get("collection"), label="Milvus collection"
    )
    primary_key_field = _non_empty_string(
        materializer.get("primary_key_field"), label="Milvus primary key field"
    )
    primary_keys = _selected_strings(
        materializer.get("primary_keys"), label="Milvus primary keys", maximum=32
    )
    output_fields = _selected_strings(
        materializer.get("output_fields"), label="Milvus output fields", maximum=32
    )
    if primary_key_field not in output_fields:
        raise MatrixReplayError("Milvus output fields must include the primary key")
    if any("vector" in field.casefold() for field in output_fields):
        raise MatrixReplayError("bounded Milvus replay cannot export vector fields")
    work_root.mkdir(parents=True, exist_ok=True)
    source_before = _sha256_file(source_path)
    if source_before != expected_sha256:
        raise MatrixReplayError("Milvus restore copy changed before bounded export")
    with tempfile.TemporaryDirectory(prefix="milvus-copy-", dir=work_root) as directory:
        working_copy = Path(directory) / "milvus.db"
        subprocess.run(
            ["cp", "--reflink=auto", "--", str(source_path), str(working_copy)],
            check=True,
        )
        if (source_path.stat().st_dev, source_path.stat().st_ino) == (
            working_copy.stat().st_dev,
            working_copy.stat().st_ino,
        ):
            raise MatrixReplayError("Milvus working copy is not inode-independent")
        working_before = _sha256_file(working_copy)
        if working_before != expected_sha256:
            raise MatrixReplayError(
                "Milvus working copy hash differs from restore input"
            )
        os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="pkg_resources is deprecated as an API.*",
                category=UserWarning,
            )
            from pymilvus import MilvusClient

        client = MilvusClient(uri=str(working_copy))
        try:
            expression = (
                f"{primary_key_field} in ["
                + ",".join(json.dumps(key, ensure_ascii=False) for key in primary_keys)
                + "]"
            )
            rows = client.query(
                collection_name=collection,
                filter=expression,
                output_fields=list(output_fields),
                limit=len(primary_keys),
            )
        finally:
            client.close()
        working_after = _sha256_file(working_copy)
        if working_after != working_before:
            raise MatrixReplayError("bounded Milvus query mutated its working copy")
    source_after = _sha256_file(source_path)
    if source_after != source_before:
        raise MatrixReplayError(
            "bounded Milvus export mutated the verified restore copy"
        )
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise MatrixReplayError("bounded Milvus query returned an invalid row set")
    return tuple(rows)


def prepare_matrix(
    spec: MatrixSpec,
    *,
    evidence_root: Path,
    work_root: Path,
) -> PreparedMatrix:
    from src.data_agents.canonical_v2.rebuild_write_gate import (
        require_accepted_backup_gate,
    )

    gate = require_accepted_backup_gate(evidence_root)
    backup_document = _load_json_object(
        evidence_root / "s2b/backup-manifest.json", label="accepted backup manifest"
    )
    restore_document = _load_json_object(
        evidence_root / "s2b/restore-verification.json",
        label="accepted restore verification",
    )
    backup_root_value = _non_empty_string(
        backup_document.get("backup_root"), label="accepted backup root"
    )
    restore_root_value = _non_empty_string(
        restore_document.get("restore_root"), label="accepted restore root"
    )
    backup_root = Path(backup_root_value)
    restore_root = Path(restore_root_value)
    if not backup_root.is_absolute() or not restore_root.is_absolute():
        raise MatrixReplayError("accepted backup and restore roots must be absolute")
    backup_sources = _indexed_sources(backup_document, label="backup manifest")
    restore_sources = _indexed_sources(restore_document, label="restore verification")

    verified: list[tuple[dict[str, Any], VerifiedMember]] = []
    for entry in spec.entries:
        entry_id = str(entry["entry_id"])
        source_id = str(entry["source_id"])
        backup_source = backup_sources.get(source_id)
        restore_source = restore_sources.get(source_id)
        if backup_source is None or restore_source is None:
            raise MatrixReplayError(f"{entry_id} source is absent from Accepted S2B")
        if (
            backup_source.get("kind") != entry["accepted_source_kind"]
            or restore_source.get("kind") != entry["accepted_source_kind"]
        ):
            raise MatrixReplayError(f"{entry_id} accepted source kind changed")
        manifest_relative = backup_source.get("backup_member_manifest_path")
        manifest_sha256 = backup_source.get("backup_member_manifest_sha256")
        if not isinstance(manifest_relative, str) or not isinstance(
            manifest_sha256, str
        ):
            raise MatrixReplayError(f"{entry_id} has no accepted member manifest")
        member_manifest_path = _resolve_beneath(
            backup_root,
            manifest_relative,
            label=f"{entry_id} member manifest",
        )
        if _sha256_file(member_manifest_path) != manifest_sha256:
            raise MatrixReplayError(f"{entry_id} member manifest hash changed")
        member = verify_member(
            source_id=source_id,
            member_relative_path=str(entry["member_relative_path"]),
            restore_relative_path=str(entry["restore_relative_path"]),
            backup_root=backup_root,
            restore_root=restore_root,
            member_manifest_path=member_manifest_path,
            restore_source=restore_source,
            expected_sha256=str(entry["expected_source_sha256"]),
            expected_byte_size=int(entry["expected_source_bytes"]),
        )
        verified.append((entry, member))

    prepared: list[PreparedEntry] = []
    for entry, source in verified:
        materializer = entry["materializer"]
        assert isinstance(materializer, dict)
        kind = materializer["kind"]
        if kind == "direct":
            content = source.restore_path.read_bytes()
        elif kind == "wal_fpi":
            record_keys = _selected_strings(
                materializer.get("record_keys"),
                label="WAL/FPI record keys",
                maximum=32,
            )
            selected = frozenset(record_keys)
            paper_rows = _pg_restore_selected_rows(
                source.restore_path,
                table="paper",
                expected_table="salvage.paper",
                selected_field="paper_id",
                selected_values=selected,
            )
            error_rows = _pg_restore_selected_rows(
                source.restore_path,
                table="field_errors",
                expected_table="salvage.field_errors",
                selected_field="record_key",
                selected_values=selected,
            )
            content = materialize_wal_fpi(
                paper_rows, error_rows, record_keys=record_keys
            )
        elif kind == "milvus":
            rows = _query_milvus_copy(
                source.restore_path,
                materializer=materializer,
                expected_sha256=source.content_sha256,
                work_root=work_root,
            )
            content = materialize_milvus(
                rows,
                collection=str(materializer["collection"]),
                primary_key_field=str(materializer["primary_key_field"]),
                primary_keys=tuple(materializer["primary_keys"]),
                copy_sha256=source.content_sha256,
            )
        elif kind == "recorded_response":
            cache_content = source.restore_path.read_bytes()
            content = materialize_recorded_response(
                cache_content,
                source_sha256=source.content_sha256,
                relative_path=source.member_relative_path,
            )
        else:
            raise MatrixReplayError(f"unsupported materializer {kind}")
        parser = entry["parser"]
        assert isinstance(parser, dict)
        prepared.append(
            PreparedEntry(
                entry_id=str(entry["entry_id"]),
                source_batch_id=str(entry["source_batch_id"]),
                source_kind=str(entry["source_kind"]),
                source_locator=str(entry["source_locator"]),
                parser_name=str(parser["name"]),
                parser_version=str(parser["version"]),
                schema_version=str(parser["schema_version"]),
                parser_options=dict(parser["options"]),
                content=content,
                source=source,
                derived=bool(entry["derived"]),
            )
        )
    return PreparedMatrix(spec=spec, entries=tuple(prepared), gate=gate)


def _result_document(
    prepared: PreparedMatrix,
    summary: dict[str, Any],
    *,
    target: dict[str, str] | None,
) -> dict[str, Any]:
    gate = prepared.gate
    return {
        "schema_version": "canonical-v2-landing-replay-summary-v1",
        "matrix_id": prepared.spec.matrix_id,
        "observed_at": prepared.spec.observed_at.astimezone(timezone.utc).isoformat(),
        "gate": {
            "acceptance_record_sha256": gate.acceptance_record_sha256,
            "backup_manifest_sha256": gate.backup_manifest_sha256,
            "restore_verification_sha256": gate.restore_verification_sha256,
            "source_count": gate.source_count,
            "source_inventory_sha256": gate.source_inventory_sha256,
            "state": gate.state,
        },
        "target": target,
        **summary,
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("observe", "replay"))
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--expected-database")
    parser.add_argument("--target-kind")
    args = parser.parse_args()
    if not args.evidence_root.is_absolute() or not args.work_root.is_absolute():
        raise MatrixReplayError(
            "evidence and work roots must be explicit absolute paths"
        )
    spec = load_matrix(args.matrix)
    prepared = prepare_matrix(
        spec,
        evidence_root=args.evidence_root,
        work_root=args.work_root,
    )
    landing_factory: Callable[[], Any] | None = None
    target: dict[str, str] | None = None
    if args.mode == "replay":
        if not all((args.database_url, args.expected_database, args.target_kind)):
            raise MatrixReplayError("replay requires an explicit database target")
        from src.data_agents.canonical_v2.evidence_landing_postgres import (
            create_postgres_evidence_landing,
        )

        database_url = str(args.database_url)
        expected_database = str(args.expected_database)
        target_kind = str(args.target_kind)

        def _landing_factory() -> Any:
            return create_postgres_evidence_landing(
                database_url=database_url,
                expected_database=expected_database,
                target_kind=target_kind,
                backup_gate_root=args.evidence_root,
            )

        landing_factory = _landing_factory
        target = {
            "database": expected_database,
            "kind": target_kind,
            "revision": "C2_0004",
        }
    summary = execute_prepared_matrix(
        prepared.entries,
        observed_at=spec.observed_at,
        expected_by_entry=spec.expected_by_entry,
        landing_factory=landing_factory,
    )
    result = _result_document(prepared, summary, target=target)
    _write_json(args.output, result)
    print(
        json.dumps(
            {
                "entry_count": result["entry_count"],
                "error_count": result["error_count"],
                "matrix_entries_sha256": result["matrix_entries_sha256"],
                "mode": args.mode,
                "output": str(args.output),
                "record_count": result["record_count"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
