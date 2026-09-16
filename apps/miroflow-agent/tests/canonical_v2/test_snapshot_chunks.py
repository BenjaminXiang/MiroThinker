"""Chunked run-snapshot persistence helpers (C2_0013)."""

from __future__ import annotations

import pytest

from src.data_agents.canonical_v2.snapshot_chunks import (
    INLINE_LIMIT_BYTES,
    reassemble_snapshot_chunks,
    serialize_snapshot_chunks,
)


def test_small_snapshots_stay_inline() -> None:
    value = {"release_id": "candidate-v2-test", "rows": [1, 2, 3]}
    chunks = serialize_snapshot_chunks(value)
    assert not chunks.is_chunked
    assert chunks.inline_jsonb == value
    assert chunks.chunks == ()


def test_large_snapshots_chunk_and_roundtrip() -> None:
    value = {
        "release_id": "candidate-v2-large",
        # ~300 MB of payload forces the chunked path past the inline limit.
        "assertions": [
            {"assertion_id": f"a:{index:07d}", "value": "x" * 512}
            for index in range(600_000)
        ],
    }
    chunks = serialize_snapshot_chunks(value)
    assert chunks.is_chunked
    assert chunks.inline_jsonb is None
    assert len(chunks.chunks) >= 2
    rows = [
        {"chunk_index": index, "chunk_b64": text, "chunk_sha256": digest}
        for index, text, digest in chunks.chunks
    ]
    assert reassemble_snapshot_chunks(rows) == value


def test_chunk_hash_mismatch_is_rejected() -> None:
    value = {
        "release_id": "candidate-v2-tamper",
        "assertions": [
            {"assertion_id": f"a:{index:07d}", "value": "y" * 512}
            for index in range(600_000)
        ],
    }
    chunks = serialize_snapshot_chunks(value)
    assert chunks.is_chunked
    rows = [
        {"chunk_index": index, "chunk_b64": text, "chunk_sha256": digest}
        for index, text, digest in chunks.chunks
    ]
    rows[0] = {**rows[0], "chunk_b64": rows[0]["chunk_b64"][:-2] + "=="}
    with pytest.raises(ValueError, match="chunk hash differs"):
        reassemble_snapshot_chunks(rows)


def test_chunk_gap_is_rejected() -> None:
    value = {
        "release_id": "candidate-v2-gap",
        "assertions": [
            {"assertion_id": f"a:{index:07d}", "value": "z" * 512}
            for index in range(600_000)
        ],
    }
    chunks = serialize_snapshot_chunks(value)
    rows = [
        {"chunk_index": index, "chunk_b64": text, "chunk_sha256": digest}
        for index, text, digest in chunks.chunks
    ]
    with pytest.raises(ValueError, match="not contiguous"):
        reassemble_snapshot_chunks(rows[1:])


def test_inline_limit_is_below_the_postgres_jsonb_cap() -> None:
    assert INLINE_LIMIT_BYTES < 268_435_455
