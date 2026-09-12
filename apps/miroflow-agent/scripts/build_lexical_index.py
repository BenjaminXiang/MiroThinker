#!/usr/bin/env python3
"""Build the derived lexical index for one sealed serving pack (retrieval-v2).

Reads the pack's lookup SQLite read-only, segments every document with jieba
(domain dictionary = entity name forms), and writes the FTS5 artifact +
manifest OUTSIDE the sealed pack. Idempotent: an artifact bound to the same
release id and pack file fingerprint is reused.

Usage:
  cd apps/miroflow-agent && uv run python scripts/build_lexical_index.py \
      --pack /var/tmp/mirothinker-data-v2/serving-pack-run14-sealed \
      --out /var/tmp/mirothinker-data-v2/derived/lexical \
      --release-id candidate-v2-20260819-r1
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
import sys
import time

REPO_APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_APP_ROOT))

from src.data_agents.canonical_v2 import lexical_index as lex  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read_isolated import (  # noqa: E402
    _entity_name_forms,
)


def _dictionary_words(lookup_sqlite: Path) -> tuple[str, ...]:
    words: set[str] = set()
    connection = sqlite3.connect(f"file:{lookup_sqlite}?mode=ro", uri=True)
    try:
        for (document_json,) in connection.execute(
            "SELECT document_json FROM lookup_document"
        ):
            parsed = lex._document_payload(document_json)
            if parsed is None:
                continue
            _document_id, _canonical_id, domain, content = parsed
            try:
                payload = json.loads(content)
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            terms: set[str] = set()
            for key in ("name", "normalized_name", "title", "canonical_name_zh"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    terms.add(value.strip())
            aliases = payload.get("aliases")
            if isinstance(aliases, list):
                for item in aliases:
                    if isinstance(item, str) and item.strip():
                        terms.add(item.strip())
                    elif isinstance(item, dict):
                        name = item.get("name")
                        if isinstance(name, str) and name.strip():
                            terms.add(name.strip())
            if not terms:
                continue
            words.update(_entity_name_forms(domain, frozenset(terms)))
    finally:
        connection.close()
    return tuple(sorted(words))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", required=True, help="sealed pack directory")
    parser.add_argument("--out", required=True, help="artifact root directory")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    pack = Path(args.pack).resolve()
    lookup_sqlite = pack / "lookup.sqlite3"
    if not lookup_sqlite.is_file():
        print(f"lookup.sqlite3 missing under {pack}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    words = _dictionary_words(lookup_sqlite)
    dictionary_s = time.perf_counter() - started
    print(f"dictionary words: {len(words)} ({dictionary_s:.1f}s)")

    out_dir = Path(args.out).resolve() / args.release_id
    build_started = time.perf_counter()
    lex.build_lexical_index(
        lookup_sqlite=lookup_sqlite,
        out_dir=out_dir,
        release_id=args.release_id,
        dictionary_words=words,
        built_at=datetime.now(UTC).isoformat(),
        force=args.force,
    )
    build_s = time.perf_counter() - build_started
    manifest = lex.LexicalIndexManifest.from_json(
        (out_dir / lex.MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    index_mb = (out_dir / lex.INDEX_FILENAME).stat().st_size / (1024 * 1024)
    print(
        f"artifact {out_dir} | documents {manifest.document_count} | "
        f"{index_mb:.1f} MB | build {build_s:.1f}s | "
        f"pack sha {manifest.pack_lookup_sha256[:12]}…"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
