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

from src.data_agents.company.vectorizer import (  # noqa: E402
    _company_row_to_payload,
    _compose_company_text,
)
from src.data_agents.paper.milvus_backfill import backfill_paper_chunks  # noqa: E402
from src.data_agents.patent.vectorizer import (  # noqa: E402
    _compose_patent_text,
    _patent_row_to_payload,
)
from src.data_agents.professor.models import EnrichedProfessorProfile  # noqa: E402
from src.data_agents.professor.vectorizer import (  # noqa: E402
    EmbeddingClient,
    build_professor_identity_text,
    build_professor_research_text,
)
from src.data_agents.providers.local_api_key import load_local_api_key  # noqa: E402
from src.data_agents.storage.milvus_collections import (  # noqa: E402
    COMPANY_PROFILES_COLLECTION,
    PAPER_CHUNKS_COLLECTION,
    PATENT_PROFILES_COLLECTION,
    PROFESSOR_IDENTITY_PROFILES_COLLECTION,
    PROFESSOR_PROFILES_COLLECTION,
    PROFESSOR_RESEARCH_PROFILES_COLLECTION,
    drop_company_profiles_collection,
    drop_paper_chunks_collection,
    drop_patent_profiles_collection,
    drop_professor_identity_profiles_collection,
    drop_professor_profiles_collection,
    drop_professor_research_profiles_collection,
    ensure_company_profiles_collection,
    ensure_patent_profiles_collection,
    ensure_professor_identity_profiles_collection,
    ensure_professor_profiles_collection,
    ensure_professor_research_profiles_collection,
)

logger = logging.getLogger(__name__)


def _open_database_connection(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, row_factory=dict_row)


def _open_milvus_client(uri: str):
    _prepare_milvus_client_env(uri)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        from pymilvus import MilvusClient

    return MilvusClient(uri=uri)


def _prepare_milvus_client_env(uri: str) -> None:
    if uri.strip() == ":memory:":
        return
    os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")


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
        for key in ("paper_id", "professor_id", "company_id", "patent_id", "id"):
            entity_id = payload.get(key)
            if isinstance(entity_id, str) and entity_id:
                resume_ids.add(entity_id)
                break
    return resume_ids


_PROFESSOR_COLLECTION = PROFESSOR_PROFILES_COLLECTION
_PROFESSOR_DEFAULT_COLLECTIONS = (
    PROFESSOR_IDENTITY_PROFILES_COLLECTION,
    PROFESSOR_RESEARCH_PROFILES_COLLECTION,
)
_PROFESSOR_SPLIT_COLLECTIONS = frozenset(_PROFESSOR_DEFAULT_COLLECTIONS)
_PROFESSOR_ALL_COLLECTIONS = frozenset(
    (*_PROFESSOR_DEFAULT_COLLECTIONS, PROFESSOR_PROFILES_COLLECTION)
)
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
_PROFESSOR_IDENTITY_EXPECTED_FIELDS = [
    "id",
    "name",
    "name_en",
    "institution",
    "department",
    "title",
    "profile_url",
    "identity_text",
    "identity_vector",
    "quality_status",
]
_PROFESSOR_RESEARCH_EXPECTED_FIELDS = [
    "id",
    "research_text",
    "research_directions",
    "profile_summary",
    "paper_summary",
    "patent_summary",
    "quality_status",
    "h_index",
    "citation_count",
    "paper_count",
    "research_vector",
]

_COMPANY_COLLECTION = COMPANY_PROFILES_COLLECTION
_COMPANY_EXPECTED_FIELDS = [
    "id",
    "name",
    "industry",
    "hq_city",
    "description",
    "profile_summary",
    "technology_route_summary",
    "profile_vector",
]

_PATENT_COLLECTION = PATENT_PROFILES_COLLECTION
_PATENT_EXPECTED_FIELDS = [
    "id",
    "patent_number",
    "title",
    "abstract",
    "technology_effect",
    "patent_type",
    "ipc_codes",
    "profile_vector",
]


def _ensure_professor_collection(milvus_client, collection_name: str) -> None:
    if collection_name == PROFESSOR_IDENTITY_PROFILES_COLLECTION:
        ensure_professor_identity_profiles_collection(milvus_client)
    elif collection_name == PROFESSOR_RESEARCH_PROFILES_COLLECTION:
        ensure_professor_research_profiles_collection(milvus_client)
    elif collection_name == PROFESSOR_PROFILES_COLLECTION:
        ensure_professor_profiles_collection(milvus_client)
    else:
        raise ValueError(f"Unsupported professor collection: {collection_name}")


def _ensure_company_collection(milvus_client) -> None:
    ensure_company_profiles_collection(milvus_client)


def _ensure_patent_collection(milvus_client) -> None:
    ensure_patent_profiles_collection(milvus_client)


_PROFESSOR_SQL = """
    SELECT p.professor_id,
           p.canonical_name,
           p.canonical_name_en,
           p.profile_summary,
           p.paper_summary,
           p.patent_summary,
           p.profile_raw_text,
           p.quality_status,
           p.h_index,
           p.citation_count,
           p.paper_count,
           pa.institution,
           pa.department,
           pa.title,
           COALESCE(rd.research_directions, ARRAY[]::text[]) AS research_directions
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
      LEFT JOIN LATERAL (
          SELECT array_agg(value_raw ORDER BY confidence DESC NULLS LAST)
                 AS research_directions
            FROM professor_fact
           WHERE professor_id = p.professor_id
             AND fact_type = 'research_topic'
             AND status = 'active'
      ) rd ON true
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


def _metric_int(value) -> int:
    """Milvus stores 0 when canonical metrics are NULL; Postgres remains authoritative."""
    return int(value) if value is not None else 0


def _backfill_professor_domain(
    conn,
    milvus_client,
    embedding_client,
    *,
    limit=None,
    batch_size=32,
    resume_ids=None,
    include_ids=None,
    professor_collections=None,
    dry_run=False,
):
    started_at = time.monotonic()
    selected_collections = _normalize_professor_collections(professor_collections)
    for collection_name in selected_collections:
        _ensure_professor_collection(milvus_client, collection_name)

    sql = _PROFESSOR_SQL
    params: list[object] = []
    if include_ids:
        placeholders = ", ".join(["%s"] * len(include_ids))
        sql += f" AND p.professor_id IN ({placeholders})"
        params.extend(sorted(include_ids))
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
    processed_ids: set[str] = set()
    collection_counts = _empty_professor_collection_counts()

    for batch_start in range(0, profs_total, max(1, batch_size)):
        batch_rows = rows[batch_start : batch_start + max(1, batch_size)]
        planned_by_collection = {
            collection_name: _prepare_professor_collection_batch(
                collection_name,
                batch_rows,
            )
            for collection_name in selected_collections
        }
        planned_ids = {
            item["professor_id"]
            for items in planned_by_collection.values()
            for item in items
        }
        profs_skipped += len(batch_rows) - len(planned_ids)

        if dry_run:
            for collection_name, items in planned_by_collection.items():
                collection_counts[collection_name] += len(items)
            continue

        for collection_name, items in planned_by_collection.items():
            if not items:
                continue
            texts = [str(item["text"])[:3800] for item in items]
            try:
                vectors = embedding_client.embed_batch(texts)
            except Exception as exc:
                profs_with_errors += len(texts)
                logger.warning(
                    "Embedding batch failed (%d profs, %s): %s",
                    len(texts),
                    collection_name,
                    exc,
                )
                continue

            payload = [
                _professor_payload_for_collection(collection_name, item, vector)
                for item, vector in zip(items, vectors, strict=False)
            ]
            if len(payload) != len(items):
                profs_with_errors += len(items)
                logger.warning(
                    "Embedding batch returned %d vectors for %d profs",
                    len(payload),
                    len(items),
                )
                continue

            try:
                milvus_client.upsert(collection_name=collection_name, data=payload)
            except Exception as exc:
                profs_with_errors += len(payload)
                logger.warning(
                    "Milvus upsert failed (%d profs, %s): %s",
                    len(payload),
                    collection_name,
                    exc,
                )
                continue

            collection_counts[collection_name] += len(payload)
            processed_ids.update(str(item["professor_id"]) for item in items)

    profs_processed = len(processed_ids)

    return {
        "profs_total": profs_total,
        "profs_processed": profs_processed,
        "profs_skipped": profs_skipped,
        "profs_with_errors": profs_with_errors,
        "collection_counts": collection_counts,
        "dry_run": bool(dry_run),
        "duration_seconds": time.monotonic() - started_at,
    }


def _normalize_professor_collections(collections) -> tuple[str, ...]:
    if collections is None:
        return _PROFESSOR_DEFAULT_COLLECTIONS
    selected = tuple(collections)
    unknown = [item for item in selected if item not in _PROFESSOR_ALL_COLLECTIONS]
    if unknown:
        raise ValueError(f"Unsupported professor collection(s): {unknown}")
    return selected


def _empty_professor_collection_counts() -> dict[str, int]:
    return {
        PROFESSOR_IDENTITY_PROFILES_COLLECTION: 0,
        PROFESSOR_RESEARCH_PROFILES_COLLECTION: 0,
        PROFESSOR_PROFILES_COLLECTION: 0,
    }


def _prepare_professor_collection_batch(
    collection_name: str,
    rows: list[dict],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for row in rows:
        if collection_name == PROFESSOR_PROFILES_COLLECTION:
            text = _compose_profile_text(row)
        else:
            profile = _profile_from_professor_row(row)
            if collection_name == PROFESSOR_IDENTITY_PROFILES_COLLECTION:
                text = build_professor_identity_text(profile)
            elif collection_name == PROFESSOR_RESEARCH_PROFILES_COLLECTION:
                text = build_professor_research_text(profile)
            else:
                raise ValueError(f"Unsupported professor collection: {collection_name}")
        if not text.strip():
            continue
        items.append(
            {
                "professor_id": str(row["professor_id"]),
                "row": row,
                "text": text,
            }
        )
    return items


def _profile_from_professor_row(row: dict) -> EnrichedProfessorProfile:
    return EnrichedProfessorProfile(
        name=str(row.get("canonical_name") or ""),
        name_en=_optional_text(row.get("canonical_name_en")),
        institution=str(row.get("institution") or ""),
        department=_optional_text(row.get("department")),
        title=_optional_text(row.get("title")),
        research_directions=[
            str(item).strip()
            for item in (row.get("research_directions") or [])
            if str(item).strip()
        ],
        profile_summary=str(row.get("profile_summary") or ""),
        paper_summary=_optional_text(row.get("paper_summary")),
        patent_summary=_optional_text(row.get("patent_summary")),
        h_index=row.get("h_index"),
        citation_count=row.get("citation_count"),
        paper_count=row.get("paper_count"),
        profile_url="",
        roster_source="milvus_backfill",
        extraction_status="canonical_backfill",
    )


def _professor_payload_for_collection(
    collection_name: str,
    item: dict[str, object],
    vector: list[float],
) -> dict[str, object]:
    row = item["row"]
    if not isinstance(row, dict):
        raise TypeError("professor payload item row must be a dict")
    text = str(item["text"])
    prof_id = str(item["professor_id"])
    if collection_name == PROFESSOR_IDENTITY_PROFILES_COLLECTION:
        return {
            "id": prof_id,
            "name": str(row.get("canonical_name") or "")[:128],
            "name_en": str(row.get("canonical_name_en") or "")[:128],
            "institution": str(row.get("institution") or "")[:256],
            "department": str(row.get("department") or "")[:128],
            "title": str(row.get("title") or "")[:64],
            "profile_url": "",
            "identity_text": text[:4000],
            "identity_vector": vector,
            "quality_status": str(row.get("quality_status") or "")[:32],
        }
    if collection_name == PROFESSOR_RESEARCH_PROFILES_COLLECTION:
        return {
            "id": prof_id,
            "research_text": text[:4000],
            "research_directions": json.dumps(
                row.get("research_directions") or [],
                ensure_ascii=False,
            )[:2048],
            "profile_summary": str(row.get("profile_summary") or "")[:4000],
            "paper_summary": str(row.get("paper_summary") or "")[:4000],
            "patent_summary": str(row.get("patent_summary") or "")[:4000],
            "quality_status": str(row.get("quality_status") or "")[:32],
            "h_index": _metric_int(row.get("h_index")),
            "citation_count": _metric_int(row.get("citation_count")),
            "paper_count": _metric_int(row.get("paper_count")),
            "research_vector": vector,
        }
    if collection_name == PROFESSOR_PROFILES_COLLECTION:
        return {
            "id": prof_id,
            "name": str(row.get("canonical_name") or "")[:128],
            "institution": str(row.get("institution") or "")[:256],
            "department": str(row.get("department") or "")[:128],
            "title": str(row.get("title") or "")[:64],
            "profile_summary": text[:4000],
            "profile_vector": vector,
            "h_index": _metric_int(row.get("h_index")),
            "citation_count": _metric_int(row.get("citation_count")),
            "paper_count": _metric_int(row.get("paper_count")),
        }
    raise ValueError(f"Unsupported professor collection: {collection_name}")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


_COMPANY_SQL = """
    SELECT c.company_id,
           c.canonical_name,
           c.hq_city,
           c.profile_summary,
           c.technology_route_summary,
           cs.industry,
           cs.description,
           COALESCE(products.products_json, '[]'::jsonb) AS products_json,
           COALESCE(scenarios.application_scenarios_json, '[]'::jsonb) AS application_scenarios_json,
           COALESCE(recent_events.recent_events_json, '[]'::jsonb) AS recent_events_json
      FROM company c
      LEFT JOIN LATERAL (
          SELECT industry, description
            FROM company_snapshot
           WHERE company_id = c.company_id
           ORDER BY snapshot_created_at DESC NULLS LAST
           LIMIT 1
      ) cs ON true
      LEFT JOIN LATERAL (
          SELECT jsonb_agg(
              jsonb_build_object(
                  'name', cp.canonical_name,
                  'description', cp.short_description,
                  'product_category', cp.product_category,
                  'target_customers', cp.target_customers,
                  'application_scenarios', cp.application_scenarios,
                  'technical_tags', cp.technical_tags
              )
              ORDER BY cp.confidence DESC NULLS LAST, cp.last_refreshed_at DESC NULLS LAST
          ) AS products_json
            FROM company_product cp
           WHERE cp.company_id = c.company_id
             AND (
                 cp.quality_status = 'ready'
                 OR (
                     cp.quality_status = 'needs_review'
                     AND COALESCE(cp.confidence, 1.0) >= 0.60
                     AND EXISTS (
                         SELECT 1
                           FROM company_product_evidence publishable_evidence
                          WHERE publishable_evidence.product_id = cp.product_id
                            AND COALESCE(publishable_evidence.source_tier, '') IN (
                                'xlsx', 'official', 'official_site', 'iyiou', 'pitchhub_36kr'
                            )
                     )
                 )
             )
      ) products ON true
      LEFT JOIN LATERAL (
          SELECT jsonb_agg(
              jsonb_build_object(
                  'scenario_name', cas.scenario_name,
                  'scenario_category', cas.scenario_category,
                  'description', cas.description,
                  'target_customer', cas.target_customer
              )
              ORDER BY cas.confidence DESC NULLS LAST, cas.last_refreshed_at DESC NULLS LAST
          ) AS application_scenarios_json
            FROM company_application_scenario cas
           WHERE cas.company_id = c.company_id
             AND (
                 cas.quality_status = 'ready'
                 OR (
                     cas.quality_status = 'needs_review'
                     AND COALESCE(cas.confidence, 1.0) >= 0.60
                     AND EXISTS (
                         SELECT 1
                           FROM company_application_scenario_evidence publishable_evidence
                          WHERE publishable_evidence.scenario_id = cas.scenario_id
                            AND COALESCE(publishable_evidence.source_tier, '') IN (
                                'xlsx', 'official', 'official_site', 'iyiou', 'pitchhub_36kr'
                            )
                     )
                 )
             )
      ) scenarios ON true
      LEFT JOIN LATERAL (
          SELECT jsonb_agg(
              jsonb_build_object(
                  'event_type', cse.event_type,
                  'event_date', cse.event_date,
                  'summary', cse.event_summary
              )
              ORDER BY cse.event_date DESC, cse.created_at DESC NULLS LAST
          ) AS recent_events_json
            FROM (
                SELECT *
                  FROM company_signal_event cse
                 WHERE cse.company_id = c.company_id
                   AND cse.status = 'active'
                 ORDER BY cse.event_date DESC, cse.created_at DESC NULLS LAST
                 LIMIT 10
            ) cse
      ) recent_events ON true
     WHERE c.canonical_name IS NOT NULL
       AND c.identity_status != 'inactive'
"""


def _backfill_company_domain(
    conn,
    milvus_client,
    embedding_client,
    *,
    limit=None,
    batch_size=32,
    resume_ids=None,
    company_ids=None,
):
    started_at = time.monotonic()
    _ensure_company_collection(milvus_client)

    sql = _COMPANY_SQL
    params: list[object] = []
    if company_ids:
        placeholders = ", ".join(["%s"] * len(company_ids))
        sql += f" AND c.company_id IN ({placeholders})"
        params.extend(sorted(company_ids))
    if resume_ids:
        placeholders = ", ".join(["%s"] * len(resume_ids))
        sql += f" AND c.company_id NOT IN ({placeholders})"
        params.extend(sorted(resume_ids))
    sql += " ORDER BY c.company_id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))

    rows = conn.execute(sql, params).fetchall()
    companies_total = len(rows)
    companies_processed = 0
    companies_skipped = 0
    companies_with_errors = 0

    for batch_start in range(0, companies_total, max(1, batch_size)):
        batch_rows = rows[batch_start : batch_start + max(1, batch_size)]
        texts: list[str] = []
        row_refs: list[dict] = []
        for row in batch_rows:
            text = _compose_company_text(row)
            if not str(row.get("canonical_name") or "").strip() or not text.strip():
                companies_skipped += 1
                continue
            texts.append(text[:3800])
            row_refs.append(row)

        if not texts:
            continue

        try:
            vectors = embedding_client.embed_batch(texts)
        except Exception as exc:
            companies_with_errors += len(texts)
            logger.warning(
                "Embedding batch failed (%d companies): %s", len(texts), exc
            )
            continue

        payload = [
            _company_row_to_payload(row, vector)
            for row, vector in zip(row_refs, vectors, strict=False)
        ]
        if len(payload) != len(texts):
            companies_with_errors += len(texts)
            logger.warning(
                "Embedding batch returned %d vectors for %d companies",
                len(payload),
                len(texts),
            )
            continue

        try:
            milvus_client.upsert(collection_name=_COMPANY_COLLECTION, data=payload)
            flush = getattr(milvus_client, "flush", None)
            if callable(flush):
                flush(collection_name=_COMPANY_COLLECTION)
        except Exception as exc:
            companies_with_errors += len(payload)
            logger.warning(
                "Milvus upsert failed (%d companies): %s", len(payload), exc
            )
            continue

        companies_processed += len(payload)

    return {
        "companies_total": companies_total,
        "companies_processed": companies_processed,
        "companies_skipped": companies_skipped,
        "companies_with_errors": companies_with_errors,
        "duration_seconds": time.monotonic() - started_at,
    }


_PATENT_SQL = """
    SELECT patent_id,
           patent_number,
           title_clean,
           abstract_clean,
           technology_effect,
           patent_type,
           ipc_codes
      FROM patent
     WHERE patent_id IS NOT NULL
"""


def _backfill_patent_domain(
    conn,
    milvus_client,
    embedding_client,
    *,
    limit=None,
    batch_size=32,
    resume_ids=None,
):
    started_at = time.monotonic()
    _ensure_patent_collection(milvus_client)

    sql = _PATENT_SQL
    params: list[object] = []
    if resume_ids:
        placeholders = ", ".join(["%s"] * len(resume_ids))
        sql += f" AND patent_id NOT IN ({placeholders})"
        params.extend(sorted(resume_ids))
    sql += " ORDER BY patent_id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))

    rows = conn.execute(sql, params).fetchall()
    patents_total = len(rows)
    patents_processed = 0
    patents_skipped = 0
    patents_with_errors = 0

    for batch_start in range(0, patents_total, max(1, batch_size)):
        batch_rows = rows[batch_start : batch_start + max(1, batch_size)]
        texts: list[str] = []
        row_refs: list[dict] = []
        for row in batch_rows:
            text = _compose_patent_text(row)
            if not text.strip():
                patents_skipped += 1
                continue
            texts.append(text[:3800])
            row_refs.append(row)

        if not texts:
            continue

        try:
            vectors = embedding_client.embed_batch(texts)
        except Exception as exc:
            patents_with_errors += len(texts)
            logger.warning(
                "Embedding batch failed (%d patents): %s", len(texts), exc
            )
            continue

        payload = [
            _patent_row_to_payload(row, vector)
            for row, vector in zip(row_refs, vectors, strict=False)
        ]
        if len(payload) != len(texts):
            patents_with_errors += len(texts)
            logger.warning(
                "Embedding batch returned %d vectors for %d patents",
                len(payload),
                len(texts),
            )
            continue

        try:
            milvus_client.upsert(collection_name=_PATENT_COLLECTION, data=payload)
        except Exception as exc:
            patents_with_errors += len(payload)
            logger.warning("Milvus upsert failed (%d patents): %s", len(payload), exc)
            continue

        patents_processed += len(payload)

    return {
        "patents_total": patents_total,
        "patents_processed": patents_processed,
        "patents_skipped": patents_skipped,
        "patents_with_errors": patents_with_errors,
        "duration_seconds": time.monotonic() - started_at,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Milvus collections.")
    parser.add_argument("--domain", choices=("paper", "professor", "company", "patent"))
    parser.add_argument(
        "--collection",
        choices=(
            PAPER_CHUNKS_COLLECTION,
            PROFESSOR_PROFILES_COLLECTION,
            PROFESSOR_IDENTITY_PROFILES_COLLECTION,
            PROFESSOR_RESEARCH_PROFILES_COLLECTION,
            COMPANY_PROFILES_COLLECTION,
            PATENT_PROFILES_COLLECTION,
        ),
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
    parser.add_argument(
        "--id",
        action="append",
        dest="ids",
        help="Restrict professor backfill to a specific professor_id. Repeatable.",
    )
    parser.add_argument(
        "--paper-id",
        action="append",
        dest="paper_ids",
        help="Restrict paper backfill to a specific paper_id. Repeatable.",
    )
    parser.add_argument(
        "--company-id",
        action="append",
        dest="company_ids",
        help="Restrict company backfill to a specific company_id. Repeatable.",
    )
    parser.add_argument(
        "--changed-since",
        help=(
            "Restrict paper backfill to rows whose paper.updated_at is greater "
            "than or equal to this timestamp."
        ),
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    if args.domain is None and args.collection is None:
        parser.error("one of --domain or --collection is required")
    return args


def _resolve_domain(args: argparse.Namespace) -> str:
    if args.collection in _PROFESSOR_ALL_COLLECTIONS:
        collection_domain = "professor"
    elif args.collection == PAPER_CHUNKS_COLLECTION:
        collection_domain = "paper"
    elif args.collection == COMPANY_PROFILES_COLLECTION:
        collection_domain = "company"
    elif args.collection == PATENT_PROFILES_COLLECTION:
        collection_domain = "patent"
    else:
        collection_domain = None
    if args.domain and collection_domain and args.domain != collection_domain:
        raise ValueError(
            f"--domain={args.domain} does not match --collection={args.collection}"
        )
    return args.domain or collection_domain


def _professor_collections_from_args(args: argparse.Namespace) -> set[str]:
    if args.collection in _PROFESSOR_ALL_COLLECTIONS:
        return {args.collection}
    return set(_PROFESSOR_DEFAULT_COLLECTIONS)


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
    elif collection_name == PROFESSOR_IDENTITY_PROFILES_COLLECTION:
        expected_fields = list(_PROFESSOR_IDENTITY_EXPECTED_FIELDS)
    elif collection_name == PROFESSOR_RESEARCH_PROFILES_COLLECTION:
        expected_fields = list(_PROFESSOR_RESEARCH_EXPECTED_FIELDS)
    elif collection_name == COMPANY_PROFILES_COLLECTION:
        expected_fields = list(_COMPANY_EXPECTED_FIELDS)
    elif collection_name == PATENT_PROFILES_COLLECTION:
        expected_fields = list(_PATENT_EXPECTED_FIELDS)
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
    include_ids = set(args.ids or [])
    if include_ids and domain != "professor":
        raise SystemExit("--id is currently supported only with --domain professor")
    paper_ids = set(args.paper_ids or [])
    if paper_ids and domain != "paper":
        raise SystemExit("--paper-id is currently supported only with --domain paper")
    company_ids = set(args.company_ids or [])
    if company_ids and domain != "company":
        raise SystemExit("--company-id is currently supported only with --domain company")
    if args.changed_since and domain != "paper":
        raise SystemExit(
            "--changed-since is currently supported only with --domain paper"
        )
    collection_by_domain = {
        "paper": PAPER_CHUNKS_COLLECTION,
        "professor": PROFESSOR_PROFILES_COLLECTION,
        "company": COMPANY_PROFILES_COLLECTION,
        "patent": PATENT_PROFILES_COLLECTION,
    }
    collection_name = args.collection or collection_by_domain[domain]
    log_level = getattr(logging, str(args.log_level).upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")

    if args.dry_run:
        milvus_client = _open_milvus_client(args.milvus_uri)
        if domain == "professor" and args.collection is None:
            reports = [
                _dry_run_collection_report(milvus_client, collection)
                for collection in _PROFESSOR_DEFAULT_COLLECTIONS
            ]
            print(json.dumps({"collections": reports}, ensure_ascii=False))
            return 0
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
    milvus_client = None
    try:
        conn = _open_database_connection(dsn)
        milvus_client = _open_milvus_client(args.milvus_uri)
        embedding_client = _open_embedding_client()
        resume_ids = _load_resume_ids(Path(args.resume) if args.resume else None)

        if args.rebuild:
            if domain == "paper":
                drop_paper_chunks_collection(milvus_client)
            elif domain == "professor":
                for collection in _professor_collections_from_args(args):
                    if collection == PROFESSOR_IDENTITY_PROFILES_COLLECTION:
                        drop_professor_identity_profiles_collection(milvus_client)
                    elif collection == PROFESSOR_RESEARCH_PROFILES_COLLECTION:
                        drop_professor_research_profiles_collection(milvus_client)
                    else:
                        drop_professor_profiles_collection(milvus_client)
            elif domain == "company":
                drop_company_profiles_collection(milvus_client)
            elif domain == "patent":
                drop_patent_profiles_collection(milvus_client)

        if domain == "paper":
            report = backfill_paper_chunks(
                conn,
                milvus_client,
                embedding_client,
                limit=args.limit,
                batch_size=args.batch_size,
                resume_ids=resume_ids,
                paper_ids=paper_ids,
                changed_since=args.changed_since,
            )
        elif domain == "professor":
            report = _backfill_professor_domain(
                conn,
                milvus_client,
                embedding_client,
                limit=args.limit,
                batch_size=args.batch_size,
                resume_ids=resume_ids,
                include_ids=include_ids,
                professor_collections=_professor_collections_from_args(args),
            )
        elif domain == "company":
            report = _backfill_company_domain(
                conn,
                milvus_client,
                embedding_client,
                limit=args.limit,
                batch_size=args.batch_size,
                resume_ids=resume_ids,
                company_ids=company_ids,
            )
        elif domain == "patent":
            report = _backfill_patent_domain(
                conn,
                milvus_client,
                embedding_client,
                limit=args.limit,
                batch_size=args.batch_size,
                resume_ids=resume_ids,
            )
        else:
            raise ValueError(f"Unsupported domain: {domain}")

        payload = report if isinstance(report, dict) else asdict(report)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception:
        logging.exception("Milvus backfill failed")
        return 1
    finally:
        if milvus_client is not None:
            close = getattr(milvus_client, "close", None)
            if callable(close):
                close()
        if conn is not None:
            close = getattr(conn, "close", None)
            if callable(close):
                close()


if __name__ == "__main__":
    raise SystemExit(main())
