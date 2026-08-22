"""Batch-embed light-lane entities via the school Qwen3 endpoint.

Resumable: skips entities already embedded (content-hash keyed), commits per
batch, writes a checkpoint log line per 50 batches.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import requests

DATABASE = "miroflow_light_lane_r1"
ENDPOINT = "http://100.64.0.27:18005/v1/embeddings"
MODEL = "Qwen/Qwen3-Embedding-8B"
KEY = Path("/home/longxiang/MiroThinker/.sglang_api_key").read_text().splitlines()[0]
BATCH = 16
WORKERS = 24
LIMIT_CHARS = 1200


def _clip(text: str | None) -> str:
    if not text:
        return ""
    return text[:LIMIT_CHARS]


def entity_text(entity_type: str, record: dict) -> str:
    if entity_type == "professor":
        directions = record.get("research_directions") or []
        if isinstance(directions, str):
            directions = [directions]
        return " ".join(filter(None, [
            record.get("name"), record.get("name_en"),
            record.get("institution"), record.get("department"),
            record.get("title"), "研究方向: " + "; ".join(directions),
        ]))
    if entity_type == "company":
        return " ".join(filter(None, [
            record.get("company_name"), record.get("industry"),
            record.get("business"), _clip(record.get("product_description")),
            _clip(record.get("application_scenarios")),
        ]))
    if entity_type == "patent":
        applicants = record.get("applicants") or []
        return " ".join(filter(None, [
            record.get("title"), "、".join(applicants), record.get("patent_type"),
            _clip(record.get("abstract")), _clip(record.get("technology_effect")),
        ]))
    if entity_type == "paper":
        authors = [a.get("name", "") for a in (record.get("authors") or [])][:12]
        return " ".join(filter(None, [
            record.get("title"), " ".join(authors), record.get("venue"),
            _clip(record.get("abstract")), _clip(record.get("summary_zh")),
        ]))
    raise ValueError(entity_type)


def fetch_entities(connection) -> list[tuple[str, str, str, str]]:
    rows = []
    for entity_type, table, id_column in (
        ("professor", "professor", "professor_id"),
        ("company", "company", "company_name"),
        ("patent", "patent", "patent_id"),
        ("paper", "paper", "paper_id"),
    ):
        for entity_id, raw in connection.execute(
            f"SELECT {id_column}, raw FROM {table}"
        ).fetchall():
            text = entity_text(entity_type, raw)
            if not text:
                continue
            content_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            rows.append((entity_type, str(entity_id), content_sha, text))
    return rows


def call_endpoint(batch: list[tuple[str, str, str, str]]) -> list[list[float]]:
    response = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {KEY}"},
        json={"model": MODEL, "input": [item[3] for item in batch]},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    data = sorted(payload["data"], key=lambda item: item["index"])
    return [item["embedding"] for item in data]


def main() -> None:
    connection = psycopg.connect(
        f"postgresql://miroflow@127.0.0.1:55458/{DATABASE}", autocommit=True
    )
    done = {
        (row[0], row[1]): row[2]
        for row in connection.execute(
            "SELECT entity_type, entity_id, content_sha256 FROM embedding"
        ).fetchall()
    }
    entities = fetch_entities(connection)
    pending = [
        item for item in entities
        if done.get((item[0], item[1])) != item[2]
    ]
    print(f"entities={len(entities)} already={len(entities)-len(pending)} pending={len(pending)}", flush=True)
    batches = [pending[i:i + BATCH] for i in range(0, len(pending), BATCH)]

    stats = {"ok": 0, "fail": 0}

    def run_batch(index_batch):
        index, batch = index_batch
        for attempt in range(4):
            try:
                vectors = call_endpoint(batch)
                with connection.cursor() as cursor:
                    for (entity_type, entity_id, content_sha, _), vector in zip(batch, vectors, strict=True):
                        vector_literal = "[" + ",".join(repr(value) for value in vector) + "]"
                        cursor.execute(
                            "INSERT INTO embedding (vec_id, entity_type, entity_id, "
                            "content_sha256, dim, vec) VALUES (%s, %s, %s, %s, %s, %s::vector) "
                            "ON CONFLICT (vec_id) DO UPDATE SET "
                            "content_sha256 = EXCLUDED.content_sha256, vec = EXCLUDED.vec",
                            (
                                f"{entity_type}:{entity_id}", entity_type, entity_id,
                                content_sha, len(vector), vector_literal,
                            ),
                        )
                stats["ok"] += len(batch)
                return
            except Exception as exc:  # noqa: BLE001 - per-batch retry with backoff
                if attempt == 3:
                    stats["fail"] += len(batch)
                    print(f"batch {index} failed: {exc}", flush=True)
                    return
                time.sleep(2 ** attempt)

    started = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for count, _ in enumerate(pool.map(run_batch, enumerate(batches)), 1):
            if count % 50 == 0:
                elapsed = time.time() - started
                print(
                    f"{count}/{len(batches)} batches, ok={stats['ok']} "
                    f"fail={stats['fail']} elapsed={elapsed:.0f}s",
                    flush=True,
                )
    print(json.dumps(stats), flush=True)
    connection.close()
    sys.exit(1 if stats["fail"] else 0)


if __name__ == "__main__":
    main()
