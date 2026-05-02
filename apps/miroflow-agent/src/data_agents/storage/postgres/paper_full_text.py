from __future__ import annotations

import logging
from uuid import UUID

from psycopg import Connection

from src.data_agents.paper.full_text_fetcher import FullTextExtract
from src.data_agents.storage.postgres.pipeline_run import require_real_run_id

logger = logging.getLogger(__name__)


def upsert_paper_full_text(
    conn: Connection,
    *,
    paper_id: str,
    extract: FullTextExtract,
    run_id: UUID | str,
) -> None:
    run_id = require_real_run_id(run_id, writer_name="upsert_paper_full_text")
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
            fetch_error,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, now(), %s, %s)
        ON CONFLICT (paper_id) DO UPDATE
           SET abstract = EXCLUDED.abstract,
               intro = EXCLUDED.intro,
               pdf_url = EXCLUDED.pdf_url,
               pdf_sha256 = EXCLUDED.pdf_sha256,
               source = EXCLUDED.source,
               fetched_at = now(),
               fetch_error = EXCLUDED.fetch_error,
               run_id = EXCLUDED.run_id
        """,
        (
            paper_id,
            extract.abstract,
            extract.intro,
            extract.pdf_url,
            extract.pdf_sha256,
            extract.source,
            extract.fetch_error,
            run_id,
        ),
    )


def paper_full_text_exists(conn: Connection, paper_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM paper_full_text WHERE paper_id = %s",
        (paper_id,),
    ).fetchone()
    return row is not None
