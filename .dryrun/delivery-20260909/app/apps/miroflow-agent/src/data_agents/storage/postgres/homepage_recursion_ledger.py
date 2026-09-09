from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any
from urllib.parse import urldefrag
from uuid import UUID

from .pipeline_run import require_real_run_id


class HomepageRecursionLedgerStatus(StrEnum):
    PROCESSED = "processed"
    ZERO_EXTRACTION = "zero_extraction"
    FETCH_FAILED = "fetch_failed"
    SKIPPED = "skipped"


def upsert_homepage_recursion_ledger_entry(
    conn,
    *,
    run_id: UUID | str,
    professor_id: str,
    url: str,
    page_role: str,
    discovery_source: str,
    recursion_depth: int,
    status: HomepageRecursionLedgerStatus | str,
    parent_source_page_id: UUID | str | None = None,
    source_page_id: UUID | str | None = None,
    skip_reason: str | None = None,
    fetch_error_type: str | None = None,
    fetch_error_message: str | None = None,
    http_status: int | None = None,
    publications_extracted: int = 0,
    sections_detected: int = 0,
    heading_texts: tuple[str, ...] | list[str] = (),
) -> UUID:
    run_uuid = require_real_run_id(
        run_id,
        writer_name="upsert_homepage_recursion_ledger_entry",
    )
    normalized_url = _normalize_ledger_url(url)
    if not normalized_url:
        raise ValueError("url must be non-empty")
    status_value = (
        status.value if isinstance(status, HomepageRecursionLedgerStatus) else status
    )
    heading_texts_json = json.dumps(
        [str(item) for item in heading_texts if str(item).strip()],
        ensure_ascii=False,
    )
    row = conn.execute(
        """
        INSERT INTO homepage_recursion_page_ledger (
            run_id,
            professor_id,
            parent_source_page_id,
            source_page_id,
            url,
            normalized_url,
            page_role,
            discovery_source,
            recursion_depth,
            status,
            skip_reason,
            fetch_error_type,
            fetch_error_message,
            http_status,
            publications_extracted,
            sections_detected,
            heading_texts
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (run_id, professor_id, normalized_url, discovery_source)
        DO UPDATE
           SET parent_source_page_id = COALESCE(
                   EXCLUDED.parent_source_page_id,
                   homepage_recursion_page_ledger.parent_source_page_id
               ),
               source_page_id = COALESCE(
                   EXCLUDED.source_page_id,
                   homepage_recursion_page_ledger.source_page_id
               ),
               page_role = EXCLUDED.page_role,
               recursion_depth = EXCLUDED.recursion_depth,
               status = EXCLUDED.status,
               skip_reason = EXCLUDED.skip_reason,
               fetch_error_type = EXCLUDED.fetch_error_type,
               fetch_error_message = EXCLUDED.fetch_error_message,
               http_status = EXCLUDED.http_status,
               publications_extracted = EXCLUDED.publications_extracted,
               sections_detected = EXCLUDED.sections_detected,
               heading_texts = EXCLUDED.heading_texts,
               updated_at = now()
        RETURNING ledger_id
        """,
        (
            run_uuid,
            professor_id,
            parent_source_page_id,
            source_page_id,
            url.strip(),
            normalized_url,
            page_role,
            discovery_source,
            int(recursion_depth),
            status_value,
            skip_reason,
            fetch_error_type,
            _truncate(fetch_error_message, limit=500),
            http_status,
            max(0, int(publications_extracted)),
            max(0, int(sections_detected)),
            heading_texts_json,
        ),
    ).fetchone()
    if row is None:
        raise RuntimeError("homepage recursion ledger upsert returned no row")
    return _row_value(row, "ledger_id")


def record_homepage_recursion_processed(
    conn,
    **kwargs: Any,
) -> UUID:
    return upsert_homepage_recursion_ledger_entry(
        conn,
        status=HomepageRecursionLedgerStatus.PROCESSED,
        **kwargs,
    )


def record_homepage_recursion_zero_extraction(
    conn,
    **kwargs: Any,
) -> UUID:
    return upsert_homepage_recursion_ledger_entry(
        conn,
        status=HomepageRecursionLedgerStatus.ZERO_EXTRACTION,
        publications_extracted=0,
        **kwargs,
    )


def record_homepage_recursion_fetch_failed(
    conn,
    **kwargs: Any,
) -> UUID:
    return upsert_homepage_recursion_ledger_entry(
        conn,
        status=HomepageRecursionLedgerStatus.FETCH_FAILED,
        publications_extracted=0,
        **kwargs,
    )


def record_homepage_recursion_skipped(
    conn,
    **kwargs: Any,
) -> UUID:
    return upsert_homepage_recursion_ledger_entry(
        conn,
        status=HomepageRecursionLedgerStatus.SKIPPED,
        publications_extracted=0,
        **kwargs,
    )


def _normalize_ledger_url(url: str) -> str:
    normalized = urldefrag(str(url).strip())[0].rstrip("/")
    return re.sub(r"\s+", "", normalized)


def _truncate(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _row_value(row, key: str):
    if isinstance(row, dict):
        value = row[key]
    else:
        value = getattr(row, key, row[0])
    return value if isinstance(value, UUID) else UUID(str(value))
