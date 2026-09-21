#!/usr/bin/env python3
"""Pre-flight probe: the *build's own* embedding path, at batch 20, for real.

Why this exists: the runner's embedding phase starts only after its
restore/merge phase, and the window's first question — "does the first batch get
a 200 at the declared batch size, through the code the build will use?" — should
not wait hours to be answered. This drives the same chain the build drives:

    load_content_addressed_embedding_adapter(bundle, role="document")
      → _DashScopeNativeEmbeddingAdapter → DashScopeTextEmbeddingClient → gateway

with 20 real documents taken **read-only** from the live serving pack's
`lookup.sqlite3` (the same table `index_point` the build embeds from), so the
text shapes and sizes match the corpus instead of the probe's own strings.

    switch_line/.venv is not used; the deployment interpreter runs it:
    PYTHONPATH=$SWITCH_LINE/apps/miroflow-agent \\
      CANONICAL_V2_EMBEDDING_API_KEY="$(cat /var/tmp/mirothinker-qianwen-api-key)" \\
      /home/longxiang/MiroThinker/.venv/bin/python probe_build_embedding_path.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
import time

SWITCH_LINE = Path(__file__).resolve().parents[3]
APP_ROOT = SWITCH_LINE / "apps/miroflow-agent"
sys.path.insert(0, str(APP_ROOT))

from src.data_agents.canonical_v2.knowledge_build_isolated import (  # noqa: E402
    EMBEDDING_ROLE_DOCUMENT,
    load_content_addressed_embedding_adapter,
)

BUNDLE = (
    SWITCH_LINE
    / ".agents/runs/embedding-model-switch-v2"
    / "qwen3.7-text-embedding-flash-embedding-bundle-v1.json"
)
LIVE_PACK = Path(
    os.environ.get(
        "PROBE_LIVE_PACK",
        "/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound",
    )
)
OUTPUT = Path(
    os.environ.get(
        "PROBE_OUT", str(Path(__file__).with_name("build-embedding-path-probe.json"))
    )
)


def _document_texts(count: int = 20) -> list[str]:
    """``count`` real ``embedded_content`` values, longest first (worst case)."""

    query = (
        "SELECT json_extract(point_json, '$.embedded_content') AS content"
        " FROM index_point"
        " WHERE content IS NOT NULL AND length(content) > 200"
        " ORDER BY length(content) DESC LIMIT ?"
    )
    with sqlite3.connect(f"file:{LIVE_PACK / 'lookup.sqlite3'}?mode=ro", uri=True) as conn:
        rows = conn.execute(query, (count,)).fetchall()
    texts = [str(row[0]) for row in rows if row[0]]
    if len(texts) != count:
        raise SystemExit(f"expected {count} documents from the live pack, got {len(texts)}")
    return texts


def main() -> int:
    if not os.environ.get("CANONICAL_V2_EMBEDDING_API_KEY", "").strip():
        raise SystemExit("CANONICAL_V2_EMBEDDING_API_KEY is not set")

    adapter = load_content_addressed_embedding_adapter(
        BUNDLE, role=EMBEDDING_ROLE_DOCUMENT
    )
    texts = _document_texts()
    started = time.perf_counter()
    vectors = adapter.embed_batch(tuple(texts))
    elapsed = time.perf_counter() - started

    report = {
        "bundle": BUNDLE.name,
        "role": adapter.role,
        "model_id": adapter.model_id,
        "dimension": adapter.dimension,
        "declared_batch_size": adapter.batch_size,
        "authority_sha256": adapter.authority_sha256,
        "base_url": adapter.base_url,
        "documents": len(texts),
        "document_chars_total": sum(len(text) for text in texts),
        "document_chars_max": max(len(text) for text in texts),
        "rows_returned": len(vectors),
        "row_dimensions": len(vectors[0]) if vectors else 0,
        "nonzero_vectors": sum(1 for vector in vectors if any(value != 0.0 for value in vector)),
        "seconds": round(elapsed, 3),
        "seconds_per_document": round(elapsed / len(texts), 4),
    }
    report["verdict"] = (
        "the build's document-role path answers at batch "
        f"{adapter.batch_size}: {len(vectors)} rows x {report['row_dimensions']} dims"
        if len(vectors) == len(texts) and report["row_dimensions"] == adapter.dimension
        else "UNEXPECTED: the provider answered a different shape"
    )
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
