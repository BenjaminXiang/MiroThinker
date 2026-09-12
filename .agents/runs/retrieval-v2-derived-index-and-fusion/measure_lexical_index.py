#!/usr/bin/env python3
"""Offline measurement for retrieval-v2 Step 1: index latency + candidate
quality vs the substring lane (same sealed pack).

Window classification (the decision-relevant view of the P2 leak):

- typed     : the phrase (or all of its content tokens) appears in the
              document's NAME or TAGS surface — the place the field contract
              blesses for "this entity operates in the category".
- body_only : the phrase only appears in body text (profile/description) —
              the mention-channel the old lane cannot distinguish; these are
              the off-category leak candidates.
- neither   : matched through some other flattened field.

Index top-64 (BM25 order) vs old-lane document-order top-64 for the same
phrase; plus the old lane's full matched set for context.

Usage:
  cd apps/miroflow-agent && uv run python \
    /home/longxiang/MiroThinker/.agents/runs/retrieval-v2-derived-index-and-fusion/measure_lexical_index.py \
    --pack /var/tmp/mirothinker-data-v2/serving-pack-run14-sealed \
    --artifact /var/tmp/mirothinker-data-v2/derived/lexical \
    --release-id candidate-v2-20260819-r1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

REPO = Path("/home/longxiang/MiroThinker")
WORKTREE = REPO / ".worktrees/canonical-v2-s11-consolidation"
sys.path.insert(0, str(WORKTREE / "apps/miroflow-agent"))

from src.data_agents.canonical_v2 import lexical_index as lex  # noqa: E402

PHRASES = (
    "激光雷达",
    "储能电池",
    "酒店送餐机器人",
    "PCB打板",
    "具身智能",
    "无人机整机",
    "医疗器械",
)
GENERIC_TOKENS = {"深圳", "深圳市", "公司", "有限", "科技", "企业", "做", "的"}


def _surface_text(payload: dict, keys: tuple[str, ...]) -> str:
    parts: list[str] = []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("name"), str):
                    parts.append(item["name"])
        elif isinstance(value, dict) and isinstance(value.get("name"), str):
            parts.append(value["name"])
    return " ".join(parts)


NAME_KEYS = ("name", "normalized_name", "title", "canonical_name_zh")
TAG_KEYS = (
    "aliases",
    "industry",
    "industry_tags",
    "tech_tags",
    "products",
    "applicants",
    "inventors",
    "authors",
)
BODY_KEYS = (
    "profile_summary",
    "product_description",
    "technology_route_summary",
    "summary_text",
    "team_description",
)


def classify(payload: dict, phrase: str, segmenter: lex.Segmenter) -> str:
    typed = _surface_text(payload, NAME_KEYS + TAG_KEYS)
    body = _surface_text(payload, BODY_KEYS)
    tokens = [t for t in segmenter.tokens(phrase) if t not in GENERIC_TOKENS]

    def in_typed() -> bool:
        return phrase in typed or (bool(tokens) and all(t in typed for t in tokens))

    def in_body() -> bool:
        return phrase in body or (bool(tokens) and all(t in body for t in tokens))

    if in_typed():
        return "typed"
    if in_body():
        return "body_only"
    return "neither"


def shares(documents: list[tuple[str, dict]], phrase: str, segmenter: lex.Segmenter) -> str:
    counts = {"typed": 0, "body_only": 0, "neither": 0}
    for _document_id, payload in documents:
        counts[classify(payload, phrase, segmenter)] += 1
    total = max(1, len(documents))
    return (
        f"typed={counts['typed'] / total:.2f} "
        f"body_only={counts['body_only'] / total:.2f} "
        f"neither={counts['neither'] / total:.2f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--release-id", required=True)
    args = parser.parse_args()

    lookup = Path(args.pack) / "lookup.sqlite3"
    records: list[tuple[str, str, dict]] = []
    started = time.perf_counter()
    connection = sqlite3.connect(f"file:{lookup}?mode=ro", uri=True)
    try:
        for (document_json,) in connection.execute(
            "SELECT document_json FROM lookup_document"
        ):
            parsed = lex._document_payload(document_json)
            if parsed is None:
                continue
            document_id, _canonical_id, _domain, content = parsed
            try:
                payload = json.loads(content)
            except (TypeError, ValueError):
                payload = {}
            records.append((document_id, json.dumps(payload, ensure_ascii=False), payload))
    finally:
        connection.close()
    print(f"loaded {len(records)} documents in {time.perf_counter() - started:.1f}s")

    index = lex.LexicalIndex.open(
        Path(args.artifact) / args.release_id,
        expected_release_id=args.release_id,
        lookup_sqlite=lookup,
    )
    assert index is not None
    payload_by_id = {document_id: payload for document_id, _raw, payload in records}
    segmenter = lex.Segmenter(
        tuple(
            row[0]
            for row in index._connection.execute("SELECT word FROM segment_dict")
        )
    )

    for phrase in PHRASES:
        started = time.perf_counter()
        hits = index.search(phrase, domains=("company",), limit=128)
        latency_ms = (time.perf_counter() - started) * 1000
        index_window = [
            (document_id, payload_by_id[document_id])
            for document_id, _score in hits[:64]
            if document_id in payload_by_id
        ]
        matched = [record for record in records if phrase in record[1]]
        old_window = [(doc_id, payload) for doc_id, _raw, payload in matched[:64]]
        print(
            f"{phrase}: index {latency_ms:.1f}ms hits={len(hits)} | "
            f"index-top64 {shares(index_window, phrase, segmenter)} | "
            f"old-matched={len(matched)} old-top64 {shares(old_window, phrase, segmenter)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
