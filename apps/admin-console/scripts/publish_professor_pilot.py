"""Publish enriched professors into the manual-recall store (pilot batch).

The enrichment writes biographies into the collection database, but the serving
line reads the manual-recall store, which is loaded into memory at boot. This
script adds the enriched professors as `manual_record` points — through the same
store class the service uses, so the on-disk format cannot drift.

Safety:
- ``--dry-run`` prints the payloads without embedding or writing;
- the caller must back up ``var/manual-recall-v1`` first (the runbook says so);
- the store loader is fail-open, but a broken file still drops existing manual
  points, hence the backup;
- records are deterministic (``pilot-<professor_id>``), so re-running replaces
  rather than duplicates.

Usage::

    python scripts/publish_professor_pilot.py \
        --dsn postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1 \
        --store-dir /root/deploy/fullstack-v2/var/manual-recall-v1 \
        [--ids id1,id2] [--limit 20] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request

import psycopg

from backend.services.canonical_v2_manual_recall import ManualRecallStore

DIMENSION = 1024
BATCH = 16
PLACEHOLDER = "待补全。"


class HttpEmbeddingAdapter:
    """Minimal adapter: batch POST to the serving embedding endpoint."""

    def __init__(self, endpoint: str, api_key: str, model: str) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._model = model

    @property
    def dimension(self) -> int:
        return DIMENSION

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(texts), BATCH):
            body = {
                "model": self._model,
                "input": {"texts": list(texts[start : start + BATCH])},
                "parameters": {"text_type": "document", "dimension": DIMENSION},
            }
            request = urllib.request.Request(
                self._endpoint,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read())
            vectors.extend(
                tuple(entry["embedding"]) for entry in payload["output"]["embeddings"]
            )
        return tuple(vectors)


def load_professors(dsn: str, ids: list[str] | None, limit: int) -> list[dict]:
    connection = psycopg.connect(dsn)
    try:
        with connection.cursor() as cursor:
            params: list[object] = [PLACEHOLDER]
            where = "profile_summary IS NOT NULL AND profile_summary <> %s"
            if ids:
                where += " AND professor_id = ANY(%s)"
                params.append(ids)
            cursor.execute(
                "SELECT p.professor_id, p.canonical_name, p.profile_summary,"
                " pa.institution, pa.department, sp.url"
                " FROM professor p"
                " JOIN professor_affiliation pa ON pa.professor_id = p.professor_id"
                " AND pa.is_primary"
                " LEFT JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id"
                f" WHERE {where} ORDER BY p.canonical_name LIMIT %s",
                params + [limit],
            )
            return [
                {
                    "professor_id": row[0],
                    "name": row[1],
                    "profile_summary": row[2],
                    "institution": row[3],
                    "department": row[4],
                    "homepage": row[5],
                }
                for row in cursor.fetchall()
            ]
    finally:
        connection.close()


def build_payload(record: dict) -> dict:
    payload = {
        "name": record["name"],
        "institution": record["institution"],
        "profile_summary": record["profile_summary"],
    }
    if record.get("department"):
        payload["department"] = record["department"]
    if record.get("homepage"):
        payload["homepage"] = record["homepage"]
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--store-dir", required=True)
    parser.add_argument("--ids", default=None, help="comma separated professor ids")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    ids = [value.strip() for value in args.ids.split(",")] if args.ids else None
    records = load_professors(args.dsn, ids, args.limit)
    print(f"professors to publish: {len(records)}")

    if args.dry_run:
        for record in records:
            print(
                f"  {record['name']} ({record['institution']}) "
                f"{len(record['profile_summary'])} chars"
            )
            print(f"    {record['profile_summary'][:120]}")
        return 0

    from src.data_agents.canonical_v2.managed_runtime import (
        apply_managed_runtime_config,
    )

    apply_managed_runtime_config()
    base_url = os.environ.get(
        "CANONICAL_V2_EMBEDDING_BASE_URL", "https://maas.qianwenaiapi.com/api/v1"
    ).rstrip("/")
    api_key = os.environ.get("CANONICAL_V2_EMBEDDING_API_KEY", "")
    if not api_key:
        print("missing CANONICAL_V2_EMBEDDING_API_KEY", file=sys.stderr)
        return 2
    adapter = HttpEmbeddingAdapter(
        endpoint=f"{base_url}/services/embeddings/text-embedding/text-embedding",
        api_key=api_key,
        model=os.environ.get(
            "CANONICAL_V2_EMBEDDING_MODEL", "qwen3.7-text-embedding-flash"
        ),
    )
    store = ManualRecallStore(Path(args.store_dir), adapter)
    print(f"store points before: {len(store.active_points())}")

    written = 0
    for record in records:
        point_id = store.add_manual_record(
            record_id=f"pilot-{record['professor_id']}",
            domain="professor",
            manual_object_id=record["professor_id"],
            payload=build_payload(record),
            operator="pilot",
            reason="web enrichment 2026-10-27 (pack thin profiles)",
        )
        written += 1
        print(f"  {record['name']}: {point_id}")

    print(f"written: {written}; store points after: {len(store.active_points())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
