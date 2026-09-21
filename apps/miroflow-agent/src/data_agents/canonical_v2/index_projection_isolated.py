"""Guarded local adapters for one isolated Canonical V2 full index build."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Any, Literal, Protocol, cast
import warnings

import numpy as np

from pydantic import Field, JsonValue, field_validator, model_validator

from . import serving_timing
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
from .publication_cleaning import (
    audit_lookup_documents,
    compose_publication_quality_report,
    quarantine_records_from_selections,
)
from .rebuild_write_gate import BackupGateReceipt, require_accepted_backup_gate


_MARKER_NAME = ".canonical-v2-isolated-index-target.json"
_MARKER_SCHEMA_VERSION = "canonical-v2-isolated-index-target-v1"
_MILVUS_FILENAME = "milvus.db"
_LOOKUP_FILENAME = "lookup.sqlite3"
_PUBLICATION_QUALITY_REPORT_FILENAME = "publication-quality-report.json"
_VECTOR_MATRIX_FILENAME = "vector_matrix.npz"
_VECTOR_MATRIX_SCHEMA_VERSION = "canonical-v2-vector-matrix-v1"
_INDEX_POINT_TABLE = "index_point"
_POINT_READ_BATCH_SIZE = 128
_POINT_WRITE_BATCH_SIZE = 128
#: The cosine a re-embedded point must reach against the vector stored for it.
#:
#: This is a **corruption** guard, not a space-drift guard: the point's own
#: content is embedded again and compared with what the index kept. It used to
#: sit at 0.999, which encoded "a deterministic endpoint reproduces its own
#: vector". The candidate gateway is not deterministic — measured 2026-09-21,
#: same text and route, 30 repeats per text: answers are bimodal (identical, or
#: ~0.998) with a pooled minimum of 0.998004 over 1305 pairs and 0.997556 in an
#: earlier run, and the noisy mode itself moved ~0.0013 between runs. Because
#: this audit runs per point, a ~51k-point rebuild reaches the tail of that
#: distribution: at 0.999 it would abort with "isolated Milvus vector differs
#: from its bound embedding", which reads like corruption but is the endpoint's
#: rounding.
#:
#: 0.99 is chosen from the measurements: 0.0076 below the lowest repeat ever
#: observed (3x the full observed spread) while keeping 0.06 of separation from
#: the highest measured wrong answer — a vector bound to the wrong point
#: measures 0.24 for unrelated documents and up to 0.93 for the sibling route of
#: the same model, and another space measures ≈ -0.03. Dimension and norm are
#: checked separately below, so lowering the cosine floor does not weaken them.
_MIN_VECTOR_COSINE_SIMILARITY = 0.99
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{1,}|[\u3400-\u4DBF\u4E00-\u9FFF]")

#: Where a marked isolated index keeps its ``IndexProjectionPoint`` objects.
#: ``milvus-lite`` is the v1 storage (the Milvus row's ``point_json`` column);
#: ``lookup-sqlite`` is the v2 storage (the ``index_point`` table of the same
#: release ``lookup.sqlite3`` that already carries the lookup documents).
IndexPointStore = Literal["milvus-lite", "lookup-sqlite"]
POINT_STORE_MILVUS: IndexPointStore = "milvus-lite"
POINT_STORE_LOOKUP: IndexPointStore = "lookup-sqlite"


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
            vectors = _write_milvus_projection(
                client,
                collection_name=collection_name,
                points=points,
                embedding_adapter=self._embedding_adapter,
            )
            write_persisted_vector_matrix(
                self._target.root,
                points=points,
                vectors=vectors,
                embedding_model_id=request.embedding_model,
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
            _write_publication_quality_report(
                self._target.root,
                release_id=self._target.release_id,
                request=request,
                documents=read_documents,
            )
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
    return _open_verified_index_snapshot(
        target,
        expected_embedding_model_id=embedding_adapter.model_id,
        embedding_adapter=embedding_adapter,
    )


def open_manifest_verified_index_snapshot(
    target: IsolatedIndexTarget,
    *,
    expected_embedding_model_id: str,
    point_store: IndexPointStore = POINT_STORE_MILVUS,
) -> IsolatedIndexSnapshot:
    """Open the marked snapshot after manifest/hash binding, without re-embedding.

    This is the fast-boot alternative to :func:`audit_isolated_index_snapshot`:
    it performs the same marker, self-hashed receipt, projection-manifest,
    lookup inventory, and point-store checks and still reads every point row
    with full per-row metadata binding, but it does not re-derive the stored
    vectors from the embedding model. Stored vectors are write-time artifacts;
    serving re-embeds ``embedded_content`` at query time, so skipping their
    readback verification does not change query behavior. The caller must still
    bind the returned snapshot to the accepted release bundle.

    ``point_store`` names where the points live: ``milvus-lite`` (v1 packs)
    opens the marked ``milvus.db``; ``lookup-sqlite`` (v2 packs) reads the
    ``index_point`` table of the release lookup store and never touches Milvus.
    """

    return _open_verified_index_snapshot(
        target,
        expected_embedding_model_id=expected_embedding_model_id,
        embedding_adapter=None,
        point_store=point_store,
    )


def _open_verified_index_snapshot(
    target: IsolatedIndexTarget,
    *,
    expected_embedding_model_id: str,
    embedding_adapter: EmbeddingAdapter | None,
    point_store: IndexPointStore = POINT_STORE_MILVUS,
) -> IsolatedIndexSnapshot:
    _validate_target_marker(target)
    lookup_path = target.root / _LOOKUP_FILENAME
    receipt = _read_receipt(lookup_path)
    if receipt.release_id != target.release_id or receipt.target_id != target.target_id:
        raise IndexProjectionIntegrityError(
            "isolated index receipt differs from the marked target"
        )
    if any(
        manifest.release_id != target.release_id
        or manifest.embedding_model != expected_embedding_model_id
        for manifest in receipt.index_projections
    ) or any(
        manifest.release_id != target.release_id
        for manifest in receipt.lookup_projections
    ):
        raise IndexProjectionIntegrityError(
            "isolated receipt projection identity differs from the marked target"
        )
    with serving_timing.timed_step("snapshot.lookup_docs"):
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

    if point_store == POINT_STORE_LOOKUP:
        if embedding_adapter is not None:
            raise IsolatedIndexTargetSafetyError(
                "the full vector audit requires the v1 Milvus point store"
            )
        stray_milvus = target.root / _MILVUS_FILENAME
        if stray_milvus.exists() or stray_milvus.is_symlink():
            raise IndexProjectionIntegrityError(
                "v2 isolated target must not carry a Milvus store"
            )
        with serving_timing.timed_step("snapshot.lookup_points"):
            points = _read_index_points_from_path(
                lookup_path,
                expected_release_id=target.release_id,
            )
        if tuple(sorted(point.point_id for point in points)) != receipt.point_ids:
            raise IndexProjectionIntegrityError(
                "isolated point store inventory differs from the receipt"
            )
        return IsolatedIndexSnapshot(
            receipt=receipt,
            points=points,
            lookup_documents=documents,
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
    with serving_timing.timed_step("snapshot.milvus_client_open"):
        client = _open_milvus_client(milvus_path)
    try:
        with serving_timing.timed_step("snapshot.milvus_list_collections"):
            collections = tuple(sorted(client.list_collections()))
        if collections != (collection_name,):
            raise IndexProjectionIntegrityError(
                "isolated target must contain exactly its recorded Milvus collection"
            )
        with serving_timing.timed_step("snapshot.milvus_read_points"):
            points = _read_all_points_with_client(
                client,
                collection_name=collection_name,
                embedding_adapter=embedding_adapter,
            )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            with serving_timing.timed_step("snapshot.milvus_close"):
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


def write_persisted_vector_matrix(
    root: Path,
    *,
    points: tuple[IndexProjectionPoint, ...],
    vectors: tuple[tuple[float, ...], ...],
    embedding_model_id: str,
) -> None:
    """Persist the released point vectors as a numpy matrix for fast boot.

    The build already embeds every point exactly once (the same ``vectors``
    upserted into Milvus); writing them here as ``vector_matrix.npz`` lets the
    serving process load the scoring matrix at boot instead of re-embedding
    all ~6k points on the first vector request (~77s cold spike).
    """
    if len(vectors) != len(points):
        raise IndexProjectionIntegrityError(
            "persisted vector matrix cardinality differs from index points"
        )
    if not points:
        return
    dimension = len(vectors[0])
    if any(len(vector) != dimension for vector in vectors):
        raise IndexProjectionIntegrityError(
            "persisted vector matrix dimension differs within the batch"
        )
    matrix = np.asarray(tuple(vectors), dtype=np.float64)
    if matrix.shape != (len(points), dimension):
        raise IndexProjectionIntegrityError(
            "persisted vector matrix shape differs from index points"
        )
    norms = np.linalg.norm(matrix, axis=1)
    if not np.all(np.isfinite(norms)) or np.any(norms == 0.0):
        raise IndexProjectionIntegrityError(
            "persisted vector matrix has an invalid norm"
        )
    meta = json.dumps(
        {
            "schema_version": _VECTOR_MATRIX_SCHEMA_VERSION,
            "embedding_model_id": embedding_model_id,
            "dimension": dimension,
            "point_count": len(points),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    np.savez(
        root / _VECTOR_MATRIX_FILENAME,
        point_ids=np.asarray(tuple(point.point_id for point in points), dtype=object),
        matrix=matrix,
        norms=norms,
        meta=np.asarray(meta, dtype=object),
    )


def load_persisted_vector_matrix(
    path: Path,
    *,
    points: tuple[IndexProjectionPoint, ...],
    expected_embedding_model_id: str,
    dimension: int,
) -> tuple[dict[str, int], Any, Any] | None:
    """Load the persisted vector matrix, or return None when absent.

    Validates schema/model/dimension/point-set/norm consistency; any mismatch
    raises ``IndexProjectionIntegrityError`` (fail closed).  Row order is taken
    from the file's ``point_ids`` (not assumed to match the snapshot order).
    """
    if not path.exists() or path.is_symlink():
        return None
    try:
        data = np.load(path, allow_pickle=True)
        meta = json.loads(str(data["meta"].item()))
        point_ids = tuple(str(value) for value in data["point_ids"].tolist())
        matrix = np.asarray(data["matrix"], dtype=np.float64)
        norms = np.asarray(data["norms"], dtype=np.float64)
    except Exception as exc:  # noqa: BLE001
        raise IndexProjectionIntegrityError(
            "persisted vector matrix could not be loaded"
        ) from exc
    if meta.get("schema_version") != _VECTOR_MATRIX_SCHEMA_VERSION:
        raise IndexProjectionIntegrityError(
            "persisted vector matrix schema version differs"
        )
    if meta.get("embedding_model_id") != expected_embedding_model_id:
        raise IndexProjectionIntegrityError(
            "persisted vector matrix embedding model differs"
        )
    expected_count = len(points)
    if (
        meta.get("point_count") != expected_count
        or matrix.shape != (expected_count, dimension)
        or len(point_ids) != expected_count
        or len(norms) != expected_count
    ):
        raise IndexProjectionIntegrityError(
            "persisted vector matrix shape or count differs from the snapshot"
        )
    point_id_set = set(point_ids)
    if len(point_id_set) != expected_count or point_id_set != {
        point.point_id for point in points
    }:
        raise IndexProjectionIntegrityError(
            "persisted vector matrix point set differs from the snapshot"
        )
    if not np.all(np.isfinite(norms)) or np.any(norms == 0.0):
        raise IndexProjectionIntegrityError(
            "persisted vector matrix has an invalid norm"
        )
    positions = {point_id: index for index, point_id in enumerate(point_ids)}
    return positions, matrix, norms


@dataclass(frozen=True, slots=True)
class IsolatedIndexConversionReport:
    """What one v1→v2 isolated index conversion materialized."""

    source_root: Path
    dest_root: Path
    release_id: str
    point_count: int
    dest_lookup_bytes: int
    dest_vector_matrix_bytes: int
    removed_milvus_bytes: int
    dest_lookup_sha256: str
    dest_marker_sha256: str


def convert_isolated_index_to_v2(
    *,
    source_root: Path,
    dest_root: Path,
) -> IsolatedIndexConversionReport:
    """Materialize a v2 isolated index root from one v1 (Milvus-backed) root.

    The v2 root keeps the same authority — the same lookup documents, the same
    points, the same vector matrix — in the v2 storage form: the points move
    from the Milvus ``point_json`` column into the ``index_point`` table of the
    release ``lookup.sqlite3``, and no ``milvus.db`` is written. Fail closed on
    any identity or inventory drift; the source root is never modified.
    A failed conversion leaves a partial destination root behind, which the
    operator removes before retrying (the destination must stay fresh).
    """

    if not source_root.is_absolute() or not dest_root.is_absolute():
        raise IsolatedIndexTargetSafetyError(
            "isolated index conversion requires explicit absolute roots"
        )
    source_root = source_root.resolve(strict=False)
    dest_root = dest_root.resolve(strict=False)
    if not source_root.is_dir() or source_root.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "conversion source root is missing or unsafe"
        )
    marker_path = source_root / _MARKER_NAME
    if not marker_path.is_file() or marker_path.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "conversion source marker is missing or unsafe"
        )
    marker_bytes = marker_path.read_bytes()
    marker = json.loads(marker_bytes)
    if marker.get("schema_version") != _MARKER_SCHEMA_VERSION:
        raise IsolatedIndexTargetSafetyError("conversion source marker schema differs")
    if marker.get("root") != str(source_root):
        raise IsolatedIndexTargetSafetyError("conversion source marker root differs")
    target = IsolatedIndexTarget(
        root=source_root,
        target_id=marker["target_id"],
        release_id=marker["release_id"],
        forbidden_milvus_paths=tuple(
            Path(value) for value in marker["forbidden_milvus_paths"]
        ),
        marker_sha256=_sha256_bytes(marker_bytes),
    )
    _validate_target_marker(target)

    lookup_path = source_root / _LOOKUP_FILENAME
    receipt = _read_receipt(lookup_path)
    if receipt.release_id != target.release_id or receipt.target_id != target.target_id:
        raise IndexProjectionIntegrityError(
            "conversion source receipt differs from the marked target"
        )
    embedding_models = {
        manifest.embedding_model for manifest in receipt.index_projections
    }
    if len(embedding_models) != 1:
        raise IndexProjectionIntegrityError(
            "conversion source receipt embedding model is not uniform"
        )
    embedding_model_id = embedding_models.pop()

    milvus_path = source_root / _MILVUS_FILENAME
    if not milvus_path.is_file() or milvus_path.is_symlink():
        raise IndexProjectionIntegrityError(
            "conversion source Milvus store is missing or unsafe"
        )
    collection_name = _read_collection_name(
        lookup_path,
        expected_release_id=target.release_id,
    )
    client = _open_milvus_client(milvus_path)
    try:
        points = _read_all_points_with_client(
            client,
            collection_name=collection_name,
            embedding_adapter=None,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    if tuple(sorted(point.point_id for point in points)) != receipt.point_ids:
        raise IndexProjectionIntegrityError(
            "conversion source point inventory differs from the receipt"
        )

    for ancestor in (dest_root, *dest_root.parents):
        if ancestor.is_symlink():
            raise IsolatedIndexTargetSafetyError(
                "conversion destination ancestry contains a symlink"
            )
    if dest_root.exists() or dest_root.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "conversion destination already exists; a fresh root is required"
        )
    if not dest_root.parent.is_dir() or dest_root.parent.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "conversion destination parent must exist and not be a symlink"
        )
    dest_root.mkdir(mode=0o700)
    dest_lookup = dest_root / _LOOKUP_FILENAME
    shutil.copyfile(lookup_path, dest_lookup)
    write_lookup_index_points(dest_lookup, points=points)
    dest_matrix = dest_root / _VECTOR_MATRIX_FILENAME
    source_matrix = source_root / _VECTOR_MATRIX_FILENAME
    if not source_matrix.is_file() or source_matrix.is_symlink():
        raise IndexProjectionIntegrityError(
            "conversion source vector matrix is missing or unsafe"
        )
    shutil.copyfile(source_matrix, dest_matrix)
    with np.load(dest_matrix, allow_pickle=True) as data:
        matrix_meta = json.loads(str(data["meta"].item()))
    _require_compatible_vector_matrix(
        dest_matrix,
        points=points,
        expected_embedding_model_id=embedding_model_id,
        dimension=int(matrix_meta["dimension"]),
    )
    dest_marker_bytes = (
        _canonical_json_bytes(
            cast(
                JsonValue,
                _marker_document(
                    root=dest_root,
                    target_id=target.target_id,
                    release_id=target.release_id,
                    forbidden_milvus_paths=target.forbidden_milvus_paths,
                ),
            )
        )
        + b"\n"
    )
    with (dest_root / _MARKER_NAME).open("xb") as stream:
        stream.write(dest_marker_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    return IsolatedIndexConversionReport(
        source_root=source_root,
        dest_root=dest_root,
        release_id=target.release_id,
        point_count=len(points),
        dest_lookup_bytes=dest_lookup.stat().st_size,
        dest_vector_matrix_bytes=dest_matrix.stat().st_size,
        removed_milvus_bytes=milvus_path.stat().st_size,
        dest_lookup_sha256=_sha256_file(dest_lookup),
        dest_marker_sha256=_sha256_bytes(dest_marker_bytes),
    )


def _require_compatible_vector_matrix(
    path: Path,
    *,
    points: tuple[IndexProjectionPoint, ...],
    expected_embedding_model_id: str,
    dimension: int,
) -> None:
    if (
        load_persisted_vector_matrix(
            path,
            points=points,
            expected_embedding_model_id=expected_embedding_model_id,
            dimension=dimension,
        )
        is None
    ):
        raise IndexProjectionIntegrityError(
            "conversion destination vector matrix is missing"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_milvus_projection(
    client: Any,
    *,
    collection_name: str,
    points: tuple[IndexProjectionPoint, ...],
    embedding_adapter: EmbeddingAdapter,
) -> tuple[tuple[tuple[float, ...], ...], ...]:
    """Write points into Milvus and return the embedded vectors.

    The returned vectors are the exact build-time embeddings (also persisted
    by the caller as ``vector_matrix.npz`` for fast serving boot).
    """
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
        for offset in range(0, len(points), _POINT_WRITE_BATCH_SIZE):
            batch_points = points[offset : offset + _POINT_WRITE_BATCH_SIZE]
            batch_vectors = vectors[offset : offset + _POINT_WRITE_BATCH_SIZE]
            client.upsert(
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
                    for point, vector in zip(batch_points, batch_vectors, strict=True)
                ],
            )
        client.flush(collection_name=collection_name)
    return tuple(tuple(vector) for vector in vectors)


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
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(point_ids), _POINT_READ_BATCH_SIZE):
        rows.extend(
            client.get(
                collection_name=collection_name,
                ids=list(point_ids[offset : offset + _POINT_READ_BATCH_SIZE]),
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
    embedding_adapter: EmbeddingAdapter | None,
) -> tuple[IndexProjectionPoint, ...]:
    if not client.has_collection(collection_name):
        raise IndexProjectionIntegrityError("isolated Milvus collection is missing")
    iterator = client.query_iterator(
        collection_name=collection_name,
        batch_size=_POINT_READ_BATCH_SIZE,
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
    expected_vectors = (
        embedding_adapter.embed_batch(
            tuple(point.embedded_content for point, _ in points_and_rows)
        )
        if embedding_adapter is not None
        else None
    )
    if expected_vectors is not None and len(expected_vectors) != len(points_and_rows):
        raise IndexProjectionIntegrityError(
            "isolated Milvus vector verification cardinality differs"
        )
    for index, (point, row) in enumerate(points_and_rows):
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
            assert expected_vectors is not None
            expected_vector = expected_vectors[index]
            actual_vector = (
                tuple(float(value) for value in vector)
                if isinstance(vector, list)
                and all(
                    isinstance(value, (int, float)) and math.isfinite(float(value))
                    for value in vector
                )
                else ()
            )
            actual_norm = math.sqrt(sum(value * value for value in actual_vector))
            expected_norm = math.sqrt(sum(value * value for value in expected_vector))
            cosine_similarity = (
                sum(
                    actual * expected
                    for actual, expected in zip(
                        actual_vector, expected_vector, strict=True
                    )
                )
                / (actual_norm * expected_norm)
                if actual_norm > 0.0
                and expected_norm > 0.0
                and len(actual_vector) == len(expected_vector)
                else -1.0
            )
            if (
                len(actual_vector) != embedding_adapter.dimension
                or not math.isclose(
                    actual_norm,
                    expected_norm,
                    rel_tol=1e-3,
                    abs_tol=1e-3,
                )
                or cosine_similarity < _MIN_VECTOR_COSINE_SIMILARITY
            ):
                raise IndexProjectionIntegrityError(
                    "isolated Milvus vector differs from its bound embedding"
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
        connection.cursor().executemany(
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
        connection.cursor().executemany(
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


def has_lookup_index_points(path: Path) -> bool:
    """Whether one release lookup store carries the v2 ``index_point`` table."""

    if not path.is_file() or path.is_symlink():
        raise IndexProjectionIntegrityError("isolated lookup store is missing")
    uri = f"file:{path}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (_INDEX_POINT_TABLE,),
        ).fetchone()
    return row is not None


def write_lookup_index_points(
    path: Path,
    *,
    points: tuple[IndexProjectionPoint, ...],
) -> None:
    """Store the isolated index points in one lookup store (v2 point authority).

    The four metadata columns mirror the Milvus row columns the v1 read
    validates, so "the physical row must agree with the point JSON" keeps the
    same strength; ``point_json`` stays the authority. Refuses a store that
    already carries the table (one materialization per store).
    """

    if not path.is_file() or path.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "isolated lookup target changed before the point store was written"
        )
    point_ids = tuple(point.point_id for point in points)
    if len(set(point_ids)) != len(point_ids):
        raise IndexProjectionIntegrityError(
            "isolated index points contain duplicate point IDs"
        )
    with sqlite3.connect(path) as connection:
        connection.executescript(
            f"""
            PRAGMA journal_mode = DELETE;
            CREATE TABLE {_INDEX_POINT_TABLE} (
                point_id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL,
                projection_id TEXT NOT NULL,
                canonical_object_id TEXT NOT NULL,
                embedded_content_sha256 TEXT NOT NULL,
                point_json TEXT NOT NULL
            ) STRICT;
            CREATE INDEX index_point_owner
              ON {_INDEX_POINT_TABLE}(release_id, projection_id, canonical_object_id);
            """
        )
        connection.executemany(
            f"""
            INSERT INTO {_INDEX_POINT_TABLE} (
                point_id, release_id, projection_id,
                canonical_object_id, embedded_content_sha256, point_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    point.point_id,
                    point.release_id,
                    point.projection_id,
                    point.canonical_object_id,
                    point.embedded_content_sha256,
                    point.model_dump_json(),
                )
                for point in points
            ],
        )


def _read_index_points_from_path(
    path: Path,
    *,
    expected_release_id: str,
) -> tuple[IndexProjectionPoint, ...]:
    """Read every v2 index point, fail closed on a missing or drifting store."""

    if not path.is_file() or path.is_symlink():
        raise IndexProjectionIntegrityError("isolated lookup store is missing")
    uri = f"file:{path}?mode=ro&immutable=1"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            rows = connection.execute(
                "SELECT point_id, release_id, projection_id, canonical_object_id, "
                f"embedded_content_sha256, point_json FROM {_INDEX_POINT_TABLE}"
            ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise IndexProjectionIntegrityError(
            "isolated point store is missing or unreadable"
        ) from exc
    points: list[IndexProjectionPoint] = []
    for row in rows:
        point = IndexProjectionPoint.model_validate_json(row[5])
        if row[:5] != (
            point.point_id,
            point.release_id,
            point.projection_id,
            point.canonical_object_id,
            point.embedded_content_sha256,
        ):
            raise IndexProjectionIntegrityError(
                "isolated point store metadata differs from point JSON"
            )
        if point.release_id != expected_release_id:
            raise IndexProjectionIntegrityError(
                "isolated point store contains a cross-release point"
            )
        points.append(point)
    ordered = tuple(
        sorted(
            points,
            key=lambda item: (
                item.projection_id,
                item.canonical_object_id,
                item.point_id,
            ),
        )
    )
    point_ids = tuple(point.point_id for point in ordered)
    if len(point_ids) != len(set(point_ids)):
        raise IndexProjectionIntegrityError(
            "isolated point store contains duplicate point IDs"
        )
    return ordered


def _write_publication_quality_report(
    root: Path,
    *,
    release_id: str,
    request: IndexProjectionRequest,
    documents: tuple[LookupProjectionDocument, ...],
) -> None:
    """Write the build's data-quality report next to the index artifacts.

    The report is *not* part of the pack: the serving-pack loader binds an exact
    file registry, and the sealer copies only ``lookup.sqlite3``/``milvus.db``/
    the marker, so this file stays in the build output and never enters a
    content hash.  ``quarantine_records`` are re-derived from the request's own
    source selections with the same pure rules the projection applied.
    """
    path = root / _PUBLICATION_QUALITY_REPORT_FILENAME
    if path.is_symlink():
        raise IsolatedIndexTargetSafetyError(
            "publication quality report cannot be a symlink"
        )
    report = audit_lookup_documents(
        documents,
        released_company_ids=frozenset(
            projection.canonical_identity_id
            for projection in request.candidate_projection_result.public_domain_projections
            if projection.entity_type == "company"
        ),
    )
    domain_request = request.candidate_projection_request.internal_reference_projection_request.public_domain_projection_request
    domain_by_identity = {
        identity.canonical_identity_id: identity.entity_type
        for identity in domain_request.canonical_identities
    }
    quarantine = quarantine_records_from_selections(
        (
            domain_by_identity[selection.canonical_identity_id],
            selection.canonical_identity_id,
            selection.field_path,
            selection.value,
        )
        for selection in domain_request.current_fields
        if selection.canonical_identity_id in domain_by_identity
    )
    payload = compose_publication_quality_report(
        release_id=release_id,
        report=report,
        quarantine=quarantine,
    )
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


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
    "IndexPointStore",
    "IsolatedIndexConversionReport",
    "IsolatedIndexSnapshot",
    "IsolatedIndexTarget",
    "IsolatedIndexTargetSafetyError",
    "POINT_STORE_LOOKUP",
    "POINT_STORE_MILVUS",
    "RecordedEmbeddingAdapter",
    "audit_isolated_index_snapshot",
    "convert_isolated_index_to_v2",
    "create_isolated_index_projection_builder",
    "has_lookup_index_points",
    "open_manifest_verified_index_snapshot",
    "prepare_isolated_index_target",
    "read_isolated_index_points",
    "read_isolated_lookup_documents",
    "write_lookup_index_points",
]
