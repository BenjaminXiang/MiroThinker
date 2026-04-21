from __future__ import annotations

import logging
from uuid import UUID

from psycopg import Connection

from src.data_agents.paper.full_text_fetcher import FullTextExtract

logger = logging.getLogger(__name__)


def upsert_paper_full_text(
    conn: Connection,
    *,
    paper_id: str,
    extract: FullTextExtract,
    run_id: UUID | str | None = None,
) -> None:
    if run_id is not None:
        logger.debug("paper_full_text write received run_id=%s", run_id)

    conn.execute(
        """
        INSERT INTO paper_full_text (
            paper_id,
            abstract,
            intro,
            pdf_url,
            pdf_sha256,
            source,
            fetched_at,
            fetch_error
        )
        VALUES (%s, %s, %s, %s, %s, %s, now(), %s)
        ON CONFLICT (paper_id) DO UPDATE
           SET abstract = EXCLUDED.abstract,
               intro = EXCLUDED.intro,
               pdf_url = EXCLUDED.pdf_url,
               pdf_sha256 = EXCLUDED.pdf_sha256,
               source = EXCLUDED.source,
               fetched_at = now(),
               fetch_error = EXCLUDED.fetch_error
        """,
        (
            paper_id,
            extract.abstract,
            extract.intro,
            extract.pdf_url,
            extract.pdf_sha256,
            extract.source,
            extract.fetch_error,
        ),
    )


def paper_full_text_exists(conn: Connection, paper_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM paper_full_text WHERE paper_id = %s",
        (paper_id,),
    ).fetchone()
    return row is not None
