#!/usr/bin/env python3
"""Produce a deterministic fingerprint from PostgreSQL 16 schema-only dump bytes."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import TypedDict


_RANDOM_CONTROL_PREFIXES = (b"\\restrict ", b"\\unrestrict ")


class SchemaFingerprint(TypedDict):
    normalized_sha256: str
    normalized_bytes: int
    removed_control_lines: int


def normalize_schema_dump(payload: bytes) -> tuple[bytes, int]:
    """Remove only pg_dump's per-run random psql restriction control lines."""
    kept: list[bytes] = []
    removed = 0
    for line in payload.splitlines(keepends=True):
        if line.startswith(_RANDOM_CONTROL_PREFIXES):
            removed += 1
        else:
            kept.append(line)
    return b"".join(kept), removed


def fingerprint_schema_dump(payload: bytes) -> SchemaFingerprint:
    """Return a content fingerprint without exposing the schema dump itself."""
    normalized, removed = normalize_schema_dump(payload)
    return {
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        "normalized_bytes": len(normalized),
        "removed_control_lines": removed,
    }


def main() -> int:
    result = fingerprint_schema_dump(sys.stdin.buffer.read())
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
