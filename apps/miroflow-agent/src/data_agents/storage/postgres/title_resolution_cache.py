from __future__ import annotations

import json
import logging
from typing import Any

from psycopg import Connection

from src.data_agents.paper.title_resolver import ResolvedPaper

logger = logging.getLogger(__name__)


def _resolved_to_dict(value: ResolvedPaper) -> dict[str, Any]:
    return {
        "title": value.title,
        "doi": value.doi,
        "openalex_id": value.openalex_id,
        "arxiv_id": value.arxiv_id,
        "abstract": value.abstract,
        "pdf_url": value.pdf_url,
        "authors": list(value.authors),
        "year": value.year,
        "venue": value.venue,
        "match_confidence": value.match_confidence,
        "match_source": value.match_source,
    }


def _dict_to_resolved(payload: dict[str, Any]) -> ResolvedPaper:
    authors = payload.get("authors") or []
    return ResolvedPaper(
        title=payload["title"],
        doi=payload.get("doi"),
        openalex_id=payload.get("openalex_id"),
        arxiv_id=payload.get("arxiv_id"),
        abstract=payload.get("abstract"),
        pdf_url=payload.get("pdf_url"),
        authors=tuple(authors),
        year=payload.get("year"),
        venue=payload.get("venue"),
        match_confidence=payload["match_confidence"],
        match_source=payload["match_source"],
    )


class PostgresTitleResolutionCache:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def get(self, key: str) -> ResolvedPaper | None:
        row = self._conn.execute(
            """
            SELECT resolved
              FROM paper_title_resolution_cache
             WHERE title_sha1 = %s
               AND cached_at > now() - interval '30 days'
            """,
            (key,),
        ).fetchone()
        if row is None:
            return None
        payload = row["resolved"] if isinstance(row, dict) else row[0]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return _dict_to_resolved(payload)

    def set(self, key: str, value: ResolvedPaper) -> None:
        payload = _resolved_to_dict(value)
        payload_json = json.dumps(payload, ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO paper_title_resolution_cache (
                title_sha1,
                clean_title_preview,
                resolved,
                match_source,
                match_confidence,
                cached_at
            )
            VALUES (%s, %s, %s::jsonb, %s, %s, now())
            ON CONFLICT (title_sha1) DO UPDATE
               SET clean_title_preview = EXCLUDED.clean_title_preview,
                   resolved = EXCLUDED.resolved,
                   match_source = EXCLUDED.match_source,
                   match_confidence = EXCLUDED.match_confidence,
                   cached_at = now()
            """,
            (
                key,
                value.title[:500],
                payload_json,
                value.match_source,
                value.match_confidence,
            ),
        )
