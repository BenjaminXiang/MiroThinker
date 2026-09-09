from __future__ import annotations

import logging
import re
from uuid import UUID

from psycopg import Connection

logger = logging.getLogger(__name__)

_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def upsert_professor_orcid(
    conn: Connection,
    *,
    professor_id: UUID | str,
    orcid: str,
    source: str,
    confidence: float,
) -> None:
    if _ORCID_RE.fullmatch(orcid) is None:
        raise ValueError(f"malformed ORCID: {orcid}")

    conn.execute(
        """
        INSERT INTO professor_orcid (
            professor_id,
            orcid,
            source,
            confidence,
            verified_at
        )
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (professor_id) DO UPDATE
           SET orcid = EXCLUDED.orcid,
               source = EXCLUDED.source,
               confidence = EXCLUDED.confidence,
               verified_at = now()
        """,
        (professor_id, orcid, source, confidence),
    )


def get_professor_orcid(conn: Connection, professor_id: UUID | str) -> str | None:
    row = conn.execute(
        "SELECT orcid FROM professor_orcid WHERE professor_id = %s",
        (professor_id,),
    ).fetchone()
    if row is None:
        return None
    return row["orcid"] if isinstance(row, dict) else row[0]
