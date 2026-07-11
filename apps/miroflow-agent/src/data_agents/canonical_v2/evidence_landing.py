"""Immutable, storage-independent evidence landing core.

Task 4.2 provides an ephemeral repository composition. Durable PostgreSQL persistence is a separate
adapter owned by Task 4.3; callers depend only on :class:`EvidenceLanding`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import stat
from threading import RLock
from typing import Protocol

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from .contracts import (
    ContractModel,
    EvidenceArtifact,
    NonEmptyStr,
    ParseStatus,
    Sha256,
    SourceError,
    SourceRecord,
)


class EvidenceLandingError(RuntimeError):
    """Base error raised before invalid evidence becomes stream-visible."""


class EvidenceIntegrityError(EvidenceLandingError):
    """Evidence bytes or lineage do not match their declared identity."""


class EvidenceLandingPersistenceError(EvidenceLandingError):
    """A durable landing transaction failed before becoming visible."""


class SourceAdapterError(EvidenceLandingError):
    """A configured source adapter cannot safely interpret the supplied input."""


class UnverifiedSourceError(SourceAdapterError):
    """An adapter was asked to consume an original or otherwise unverified source."""


class LandingStatus(str, Enum):
    accepted = "accepted"
    partial = "partial"
    quarantined = "quarantined"


class ParserReference(ContractModel):
    parser_name: NonEmptyStr
    parser_version: NonEmptyStr
    schema_version: NonEmptyStr
    options: dict[NonEmptyStr, JsonValue] = Field(default_factory=dict)


def _default_parser_reference() -> ParserReference:
    return ParserReference(
        parser_name="historical_jsonl",
        parser_version="v1",
        schema_version="historical-record-v1",
    )


class IngestEvidenceRequest(ContractModel):
    run_id: NonEmptyStr
    source_batch_id: NonEmptyStr
    source_kind: NonEmptyStr
    source_locator: NonEmptyStr
    content: bytes
    observed_at: AwareDatetime
    expected_content_sha256: Sha256 | None = None
    parser: ParserReference = Field(default_factory=_default_parser_reference)
    parent_artifact_id: NonEmptyStr | None = None
    parent_content_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def validate_parent_pair(self) -> IngestEvidenceRequest:
        if (self.parent_artifact_id is None) != (self.parent_content_sha256 is None):
            raise ValueError(
                "parent_artifact_id and parent_content_sha256 must be provided together"
            )
        return self


class RegisterArtifactRequest(ContractModel):
    """Register the manifest of a local evidence file without loading it for parsing."""

    run_id: NonEmptyStr
    source_kind: NonEmptyStr
    source_locator: NonEmptyStr
    content_path: Path
    observed_at: AwareDatetime
    expected_content_sha256: Sha256
    expected_byte_size: int = Field(ge=0)
    parent_artifact_id: NonEmptyStr | None = None
    parent_content_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def validate_parent_pair(self) -> RegisterArtifactRequest:
        if (self.parent_artifact_id is None) != (self.parent_content_sha256 is None):
            raise ValueError(
                "parent_artifact_id and parent_content_sha256 must be provided together"
            )
        return self


class LandingReceipt(ContractModel):
    run_id: NonEmptyStr
    source_batch_id: NonEmptyStr
    artifact_id: NonEmptyStr
    content_sha256: Sha256
    bytes_written: int = Field(ge=0)
    status: LandingStatus
    parse_run_id: NonEmptyStr | None = None
    record_count: int = Field(default=0, ge=0)
    parent_artifact_id: NonEmptyStr | None = None
    parent_content_sha256: Sha256 | None = None
    active_release_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_no_active_release_effect(self) -> LandingReceipt:
        if self.active_release_id is not None:
            raise ValueError("evidence landing cannot change an active release")
        if (self.parent_artifact_id is None) != (self.parent_content_sha256 is None):
            raise ValueError("landing receipt parent identity must be complete")
        return self


class ParsedRecordDraft(ContractModel):
    record_locator: NonEmptyStr
    parse_status: ParseStatus
    payload: dict[NonEmptyStr, JsonValue]
    errors: tuple[SourceError, ...] = ()

    @model_validator(mode="after")
    def validate_outcome(self) -> ParsedRecordDraft:
        if self.parse_status is not ParseStatus.parsed and not self.errors:
            raise ValueError("a non-parsed record draft requires a typed error")
        return self


@dataclass(frozen=True, slots=True)
class AdapterInput:
    content: bytes
    source_kind: str
    source_locator: str
    parser: ParserReference


class SourceAdapter(Protocol):
    parser_name: str

    def validate_source(self, value: AdapterInput) -> None:
        """Reject a source kind before parsing when its provenance is unsafe."""
        ...

    def parse(self, value: AdapterInput) -> tuple[ParsedRecordDraft, ...]:
        """Convert immutable bytes into storage-independent record drafts."""
        ...


@dataclass(frozen=True, slots=True)
class PreparedLandingRun:
    request_fingerprint: str
    output_fingerprint: str
    artifact: EvidenceArtifact
    parser: ParserReference
    receipt: LandingReceipt
    records: tuple[SourceRecord, ...]


class LandingRepository(Protocol):
    def register(self, artifact: EvidenceArtifact) -> EvidenceArtifact:
        """Atomically retain or return one content-addressed artifact manifest."""
        ...

    def assert_admissible(
        self,
        *,
        run_id: str,
        request_fingerprint: str,
        artifact: EvidenceArtifact,
    ) -> None:
        """Reject known run or lineage conflicts before parsing."""
        ...

    def commit(self, prepared: PreparedLandingRun) -> LandingReceipt:
        """Atomically retain or idempotently return one complete prepared run."""
        ...

    def stream(self, source_batch_id: str) -> tuple[SourceRecord, ...]:
        """Reconstruct detached records in committed parser-output order."""
        ...


class EvidenceLanding(ABC):
    """Deep public seam for immutable evidence registration and replay."""

    @abstractmethod
    def register_artifact(self, request: RegisterArtifactRequest) -> EvidenceArtifact:
        """Hash a file as a stream and retain its immutable evidence manifest."""

    @abstractmethod
    def ingest(self, request: IngestEvidenceRequest) -> LandingReceipt:
        """Verify, parse, and atomically make one evidence run visible."""

    @abstractmethod
    def stream(self, source_batch_id: str) -> tuple[SourceRecord, ...]:
        """Return immutable record snapshots for all retained runs in a batch."""


@dataclass(frozen=True, slots=True)
class _CommittedRun:
    request_fingerprint: str
    fingerprint: str
    receipt: LandingReceipt
    records: tuple[SourceRecord, ...]


class _EphemeralLandingRepository:
    """Atomic in-memory adapter for local conformance and unit use."""

    def __init__(self) -> None:
        self.lock = RLock()
        self.artifacts: dict[str, EvidenceArtifact] = {}
        self.artifact_ids_by_source: dict[tuple[str, str, str], str] = {}
        self.runs_by_run_id: dict[str, _CommittedRun] = {}
        self.records_by_batch: dict[str, list[SourceRecord]] = {}

    def register(self, artifact: EvidenceArtifact) -> EvidenceArtifact:
        with self.lock:
            existing = _registered_artifact_for_lineage(self, artifact)
            if existing is not None:
                return existing
            self.artifacts[artifact.artifact_id] = artifact
            self.artifact_ids_by_source[_artifact_key(artifact)] = artifact.artifact_id
            return artifact

    def assert_admissible(
        self,
        *,
        run_id: str,
        request_fingerprint: str,
        artifact: EvidenceArtifact,
    ) -> None:
        with self.lock:
            previous_run = self.runs_by_run_id.get(run_id)
            if (
                previous_run is not None
                and previous_run.request_fingerprint != request_fingerprint
            ):
                raise EvidenceIntegrityError(
                    "one landing run_id cannot identify different evidence or parser output"
                )
            _registered_artifact_for_lineage(self, artifact)

    def commit(self, prepared: PreparedLandingRun) -> LandingReceipt:
        with self.lock:
            previous_run = self.runs_by_run_id.get(prepared.receipt.run_id)
            if previous_run is not None:
                if previous_run.fingerprint != prepared.output_fingerprint:
                    raise EvidenceIntegrityError(
                        "one landing run_id cannot identify different evidence or parser output"
                    )
                return previous_run.receipt

            artifact = _registered_artifact_for_lineage(self, prepared.artifact)
            if artifact is None:
                artifact = prepared.artifact
                self.artifacts[artifact.artifact_id] = artifact
                self.artifact_ids_by_source[_artifact_key(artifact)] = (
                    artifact.artifact_id
                )
            self.records_by_batch.setdefault(
                prepared.receipt.source_batch_id, []
            ).extend(prepared.records)
            self.runs_by_run_id[prepared.receipt.run_id] = _CommittedRun(
                request_fingerprint=prepared.request_fingerprint,
                fingerprint=prepared.output_fingerprint,
                receipt=prepared.receipt,
                records=prepared.records,
            )
            return prepared.receipt

    def stream(self, source_batch_id: str) -> tuple[SourceRecord, ...]:
        with self.lock:
            return tuple(
                record.model_copy(deep=True)
                for record in self.records_by_batch.get(source_batch_id, ())
            )


def _stable_id(prefix: str, *parts: str) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()
    return f"{prefix}:sha256:{hashlib.sha256(encoded).hexdigest()}"


def _record_fingerprint(draft: ParsedRecordDraft) -> str:
    payload = draft.model_dump(mode="json")
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _request_fingerprint(
    request: IngestEvidenceRequest,
    *,
    artifact_id: str,
    content_sha256: str,
) -> str:
    payload = {
        "artifact_id": artifact_id,
        "content_sha256": content_sha256,
        "source_batch_id": request.source_batch_id,
        "observed_at": request.observed_at.astimezone(timezone.utc).isoformat(),
        "parent_artifact_id": request.parent_artifact_id,
        "parent_content_sha256": request.parent_content_sha256,
        "parser": request.parser.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _run_fingerprint(
    request_fingerprint: str,
    drafts: tuple[ParsedRecordDraft, ...],
) -> str:
    payload = {
        "request_fingerprint": request_fingerprint,
        "records": [_record_fingerprint(draft) for draft in drafts],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _landing_status(records: tuple[SourceRecord, ...]) -> LandingStatus:
    statuses = {record.parse_status for record in records}
    if not statuses or statuses == {ParseStatus.parsed}:
        return LandingStatus.accepted
    if statuses <= {
        ParseStatus.quarantined,
        ParseStatus.unsupported,
        ParseStatus.corrupt,
    }:
        return LandingStatus.quarantined
    return LandingStatus.partial


def _artifact_key(artifact: EvidenceArtifact) -> tuple[str, str, str]:
    return (
        artifact.source_kind,
        artifact.source_locator,
        artifact.content_sha256,
    )


def _registered_artifact_for_lineage(
    repository: _EphemeralLandingRepository,
    artifact: EvidenceArtifact,
) -> EvidenceArtifact | None:
    if artifact.parent_artifact_id is not None:
        parent = repository.artifacts.get(artifact.parent_artifact_id)
        if parent is None:
            raise EvidenceIntegrityError("parent artifact is not registered")
        if parent.content_sha256 != artifact.parent_content_sha256:
            raise EvidenceIntegrityError(
                "parent content hash does not match the registered parent artifact"
            )
        if parent.artifact_id == artifact.artifact_id:
            raise EvidenceIntegrityError("an artifact cannot be its own parent")

    existing_artifact_id = repository.artifact_ids_by_source.get(
        _artifact_key(artifact)
    )
    if existing_artifact_id is None:
        return None
    existing_artifact = repository.artifacts[existing_artifact_id]
    if (
        existing_artifact.parent_artifact_id != artifact.parent_artifact_id
        or existing_artifact.parent_content_sha256 != artifact.parent_content_sha256
    ):
        raise EvidenceIntegrityError(
            "registered artifact lineage conflicts with the existing artifact"
        )
    return existing_artifact


class EvidenceLandingService(EvidenceLanding):
    """Verify and atomically retain evidence using injected format adapters."""

    def __init__(
        self,
        *,
        repository: LandingRepository,
        adapters: Iterable[SourceAdapter],
    ) -> None:
        self._repository = repository
        self._adapters: dict[str, SourceAdapter] = {}
        for adapter in adapters:
            if adapter.parser_name in self._adapters:
                raise ValueError(f"duplicate source adapter: {adapter.parser_name}")
            self._adapters[adapter.parser_name] = adapter

    def register_artifact(self, request: RegisterArtifactRequest) -> EvidenceArtifact:
        hasher = hashlib.sha256()
        byte_size = 0
        try:
            with request.content_path.open("rb") as content_stream:
                before = os.fstat(content_stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise EvidenceIntegrityError(
                        "artifact registration path is not a regular file"
                    )
                while chunk := content_stream.read(1024 * 1024):
                    hasher.update(chunk)
                    byte_size += len(chunk)
                after = os.fstat(content_stream.fileno())
        except EvidenceIntegrityError:
            raise
        except OSError as exc:
            raise EvidenceIntegrityError(
                "artifact registration file is missing or unreadable"
            ) from exc
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise EvidenceIntegrityError(
                "artifact registration file changed while hashing"
            )
        if byte_size != request.expected_byte_size:
            raise EvidenceIntegrityError(
                "artifact size mismatch: supplied file does not match the registered identity"
            )
        content_sha256 = hasher.hexdigest()
        if content_sha256 != request.expected_content_sha256:
            raise EvidenceIntegrityError(
                "artifact hash mismatch: supplied file does not match the registered identity"
            )
        artifact = EvidenceArtifact(
            artifact_id=_stable_id(
                "artifact",
                request.source_kind,
                request.source_locator,
                content_sha256,
            ),
            source_kind=request.source_kind,
            source_locator=request.source_locator,
            content_sha256=content_sha256,
            byte_size=byte_size,
            acquired_at=request.observed_at,
            run_id=request.run_id,
            parent_artifact_id=request.parent_artifact_id,
            parent_content_sha256=request.parent_content_sha256,
        )
        return self._repository.register(artifact)

    def ingest(self, request: IngestEvidenceRequest) -> LandingReceipt:
        content_sha256 = hashlib.sha256(request.content).hexdigest()
        if (
            request.expected_content_sha256 is not None
            and request.expected_content_sha256 != content_sha256
        ):
            raise EvidenceIntegrityError(
                "content hash mismatch: supplied bytes do not match the registered identity"
            )
        adapter = self._adapters.get(request.parser.parser_name)
        if adapter is None:
            raise SourceAdapterError(
                f"no source adapter is registered for parser {request.parser.parser_name}"
            )
        adapter_input = AdapterInput(
            content=request.content,
            source_kind=request.source_kind,
            source_locator=request.source_locator,
            parser=request.parser,
        )
        adapter.validate_source(adapter_input)
        artifact_id = _stable_id(
            "artifact",
            request.source_kind,
            request.source_locator,
            content_sha256,
        )
        artifact = EvidenceArtifact(
            artifact_id=artifact_id,
            source_kind=request.source_kind,
            source_locator=request.source_locator,
            content_sha256=content_sha256,
            byte_size=len(request.content),
            acquired_at=request.observed_at,
            run_id=request.run_id,
            parent_artifact_id=request.parent_artifact_id,
            parent_content_sha256=request.parent_content_sha256,
        )
        request_fingerprint = _request_fingerprint(
            request,
            artifact_id=artifact_id,
            content_sha256=content_sha256,
        )
        self._repository.assert_admissible(
            run_id=request.run_id,
            request_fingerprint=request_fingerprint,
            artifact=artifact,
        )

        drafts = tuple(adapter.parse(adapter_input))
        locators = tuple(draft.record_locator for draft in drafts)
        if len(locators) != len(set(locators)):
            raise SourceAdapterError(
                "one parser run cannot emit duplicate record locators"
            )

        parse_run_id = _stable_id(
            "parse-run",
            request.run_id,
            request.source_batch_id,
            artifact_id,
            request.parser.parser_name,
            request.parser.parser_version,
            request.parser.schema_version,
        )
        output_fingerprint = _run_fingerprint(request_fingerprint, drafts)
        records = tuple(
            SourceRecord(
                record_id=_stable_id(
                    "record",
                    parse_run_id,
                    draft.record_locator,
                    _record_fingerprint(draft),
                ),
                artifact_id=artifact.artifact_id,
                source_batch_id=request.source_batch_id,
                record_locator=draft.record_locator,
                parser_name=request.parser.parser_name,
                parser_version=request.parser.parser_version,
                schema_version=request.parser.schema_version,
                parse_run_id=parse_run_id,
                parse_status=draft.parse_status,
                payload=draft.payload,
                errors=draft.errors,
                parsed_at=request.observed_at,
            )
            for draft in drafts
        )
        receipt = LandingReceipt(
            run_id=request.run_id,
            source_batch_id=request.source_batch_id,
            artifact_id=artifact.artifact_id,
            content_sha256=content_sha256,
            bytes_written=len(request.content),
            status=_landing_status(records),
            parse_run_id=parse_run_id,
            record_count=len(records),
            parent_artifact_id=request.parent_artifact_id,
            parent_content_sha256=request.parent_content_sha256,
            active_release_id=None,
        )
        return self._repository.commit(
            PreparedLandingRun(
                request_fingerprint=request_fingerprint,
                output_fingerprint=output_fingerprint,
                artifact=artifact,
                parser=request.parser,
                receipt=receipt,
                records=records,
            )
        )

    def stream(self, source_batch_id: str) -> tuple[SourceRecord, ...]:
        return self._repository.stream(source_batch_id)


def create_ephemeral_evidence_landing() -> EvidenceLanding:
    """Compose the real landing core with deterministic in-process storage/adapters."""
    from .evidence_adapters import default_source_adapters

    return EvidenceLandingService(
        repository=_EphemeralLandingRepository(),
        adapters=default_source_adapters(),
    )


__all__ = [
    "EvidenceIntegrityError",
    "EvidenceLanding",
    "EvidenceLandingError",
    "EvidenceLandingPersistenceError",
    "IngestEvidenceRequest",
    "LandingReceipt",
    "LandingStatus",
    "ParsedRecordDraft",
    "ParserReference",
    "RegisterArtifactRequest",
    "SourceAdapterError",
    "SourceRecord",
    "UnverifiedSourceError",
    "create_ephemeral_evidence_landing",
]
