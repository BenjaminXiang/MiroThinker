"""SQLite-backed correction overlay for Canonical V2 released data.

Edits never touch the immutable serving-pack release artifacts (their hash
provenance chain must stay intact). Field corrections and manually added
records live in one independent database, are merged at read time by the
admin runtime, and can be exported as input for the next release build —
which is how corrections reach chat answers.

Unlike the access log, writes here are explicit admin actions: failures
raise, they are never swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
from typing import Any, Literal

SCHEMA_VERSION = "canonical-v2-corrections-v1"

CorrectionStatus = Literal["active", "reverted"]

_REASON_MAX = 500
_OPERATOR_MAX = 200


class CorrectionsStoreError(ValueError):
    """Raised for invalid correction operations (bad status, unknown id)."""


@dataclass(frozen=True, slots=True)
class FieldCorrectionRecord:
    """One field-level correction write (values pre-serialization)."""

    domain: str
    canonical_object_id: str
    field_path: str
    old_value: Any
    new_value: Any
    reason: str
    operator: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class FieldCorrectionDetail:
    correction_id: str
    domain: str
    canonical_object_id: str
    field_path: str
    old_value: Any
    new_value: Any
    reason: str
    operator: str
    created_at: str
    status: str


@dataclass(frozen=True, slots=True)
class AddedRecordDetail:
    record_id: str
    domain: str
    manual_object_id: str
    payload: dict[str, Any]
    reason: str
    operator: str
    created_at: str
    status: str


_DDL = """
CREATE TABLE IF NOT EXISTS workspace_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS field_corrections (
    correction_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    canonical_object_id TEXT NOT NULL,
    field_path TEXT NOT NULL,
    old_value_json TEXT,
    new_value_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    operator TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS field_corrections_object
    ON field_corrections (domain, canonical_object_id, status);
CREATE TABLE IF NOT EXISTS added_records (
    record_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    manual_object_id TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    operator TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS added_records_domain
    ON added_records (domain, status);
"""


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("correction timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _prepare_database_file(database_path: Path) -> Path:
    """Create the database file with private permissions if missing."""

    if database_path.name in {"", ".", ".."} or not database_path.name:
        raise OSError("corrections path must name a file")
    parent = database_path.parent
    if not parent.is_dir():
        raise OSError("corrections parent directory does not exist")
    if parent.is_symlink():
        raise OSError("corrections parent directory must not be a symlink")
    try:
        os.lstat(database_path)
    except FileNotFoundError:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(database_path, flags, 0o600)
        os.close(descriptor)
    metadata = os.lstat(database_path)
    if database_path.is_symlink() or not database_path.is_file():
        raise OSError("corrections path must be a regular file")
    if metadata.st_nlink != 1:
        raise OSError("corrections path must not be hard-linked")
    os.chmod(database_path, 0o600, follow_symlinks=False)
    return database_path


class CorrectionsStore:
    """Owns one SQLite database of field corrections and added records."""

    def __init__(self, database_path: Path) -> None:
        safe_path = _prepare_database_file(Path(database_path))
        self._database_path = safe_path
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            safe_path,
            check_same_thread=False,
            timeout=30.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = NORMAL")
        self._connection.execute("PRAGMA busy_timeout = 30000")
        self._initialize_schema()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def _initialize_schema(self) -> None:
        with self._lock:
            with self._connection:
                self._connection.executescript(_DDL)
                row = self._connection.execute(
                    "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        "INSERT INTO workspace_meta (key, value) VALUES (?, ?)",
                        ("schema_version", SCHEMA_VERSION),
                    )
                elif row["value"] != SCHEMA_VERSION:
                    raise sqlite3.Error(
                        "corrections schema version differs from "
                        f"{SCHEMA_VERSION}: {row['value']}"
                    )

    # -- field corrections ------------------------------------------------

    def record_correction(self, record: FieldCorrectionRecord) -> str:
        """Persist one field correction; returns the correction id."""

        reason = record.reason.strip()
        if not reason:
            raise CorrectionsStoreError("correction reason must not be empty")
        operator = record.operator.strip()
        if not operator:
            raise CorrectionsStoreError("correction operator must not be empty")
        field_path = record.field_path.strip()
        if not field_path:
            raise CorrectionsStoreError("correction field_path must not be empty")
        correction_id = f"correction-{secrets.token_hex(8)}"
        with self._lock:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO field_corrections (
                        correction_id, domain, canonical_object_id, field_path,
                        old_value_json, new_value_json, reason, operator,
                        created_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (
                        correction_id,
                        record.domain,
                        record.canonical_object_id,
                        field_path,
                        (
                            None
                            if record.old_value is None
                            else json.dumps(record.old_value, ensure_ascii=False)
                        ),
                        json.dumps(record.new_value, ensure_ascii=False),
                        reason[:_REASON_MAX],
                        operator[:_OPERATOR_MAX],
                        _utc_iso(record.created_at),
                    ),
                )
        return correction_id

    def list_corrections(
        self,
        *,
        domain: str | None = None,
        canonical_object_id: str | None = None,
        status: str | None = None,
    ) -> tuple[FieldCorrectionDetail, ...]:
        clauses: list[str] = []
        params: list[Any] = []
        if domain is not None:
            clauses.append("domain = ?")
            params.append(domain)
        if canonical_object_id is not None:
            clauses.append("canonical_object_id = ?")
            params.append(canonical_object_id)
        if status is not None:
            if status not in ("active", "reverted"):
                raise CorrectionsStoreError(f"unknown correction status: {status}")
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT correction_id, domain, canonical_object_id, field_path,
                       old_value_json, new_value_json, reason, operator,
                       created_at, status
                FROM field_corrections{where}
                ORDER BY created_at DESC, correction_id ASC
                """,
                params,
            ).fetchall()
        return tuple(self._correction_from_row(row) for row in rows)

    def active_corrections(
        self, *, domain: str, canonical_object_id: str
    ) -> tuple[FieldCorrectionDetail, ...]:
        """Latest active correction per field_path for one object."""

        active = self.list_corrections(
            domain=domain, canonical_object_id=canonical_object_id, status="active"
        )
        latest: dict[str, FieldCorrectionDetail] = {}
        for detail in active:  # already newest-first
            if detail.field_path not in latest:
                latest[detail.field_path] = detail
        return tuple(latest.values())

    def revert_correction(self, correction_id: str) -> bool:
        """Soft-revert one correction; False when the id is unknown."""

        return self._revert("field_corrections", "correction_id", correction_id)

    # -- added records -----------------------------------------------------

    def add_record(
        self,
        *,
        domain: str,
        payload: dict[str, Any],
        reason: str,
        operator: str,
        created_at: datetime,
    ) -> AddedRecordDetail:
        """Persist one manually added record with a generated manual id."""

        if not isinstance(payload, dict) or not payload:
            raise CorrectionsStoreError("added record payload must be a non-empty object")
        if not reason.strip():
            raise CorrectionsStoreError("added record reason must not be empty")
        if not operator.strip():
            raise CorrectionsStoreError("added record operator must not be empty")
        record_id = f"added-{secrets.token_hex(8)}"
        manual_object_id = f"{domain}-manual-{secrets.token_hex(6)}"
        created_iso = _utc_iso(created_at)
        with self._lock:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO added_records (
                        record_id, domain, manual_object_id, payload_json,
                        reason, operator, created_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (
                        record_id,
                        domain,
                        manual_object_id,
                        json.dumps(payload, ensure_ascii=False),
                        reason.strip()[:_REASON_MAX],
                        operator.strip()[:_OPERATOR_MAX],
                        created_iso,
                    ),
                )
        return AddedRecordDetail(
            record_id=record_id,
            domain=domain,
            manual_object_id=manual_object_id,
            payload=dict(payload),
            reason=reason.strip()[:_REASON_MAX],
            operator=operator.strip()[:_OPERATOR_MAX],
            created_at=created_iso,
            status="active",
        )

    def list_added_records(
        self,
        *,
        domain: str | None = None,
        status: str | None = None,
    ) -> tuple[AddedRecordDetail, ...]:
        clauses: list[str] = []
        params: list[Any] = []
        if domain is not None:
            clauses.append("domain = ?")
            params.append(domain)
        if status is not None:
            if status not in ("active", "reverted"):
                raise CorrectionsStoreError(f"unknown added-record status: {status}")
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT record_id, domain, manual_object_id, payload_json,
                       reason, operator, created_at, status
                FROM added_records{where}
                ORDER BY created_at DESC, record_id ASC
                """,
                params,
            ).fetchall()
        return tuple(
            AddedRecordDetail(
                record_id=row["record_id"],
                domain=row["domain"],
                manual_object_id=row["manual_object_id"],
                payload=json.loads(row["payload_json"]),
                reason=row["reason"],
                operator=row["operator"],
                created_at=row["created_at"],
                status=row["status"],
            )
            for row in rows
        )

    def get_added_record(self, manual_object_id: str) -> AddedRecordDetail | None:
        """One active added record by its manual object id, else None."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT record_id, domain, manual_object_id, payload_json,
                       reason, operator, created_at, status
                FROM added_records
                WHERE manual_object_id = ? AND status = 'active'
                """,
                (manual_object_id,),
            ).fetchone()
        if row is None:
            return None
        return AddedRecordDetail(
            record_id=row["record_id"],
            domain=row["domain"],
            manual_object_id=row["manual_object_id"],
            payload=json.loads(row["payload_json"]),
            reason=row["reason"],
            operator=row["operator"],
            created_at=row["created_at"],
            status=row["status"],
        )

    def revert_added_record(self, record_id: str) -> bool:
        """Soft-revert one added record; False when the id is unknown."""

        return self._revert("added_records", "record_id", record_id)

    # -- shared -------------------------------------------------------------

    def _revert(self, table: str, id_column: str, record_id: str) -> bool:
        with self._lock:
            with self._connection:
                cursor = self._connection.execute(
                    f"UPDATE {table} SET status = 'reverted'"
                    f" WHERE {id_column} = ? AND status = 'active'",
                    (record_id,),
                )
        return cursor.rowcount > 0

    @staticmethod
    def _correction_from_row(row: sqlite3.Row) -> FieldCorrectionDetail:
        return FieldCorrectionDetail(
            correction_id=row["correction_id"],
            domain=row["domain"],
            canonical_object_id=row["canonical_object_id"],
            field_path=row["field_path"],
            old_value=(
                None
                if row["old_value_json"] is None
                else json.loads(row["old_value_json"])
            ),
            new_value=json.loads(row["new_value_json"]),
            reason=row["reason"],
            operator=row["operator"],
            created_at=row["created_at"],
            status=row["status"],
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()
