from __future__ import annotations

import logging
from uuid import UUID

from psycopg import Connection

from src.data_agents.paper.full_text_fetcher import FullTextExtract
from src.data_agents.paper.text_sanitizer import sanitize_text_for_postgres
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
            pdf_byte_size,
            raw_pdf_storage_ref,
            source,
            fetched_at,
            fetch_error,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), %s, %s)
        ON CONFLICT (paper_id) DO UPDATE
           SET abstract = EXCLUDED.abstract,
               intro = EXCLUDED.intro,
               pdf_url = EXCLUDED.pdf_url,
               pdf_sha256 = EXCLUDED.pdf_sha256,
               pdf_byte_size = EXCLUDED.pdf_byte_size,
               raw_pdf_storage_ref = EXCLUDED.raw_pdf_storage_ref,
               source = EXCLUDED.source,
               fetched_at = now(),
               fetch_error = EXCLUDED.fetch_error,
               run_id = EXCLUDED.run_id
        """,
        (
            paper_id,
            _strip_nul_bytes(extract.abstract),
            _strip_nul_bytes(extract.intro),
            _strip_nul_bytes(extract.pdf_url),
            extract.pdf_sha256,
            extract.pdf_byte_size,
            _strip_nul_bytes(extract.raw_pdf_storage_ref),
            extract.source,
            _strip_nul_bytes(extract.fetch_error),
            run_id,
        ),
    )


def _strip_nul_bytes(value: str | None) -> str | None:
    return sanitize_text_for_postgres(value)


def paper_full_text_exists(conn: Connection, paper_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM paper_full_text WHERE paper_id = %s",
        (paper_id,),
    ).fetchone()
    return row is not None
