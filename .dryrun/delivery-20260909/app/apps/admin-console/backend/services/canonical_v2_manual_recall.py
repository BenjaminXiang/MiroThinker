"""Online recall sidecar for manual knowledge (uploaded documents and
manually added records).

The serving process never queries Milvus at request time: vector recall is
in-process numpy cosine over an audited, hash-pinned snapshot of the release
points. Manual knowledge must therefore live in a *separate* writable point
set that the vector lane can union into its candidate pool (the release
artifacts stay untouched and their provenance chain intact).

This module owns that sidecar: a small JSON file (atomically rewritten on
every mutation, private permissions) plus the in-memory point set. Points
are embedded at write time with the same serving embedding adapter, so query
time adds no new external calls or failure modes. Boot is fail-open — a
missing/corrupt/superseeded file yields an empty store and never blocks
chat.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import secrets
import threading
from typing import Any, Protocol

SCHEMA_VERSION = "canonical-v2-manual-recall-v1"

_CHUNK_MAX_CHARS = 800
_CHUNK_MAX_PER_DOCUMENT = 200
_REASON_MAX = 500
_OPERATOR_MAX = 200

_FILE_NAME = "manual-recall.json"


class ManualRecallError(ValueError):
    """Raised for invalid manual recall operations (bad input, embedding
    validation failure, unsupported domain)."""


class EmbeddingAdapter(Protocol):
    """Serving embedding adapter shape (embed_batch + dimension)."""

    @property
    def dimension(self) -> int: ...

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


@dataclass(frozen=True, slots=True)
class ManualPoint:
    """One recallable point of manual knowledge."""

    point_id: str
    kind: str  # "upload_chunk" | "manual_record"
    domain: str
    display_name: str
    canonical_ref: str
    embedded_content: str
    vector: tuple[float, ...]
    status: str  # "active" | "reverted"
    ref_id: str
    chunk_index: int
    source_label: str
    doc_title: str
    operator: str
    reason: str
    created_at: str


# ---------------------------------------------------------------------------
# document chunking


def chunk_document_text(text: str, *, max_chars: int = _CHUNK_MAX_CHARS) -> list[str]:
    """Split extracted document text into recall-sized chunks.

    Paragraph-first packing (blank-line boundaries); single over-long
    paragraphs are hard-sliced. Raises on empty input or when the document
    would exceed the per-document chunk ceiling (bomb guard).
    """

    cleaned = (text or "").replace("\r\n", "\n").strip()
    if not cleaned:
        raise ManualRecallError("document text is empty")
    paragraphs = [
        piece.strip() for piece in re.split(r"\n\s*\n", cleaned) if piece.strip()
    ]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start : start + max_chars])
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    if len(chunks) > _CHUNK_MAX_PER_DOCUMENT:
        raise ManualRecallError(
            f"document exceeds {_CHUNK_MAX_PER_DOCUMENT} chunks"
        )
    return chunks


# ---------------------------------------------------------------------------
# manual record serialization (mirrors the release embedded-content shapes
# so downstream display-name/snippet parsing accepts manual points)


_SERIALIZE_KEYS = {
    "company": (
        "name",
        "aliases",
        "profile_summary",
        "product_description",
        "technology_route_summary",
        "industry",
        "tech_tags",
    ),
    "professor": (
        "name",
        "canonical_name_zh",
        "canonical_name_en",
        "aliases",
        "institution",
        "department",
        "title",
        "profile_summary",
        "research_directions",
    ),
    "paper": (
        "title",
        "title_zh",
        "abstract",
        "summary_text",
        "summary_zh",
        "tldr",
        "keywords",
        "fields_of_study",
    ),
    "patent": (
        "title",
        "title_en",
        "abstract",
        "summary_text",
        "technology_effect",
        "ipc_codes",
    ),
}


def serialize_manual_record(domain: str, payload: dict[str, Any]) -> str:
    """Serialize a manual record payload into embedded-content JSON."""

    keys = _SERIALIZE_KEYS.get(domain)
    if keys is None:
        raise ManualRecallError(f"unsupported domain for manual recall: {domain}")
    content = {key: payload[key] for key in keys if payload.get(key) is not None}
    if not content:
        raise ManualRecallError("manual record payload has no serializable fields")
    return json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# store


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _point_to_dict(point: ManualPoint) -> dict[str, Any]:
    raw = asdict(point)
    raw["vector"] = list(point.vector)
    return raw


def _point_from_dict(raw: dict[str, Any]) -> ManualPoint:
    if not isinstance(raw, dict):
        raise ManualRecallError("point entry is not an object")
    fields = {**raw, "vector": tuple(float(v) for v in raw["vector"])}
    return ManualPoint(**fields)


class ManualRecallStore:
    """Owns the writable sidecar of manual recall points."""

    def __init__(self, root: Path, embedding_adapter: EmbeddingAdapter) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._adapter = embedding_adapter
        self._file = self._root / _FILE_NAME
        self._lock = threading.Lock()
        self._points: dict[str, ManualPoint] = {}
        self._load()

    @property
    def store_path(self) -> Path:
        return self._file

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = self._file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError as exc:
            print(f"manual_recall_store=disabled (read: {exc})", flush=True)
            return
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ManualRecallError("store payload is not an object")
            if payload.get("schema_version") != SCHEMA_VERSION:
                raise ManualRecallError("store schema version differs")
            points = payload["points"]
            if not isinstance(points, list):
                raise ManualRecallError("store points are not a list")
            loaded: dict[str, ManualPoint] = {}
            for item in points:
                point = _point_from_dict(item)
                if len(point.vector) != self._adapter.dimension:
                    # Embedding dimension drift: skip the point rather than
                    # poisoning cosine scoring with a mismatched vector.
                    continue
                loaded[point.point_id] = point
            self._points = loaded
        except Exception as exc:  # noqa: BLE001 - boot stays fail-open
            print(f"manual_recall_store=disabled (load: {exc})", flush=True)
            self._points = {}

    def _persist_locked(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "points": [_point_to_dict(point) for point in self._points.values()],
        }
        tmp = self._file.with_name(f"{_FILE_NAME}.tmp")
        descriptor = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp, self._file)
        os.chmod(self._file, 0o600, follow_symlinks=False)

    # -- embedding -----------------------------------------------------------

    def _embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors = self._adapter.embed_batch(tuple(texts))
        if len(vectors) != len(texts):
            raise ManualRecallError("embedding cardinality mismatch")
        result: list[tuple[float, ...]] = []
        for vector in vectors:
            if len(vector) != self._adapter.dimension:
                raise ManualRecallError("embedding dimension mismatch")
            result.append(tuple(float(component) for component in vector))
        return result

    # -- writes ---------------------------------------------------------------

    def add_upload(
        self,
        *,
        domain: str,
        company_name: str,
        title: str,
        text: str,
        reason: str,
        operator: str,
        source_label: str,
        matched_canonical_id: str | None,
    ) -> tuple[str, int]:
        """Chunk + embed one confirmed document; returns (doc_id, points)."""

        name = company_name.strip()
        if not name:
            raise ManualRecallError("company_name must not be empty")
        clean_reason = reason.strip()
        if not clean_reason:
            raise ManualRecallError("reason must not be empty")
        clean_operator = operator.strip() or "unknown"
        chunks = chunk_document_text(text)
        vectors = self._embed(chunks)
        doc_id = f"doc-{secrets.token_hex(8)}"
        created = _utc_now_iso()
        canonical_ref = (
            matched_canonical_id.strip() if matched_canonical_id else ""
        ) or f"manual-upload:{doc_id}"
        points = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            embedded = json.dumps(
                {"name": name, "profile_summary": chunk, "source": source_label},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            points.append(
                ManualPoint(
                    point_id=f"chunk-{doc_id.removeprefix('doc-')}-{index}",
                    kind="upload_chunk",
                    domain=domain,
                    display_name=name,
                    canonical_ref=canonical_ref,
                    embedded_content=embedded,
                    vector=vector,
                    status="active",
                    ref_id=doc_id,
                    chunk_index=index,
                    source_label=source_label[:200],
                    doc_title=title.strip()[:200],
                    operator=clean_operator[:_OPERATOR_MAX],
                    reason=clean_reason[:_REASON_MAX],
                    created_at=created,
                )
            )
        with self._lock:
            self._points.update((point.point_id, point) for point in points)
            self._persist_locked()
        return doc_id, len(points)

    def add_manual_record(
        self,
        *,
        record_id: str,
        domain: str,
        manual_object_id: str,
        payload: dict[str, Any],
        operator: str,
        reason: str,
    ) -> str:
        """Embed one manually added record; returns the point id."""

        text = serialize_manual_record(domain, payload)
        display = payload.get("name") or payload.get("title") or manual_object_id
        vector = self._embed([text])[0]
        point = ManualPoint(
            point_id=f"manual-{record_id}",
            kind="manual_record",
            domain=domain,
            display_name=str(display)[:200],
            canonical_ref=manual_object_id,
            embedded_content=text,
            vector=vector,
            status="active",
            ref_id=record_id,
            chunk_index=0,
            source_label="manual-record",
            doc_title="",
            operator=(operator.strip() or "unknown")[:_OPERATOR_MAX],
            reason=reason.strip()[:_REASON_MAX],
            created_at=_utc_now_iso(),
        )
        with self._lock:
            self._points[point.point_id] = point
            self._persist_locked()
        return point.point_id

    # -- tombstones -------------------------------------------------------------

    def tombstone_by_ref(self, ref_id: str) -> int:
        """Revert every active point carrying this ref id; returns the count."""

        with self._lock:
            hits = [
                point_id
                for point_id, point in self._points.items()
                if point.ref_id == ref_id and point.status == "active"
            ]
            for point_id in hits:
                self._points[point_id] = replace(
                    self._points[point_id], status="reverted"
                )
            if hits:
                self._persist_locked()
            return len(hits)

    def tombstone_point(self, point_id: str) -> bool:
        """Revert one point; False when unknown or already reverted."""

        with self._lock:
            point = self._points.get(point_id)
            if point is None or point.status != "active":
                return False
            self._points[point_id] = replace(point, status="reverted")
            self._persist_locked()
            return True

    # -- reads -----------------------------------------------------------------

    def active_points(self) -> tuple[ManualPoint, ...]:
        """Read-only view of the currently recallable points."""

        with self._lock:
            return tuple(
                point for point in self._points.values() if point.status == "active"
            )

    def list_uploads(self) -> tuple[dict[str, Any], ...]:
        """One entry per uploaded document, newest first."""

        with self._lock:
            uploads: dict[str, dict[str, Any]] = {}
            for point in self._points.values():
                if point.kind != "upload_chunk":
                    continue
                entry = uploads.setdefault(
                    point.ref_id,
                    {
                        "doc_id": point.ref_id,
                        "company_name": point.display_name,
                        "title": point.doc_title,
                        "source_label": point.source_label,
                        "chunk_count": 0,
                        "operator": point.operator,
                        "reason": point.reason,
                        "created_at": point.created_at,
                        "status": "reverted",
                    },
                )
                if point.status == "active":
                    entry["status"] = "active"
                    entry["chunk_count"] += 1
            return tuple(
                sorted(uploads.values(), key=lambda item: item["created_at"], reverse=True)
            )


__all__ = [
    "SCHEMA_VERSION",
    "EmbeddingAdapter",
    "ManualPoint",
    "ManualRecallError",
    "ManualRecallStore",
    "chunk_document_text",
    "serialize_manual_record",
]
