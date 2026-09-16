"""Chunked persistence for run-snapshot payloads that exceed the jsonb cap.

PostgreSQL rejects a single jsonb value larger than 268435455 bytes. Full-scale
rebuild snapshots (identity resolution, relationship projection) serialize
well past that cap, so their run rows may store the payload as base64 text
chunks in a companion ``*_content_chunk`` table while the inline jsonb
columns stay NULL. Chunk rows carry their own sha256; the run row keeps the
aggregate content hash it always carried, so readback verification composes
chunk hashes plus the aggregate exactly like the inline path.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

# 64 MiB of base64 text per chunk keeps every jsonb value far below the
# 256 MiB program limit while bounding reassembly memory.
CHUNK_BYTES = 64 * 1024 * 1024
# Snapshots at or below this serialized size may keep using the inline jsonb
# column; anything larger must be chunked.
INLINE_LIMIT_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SnapshotChunks:
    """One payload serialized, optionally split into hash-pinned chunks."""

    inline_jsonb: Any | None
    chunks: tuple[tuple[int, str, str], ...]  # (index, b64_text, sha256)

    @property
    def is_chunked(self) -> bool:
        return self.inline_jsonb is None


def serialize_snapshot_chunks(value: Any) -> SnapshotChunks:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(payload) <= INLINE_LIMIT_BYTES:
        return SnapshotChunks(inline_jsonb=value, chunks=())
    encoded = base64.b64encode(payload).decode("ascii")
    chunks: list[tuple[int, str, str]] = []
    for index in range(0, len(encoded), CHUNK_BYTES):
        chunk = encoded[index : index + CHUNK_BYTES]
        digest = hashlib.sha256(chunk.encode("ascii")).hexdigest()
        chunks.append((len(chunks), chunk, digest))
    return SnapshotChunks(inline_jsonb=None, chunks=tuple(chunks))


def reassemble_snapshot_chunks(rows: list[dict[str, Any]]) -> Any:
    """Rebuild the payload from ordered chunk rows, verifying every hash."""
    if not rows:
        raise ValueError("snapshot chunk rows are empty")
    ordered = sorted(rows, key=lambda row: int(row["chunk_index"]))
    expected_indexes = list(range(len(ordered)))
    if [int(row["chunk_index"]) for row in ordered] != expected_indexes:
        raise ValueError("snapshot chunk rows are not contiguous")
    pieces: list[str] = []
    for row in ordered:
        text = row["chunk_b64"]
        digest = row["chunk_sha256"]
        if not isinstance(text, str) or not isinstance(digest, str):
            raise ValueError("snapshot chunk row is malformed")
        if hashlib.sha256(text.encode("ascii")).hexdigest() != digest:
            raise ValueError("snapshot chunk hash differs")
        pieces.append(text)
    payload = base64.b64decode("".join(pieces).encode("ascii"))
    return json.loads(payload.decode("utf-8"))
