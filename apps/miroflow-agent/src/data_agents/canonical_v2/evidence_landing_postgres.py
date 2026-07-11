"""Explicit-target PostgreSQL repository for immutable EvidenceLanding runs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url

from src.data_agents.storage.database_target import (
    DestructiveDatabaseTarget,
    resolve_destructive_database_target,
)

from .contracts import EvidenceArtifact, ParseStatus, SourceError, SourceRecord
from .evidence_adapters import default_source_adapters
from .evidence_landing import (
    EvidenceIntegrityError,
    EvidenceLanding,
    EvidenceLandingPersistenceError,
    EvidenceLandingService,
    LandingReceipt,
    LandingRepository,
    LandingStatus,
    PreparedLandingRun,
)
from .rebuild_write_gate import require_accepted_backup_gate


EXPECTED_REVISION = "C2_0004"
VERSION_TABLE = "public.canonical_v2_alembic_version"


class _ExplicitTargetConfig:
    def __init__(
        self,
        *,
        database_url: str,
        expected_database: str,
        target_kind: str,
    ) -> None:
        self._options = {
            "sqlalchemy.url": database_url,
            "miroflow.expected_database": expected_database,
            "miroflow.target_kind": target_kind,
        }

    def get_main_option(
        self,
        name: str,
        default: str | None = None,
    ) -> str | None:
        return self._options.get(name, default)


def _psycopg_dsn(database_url: str) -> str:
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def _integrity_error(message: str) -> EvidenceIntegrityError:
    return EvidenceIntegrityError(message)


class PostgresLandingRepository(LandingRepository):
    """Persist complete landing runs using one transaction per public ingest."""

    def __init__(
        self,
        *,
        target: DestructiveDatabaseTarget,
        backup_gate_root: Path,
    ) -> None:
        self._target = target
        self._backup_gate_root = backup_gate_root
        self._dsn = _psycopg_dsn(target.url)

    def verify_ready(self) -> None:
        with self._connection(write=False):
            pass

    @contextmanager
    def _connection(
        self,
        *,
        write: bool,
    ) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        if write:
            require_accepted_backup_gate(self._backup_gate_root)
        try:
            connection = cast(
                psycopg.Connection[dict[str, Any]],
                psycopg.connect(
                    self._dsn,
                    autocommit=False,
                    row_factory=cast(Any, dict_row),
                ),
            )
        except psycopg.Error as exc:
            raise EvidenceLandingPersistenceError(
                "PostgreSQL landing target cannot be connected"
            ) from exc
        try:
            identity = connection.execute(
                "SELECT current_database() AS database_name, "
                "shobj_description(oid, 'pg_database') AS database_marker "
                "FROM pg_database WHERE datname = current_database()"
            ).fetchone()
            if identity is None:
                raise EvidenceLandingPersistenceError(
                    "PostgreSQL landing target identity cannot be read"
                )
            self._target.verify_database_identity(
                actual_database=identity["database_name"],
                database_marker=identity["database_marker"],
            )
            revision = connection.execute(
                f"SELECT version_num FROM {VERSION_TABLE}"
            ).fetchone()
            if revision is None or revision["version_num"] != EXPECTED_REVISION:
                raise EvidenceLandingPersistenceError(
                    "PostgreSQL landing target is not at the required C2_0004 revision"
                )
            connection.rollback()
            yield connection
        except psycopg.Error as exc:
            raise EvidenceLandingPersistenceError(
                "PostgreSQL landing verification or transaction failed"
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _existing_run(connection: Any, run_id: str) -> dict[str, Any] | None:
        return connection.execute(
            "SELECT run.run_id, run.source_batch_id, run.artifact_id, "
            "run.content_sha256, run.parse_run_id, "
            "run.request_fingerprint_sha256, run.output_fingerprint_sha256, "
            "run.landing_status, run.bytes_written, run.record_count, "
            "artifact.parent_artifact_id, artifact.parent_content_sha256 "
            "FROM landing.ingest_run AS run "
            "JOIN landing.evidence_artifact AS artifact "
            "ON artifact.artifact_id = run.artifact_id "
            "AND artifact.content_sha256 = run.content_sha256 "
            "WHERE run.run_id = %s",
            (run_id,),
        ).fetchone()

    @staticmethod
    def _artifact(connection: Any, artifact_id: str) -> EvidenceArtifact | None:
        row = connection.execute(
            "SELECT artifact_id, source_kind, source_locator, content_sha256, "
            "byte_size, acquired_at, run_id, parent_artifact_id, "
            "parent_content_sha256 FROM landing.evidence_artifact "
            "WHERE artifact_id = %s",
            (artifact_id,),
        ).fetchone()
        return EvidenceArtifact.model_validate(row) if row is not None else None

    @staticmethod
    def _receipt_from_row(row: dict[str, Any]) -> LandingReceipt:
        return LandingReceipt(
            run_id=row["run_id"],
            source_batch_id=row["source_batch_id"],
            artifact_id=row["artifact_id"],
            content_sha256=row["content_sha256"],
            bytes_written=row["bytes_written"],
            status=LandingStatus(row["landing_status"]),
            parse_run_id=row["parse_run_id"],
            record_count=row["record_count"],
            parent_artifact_id=row["parent_artifact_id"],
            parent_content_sha256=row["parent_content_sha256"],
            active_release_id=None,
        )

    @staticmethod
    def _assert_existing_run(
        row: dict[str, Any],
        *,
        request_fingerprint: str,
        output_fingerprint: str | None = None,
    ) -> None:
        if row["request_fingerprint_sha256"] != request_fingerprint:
            raise _integrity_error(
                "one landing run_id cannot identify different evidence or parser output"
            )
        if (
            output_fingerprint is not None
            and row["output_fingerprint_sha256"] != output_fingerprint
        ):
            raise _integrity_error(
                "one landing run_id cannot identify different evidence or parser output"
            )

    @staticmethod
    def _assert_lineage(connection: Any, artifact: EvidenceArtifact) -> None:
        if artifact.parent_artifact_id is not None:
            parent = connection.execute(
                "SELECT content_sha256 FROM landing.evidence_artifact "
                "WHERE artifact_id = %s",
                (artifact.parent_artifact_id,),
            ).fetchone()
            if parent is None:
                raise _integrity_error("parent artifact is not registered")
            if parent["content_sha256"] != artifact.parent_content_sha256:
                raise _integrity_error(
                    "parent content hash does not match the registered parent artifact"
                )
            if artifact.parent_artifact_id == artifact.artifact_id:
                raise _integrity_error("an artifact cannot be its own parent")

        rows = connection.execute(
            "SELECT artifact_id, source_kind, source_locator, content_sha256, "
            "byte_size, parent_artifact_id, parent_content_sha256 "
            "FROM landing.evidence_artifact "
            "WHERE artifact_id = %s OR "
            "(source_kind = %s AND source_locator = %s AND content_sha256 = %s)",
            (
                artifact.artifact_id,
                artifact.source_kind,
                artifact.source_locator,
                artifact.content_sha256,
            ),
        ).fetchall()
        for existing in rows:
            if (
                existing["artifact_id"] != artifact.artifact_id
                or existing["source_kind"] != artifact.source_kind
                or existing["source_locator"] != artifact.source_locator
                or existing["content_sha256"] != artifact.content_sha256
                or existing["byte_size"] != artifact.byte_size
            ):
                raise _integrity_error(
                    "registered artifact identity conflicts with existing evidence"
                )
            if (
                existing["parent_artifact_id"] != artifact.parent_artifact_id
                or existing["parent_content_sha256"] != artifact.parent_content_sha256
            ):
                raise _integrity_error(
                    "registered artifact lineage conflicts with the existing artifact"
                )

    def assert_admissible(
        self,
        *,
        run_id: str,
        request_fingerprint: str,
        artifact: EvidenceArtifact,
    ) -> None:
        with self._connection(write=False) as connection:
            existing = self._existing_run(connection, run_id)
            if existing is not None:
                self._assert_existing_run(
                    existing,
                    request_fingerprint=request_fingerprint,
                )
            self._assert_lineage(connection, artifact)

    def register(self, artifact: EvidenceArtifact) -> EvidenceArtifact:
        try:
            with self._connection(write=True) as connection:
                with connection.transaction():
                    connection.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (artifact.artifact_id,),
                    )
                    self._assert_lineage(connection, artifact)
                    connection.execute(
                        "INSERT INTO landing.evidence_artifact "
                        "(artifact_id, source_kind, source_locator, content_sha256, "
                        "byte_size, acquired_at, run_id, parent_artifact_id, "
                        "parent_content_sha256) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (artifact_id) DO NOTHING",
                        (
                            artifact.artifact_id,
                            artifact.source_kind,
                            artifact.source_locator,
                            artifact.content_sha256,
                            artifact.byte_size,
                            artifact.acquired_at,
                            artifact.run_id,
                            artifact.parent_artifact_id,
                            artifact.parent_content_sha256,
                        ),
                    )
                    self._assert_lineage(connection, artifact)
                    registered = self._artifact(connection, artifact.artifact_id)
                    if registered is None:
                        raise EvidenceLandingPersistenceError(
                            "PostgreSQL artifact registration was not retained"
                        )
            return registered
        except (EvidenceIntegrityError, EvidenceLandingPersistenceError):
            raise
        except psycopg.Error as exc:
            raise EvidenceLandingPersistenceError(
                "PostgreSQL artifact registration rolled back"
            ) from exc

    @staticmethod
    def _run_status(status: LandingStatus) -> str:
        if status is LandingStatus.accepted:
            return "succeeded"
        if status is LandingStatus.partial:
            return "partial"
        return "failed"

    def commit(self, prepared: PreparedLandingRun) -> LandingReceipt:
        try:
            with self._connection(write=True) as connection:
                with connection.transaction():
                    connection.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (prepared.receipt.run_id,),
                    )
                    existing = self._existing_run(
                        connection,
                        prepared.receipt.run_id,
                    )
                    if existing is not None:
                        self._assert_existing_run(
                            existing,
                            request_fingerprint=prepared.request_fingerprint,
                            output_fingerprint=prepared.output_fingerprint,
                        )
                        return self._receipt_from_row(existing)

                    self._assert_lineage(connection, prepared.artifact)
                    connection.execute(
                        "INSERT INTO landing.evidence_artifact "
                        "(artifact_id, source_kind, source_locator, content_sha256, "
                        "byte_size, acquired_at, run_id, parent_artifact_id, "
                        "parent_content_sha256) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (artifact_id) DO NOTHING",
                        (
                            prepared.artifact.artifact_id,
                            prepared.artifact.source_kind,
                            prepared.artifact.source_locator,
                            prepared.artifact.content_sha256,
                            prepared.artifact.byte_size,
                            prepared.artifact.acquired_at,
                            prepared.artifact.run_id,
                            prepared.artifact.parent_artifact_id,
                            prepared.artifact.parent_content_sha256,
                        ),
                    )
                    self._assert_lineage(connection, prepared.artifact)
                    connection.execute(
                        "INSERT INTO landing.parser_run "
                        "(parse_run_id, artifact_id, parser_name, parser_version, "
                        "schema_version, parser_options, run_status, started_at, "
                        "finished_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            prepared.receipt.parse_run_id,
                            prepared.artifact.artifact_id,
                            prepared.parser.parser_name,
                            prepared.parser.parser_version,
                            prepared.parser.schema_version,
                            Jsonb(prepared.parser.options),
                            self._run_status(prepared.receipt.status),
                            prepared.artifact.acquired_at,
                            prepared.artifact.acquired_at,
                        ),
                    )
                    for record_ordinal, record in enumerate(prepared.records):
                        connection.execute(
                            "INSERT INTO landing.source_record "
                            "(record_id, artifact_id, source_batch_id, record_locator, "
                            "parse_run_id, record_ordinal, parse_status, payload, parsed_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (
                                record.record_id,
                                record.artifact_id,
                                record.source_batch_id,
                                record.record_locator,
                                record.parse_run_id,
                                record_ordinal,
                                record.parse_status.value,
                                Jsonb(record.payload),
                                record.parsed_at,
                            ),
                        )
                        for error_ordinal, error in enumerate(record.errors):
                            connection.execute(
                                "INSERT INTO landing.source_error "
                                "(record_id, error_ordinal, error_code, error_kind, "
                                "message, field_path, recoverable) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                (
                                    record.record_id,
                                    error_ordinal,
                                    error.error_code,
                                    error.error_kind.value,
                                    error.message,
                                    error.field_path,
                                    error.recoverable,
                                ),
                            )
                    connection.execute(
                        "INSERT INTO landing.ingest_run "
                        "(run_id, source_batch_id, artifact_id, content_sha256, "
                        "parse_run_id, request_fingerprint_sha256, "
                        "output_fingerprint_sha256, landing_status, bytes_written, "
                        "record_count, observed_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            prepared.receipt.run_id,
                            prepared.receipt.source_batch_id,
                            prepared.receipt.artifact_id,
                            prepared.receipt.content_sha256,
                            prepared.receipt.parse_run_id,
                            prepared.request_fingerprint,
                            prepared.output_fingerprint,
                            prepared.receipt.status.value,
                            prepared.receipt.bytes_written,
                            prepared.receipt.record_count,
                            prepared.artifact.acquired_at,
                        ),
                    )
            return prepared.receipt
        except (EvidenceIntegrityError, EvidenceLandingPersistenceError):
            raise
        except psycopg.Error as exc:
            raise EvidenceLandingPersistenceError(
                "PostgreSQL landing commit rolled back"
            ) from exc

    def stream(self, source_batch_id: str) -> tuple[SourceRecord, ...]:
        with self._connection(write=False) as connection:
            rows = connection.execute(
                "SELECT record.record_id, record.artifact_id, "
                "record.source_batch_id, record.record_locator, record.parse_run_id, "
                "record.parse_status, record.payload, record.parsed_at, "
                "parser.parser_name, parser.parser_version, parser.schema_version, "
                "error.error_ordinal, error.error_code, error.error_kind, "
                "error.message, error.field_path, error.recoverable "
                "FROM landing.source_record AS record "
                "JOIN landing.parser_run AS parser "
                "ON parser.parse_run_id = record.parse_run_id "
                "AND parser.artifact_id = record.artifact_id "
                "JOIN landing.ingest_run AS run "
                "ON run.parse_run_id = record.parse_run_id "
                "LEFT JOIN landing.source_error AS error "
                "ON error.record_id = record.record_id "
                "WHERE record.source_batch_id = %s "
                "ORDER BY run.committed_at, run.run_id, record.record_ordinal, "
                "error.error_ordinal",
                (source_batch_id,),
            ).fetchall()

        records: list[SourceRecord] = []
        current_id: str | None = None
        current: dict[str, Any] | None = None
        current_errors: list[SourceError] = []
        for row in rows:
            if row["record_id"] != current_id:
                if current is not None:
                    records.append(self._source_record(current, tuple(current_errors)))
                current_id = row["record_id"]
                current = row
                current_errors = []
            if row["error_ordinal"] is not None:
                current_errors.append(
                    SourceError(
                        error_code=row["error_code"],
                        error_kind=row["error_kind"],
                        message=row["message"],
                        field_path=row["field_path"],
                        recoverable=row["recoverable"],
                    )
                )
        if current is not None:
            records.append(self._source_record(current, tuple(current_errors)))
        return tuple(records)

    @staticmethod
    def _source_record(
        row: dict[str, Any],
        errors: tuple[SourceError, ...],
    ) -> SourceRecord:
        return SourceRecord(
            record_id=row["record_id"],
            artifact_id=row["artifact_id"],
            source_batch_id=row["source_batch_id"],
            record_locator=row["record_locator"],
            parser_name=row["parser_name"],
            parser_version=row["parser_version"],
            schema_version=row["schema_version"],
            parse_run_id=row["parse_run_id"],
            parse_status=ParseStatus(row["parse_status"]),
            payload=row["payload"],
            errors=errors,
            parsed_at=row["parsed_at"],
        )


def create_postgres_evidence_landing(
    *,
    database_url: str,
    expected_database: str,
    target_kind: str,
    backup_gate_root: Path,
) -> EvidenceLanding:
    """Create a gate-checked, explicit-target durable landing composition."""
    require_accepted_backup_gate(backup_gate_root)
    accepted_root = backup_gate_root.resolve(strict=False)
    target = resolve_destructive_database_target(
        _ExplicitTargetConfig(
            database_url=database_url,
            expected_database=expected_database,
            target_kind=target_kind,
        ),
        {},
    )
    repository = PostgresLandingRepository(
        target=target,
        backup_gate_root=accepted_root,
    )
    repository.verify_ready()
    return EvidenceLandingService(
        repository=repository,
        adapters=default_source_adapters(),
    )


__all__ = ["PostgresLandingRepository", "create_postgres_evidence_landing"]
