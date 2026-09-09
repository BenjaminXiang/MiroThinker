# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.20 — download CV PDF pages, extract text, attach to professors.

Scope (MVP): turn the 8 source_page rows with page_role='cv_pdf' into
persisted plaintext, linked to the right professor, stored in
`professor.profile_raw_text` (nullable since Round 7.19c / V010).

Not in scope for this pass: LLM structured extraction (education /
experience / awards arrays → professor_fact rows). Once the raw text
lands, that's a straightforward follow-up round.

Strategy per row:
  1. Download the PDF (httpx, 30s timeout, max 20 MB)
  2. Extract text via pdfminer-six (already a dep)
  3. Match URL host to a professor:
       - primary match: professor.primary_profile_url host
       - fallback: source_page.url host across all source_pages of a prof
       - then URL path match (e.g. Jianwei Huang's CV at
         jianwei.cuhk.edu.cn/Files/CV.pdf → prof with homepage on that host)
  4. Update professor.profile_raw_text (only if currently NULL — don't
     clobber existing manual content).
  5. File pipeline_issue severity=low on success, severity=medium if no
     professor match found (CV orphan), severity=high on download/parse
     failure.

--dry-run default, --apply --confirm-real-db for writes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
import psycopg
from pdfminer.high_level import extract_text
from psycopg.rows import dict_row

from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_20_cv_pdf_extract"
_MAX_PDF_BYTES = 20 * 1024 * 1024
_DOWNLOAD_TIMEOUT_S = 30.0


@dataclass
class Stats:
    examined: int = 0
    downloaded: int = 0
    extracted: int = 0
    linked: int = 0
    applied: int = 0
    download_failed: int = 0
    parse_failed: int = 0
    orphan: int = 0
    issues_inserted: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 7.20 — fetch CV PDFs, extract text, link to professor."
    )
    parser.add_argument("--database-url")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-real-db", action="store_true")
    return parser.parse_args()


def _url_host(url: str) -> str | None:
    try:
        return urlparse(url).hostname
    except ValueError:
        return None


def _fetch_cv_pages(conn) -> list[dict]:
    return conn.execute(
        """
        SELECT page_id::text AS page_id,
               url,
               owner_scope_kind,
               owner_scope_ref,
               content_hash,
               clean_text_path
          FROM source_page
         WHERE page_role = 'cv_pdf'
         ORDER BY fetched_at DESC NULLS LAST
        """
    ).fetchall()


def _match_professor_by_url(conn, url: str) -> dict | None:
    """Try to find the professor this CV belongs to, by URL match.

    For uniqueness: if a host points to MULTIPLE profs (common for
    shared subdomains like www.sigs.tsinghua.edu.cn), skip — we can't
    tell which prof without further signals. Caller will file an orphan
    issue so the ambiguity surfaces for human review.
    """
    host = _url_host(url)
    if not host:
        return None
    # Dedicated per-prof hosts (e.g. jianwei.cuhk.edu.cn → single prof)
    rows = conn.execute(
        """
        SELECT p.professor_id, p.canonical_name, p.profile_raw_text
          FROM professor p
          JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id
         WHERE p.identity_status = 'resolved'
           AND sp.url LIKE %s
         LIMIT 2
        """,
        (f"%://{host}%",),
    ).fetchall()
    if len(rows) == 1:
        return rows[0]
    # If multiple profs share the host, require a stronger signal:
    # the CV URL itself (path) must also appear on one of the prof's
    # source_pages (owner_scope_ref='professor').
    rows = conn.execute(
        """
        SELECT p.professor_id, p.canonical_name, p.profile_raw_text
          FROM source_page sp
          JOIN professor p ON p.professor_id = sp.owner_scope_ref
         WHERE sp.owner_scope_kind = 'professor'
           AND sp.url = %s
           AND p.identity_status = 'resolved'
         LIMIT 2
        """,
        (url,),
    ).fetchall()
    if len(rows) == 1:
        return rows[0]
    return None


def _download_pdf(url: str) -> bytes | None:
    try:
        with httpx.Client(timeout=_DOWNLOAD_TIMEOUT_S, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return None
            if len(resp.content) > _MAX_PDF_BYTES:
                return None
            return resp.content
    except Exception:
        return None


def _extract_pdf_text(pdf_bytes: bytes) -> str | None:
    import io
    try:
        text = extract_text(io.BytesIO(pdf_bytes))
        text = " ".join(text.split())  # Collapse whitespace
        return text if len(text) > 200 else None
    except Exception:
        return None


def _update_prof_raw_text(conn, professor_id: str, text: str) -> int:
    return conn.execute(
        """
        UPDATE professor
           SET profile_raw_text = %s, updated_at = now()
         WHERE professor_id = %s
           AND identity_status = 'resolved'
           AND (profile_raw_text IS NULL OR profile_raw_text = '')
        """,
        (text, professor_id),
    ).rowcount


def _file_issue(
    conn,
    *,
    page_id: str,
    url: str,
    professor_id: str | None,
    severity: str,
    description: str,
    text_len: int | None = None,
) -> int:
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "cleanup_round": "round_7_20",
        "page_id": page_id,
        "url": url,
        "professor_id": professor_id,
        "text_chars": text_len,
    }
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, institution, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (%s, %s, 'coverage', %s, %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            professor_id,
            "UNKNOWN_INSTITUTION" if professor_id is None else None,
            severity,
            description,
            json.dumps(snapshot, ensure_ascii=False),
            _REPORTED_BY,
        ),
    )
    return cursor.rowcount


def main() -> int:
    args = _parse_args()

    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print("Refusing miroflow_real without --confirm-real-db.", file=sys.stderr)
        return 2
    if "miroflow_test_mock" in dsn and os.environ.get("ALLOW_MOCK_BACKFILL") != "1":
        print("ALLOW_MOCK_BACKFILL=1 required.", file=sys.stderr)
        return 3

    stats = Stats()
    samples: list[tuple[str, str | None, str, int]] = []

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        pages = _fetch_cv_pages(conn)
        print(f"[cv_pdf] {len(pages)} pages with page_role='cv_pdf'")
        for page in pages:
            stats.examined += 1
            url = page["url"]
            host = _url_host(url) or "(none)"

            # Download
            pdf_bytes = _download_pdf(url)
            if pdf_bytes is None:
                stats.download_failed += 1
                print(f"  ✗ download failed: {host:40s} ← {url[:60]}")
                if args.apply:
                    stats.issues_inserted += _file_issue(
                        conn, page_id=page["page_id"], url=url,
                        professor_id=None, severity="high",
                        description=f"cv_pdf download failed: {url[:80]}",
                    )
                continue
            stats.downloaded += 1

            # Extract text
            text = _extract_pdf_text(pdf_bytes)
            if not text:
                stats.parse_failed += 1
                print(f"  ✗ parse failed:    {host:40s} bytes={len(pdf_bytes)}")
                if args.apply:
                    stats.issues_inserted += _file_issue(
                        conn, page_id=page["page_id"], url=url,
                        professor_id=None, severity="high",
                        description=f"cv_pdf text extract failed: {url[:80]}",
                    )
                continue
            stats.extracted += 1

            # Match to professor
            prof = _match_professor_by_url(conn, url)
            if not prof:
                stats.orphan += 1
                print(f"  ? orphan CV:        {host:40s} text={len(text)}ch")
                samples.append((host, None, url, len(text)))
                if args.apply:
                    stats.issues_inserted += _file_issue(
                        conn, page_id=page["page_id"], url=url,
                        professor_id=None, severity="medium",
                        description=f"cv_pdf text extracted but no prof match for host={host}",
                        text_len=len(text),
                    )
                continue
            stats.linked += 1
            samples.append((prof["canonical_name"], prof["professor_id"], url, len(text)))

            if args.apply:
                updated = _update_prof_raw_text(conn, prof["professor_id"], text)
                stats.applied += updated
                stats.issues_inserted += _file_issue(
                    conn, page_id=page["page_id"], url=url,
                    professor_id=prof["professor_id"],
                    severity="low" if updated else "medium",
                    description=(
                        f"cv_pdf linked to {prof['canonical_name']}"
                        + (f" — {len(text)} chars" if updated else
                           " — skipped (profile_raw_text already set)")
                    ),
                    text_len=len(text),
                )
                print(
                    f"  ✓ linked:          {prof['canonical_name']:12.12s} ← {host:30s} "
                    f"{len(text)} chars {'(applied)' if updated else '(skipped existing)'}"
                )
            else:
                print(
                    f"  • would link:      {prof['canonical_name']:12.12s} ← {host:30s} "
                    f"{len(text)} chars"
                )

        if not args.apply:
            conn.rollback()

    print()
    print("=== CV PDF extract summary ===")
    print(f"  examined         : {stats.examined}")
    print(f"  downloaded       : {stats.downloaded}")
    print(f"  extracted        : {stats.extracted}")
    print(f"  linked to prof   : {stats.linked}")
    print(f"  orphan CVs       : {stats.orphan}")
    print(f"  download_failed  : {stats.download_failed}")
    print(f"  parse_failed     : {stats.parse_failed}")
    print(f"  apply            : {args.apply}")
    if args.apply:
        print(f"  profs updated    : {stats.applied}")
        print(f"  pipeline_issue   : {stats.issues_inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
