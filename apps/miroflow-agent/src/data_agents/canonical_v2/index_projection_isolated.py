"""Guarded local adapters for one isolated Canonical V2 full index build."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Literal, Protocol, cast
import warnings

from pydantic import Field, JsonValue, field_validator, model_validator

from .contracts import ContractModel, NonEmptyStr, Sha256
from .index_projection import (
    IndexProjectionActualState,
    IndexProjectionBuilder,
    IndexProjectionIntegrityError,
    IndexProjectionManifest,
    IndexProjectionMaterializationReceipt,
    IndexProjectionPoint,
    IndexProjectionRequest,
    LookupProjectionDocument,
    LookupProjectionManifest,
    build_index_projection_manifests,
    build_lookup_projection_manifests,
)
from .rebuild_write_gate import BackupGateReceipt, require_accepted_backup_gate


_MARKER_NAME = ".canonical-v2-isolated-index-target.json"
_MARKER_SCHEMA_VERSION = "canonical-v2-isolated-index-target-v1"
_MILVUS_FILENAME = "milvus.db"
_LOOKUP_FILENAME = "lookup.sqlite3"
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{1,}|[\u3400-\u4DBF\u4E00-\u9FFF]")


class IsolatedIndexTargetSafetyError(RuntimeError):
    """The local index target is missing an explicit, safe identity."""


class EmbeddingAdapter(Protocol):
    model_id: str
    dimension: int

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class RecordedEmbeddingAdapter(ContractModel):
    """Deterministic recorded-fake embedding used by isolated acceptance."""

    model_id: NonEmptyStr
    dimension: int = Field(ge=8, le=4096)

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._embed(text) for text in texts)

    def _embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimension
        for token in _TOKEN_RE.findall(text.casefold()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        if not any(vector):
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] = 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return tuple(value / norm for value in vector)


class IsolatedIndexTarget(ContractModel):
    root: Path
    target_id: NonEmptyStr
    release_id: NonEmptyStr
    target_kind: Literal["isolated-candidate"] = "isolated-candidate"
    forbidden_milvus_paths: tuple[Path, ...] = Field(min_length=1)
    marker_sha256: Sha256

    @field_validator("root")
    @classmethod
    def validate_absolute_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("isolated index target root must be absolute")
        return value

    @field_validator("forbidden_milvus_paths")
    @classmethod
    def validate_forbidden_paths(cls, values: tuple[Path, ...]) -> tuple[Path, ...]:
        if any(not value.is_absolute() for value in values):
            raise ValueError("forbidden Milvus paths must be absolute")
        normalized = tuple(sorted({value.resolve(strict=False) for value in values}))
        if values != normalized:
            raise ValueError("forbidden Milvus paths must be sorted and unique")
        return values

    @model_validator(mode="after")
    def validate_target_paths(self) -> IsolatedIndexTarget:
        target_milvus = (self.root / _MILVUS_FILENAME).resolve(strict=False)
        if self.root.resolve(strict=False) in self.forbidden_milvus_paths or (
            target_milvus in self.forbidden_milvus_paths
        ):
            raise ValueError("isolated target resolves to a forbidden original path")
        return self


class IsolatedIndexSnapshot(ContractModel):
    """One fully enumerated physical snapshot of a marked isolated target."""

    receipt: IndexProjectionMaterializationReceipt
    points: tuple[IndexProjectionPoint, ...]
    lookup_documents: tuple[LookupProjectionDocument, ...]


def prepare_isolated_index_target(
    *,
    root: Path,
    target_id: str,
    release_id: str,
    backup_gate_root: Path,
    forbidden_milvus_paths: tuple[Path, ...],
) -> IsolatedIndexTarget:
    """Create only the marker for a fresh explicit target after the S2B gate."""

    if not root.is_absolute():
        raise IsolatedIndexTargetSafetyError(
            "isolated index target root must be an explicit absolute path"
        )
    if any(not path.is_absolute() for path in forbidden_milvus_paths):
        raise IsolatedIndexTargetSafetyError(
            "forbidden Milvus identities must be explicit absolute paths"
        )
    resolved_forbidden = tuple(
        sorted({path.resolve(strict=False) for path in forbidden_milvus_paths})
    )
    resolved_root = root.resolve(strict=False)
    target_milvus = (resolved_root / _MILVUS_FILENAME).resolve(strict=False)
    if resolved_root in resolved_forbidden or target_milvus in resolved_forbidden:
        raise IsolatedIndexTargetSafetyError(
            "refusing to prepare the forbidden original Milvus target"
        )
    if root.exists() or root.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "isolated index target already exists; a fresh target is required"
        )
    parent = root.parent
    if not parent.is_dir() or parent.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "isolated index target parent must be an existing non-symlink directory"
        )
    marker = _marker_document(
        root=resolved_root,
        target_id=target_id,
        release_id=release_id,
        forbidden_milvus_paths=resolved_forbidden,
    )
    marker_bytes = _canonical_json_bytes(cast(JsonValue, marker)) + b"\n"
    target = IsolatedIndexTarget(
        root=resolved_root,
        target_id=target_id,
        release_id=release_id,
        forbidden_milvus_paths=resolved_forbidden,
        marker_sha256=_sha256_bytes(marker_bytes),
    )
    require_accepted_backup_gate(backup_gate_root)
    root.mkdir(mode=0o700)
    marker_path = root / _MARKER_NAME
    with marker_path.open("xb") as stream:
        stream.write(marker_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    return target


def create_isolated_index_projection_builder(
    *,
    target: IsolatedIndexTarget,
    backup_gate_root: Path,
    embedding_adapter: EmbeddingAdapter,
    clock: Callable[[], datetime],
) -> IndexProjectionBuilder:
    """Create a builder without opening either physical target."""

    _validate_target_marker(target)
    require_accepted_backup_gate(backup_gate_root)
    if embedding_adapter.dimension <= 0:
        raise IsolatedIndexTargetSafetyError(
            "embedding adapter dimension must be positive"
        )
    return IndexProjectionBuilder(
        _IsolatedIndexMaterializer(
            target=target,
            backup_gate_root=backup_gate_root.resolve(strict=False),
            embedding_adapter=embedding_adapter,
            clock=clock,
        )
    )


class _IsolatedIndexMaterializer:
    def __init__(
        self,
        *,
        target: IsolatedIndexTarget,
        backup_gate_root: Path,
        embedding_adapter: EmbeddingAdapter,
        clock: Callable[[], datetime],
    ) -> None:
        self._target = target
        self._backup_gate_root = backup_gate_root
        self._embedding_adapter = embedding_adapter
        self._clock = clock
        self._last_receipt: IndexProjectionMaterializationReceipt | None = None

    @property
    def last_receipt(self) -> IndexProjectionMaterializationReceipt | None:
        return self._last_receipt

    def materialize(
        self,
        *,
        request: IndexProjectionRequest,
        points: tuple[IndexProjectionPoint, ...],
        lookup_documents: tuple[LookupProjectionDocument, ...],
        expected_index_projections: tuple[IndexProjectionManifest, ...],
        expected_lookup_projections: tuple[LookupProjectionManifest, ...],
    ) -> IndexProjectionActualState:
        if request.candidate_projection_result.release_id != self._target.release_id:
            raise IsolatedIndexTargetSafetyError(
                "isolated target release differs from the requested release"
            )
        if request.build_mode != "full" or not all(
            item.full_rebuild
            for item in (*expected_index_projections, *expected_lookup_projections)
        ):
            raise IsolatedIndexTargetSafetyError(
                "isolated Task 7.5 adapter accepts only a complete full rebuild"
            )
        if request.embedding_model != self._embedding_adapter.model_id:
            raise IsolatedIndexTargetSafetyError(
                "embedding adapter model identity differs from the request"
            )
        _validate_target_marker(self._target)
        gate_receipt = require_accepted_backup_gate(self._backup_gate_root)
        milvus_path = self._target.root / _MILVUS_FILENAME
        lookup_path = self._target.root / _LOOKUP_FILENAME
        if milvus_path.is_symlink() or lookup_path.is_symlink():
            raise IsolatedIndexTargetSafetyError(
                "isolated physical targets cannot be symlinks"
            )
        if milvus_path.exists() or lookup_path.exists():
            raise IsolatedIndexTargetSafetyError(
                "isolated full rebuild requires fresh physical targets"
            )
        client = _open_milvus_client(milvus_path)
        try:
            gate_receipt = require_accepted_backup_gate(self._backup_gate_root)
            _validate_target_marker(self._target)
            _write_lookup_projection(
                lookup_path,
                release_id=self._target.release_id,
                documents=lookup_documents,
                manifests=expected_lookup_projections,
            )
            collection_name = _collection_name(self._target, request)
            _write_milvus_projection(
                client,
                collection_name=collection_name,
                points=points,
                embedding_adapter=self._embedding_adapter,
            )
            read_points = _read_points_with_client(
                client,
                collection_name=collection_name,
                point_ids=tuple(item.point_id for item in points),
                embedding_adapter=self._embedding_adapter,
            )
            read_documents = _read_lookup_documents_from_path(lookup_path)
            stored_lookup_manifests = _read_lookup_manifests_from_path(lookup_path)
            if read_points != points or read_documents != lookup_documents:
                raise IndexProjectionIntegrityError(
                    "isolated lookup/vector point readback differs from written content"
                )
            actual_index = build_index_projection_manifests(
                request=request,
                points=read_points,
                full_rebuild=True,
            )
            actual_lookup = build_lookup_projection_manifests(
                request=request,
                documents=read_documents,
                full_rebuild=True,
            )
            if (
                actual_index != expected_index_projections
                or actual_lookup != expected_lookup_projections
                or stored_lookup_manifests != expected_lookup_projections
            ):
                raise IndexProjectionIntegrityError(
                    "isolated lookup/vector manifest readback differs"
                )
            _write_build_metadata(
                lookup_path,
                collection_name=collection_name,
            )
            receipt = _build_receipt(
                target=self._target,
                points=read_points,
                lookup_documents=read_documents,
                index_projections=actual_index,
                lookup_projections=actual_lookup,
                gate_receipt=gate_receipt,
                built_at=self._clock(),
            )
            _write_receipt(lookup_path, receipt)
            self._last_receipt = receipt
            return IndexProjectionActualState(
                index_projections=actual_index,
                lookup_projections=actual_lookup,
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def read_isolated_lookup_documents(
    target: IsolatedIndexTarget,
) -> tuple[LookupProjectionDocument, ...]:
    _validate_target_marker(target)
    lookup_path = target.root / _LOOKUP_FILENAME
    receipt = _read_receipt(lookup_path)
    if receipt.release_id != target.release_id or receipt.target_id != target.target_id:
        raise IndexProjectionIntegrityError(
            "isolated lookup receipt differs from the marked target"
        )
    documents = _read_lookup_documents_from_path(lookup_path)
    manifests = _read_lookup_manifests_from_path(lookup_path)
    if any(document.release_id != target.release_id for document in documents):
        raise IndexProjectionIntegrityError(
            "isolated lookup readback contains a cross-release document"
        )
    if (
        tuple(sorted(item.document_id for item in documents))
        != receipt.lookup_document_ids
        or manifests != receipt.lookup_projections
    ):
        raise IndexProjectionIntegrityError(
            "isolated lookup content differs from the successful receipt"
        )
    return documents


def read_isolated_index_points(
    target: IsolatedIndexTarget,
) -> tuple[IndexProjectionPoint, ...]:
    _validate_target_marker(target)
    lookup_path = target.root / _LOOKUP_FILENAME
    receipt = _read_receipt(lookup_path)
    if receipt.release_id != target.release_id or receipt.target_id != target.target_id:
        raise IndexProjectionIntegrityError(
            "isolated index receipt differs from the marked target"
        )
    collection_name = _read_collection_name(
        lookup_path,
        expected_release_id=target.release_id,
    )
    milvus_path = target.root / _MILVUS_FILENAME
    if not milvus_path.is_file() or milvus_path.is_symlink():
        raise IndexProjectionIntegrityError(
            "isolated Milvus store is missing or unsafe"
        )
    client = _open_milvus_client(milvus_path)
    try:
        return _read_points_with_client(
            client,
            collection_name=collection_name,
            point_ids=receipt.point_ids,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def audit_isolated_index_snapshot(
    target: IsolatedIndexTarget,
    *,
    embedding_adapter: EmbeddingAdapter,
) -> IsolatedIndexSnapshot:
    """Read and validate the complete physical inventory, including extra points."""

    _validate_target_marker(target)
    if embedding_adapter.dimension <= 0:
        raise IsolatedIndexTargetSafetyError(
            "embedding adapter dimension must be positive"
        )
    lookup_path = target.root / _LOOKUP_FILENAME
    receipt = _read_receipt(lookup_path)
    if receipt.release_id != target.release_id or receipt.target_id != target.target_id:
        raise IndexProjectionIntegrityError(
            "isolated index receipt differs from the marked target"
        )
    if any(
        manifest.release_id != target.release_id
        or manifest.embedding_model != embedding_adapter.model_id
        for manifest in receipt.index_projections
    ) or any(
        manifest.release_id != target.release_id
        for manifest in receipt.lookup_projections
    ):
        raise IndexProjectionIntegrityError(
            "isolated receipt projection identity differs from the marked target"
        )
    documents = _read_lookup_documents_from_path(lookup_path)
    lookup_manifests = _read_lookup_manifests_from_path(lookup_path)
    if any(document.release_id != target.release_id for document in documents):
        raise IndexProjectionIntegrityError(
            "isolated lookup readback contains a cross-release document"
        )
    if (
        tuple(sorted(document.document_id for document in documents))
        != receipt.lookup_document_ids
        or lookup_manifests != receipt.lookup_projections
    ):
        raise IndexProjectionIntegrityError(
            "isolated lookup content differs from the successful receipt"
        )

    collection_name = _read_collection_name(
        lookup_path,
        expected_release_id=target.release_id,
    )
    milvus_path = target.root / _MILVUS_FILENAME
    if not milvus_path.is_file() or milvus_path.is_symlink():
        raise IndexProjectionIntegrityError(
            "isolated Milvus store is missing or unsafe"
        )
    client = _open_milvus_client(milvus_path)
    try:
        collections = tuple(sorted(client.list_collections()))
        if collections != (collection_name,):
            raise IndexProjectionIntegrityError(
                "isolated target must contain exactly its recorded Milvus collection"
            )
        points = _read_all_points_with_client(
            client,
            collection_name=collection_name,
            embedding_adapter=embedding_adapter,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    return IsolatedIndexSnapshot(
        receipt=receipt,
        points=points,
        lookup_documents=documents,
    )


def _marker_document(
    *,
    root: Path,
    target_id: str,
    release_id: str,
    forbidden_milvus_paths: tuple[Path, ...],
) -> dict[str, JsonValue]:
    return {
        "schema_version": _MARKER_SCHEMA_VERSION,
        "root": str(root),
        "target_id": target_id,
        "release_id": release_id,
        "target_kind": "isolated-candidate",
        "forbidden_milvus_paths": [str(path) for path in forbidden_milvus_paths],
    }


def _validate_target_marker(target: IsolatedIndexTarget) -> None:
    if not target.root.is_absolute():
        raise IsolatedIndexTargetSafetyError("isolated target root must be absolute")
    if not target.root.is_dir() or target.root.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "isolated target root is missing or is a symlink"
        )
    marker_path = target.root / _MARKER_NAME
    if not marker_path.is_file() or marker_path.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "isolated target marker is missing or unsafe"
        )
    try:
        marker_bytes = marker_path.read_bytes()
    except OSError as exc:
        raise IsolatedIndexTargetSafetyError(
            "isolated target marker is unreadable"
        ) from exc
    if _sha256_bytes(marker_bytes) != target.marker_sha256:
        raise IsolatedIndexTargetSafetyError("isolated target marker hash differs")
    try:
        marker = json.loads(marker_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IsolatedIndexTargetSafetyError(
            "isolated target marker is invalid JSON"
        ) from exc
    expected = _marker_document(
        root=target.root,
        target_id=target.target_id,
        release_id=target.release_id,
        forbidden_milvus_paths=target.forbidden_milvus_paths,
    )
    if marker != expected:
        raise IsolatedIndexTargetSafetyError("isolated target marker identity differs")
    milvus_path = (target.root / _MILVUS_FILENAME).resolve(strict=False)
    unresolved_milvus_path = target.root / _MILVUS_FILENAME
    if unresolved_milvus_path.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "isolated Milvus target cannot be a symlink"
        )
    for forbidden in target.forbidden_milvus_paths:
        if milvus_path == forbidden:
            raise IsolatedIndexTargetSafetyError(
                "isolated target resolves to the forbidden original Milvus"
            )
        if milvus_path.exists() and forbidden.exists():
            try:
                same_file = os.path.samefile(milvus_path, forbidden)
            except OSError:
                same_file = False
            if same_file:
                raise IsolatedIndexTargetSafetyError(
                    "isolated target shares the original Milvus inode"
                )


def _open_milvus_client(path: Path) -> Any:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="milvus_lite")
        from pymilvus.milvus_client.milvus_client import MilvusClient

        return MilvusClient(uri=str(path))


def _collection_name(
    target: IsolatedIndexTarget,
    request: IndexProjectionRequest,
) -> str:
    identity = _sha256_text(
        "|".join(
            (
                target.target_id,
                target.release_id,
                request.index_projection_version,
                request.vector_schema_version,
                request.embedding_model,
            )
        )
    )
    return f"canonical_v2_{identity[:32]}"


def _write_milvus_projection(
    client: Any,
    *,
    collection_name: str,
    points: tuple[IndexProjectionPoint, ...],
    embedding_adapter: EmbeddingAdapter,
) -> None:
    if client.has_collection(collection_name):
        raise IsolatedIndexTargetSafetyError(
            "generated isolated collection unexpectedly already exists"
        )
    client.create_collection(
        collection_name=collection_name,
        dimension=embedding_adapter.dimension,
        primary_field_name="point_id",
        vector_field_name="vector",
        id_type="string",
        max_length=256,
        metric_type="COSINE",
        enable_dynamic_field=True,
    )
    vectors = embedding_adapter.embed_batch(
        tuple(point.embedded_content for point in points)
    )
    if len(vectors) != len(points) or any(
        len(vector) != embedding_adapter.dimension for vector in vectors
    ):
        raise IndexProjectionIntegrityError(
            "embedding output cardinality or dimension differs from index points"
        )
    if points:
        client.insert(
            collection_name=collection_name,
            data=[
                {
                    "point_id": point.point_id,
                    "vector": list(vector),
                    "release_id": point.release_id,
                    "projection_id": point.projection_id,
                    "canonical_object_id": point.canonical_object_id,
                    "embedded_content_sha256": point.embedded_content_sha256,
                    "point_json": point.model_dump_json(),
                }
                for point, vector in zip(points, vectors, strict=True)
            ],
        )
        client.flush(collection_name=collection_name)


def _read_points_with_client(
    client: Any,
    *,
    collection_name: str,
    point_ids: tuple[str, ...],
    embedding_adapter: EmbeddingAdapter | None = None,
) -> tuple[IndexProjectionPoint, ...]:
    if not client.has_collection(collection_name):
        raise IndexProjectionIntegrityError("isolated Milvus collection is missing")
    if not point_ids:
        return ()
    rows = client.get(
        collection_name=collection_name,
        ids=list(point_ids),
        output_fields=[
            "point_id",
            "release_id",
            "projection_id",
            "canonical_object_id",
            "embedded_content_sha256",
            "point_json",
            "vector",
        ],
    )
    return _validate_physical_point_rows(
        rows,
        expected_point_ids=point_ids,
        embedding_adapter=embedding_adapter,
    )


def _read_all_points_with_client(
    client: Any,
    *,
    collection_name: str,
    embedding_adapter: EmbeddingAdapter,
) -> tuple[IndexProjectionPoint, ...]:
    if not client.has_collection(collection_name):
        raise IndexProjectionIntegrityError("isolated Milvus collection is missing")
    iterator = client.query_iterator(
        collection_name=collection_name,
        batch_size=1000,
        filter="",
        output_fields=[
            "point_id",
            "release_id",
            "projection_id",
            "canonical_object_id",
            "embedded_content_sha256",
            "point_json",
            "vector",
        ],
    )
    rows: list[dict[str, Any]] = []
    try:
        while batch := iterator.next():
            rows.extend(batch)
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            close()
    return _validate_physical_point_rows(
        rows,
        expected_point_ids=None,
        embedding_adapter=embedding_adapter,
    )


def _validate_physical_point_rows(
    rows: Any,
    *,
    expected_point_ids: tuple[str, ...] | None,
    embedding_adapter: EmbeddingAdapter | None,
) -> tuple[IndexProjectionPoint, ...]:
    try:
        points_and_rows = tuple(
            (IndexProjectionPoint.model_validate_json(row["point_json"]), row)
            for row in rows
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise IndexProjectionIntegrityError(
            "isolated Milvus point readback is invalid"
        ) from exc
    for point, row in points_and_rows:
        if (
            row.get("point_id") != point.point_id
            or row.get("release_id") != point.release_id
            or row.get("projection_id") != point.projection_id
            or row.get("canonical_object_id") != point.canonical_object_id
            or row.get("embedded_content_sha256") != point.embedded_content_sha256
        ):
            raise IndexProjectionIntegrityError(
                "isolated Milvus physical metadata differs from point JSON"
            )
        if embedding_adapter is not None:
            vector = row.get("vector")
            expected_vector = embedding_adapter.embed_batch((point.embedded_content,))[
                0
            ]
            if (
                not isinstance(vector, list)
                or len(vector) != embedding_adapter.dimension
                or any(
                    not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    for value in vector
                )
                or any(
                    not math.isclose(
                        float(actual),
                        expected,
                        rel_tol=1e-7,
                        abs_tol=1e-7,
                    )
                    for actual, expected in zip(vector, expected_vector, strict=True)
                )
            ):
                raise IndexProjectionIntegrityError(
                    "isolated Milvus vector differs from deterministic embedding"
                )
    points = tuple(
        sorted(
            (item[0] for item in points_and_rows),
            key=lambda item: (
                item.projection_id,
                item.canonical_object_id,
                item.point_id,
            ),
        )
    )
    point_ids = tuple(sorted(item.point_id for item in points))
    if len(point_ids) != len(set(point_ids)):
        raise IndexProjectionIntegrityError(
            "isolated Milvus physical inventory contains duplicate point IDs"
        )
    if expected_point_ids is not None and point_ids != tuple(
        sorted(expected_point_ids)
    ):
        raise IndexProjectionIntegrityError(
            "isolated Milvus point identity readback differs"
        )
    return points


def _write_lookup_projection(
    path: Path,
    *,
    release_id: str,
    documents: tuple[LookupProjectionDocument, ...],
    manifests: tuple[LookupProjectionManifest, ...],
) -> None:
    if path.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "isolated lookup target cannot be a symlink"
        )
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA journal_mode = DELETE;
            CREATE TABLE lookup_document (
                document_id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL,
                projection_id TEXT NOT NULL,
                canonical_object_id TEXT NOT NULL,
                document_json TEXT NOT NULL
            ) STRICT;
            CREATE INDEX lookup_document_owner
              ON lookup_document(release_id, projection_id, canonical_object_id);
            CREATE TABLE lookup_manifest (
                projection_id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL,
                manifest_json TEXT NOT NULL
            ) STRICT;
            CREATE TABLE build_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            ) STRICT;
            CREATE TABLE build_receipt (
                release_id TEXT PRIMARY KEY,
                receipt_json TEXT NOT NULL
            ) STRICT;
            """
        )
        connection.executemany(
            """
            INSERT INTO lookup_document (
                document_id, release_id, projection_id,
                canonical_object_id, document_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    item.document_id,
                    item.release_id,
                    item.projection_id,
                    item.canonical_object_id,
                    item.model_dump_json(),
                )
                for item in documents
            ],
        )
        connection.executemany(
            """
            INSERT INTO lookup_manifest (
                projection_id, release_id, manifest_json
            ) VALUES (?, ?, ?)
            """,
            [
                (item.projection_id, item.release_id, item.model_dump_json())
                for item in manifests
            ],
        )
        connection.execute(
            "INSERT INTO build_metadata (key, value) VALUES ('release_id', ?)",
            (release_id,),
        )


def _read_lookup_documents_from_path(
    path: Path,
) -> tuple[LookupProjectionDocument, ...]:
    if not path.is_file() or path.is_symlink():
        raise IndexProjectionIntegrityError("isolated lookup store is missing")
    uri = f"file:{path}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "SELECT document_id, release_id, projection_id, "
            "canonical_object_id, document_json FROM lookup_document "
            "ORDER BY projection_id, canonical_object_id"
        ).fetchall()
    documents: list[LookupProjectionDocument] = []
    for row in rows:
        document = LookupProjectionDocument.model_validate_json(row[4])
        if row[:4] != (
            document.document_id,
            document.release_id,
            document.projection_id,
            document.canonical_object_id,
        ):
            raise IndexProjectionIntegrityError(
                "isolated lookup physical metadata differs from document JSON"
            )
        documents.append(document)
    return tuple(documents)


def _read_lookup_manifests_from_path(
    path: Path,
) -> tuple[LookupProjectionManifest, ...]:
    if not path.is_file() or path.is_symlink():
        raise IndexProjectionIntegrityError("isolated lookup manifest store is missing")
    uri = f"file:{path}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "SELECT projection_id, release_id, manifest_json "
            "FROM lookup_manifest ORDER BY rowid"
        ).fetchall()
    manifests: list[LookupProjectionManifest] = []
    for row in rows:
        manifest = LookupProjectionManifest.model_validate_json(row[2])
        if row[:2] != (manifest.projection_id, manifest.release_id):
            raise IndexProjectionIntegrityError(
                "isolated lookup manifest physical metadata differs from JSON"
            )
        manifests.append(manifest)
    return tuple(manifests)


def _write_build_metadata(path: Path, *, collection_name: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "isolated lookup target changed before metadata write"
        )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO build_metadata (key, value) VALUES ('collection_name', ?)",
            (collection_name,),
        )


def _read_collection_name(path: Path, *, expected_release_id: str) -> str:
    if not path.is_file() or path.is_symlink():
        raise IndexProjectionIntegrityError(
            "isolated index metadata store is missing or unsafe"
        )
    uri = f"file:{path}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "SELECT key, value FROM build_metadata ORDER BY key"
        ).fetchall()
    if (
        len(rows) != 2
        or {row[0] for row in rows} != {"collection_name", "release_id"}
        or any(not isinstance(row[1], str) or not row[1] for row in rows)
    ):
        raise IndexProjectionIntegrityError(
            "isolated index build metadata must contain one exact release and collection"
        )
    metadata = dict(rows)
    if metadata["release_id"] != expected_release_id:
        raise IndexProjectionIntegrityError(
            "isolated index build metadata release differs from the marked target"
        )
    return metadata["collection_name"]


def _build_receipt(
    *,
    target: IsolatedIndexTarget,
    points: tuple[IndexProjectionPoint, ...],
    lookup_documents: tuple[LookupProjectionDocument, ...],
    index_projections: tuple[IndexProjectionManifest, ...],
    lookup_projections: tuple[LookupProjectionManifest, ...],
    gate_receipt: BackupGateReceipt,
    built_at: datetime,
) -> IndexProjectionMaterializationReceipt:
    values = {
        "release_id": target.release_id,
        "target_id": target.target_id,
        "target_kind": target.target_kind,
        "vector_backend": "milvus-lite",
        "lookup_backend": "sqlite",
        "point_ids": tuple(sorted(item.point_id for item in points)),
        "lookup_document_ids": tuple(
            sorted(item.document_id for item in lookup_documents)
        ),
        "index_projections": index_projections,
        "lookup_projections": lookup_projections,
        "source_inventory_sha256": gate_receipt.source_inventory_sha256,
        "backup_manifest_sha256": gate_receipt.backup_manifest_sha256,
        "restore_verification_sha256": gate_receipt.restore_verification_sha256,
        "acceptance_record_sha256": gate_receipt.acceptance_record_sha256,
        "built_at": built_at,
    }
    provisional = IndexProjectionMaterializationReceipt.model_construct(
        **values,
        content_sha256="0" * 64,
    )
    payload = cast(
        JsonValue,
        provisional.model_dump(mode="json", exclude={"content_sha256"}),
    )
    return IndexProjectionMaterializationReceipt(
        **values,
        content_sha256=_canonical_sha256(payload),
    )


def _write_receipt(
    path: Path,
    receipt: IndexProjectionMaterializationReceipt,
) -> None:
    if not path.is_file() or path.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "isolated lookup target changed before receipt write"
        )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO build_receipt (release_id, receipt_json) VALUES (?, ?)",
            (receipt.release_id, receipt.model_dump_json()),
        )


def _read_receipt(path: Path) -> IndexProjectionMaterializationReceipt:
    if not path.is_file() or path.is_symlink():
        raise IndexProjectionIntegrityError("isolated build receipt store is missing")
    uri = f"file:{path}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute("SELECT receipt_json FROM build_receipt").fetchall()
    if len(rows) != 1:
        raise IndexProjectionIntegrityError(
            "isolated build requires one exact persisted receipt"
        )
    return IndexProjectionMaterializationReceipt.model_validate_json(rows[0][0])


def _canonical_json_bytes(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: JsonValue) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


__all__ = [
    "EmbeddingAdapter",
    "IsolatedIndexSnapshot",
    "IsolatedIndexTarget",
    "IsolatedIndexTargetSafetyError",
    "RecordedEmbeddingAdapter",
    "audit_isolated_index_snapshot",
    "create_isolated_index_projection_builder",
    "prepare_isolated_index_target",
    "read_isolated_index_points",
    "read_isolated_lookup_documents",
]
