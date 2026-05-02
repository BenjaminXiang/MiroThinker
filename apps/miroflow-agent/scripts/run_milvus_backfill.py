#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from dataclasses import asdict
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.paper.milvus_backfill import backfill_paper_chunks  # noqa: E402
from src.data_agents.professor.vectorizer import EmbeddingClient  # noqa: E402
from src.data_agents.providers.local_api_key import load_local_api_key  # noqa: E402
from src.data_agents.storage.milvus_collections import (  # noqa: E402
    PAPER_CHUNKS_COLLECTION,
    PROFESSOR_PROFILES_COLLECTION,
    drop_paper_chunks_collection,
    drop_professor_profiles_collection,
    ensure_professor_profiles_collection,
)

logger = logging.getLogger(__name__)


def _open_database_connection(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, row_factory=dict_row)


def _open_milvus_client(uri: str):
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        from pymilvus import MilvusClient

    return MilvusClient(uri=uri)


def _open_embedding_client() -> EmbeddingClient:
    return EmbeddingClient(api_key=load_local_api_key())


def _load_resume_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()

    resume_ids: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            logger.warning("Skipping corrupt resume line %d in %s", line_number, path)
            continue
        paper_id = payload.get("paper_id")
        if isinstance(paper_id, str) and paper_id:
            resume_ids.add(paper_id)
    return resume_ids


_PROFESSOR_COLLECTION = PROFESSOR_PROFILES_COLLECTION
_PROFESSOR_EXPECTED_FIELDS = [
    "id",
    "name",
    "institution",
    "department",
    "title",
    "profile_summary",
    "profile_vector",
    "h_index",
    "citation_count",
    "paper_count",
]


def _ensure_professor_collection(milvus_client) -> None:
    ensure_professor_profiles_collection(milvus_client)


_PROFESSOR_SQL = """
    SELECT p.professor_id,
           p.canonical_name,
           p.canonical_name_en,
           p.profile_summary,
           p.profile_raw_text,
           p.h_index,
           p.citation_count,
           p.paper_count,
           pa.institution,
           pa.department,
           pa.title
      FROM professor p
      LEFT JOIN LATERAL (
          SELECT institution, department, title
            FROM professor_affiliation
           WHERE professor_id = p.professor_id
           ORDER BY is_primary DESC NULLS LAST,
                    is_current DESC NULLS LAST,
                    start_year DESC NULLS LAST
           LIMIT 1
      ) pa ON true
     WHERE p.canonical_name IS NOT NULL
"""


def _compose_profile_text(row: dict) -> str:
    name = str(row.get("canonical_name") or "").strip()
    institution = str(row.get("institution") or "").strip()
    department = str(row.get("department") or "").strip()
    title = str(row.get("title") or "").strip()
    summary = str(row.get("profile_summary") or "").strip()
    raw = str(row.get("profile_raw_text") or "").strip()

    parts: list[str] = []
    header = name
    if title or institution or department:
        chunks: list[str] = []
        if title:
            chunks.append(title)
        loc = " ".join(c for c in (institution, department) if c)
        if loc:
            chunks.append(loc)
        header = f"{name}，{'，'.join(chunks)}" if chunks else name
    parts.append(header)

    if summary:
        parts.append(summary)
    elif raw:
        parts.append(raw[:1800])

    return "\n".join(parts)


def _backfill_professor_domain(
    conn,
    milvus_client,
    embedding_client,
    *,
    limit=None,
    batch_size=32,
    resume_ids=None,
):
    started_at = time.monotonic()
    _ensure_professor_collection(milvus_client)

    sql = _PROFESSOR_SQL
    params: list[object] = []
    if resume_ids:
        placeholders = ", ".join(["%s"] * len(resume_ids))
        sql += f" AND p.professor_id NOT IN ({placeholders})"
        params.extend(sorted(resume_ids))
    sql += " ORDER BY p.professor_id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))

    rows = conn.execute(sql, params).fetchall()
    profs_total = len(rows)
    profs_processed = 0
    profs_skipped = 0
    profs_with_errors = 0

    for batch_start in range(0, profs_total, max(1, batch_size)):
        batch_rows = rows[batch_start : batch_start + max(1, batch_size)]
        texts: list[str] = []
        ids: list[str] = []
        row_refs: list[dict] = []
        for row in batch_rows:
            text = _compose_profile_text(row)
            if not text.strip():
                profs_skipped += 1
                continue
            ids.append(str(row["professor_id"]))
            texts.append(text[:3800])
            row_refs.append(row)

        if not texts:
            continue

        try:
            vectors = embedding_client.embed_batch(texts)
        except Exception as exc:
            profs_with_errors += len(texts)
            logger.warning("Embedding batch failed (%d profs): %s", len(texts), exc)
            continue

        payload = []
        for prof_id, row, text, vector in zip(
            ids, row_refs, texts, vectors, strict=False
        ):
            payload.append(
                {
                    "id": prof_id,
                    "name": str(row.get("canonical_name") or "")[:128],
                    "institution": str(row.get("institution") or "")[:256],
                    "department": str(row.get("department") or "")[:128],
                    "title": str(row.get("title") or "")[:64],
                    "profile_summary": text[:4000],
                    "profile_vector": vector,
                    "h_index": row.get("h_index"),
                    "citation_count": row.get("citation_count"),
                    "paper_count": row.get("paper_count"),
                }
            )

        try:
            milvus_client.upsert(collection_name=_PROFESSOR_COLLECTION, data=payload)
        except Exception as exc:
            profs_with_errors += len(payload)
            logger.warning("Milvus upsert failed (%d profs): %s", len(payload), exc)
            continue

        profs_processed += len(payload)

    return {
        "profs_total": profs_total,
        "profs_processed": profs_processed,
        "profs_skipped": profs_skipped,
        "profs_with_errors": profs_with_errors,
        "duration_seconds": time.monotonic() - started_at,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Milvus collections.")
    parser.add_argument("--domain", choices=("paper", "professor"))
    parser.add_argument(
        "--collection",
        choices=(PAPER_CHUNKS_COLLECTION, PROFESSOR_PROFILES_COLLECTION),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect collection state and planned schema without writing.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop and recreate the selected collection before backfilling.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--milvus-uri", default="./milvus.db")
    parser.add_argument("--resume", nargs="?")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    if args.domain is None and args.collection is None:
        parser.error("one of --domain or --collection is required")
    return args


def _resolve_domain(args: argparse.Namespace) -> str:
    if args.collection == PROFESSOR_PROFILES_COLLECTION:
        collection_domain = "professor"
    elif args.collection == PAPER_CHUNKS_COLLECTION:
        collection_domain = "paper"
    else:
        collection_domain = None
    if args.domain and collection_domain and args.domain != collection_domain:
        raise ValueError(
            f"--domain={args.domain} does not match --collection={args.collection}"
        )
    return args.domain or collection_domain


def _collection_field_names(milvus_client, collection_name: str) -> list[str]:
    if not milvus_client.has_collection(collection_name):
        return []
    describe = getattr(milvus_client, "describe_collection", None)
    if callable(describe):
        try:
            description = describe(collection_name=collection_name)
        except Exception:
            description = None
        fields = description.get("fields") if isinstance(description, dict) else None
        if fields is None and isinstance(description, dict):
            schema = description.get("schema")
            if isinstance(schema, dict):
                fields = schema.get("fields")
        if isinstance(fields, list):
            names = [
                str(field.get("name"))
                for field in fields
                if isinstance(field, dict) and field.get("name")
            ]
            if names:
                return names
    return []


def _dry_run_collection_report(milvus_client, collection_name: str) -> dict[str, object]:
    existing_fields = _collection_field_names(milvus_client, collection_name)
    if collection_name == PROFESSOR_PROFILES_COLLECTION:
        expected_fields = list(_PROFESSOR_EXPECTED_FIELDS)
    elif collection_name == PAPER_CHUNKS_COLLECTION:
        expected_fields = [
            "chunk_id",
            "paper_id",
            "chunk_type",
            "segment_index",
            "year",
            "venue",
            "content_text",
            "content_vector",
        ]
    else:
        expected_fields = []
    return {
        "collection": collection_name,
        "exists": milvus_client.has_collection(collection_name),
        "existing_fields": existing_fields,
        "expected_fields": expected_fields,
        "missing_fields": [
            field for field in expected_fields if field not in existing_fields
        ],
    }


def main() -> int:
    args = _parse_args()
    domain = _resolve_domain(args)
    collection_name = args.collection or (
        PROFESSOR_PROFILES_COLLECTION if domain == "professor" else PAPER_CHUNKS_COLLECTION
    )
    log_level = getattr(logging, str(args.log_level).upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")

    if args.dry_run:
        milvus_client = _open_milvus_client(args.milvus_uri)
        print(
            json.dumps(
                _dry_run_collection_report(milvus_client, collection_name),
                ensure_ascii=False,
            )
        )
        return 0

    dsn = os.environ.get("DATABASE_URL")
    if dsn is None:
        sys.stderr.write("DATABASE_URL is required for Milvus backfill.\n")
        raise SystemExit(1)

    conn = None
    try:
        conn = _open_database_connection(dsn)
        milvus_client = _open_milvus_client(args.milvus_uri)
        embedding_client = _open_embedding_client()
        resume_ids = _load_resume_ids(Path(args.resume) if args.resume else None)

        if args.rebuild:
            if domain == "paper":
                drop_paper_chunks_collection(milvus_client)
            else:
                drop_professor_profiles_collection(milvus_client)

        if domain == "paper":
            report = backfill_paper_chunks(
                conn,
                milvus_client,
                embedding_client,
                limit=args.limit,
                batch_size=args.batch_size,
                resume_ids=resume_ids,
            )
        else:
            report = _backfill_professor_domain(
                conn,
                milvus_client,
                embedding_client,
                limit=args.limit,
                batch_size=args.batch_size,
                resume_ids=resume_ids,
            )

        payload = report if isinstance(report, dict) else asdict(report)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception:
        logging.exception("Milvus backfill failed")
        return 1
    finally:
        if conn is not None:
            close = getattr(conn, "close", None)
            if callable(close):
                close()


if __name__ == "__main__":
    raise SystemExit(main())
