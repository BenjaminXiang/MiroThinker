"""XLSX upload front door for the Canonical V2 admin zone (W3).

W3 re-mounts the legacy admin upload chain behind a V2 route. The plan's wording is "旧 `upload.py`
链…以 V2 路由受限重挂"; read literally that would re-register routes whose every dependency is a
Postgres connection, which answers 500 (not 503) on a serving host with no Postgres and would leave
the trigger outside W2's gate. This module owns the part that has to be admitted *before* any of that
work happens, and nothing else:

* the domain white list and the payload shape,
* content identity (SHA-256) and duplicate refusal,
* a cross-process advisory lock per ``(domain, sha256)`` — W2's :class:`JobLock`, not a second lock,
* staging under the existing admin upload root,
* a serving-side ledger so an upload is still trackable when the build-time Postgres is unreachable,
* dispatch through the shared gate (:class:`JobRuntime`), never a private spawn.

The real work — XLSX parsing, Postgres import, enrichment batch scheduling, professor pipeline — stays
where it is, in ``backend/api/upload.py`` and the domain modules, reached through one declared task.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from src.data_agents.canonical_v2.jobs import (
    MANUAL_TRIGGER,
    JobLock,
    JobPostgresUnavailableError,
    JobRuntime,
    JobTaskUnknownError,
    JobParameterError,
    JobsError,
    JobsStorageUnavailableError,
    redact_secrets,
)
from src.data_agents.canonical_v2.managed_config import default_repo_root


SCHEMA_VERSION = "canonical-v2-uploads-v1"
UPLOADS_DB_ENV = "CANONICAL_V2_UPLOADS_DB"
UPLOADS_DB_FILENAME = "uploads.sqlite3"
UPLOAD_ROOT_ENV = "MIROTHINKER_ADMIN_UPLOAD_DIR"
MAX_UPLOAD_BYTES_ENV = "MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES"
DEFAULT_MAX_UPLOAD_BYTES = 128 * 1024 * 1024

UPLOAD_DOMAINS: tuple[str, ...] = ("company", "patent", "professor")
DRY_RUN_DOMAINS: tuple[str, ...] = ("company", "patent")

UPLOAD_TASK_BY_DOMAIN: Mapping[str, str] = {
    "company": "upload-company-import",
    "patent": "upload-patent-import",
    "professor": "upload-professor-import",
}

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_REJECTED = "rejected"
TERMINAL_STATUSES: tuple[str, ...] = (
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_REJECTED,
)
# A failed or refused attempt must not poison the content hash: the operator has to be able to retry
# the same workbook after fixing whatever broke.
RETRYABLE_STATUSES: tuple[str, ...] = (STATUS_FAILED, STATUS_REJECTED)

_SUMMARY_LIMIT = 4000
_XLSX_SUFFIX = ".xlsx"


class UploadError(Exception):
    """Base class for every refusal this module raises; ``code`` is HTTP-stable."""

    code = "upload_error"


class UploadDomainError(UploadError):
    code = "upload_unknown_domain"


class UploadFileTypeError(UploadError):
    code = "upload_invalid_file"


class UploadTooLargeError(UploadError):
    code = "upload_too_large"


class UploadDuplicateError(UploadError):
    code = "duplicate_upload"

    def __init__(self, message: str, *, record: "UploadRecord | None" = None) -> None:
        super().__init__(message)
        self.record = record


class UploadInProgressError(UploadError):
    code = "upload_in_progress"


class UploadNotFoundError(UploadError):
    code = "upload_not_found"


class UploadRequiresPostgresError(UploadError):
    code = "upload_requires_postgres"


class UploadsStorageUnavailableError(UploadError):
    code = "uploads_storage_unavailable"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _bounded_summary(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= _SUMMARY_LIMIT:
        return dict(payload)
    return {"truncated": True, "excerpt": redact_secrets(text[:_SUMMARY_LIMIT])}


# -------------------------------------------------------------------------------------- registry


@dataclass(frozen=True, slots=True)
class UploadRecord:
    upload_id: str
    domain: str
    filename: str
    content_sha256: str
    size_bytes: int
    staged_path: str
    status: str
    dry_run: bool
    run_id: str | None
    operator: str
    created_at: str
    updated_at: str
    summary: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "upload_id": self.upload_id,
            "domain": self.domain,
            "filename": self.filename,
            "content_sha256": self.content_sha256,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "dry_run": self.dry_run,
            "run_id": self.run_id,
            "operator": self.operator,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "summary": self.summary,
        }


_DDL = """
CREATE TABLE IF NOT EXISTS upload (
    upload_id      TEXT PRIMARY KEY,
    domain         TEXT NOT NULL,
    filename       TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    size_bytes     INTEGER NOT NULL,
    staged_path    TEXT NOT NULL,
    status         TEXT NOT NULL,
    dry_run        INTEGER NOT NULL DEFAULT 0,
    run_id         TEXT,
    operator       TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    summary_json   TEXT
);
CREATE INDEX IF NOT EXISTS upload_identity ON upload(domain, content_sha256);
CREATE INDEX IF NOT EXISTS upload_recent ON upload(created_at DESC);
CREATE TABLE IF NOT EXISTS upload_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class UploadStore:
    """Serving-side ledger of admitted uploads; never stores content, environment or credentials."""

    def __init__(self, database_path: Path | str) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._conn.execute(
            "INSERT INTO upload_meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SCHEMA_VERSION,),
        )
        self._conn.commit()

    @property
    def database_path(self) -> Path:
        return self._path

    def close(self) -> None:
        self._conn.close()

    def create(
        self,
        *,
        upload_id: str,
        domain: str,
        filename: str,
        content_sha256: str,
        size_bytes: int,
        staged_path: Path | str,
        dry_run: bool,
        operator: str,
    ) -> UploadRecord:
        stamp = _now()
        self._conn.execute(
            """
            INSERT INTO upload (upload_id, domain, filename, content_sha256, size_bytes,
                                staged_path, status, dry_run, run_id, operator,
                                created_at, updated_at, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL)
            """,
            (
                upload_id,
                domain,
                filename,
                content_sha256,
                int(size_bytes),
                str(staged_path),
                STATUS_QUEUED,
                1 if dry_run else 0,
                operator,
                stamp,
                stamp,
            ),
        )
        self._conn.commit()
        record = self.get(upload_id)
        if record is None:  # pragma: no cover - the INSERT above is the only writer
            raise UploadsStorageUnavailableError(f"upload {upload_id} vanished after insert")
        return record

    def set_status(
        self,
        upload_id: str,
        *,
        status: str,
        run_id: str | None = None,
        summary: Mapping[str, Any] | None = None,
    ) -> UploadRecord | None:
        assignments = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, _now()]
        if run_id is not None:
            assignments.append("run_id = ?")
            values.append(run_id)
        if summary is not None:
            assignments.append("summary_json = ?")
            values.append(json.dumps(_bounded_summary(summary), ensure_ascii=False))
        values.append(upload_id)
        self._conn.execute(f"UPDATE upload SET {', '.join(assignments)} WHERE upload_id = ?", values)
        self._conn.commit()
        return self.get(upload_id)

    def get(self, upload_id: str) -> UploadRecord | None:
        row = self._conn.execute(
            "SELECT * FROM upload WHERE upload_id = ?", (upload_id,)
        ).fetchone()
        return None if row is None else _record_from_row(row)

    def find_active(self, *, domain: str, content_sha256: str) -> UploadRecord | None:
        row = self._conn.execute(
            """
            SELECT * FROM upload
             WHERE domain = ? AND content_sha256 = ?
               AND status NOT IN (?, ?)
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (domain, content_sha256, *RETRYABLE_STATUSES),
        ).fetchone()
        return None if row is None else _record_from_row(row)

    def list(
        self, *, domain: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[UploadRecord, ...]:
        clause, params = "", []
        if domain is not None:
            clause = "WHERE domain = ?"
            params.append(domain)
        rows = self._conn.execute(
            f"SELECT * FROM upload {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, int(limit), int(offset)),
        ).fetchall()
        return tuple(_record_from_row(row) for row in rows)

    def total(self, *, domain: str | None = None) -> int:
        if domain is None:
            row = self._conn.execute("SELECT count(*) FROM upload").fetchone()
        else:
            row = self._conn.execute(
                "SELECT count(*) FROM upload WHERE domain = ?", (domain,)
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def schema_version(self) -> str:
        row = self._conn.execute(
            "SELECT value FROM upload_meta WHERE key = 'schema_version'"
        ).fetchone()
        return str(row[0]) if row is not None else ""


def _record_from_row(row: sqlite3.Row) -> UploadRecord:
    raw_summary = row["summary_json"]
    return UploadRecord(
        upload_id=str(row["upload_id"]),
        domain=str(row["domain"]),
        filename=str(row["filename"]),
        content_sha256=str(row["content_sha256"]),
        size_bytes=int(row["size_bytes"]),
        staged_path=str(row["staged_path"]),
        status=str(row["status"]),
        dry_run=bool(row["dry_run"]),
        run_id=None if row["run_id"] is None else str(row["run_id"]),
        operator=str(row["operator"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        summary=None if raw_summary is None else json.loads(raw_summary),
    )


# ----------------------------------------------------------------------------------- locations


def uploads_database_path(environ: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environ is None else environ
    explicit = values.get(UPLOADS_DB_ENV, "").strip()
    if explicit:
        return Path(explicit)
    # Same convention W2 uses: one SQLite file per concern, next to the access-log database when the
    # deployment already declares one.
    sibling = values.get("CANONICAL_V2_ACCESS_LOG_DB", "").strip()
    if sibling:
        return Path(sibling).parent / UPLOADS_DB_FILENAME
    jobs = values.get("CANONICAL_V2_JOBS_DB", "").strip()
    if jobs:
        return Path(jobs).parent / UPLOADS_DB_FILENAME
    raise UploadsStorageUnavailableError(
        f"neither {UPLOADS_DB_ENV} nor CANONICAL_V2_ACCESS_LOG_DB is set"
    )


def default_upload_root(repo_root: Path | str) -> Path:
    root = Path(repo_root)
    return root / "data" / "admin_uploads"


def upload_root(environ: Mapping[str, str] | None = None, *, repo_root: Path | str) -> Path:
    values = os.environ if environ is None else environ
    configured = values.get(UPLOAD_ROOT_ENV, "").strip()
    return Path(configured) if configured else default_upload_root(repo_root)


def max_upload_bytes(environ: Mapping[str, str] | None = None) -> int:
    values = os.environ if environ is None else environ
    raw = values.get(MAX_UPLOAD_BYTES_ENV, "").strip()
    if not raw:
        return DEFAULT_MAX_UPLOAD_BYTES
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_MAX_UPLOAD_BYTES
    return parsed if parsed > 0 else DEFAULT_MAX_UPLOAD_BYTES


def stage_upload_path(
    *, root: Path, domain: str, digest: str, upload_id: str, filename: str
) -> Path:
    safe_name = Path(filename).name or "upload.xlsx"
    return root / domain / digest[:16] / upload_id / safe_name


# ------------------------------------------------------------------------------------- runtime


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    record: UploadRecord
    outcome: str  # "running" | "skipped"
    skip_reason: str | None = None
    gate_code: str | None = None


class UploadRuntime:
    """Admission for uploads, and the only place an upload reaches the gate."""

    def __init__(
        self,
        *,
        store: UploadStore,
        gate: JobRuntime,
        repo_root: Path | str,
        environ: Mapping[str, str] | None = None,
        preflight: Callable[[str, str], Mapping[str, Any] | None] | None = None,
        batch_reader: Callable[[str], Mapping[str, Any] | None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.gate = gate
        self._repo_root = Path(repo_root)
        self._environ = dict(os.environ if environ is None else environ)
        self._preflight = preflight
        self._batch_reader = batch_reader
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock_dir = Path(gate.store.database_path).parent / "locks"

    # -- introspection ----------------------------------------------------------------------

    @property
    def upload_root(self) -> Path:
        return upload_root(self._environ, repo_root=self._repo_root)

    def postgres_status(self) -> dict[str, Any]:
        return self.gate.postgres_status()

    def domains(self) -> list[dict[str, Any]]:
        return [
            {
                "domain": domain,
                "task_id": UPLOAD_TASK_BY_DOMAIN[domain],
                "dry_run_supported": domain in DRY_RUN_DOMAINS,
            }
            for domain in UPLOAD_DOMAINS
        ]

    def detail(self, upload_id: str) -> dict[str, Any]:
        record = self.store.get(upload_id)
        if record is None:
            raise UploadNotFoundError(f"upload {upload_id} not found")
        payload: dict[str, Any] = {"upload": record.as_dict()}
        payload["run"] = (
            None if record.run_id is None else self.gate.run_detail(record.run_id)
        )
        payload["batch"] = None
        if self._batch_reader is not None and record.summary is not None:
            batch_id = record.summary.get("batch_id")
            if isinstance(batch_id, str) and batch_id:
                try:
                    payload["batch"] = self._batch_reader(batch_id)
                except Exception as exc:  # noqa: BLE001 - batch progress is best-effort detail
                    payload["batch"] = {"available": False, "reason": type(exc).__name__}
        return payload

    # -- admission --------------------------------------------------------------------------

    def resolve_token(self, token: str) -> str:
        """Resolve an upload token server-side; the only value the gate accepts for this task."""

        record = self.store.get(token)
        if record is None:
            raise JobParameterError(f"unknown upload id: {token}")
        staged = Path(record.staged_path)
        root = self.upload_root.resolve()
        try:
            resolved = staged.resolve()
        except OSError as exc:  # pragma: no cover - defensive
            raise JobParameterError(f"upload {token} has an unusable staged path") from exc
        if root != resolved and root not in resolved.parents:
            raise JobParameterError(f"upload {token} points outside the upload root")
        if not resolved.is_file():
            raise JobParameterError(f"upload {token} is no longer staged")
        return record.upload_id

    def register(
        self,
        *,
        domain: str,
        filename: str,
        content: bytes,
        operator: str = "anonymous",
        dry_run: bool = False,
    ) -> AdmissionResult:
        if domain not in UPLOAD_DOMAINS:
            raise UploadDomainError(
                f"domain must be one of: {', '.join(UPLOAD_DOMAINS)}"
            )
        safe_name = Path(filename or "").name
        if not safe_name.lower().endswith(_XLSX_SUFFIX):
            raise UploadFileTypeError("Only .xlsx files are accepted")
        if not content:
            raise UploadFileTypeError("Uploaded file is empty")
        limit = max_upload_bytes(self._environ)
        if len(content) > limit:
            raise UploadTooLargeError(
                f"uploaded file exceeds the {limit} byte limit"
            )
        digest = hashlib.sha256(content).hexdigest()
        if dry_run and domain not in DRY_RUN_DOMAINS:
            raise UploadFileTypeError(
                f"dry-run is not available for {domain}; commit it instead"
            )
        if not dry_run and not self.gate.postgres_status().get("available"):
            raise UploadRequiresPostgresError(
                "committing an upload needs the build-time PostgreSQL, which is unavailable here"
            )

        lock = JobLock.try_acquire(self._lock_dir / f"upload-{domain}-{digest[:16]}.lock")
        if lock is None:
            raise UploadInProgressError(
                f"an upload of this content for {domain} is being admitted right now"
            )
        try:
            duplicate = self.store.find_active(domain=domain, content_sha256=digest)
            if duplicate is not None:
                raise UploadDuplicateError(
                    f"this file was already uploaded for {domain}", record=duplicate
                )
            if self._preflight is not None and not dry_run:
                existing = self._preflight(domain, digest)
                if existing:
                    raise UploadDuplicateError(
                        "this file is already being processed by the domain pipeline",
                        record=None,
                    )
            upload_id = str(uuid4())
            staged = stage_upload_path(
                root=self.upload_root,
                domain=domain,
                digest=digest,
                upload_id=upload_id,
                filename=safe_name,
            )
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(content)
            record = self.store.create(
                upload_id=upload_id,
                domain=domain,
                filename=safe_name,
                content_sha256=digest,
                size_bytes=len(content),
                staged_path=staged,
                dry_run=dry_run,
                operator=operator,
            )
        finally:
            lock.release()

        return self._dispatch(record)

    def _dispatch(self, record: UploadRecord) -> AdmissionResult:
        task_id = UPLOAD_TASK_BY_DOMAIN[record.domain]
        try:
            outcome = self.gate.trigger(
                task_id,
                params={"upload_id": record.upload_id},
                operator=record.operator,
                trigger_source=MANUAL_TRIGGER,
            )
        except JobPostgresUnavailableError:
            self.store.set_status(
                record.upload_id, status=STATUS_REJECTED, summary={"code": "job_postgres_unavailable"}
            )
            raise
        except (JobTaskUnknownError, JobParameterError, JobsStorageUnavailableError) as exc:
            self.store.set_status(
                record.upload_id, status=STATUS_REJECTED, summary={"code": exc.code}
            )
            raise
        except JobsError as exc:
            self.store.set_status(
                record.upload_id, status=STATUS_REJECTED, summary={"code": exc.code}
            )
            raise UploadInProgressError(str(exc)) from exc

        if outcome.status == "skipped":
            updated = self.store.set_status(
                record.upload_id,
                status=STATUS_SKIPPED,
                run_id=outcome.run_id,
                summary={"skip_reason": outcome.skip_reason, "task_id": task_id},
            )
            return AdmissionResult(
                record=updated or record, outcome="skipped", skip_reason=outcome.skip_reason
            )
        running = self.store.set_status(
            record.upload_id,
            status=STATUS_RUNNING,
            run_id=outcome.run_id,
            summary={"task_id": task_id, "dry_run": record.dry_run},
        )
        return AdmissionResult(record=running or record, outcome="running")


def resolve_upload_token(token: str, *, environ: Mapping[str, str] | None = None) -> str:
    """Default resolver used by the declared upload tasks: validate the token against the ledger.

    The gate hands us the caller's opaque token; everything after this point is server-side state:
    the ledger row decides whether the token exists, and the staged path must still resolve inside
    the upload root and still be a file.
    """

    values = os.environ if environ is None else environ
    try:
        store = UploadStore(uploads_database_path(values))
    except (UploadsStorageUnavailableError, OSError) as exc:
        # Fail closed: with no ledger there is no way to tell a real token from an invented one.
        raise JobParameterError(f"upload ledger is unavailable: {exc}") from exc
    try:
        record = store.get(token)
        if record is None:
            raise JobParameterError(f"unknown upload id: {token}")
        root = upload_root(values, repo_root=default_repo_root()).resolve()
        resolved = Path(record.staged_path).resolve()
        if root != resolved and root not in resolved.parents:
            raise JobParameterError(f"upload {token} points outside the upload root")
        if not resolved.is_file():
            raise JobParameterError(f"upload {token} is no longer staged")
        return record.upload_id
    finally:
        store.close()


__all__ = [
    "AdmissionResult",
    "DRY_RUN_DOMAINS",
    "SCHEMA_VERSION",
    "STATUS_FAILED",
    "STATUS_QUEUED",
    "STATUS_REJECTED",
    "STATUS_RUNNING",
    "STATUS_SKIPPED",
    "STATUS_SUCCEEDED",
    "TERMINAL_STATUSES",
    "UPLOADS_DB_ENV",
    "UPLOADS_DB_FILENAME",
    "UPLOAD_DOMAINS",
    "UPLOAD_TASK_BY_DOMAIN",
    "UPLOAD_ROOT_ENV",
    "UploadDomainError",
    "UploadDuplicateError",
    "UploadError",
    "UploadFileTypeError",
    "UploadInProgressError",
    "UploadNotFoundError",
    "UploadRecord",
    "UploadRequiresPostgresError",
    "UploadRuntime",
    "UploadStore",
    "UploadTooLargeError",
    "UploadsStorageUnavailableError",
    "default_upload_root",
    "max_upload_bytes",
    "resolve_upload_token",
    "stage_upload_path",
    "upload_root",
    "uploads_database_path",
]
