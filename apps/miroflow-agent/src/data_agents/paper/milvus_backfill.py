from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from src.data_agents.paper.chunker import PaperChunk, chunk_paper
from src.data_agents.storage.milvus_collections import (
    PAPER_CHUNKS_COLLECTION,
    ensure_paper_chunks_collection,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BackfillReport:
    papers_total: int
    papers_processed: int
    papers_skipped: int
    chunks_inserted: int
    papers_with_errors: int
    duration_seconds: float


def backfill_paper_chunks(
    conn,
    milvus_client,
    embedding_client,
    *,
    limit=None,
    batch_size=32,
    resume_ids: set[str] | None = None,
) -> BackfillReport:
    started_at = time.monotonic()
    papers_processed = 0
    papers_skipped = 0
    chunks_inserted = 0
    papers_with_errors = 0

    try:
        ensure_paper_chunks_collection(milvus_client)
    except Exception as exc:
        logger.warning(
            "Failed to ensure %s collection: %s", PAPER_CHUNKS_COLLECTION, exc
        )

    sql = (
        "SELECT p.paper_id, p.title_clean AS title, p.year, p.venue, "
        "       pft.abstract, pft.intro "
        "FROM paper p "
        "LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id"
    )
    params: list[object] = []
    where_clauses: list[str] = []
    if resume_ids:
        placeholders = ", ".join(["%s"] * len(resume_ids))
        where_clauses.append(f"p.paper_id NOT IN ({placeholders})")
        params.extend(sorted(resume_ids))
    if where_clauses:
        sql = f"{sql} WHERE {' AND '.join(where_clauses)}"
    if limit is not None:
        sql = f"{sql} LIMIT %s"
        params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    papers_total = len(rows)

    for batch_start in range(0, papers_total, max(1, batch_size)):
        batch_rows = rows[batch_start : batch_start + max(1, batch_size)]
        batch_chunks: list[PaperChunk] = []
        batch_paper_ids: list[str] = []

        for row in batch_rows:
            paper_id = row["paper_id"]
            chunks = chunk_paper(
                paper_id=paper_id,
                title=row["title"] or "",
                year=row["year"],
                venue=row["venue"],
                abstract=row["abstract"],
                intro=row["intro"],
            )
            if not chunks:
                papers_with_errors += 1
                logger.warning(
                    "Skipping paper %s because no chunks were produced", paper_id
                )
                continue
            batch_paper_ids.append(paper_id)
            batch_chunks.extend(chunks)

        if not batch_chunks:
            continue

        try:
            vectors = embedding_client.embed_batch(
                [chunk.content_text for chunk in batch_chunks]
            )
        except Exception as exc:
            papers_with_errors += len(batch_paper_ids)
            logger.warning(
                "Embedding batch failed for %d papers: %s",
                len(batch_paper_ids),
                exc,
            )
            continue

        payload = [
            _chunk_to_row(chunk, vector)
            for chunk, vector in zip(batch_chunks, vectors, strict=False)
        ]
        if len(payload) != len(batch_chunks):
            papers_with_errors += len(batch_paper_ids)
            logger.warning(
                "Embedding batch returned %d vectors for %d chunks",
                len(payload),
                len(batch_chunks),
            )
            continue

        try:
            for paper_id in sorted(set(batch_paper_ids)):
                milvus_client.delete(
                    collection_name=PAPER_CHUNKS_COLLECTION,
                    filter=f"paper_id == '{paper_id}'",
                )
            milvus_client.insert(
                collection_name=PAPER_CHUNKS_COLLECTION,
                data=payload,
            )
        except Exception as exc:
            papers_with_errors += len(batch_paper_ids)
            logger.warning(
                "Milvus write failed for %d papers: %s",
                len(batch_paper_ids),
                exc,
            )
            continue

        papers_processed += len(batch_paper_ids)
        chunks_inserted += len(payload)

    duration_seconds = time.monotonic() - started_at
    return BackfillReport(
        papers_total=papers_total,
        papers_processed=papers_processed,
        papers_skipped=papers_skipped,
        chunks_inserted=chunks_inserted,
        papers_with_errors=papers_with_errors,
        duration_seconds=duration_seconds,
    )


def _chunk_to_row(chunk: PaperChunk, vector: list[float]) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "paper_id": chunk.paper_id,
        "chunk_type": chunk.chunk_type,
        "segment_index": chunk.segment_index,
        "year": chunk.year if chunk.year is not None else 0,
        "venue": chunk.venue or "",
        "content_text": chunk.content_text,
        "content_vector": vector,
    }
