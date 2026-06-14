"""Prof-homepage-driven patent canonical ingest.

Per OpenSpec change `prof-paper-patent-from-page-flow` spec Requirement
"Patent canonical upsert with patent_id hard match" — patents are
discovered exclusively from Publications-section-style listings on a
professor's Tier 2 / Tier 3 page. No external patent API is consulted.

The entry point `run_homepage_patent_ingest` walks the same professor
roster as `paper.homepage_ingest.run_homepage_paper_ingest`, fetches each
prof's homepage HTML, calls
`professor.homepage_patents.extract_patents_from_html`, and persists
candidates as canonical patent rows. Candidates with a registration
number still hard-match on `patent_number`; title-only candidates use a
stable page/title `patent_id` with `patent_number=NULL` and start as
`needs_enrichment`.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from psycopg.types.json import Jsonb

from ..normalization import build_stable_id
from ..storage.postgres.pipeline_run import (
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)
from ..professor.homepage_patents import PatentEntry, extract_patents_from_html
from ..paper.homepage_http import fetch_homepage_html

logger = logging.getLogger(__name__)

_DRY_RUN_SENTINEL_RUN_ID = UUID("00000000-0000-0000-0000-000000000000")
_LINK_MATCH_REASON_PAGE_ONLY = "prof_page_declaration"
_LINK_EVIDENCE_SOURCE = "personal_homepage"
_LINK_ROLE_INVENTOR = "inventor"
_PIPELINE_STAGE_DATA_QUALITY = "data_quality_flag"
_REPORTED_BY = "homepage_patent_ingest"


@dataclass(frozen=True, slots=True)
class PatentIngestReport:
    run_id: UUID
    profs_total: int
    profs_processed: int
    profs_skipped: int
    patents_upserted_total: int
    patents_skipped_no_id_total: int
    links_written_total: int
    pipeline_issues_filed: int
    run_duration_seconds: float


@dataclass(frozen=True, slots=True)
class _IngestOutcome:
    upserted: int
    skipped_no_id: int
    links_written: int
    issues_filed: int


def run_homepage_patent_ingest(
    conn,
    *,
    institution: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    prof_id: str | None = None,
) -> PatentIngestReport:
    started_at = time.monotonic()
    run_id: UUID | str = _DRY_RUN_SENTINEL_RUN_ID
    run_opened = False

    profs_processed = 0
    profs_skipped = 0
    patents_upserted_total = 0
    patents_skipped_no_id_total = 0
    links_written_total = 0
    pipeline_issues_filed = 0

    try:
        if not dry_run:
            run_id = open_pipeline_run(
                conn,
                run_kind="backfill_real",
                run_scope={
                    "task": "homepage_patent_ingest",
                    "institution": institution,
                    "limit": limit,
                    "prof_id": prof_id,
                },
                triggered_by=_REPORTED_BY,
            )
            run_opened = True

        professors = _fetch_professors(
            conn,
            institution=institution,
            limit=limit,
            prof_id=prof_id,
        )

        for prof in professors:
            professor_id = str(prof["professor_id"])
            profs_processed += 1

            with conn.transaction():
                try:
                    html = fetch_homepage_html(prof["homepage_url"])
                except (
                    httpx.HTTPStatusError,
                    httpx.ConnectError,
                    httpx.TimeoutException,
                ) as exc:
                    logger.warning(
                        "Homepage fetch failed for %s (%s): %s",
                        professor_id,
                        prof["homepage_url"],
                        exc,
                    )
                    if not dry_run:
                        _file_pipeline_issue(
                            conn,
                            issue_type="homepage_fetch_error",
                            professor_id=professor_id,
                            # V006 pipeline_issue.stage enum lacks a
                            # patent-specific value; "discovery" is the
                            # closest match for a fetch failure.
                            stage="discovery",
                            severity="medium",
                            message=str(exc),
                            details={"homepage_url": prof["homepage_url"]},
                        )
                    pipeline_issues_filed += 1
                    continue

                entries = extract_patents_from_html(
                    html,
                    page_url=prof["homepage_url"],
                )

                outcome = _ingest_patents_for_professor(
                    conn,
                    entries=entries,
                    professor_id=professor_id,
                    canonical_name=prof["canonical_name"],
                    run_id=run_id,
                    dry_run=dry_run,
                )

            patents_upserted_total += outcome.upserted
            patents_skipped_no_id_total += outcome.skipped_no_id
            links_written_total += outcome.links_written
            pipeline_issues_filed += outcome.issues_filed

    except KeyboardInterrupt:
        if run_opened:
            close_pipeline_run(conn, run_id, status="failed")
        raise
    except Exception as exc:
        if run_opened:
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                error_summary={"msg": str(exc)},
            )
        raise
    else:
        if run_opened:
            close_pipeline_run(
                conn,
                run_id,
                status="succeeded",
                items_processed=profs_processed,
                items_failed=0,
            )

    return PatentIngestReport(
        run_id=run_id if isinstance(run_id, UUID) else UUID(str(run_id)),
        profs_total=len(professors),
        profs_processed=profs_processed,
        profs_skipped=profs_skipped,
        patents_upserted_total=patents_upserted_total,
        patents_skipped_no_id_total=patents_skipped_no_id_total,
        links_written_total=links_written_total,
        pipeline_issues_filed=pipeline_issues_filed,
        run_duration_seconds=time.monotonic() - started_at,
    )


def _ingest_patents_for_professor(
    conn,
    *,
    entries: list[PatentEntry],
    professor_id: str,
    canonical_name: str | None,
    run_id: UUID | str,
    dry_run: bool,
) -> _IngestOutcome:
    upserted = 0
    skipped_no_id = 0
    links_written = 0
    issues_filed = 0

    for entry in entries:
        if not entry.title.strip():
            skipped_no_id += 1
            issues_filed += 1
            if not dry_run:
                _file_pipeline_issue(
                    conn,
                    issue_type="patent_malformed_candidate",
                    professor_id=professor_id,
                    stage=_PIPELINE_STAGE_DATA_QUALITY,
                    severity="low",
                    message="Patent candidate has a blank title",
                    details={
                        "patent_id": entry.patent_id,
                        "source_url": entry.source_url,
                        "source_anchor": entry.source_anchor,
                    },
                )
            continue

        row = _build_patent_row(
            entry,
            canonical_name=canonical_name,
            professor_id=professor_id,
            run_id=run_id,
        )
        if not dry_run:
            actual_patent_id = _upsert_patent_canonical(
                conn,
                row=row,
                professor_id=professor_id,
                evidence_url=entry.source_url,
                evidence_anchor=entry.source_anchor,
            )
            _upsert_professor_patent_link(
                conn,
                professor_id=professor_id,
                patent_id=actual_patent_id,
                evidence_url=entry.source_url,
                evidence_anchor=entry.source_anchor,
                match_reason=_LINK_MATCH_REASON_PAGE_ONLY,
                verified_by="rule_auto",
            )
            links_written += 1
        upserted += 1

    return _IngestOutcome(
        upserted=upserted,
        skipped_no_id=skipped_no_id,
        links_written=links_written,
        issues_filed=issues_filed,
    )


def _build_patent_row(
    entry: PatentEntry,
    *,
    canonical_name: str | None,
    professor_id: str | None = None,
    run_id: UUID | str,
) -> dict[str, Any]:
    """Build a patent-table row from a homepage entry."""
    patent_number = entry.patent_id.strip().upper() if entry.patent_id else None
    if patent_number:
        internal_patent_id = build_stable_id("PAT", patent_number)
    else:
        internal_patent_id = build_stable_id(
            "PAT-PAGE",
            _title_only_patent_natural_key(
                entry,
                professor_id=professor_id,
            ),
        )

    inventors = (
        list(entry.inventors)
        if entry.inventors
        else ([canonical_name] if canonical_name else [])
    )
    inventors_raw = "；".join(inventors) if inventors else None
    now = datetime.now(timezone.utc)

    return {
        "patent_id": internal_patent_id,
        "patent_number": patent_number,
        "title_clean": entry.title.strip(),
        "title_raw": entry.title.strip(),
        "title_en": None,
        "applicants_raw": None,
        "applicants_parsed": [],
        "inventors_raw": inventors_raw,
        "inventors_parsed": inventors,
        "filing_date": entry.application_date,
        "publication_date": None,
        "grant_date": entry.grant_date,
        "patent_type": None,
        "status": None,
        "abstract_clean": None,
        "technology_effect": None,
        "ipc_codes": [],
        "summary_text": None,
        "summary_text_method": None,
        "identity_status": "unverified",
        "quality_status": "needs_enrichment",
        "first_seen_at": now,
        "updated_at": now,
        "run_id": run_id,
    }


def _title_only_patent_natural_key(
    entry: PatentEntry,
    *,
    professor_id: str | None,
) -> str:
    title_key = " ".join(entry.title.strip().casefold().split())
    source_url_key = (entry.source_url or "").strip().casefold()
    source_anchor_key = (entry.source_anchor or "").strip().casefold()
    professor_key = (professor_id or "").strip().casefold()
    return "|".join(
        (
            "prof_page_title_only",
            professor_key,
            source_url_key,
            source_anchor_key,
            title_key,
        )
    )


def _upsert_patent_canonical(
    conn,
    *,
    row: dict[str, Any],
    professor_id: str,
    evidence_url: str | None,
    evidence_anchor: str | None,
) -> str:
    """INSERT ... ON CONFLICT (patent_number) DO UPDATE the patent row.

    Conflict key is `patent_number` rather than `patent_id` so that
    re-discovery of the same real-world patent on a different prof page
    (or via xlsx import) merges into the existing canonical row instead
    of inserting a duplicate. Per spec Requirement "Patent canonical
    upsert with patent_id hard match".
    """
    run_id = require_real_run_id(row["run_id"], writer_name="patent.homepage_ingest")

    if row["patent_number"] is None:
        return _upsert_title_only_patent_canonical(conn, row=row, run_id=run_id)

    promoted_patent_id = _promote_title_only_patent_if_match(
        conn,
        row=row,
        run_id=run_id,
        professor_id=professor_id,
        evidence_url=evidence_url,
        evidence_anchor=evidence_anchor,
    )
    if promoted_patent_id is not None:
        return promoted_patent_id

    result = conn.execute(
        """
        INSERT INTO patent (
            patent_id,
            patent_number,
            title_clean,
            title_raw,
            title_en,
            applicants_raw,
            applicants_parsed,
            inventors_raw,
            inventors_parsed,
            filing_date,
            publication_date,
            grant_date,
            patent_type,
            status,
            abstract_clean,
            technology_effect,
            ipc_codes,
            summary_text,
            summary_text_method,
            identity_status,
            quality_status,
            run_id,
            first_seen_at,
            updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (patent_number) DO UPDATE
           SET title_clean         = COALESCE(NULLIF(EXCLUDED.title_clean, ''), patent.title_clean),
               inventors_raw       = COALESCE(EXCLUDED.inventors_raw, patent.inventors_raw),
               inventors_parsed    = COALESCE(EXCLUDED.inventors_parsed, patent.inventors_parsed),
               filing_date         = COALESCE(EXCLUDED.filing_date, patent.filing_date),
               grant_date          = COALESCE(EXCLUDED.grant_date, patent.grant_date),
               run_id              = EXCLUDED.run_id,
               updated_at          = EXCLUDED.updated_at
        RETURNING patent_id
        """,
        (
            row["patent_id"],
            row["patent_number"],
            row["title_clean"],
            row["title_raw"],
            row["title_en"],
            row["applicants_raw"],
            Jsonb(row["applicants_parsed"]),
            row["inventors_raw"],
            Jsonb(row["inventors_parsed"]),
            row["filing_date"],
            row["publication_date"],
            row["grant_date"],
            row["patent_type"],
            row["status"],
            row["abstract_clean"],
            row["technology_effect"],
            row["ipc_codes"],
            row["summary_text"],
            row["summary_text_method"],
            row["identity_status"],
            row["quality_status"],
            run_id,
            row["first_seen_at"],
            row["updated_at"],
        ),
    ).fetchone()

    if result is None:
        raise RuntimeError("patent upsert did not return patent_id")
    return str(result[0] if not isinstance(result, dict) else result["patent_id"])


def _promote_title_only_patent_if_match(
    conn,
    *,
    row: dict[str, Any],
    run_id: UUID,
    professor_id: str,
    evidence_url: str | None,
    evidence_anchor: str | None,
) -> str | None:
    result = conn.execute(
        """
        WITH candidate AS (
            SELECT patent.patent_id
              FROM patent
              JOIN professor_patent_link AS ppl
                ON ppl.patent_id = patent.patent_id
             WHERE ppl.professor_id = %s
               AND patent.patent_number IS NULL
               AND patent.title_clean = %s
               AND ppl.evidence_url IS NOT DISTINCT FROM %s
               AND ppl.evidence_anchor IS NOT DISTINCT FROM %s
               AND NOT EXISTS (
                   SELECT 1
                     FROM patent AS numbered
                    WHERE numbered.patent_number = %s
               )
             ORDER BY patent.updated_at DESC
             LIMIT 1
        )
        UPDATE patent
           SET patent_number    = %s,
               inventors_raw    = COALESCE(%s, patent.inventors_raw),
               inventors_parsed = COALESCE(%s, patent.inventors_parsed),
               filing_date      = COALESCE(%s, patent.filing_date),
               grant_date       = COALESCE(%s, patent.grant_date),
               run_id           = %s,
               updated_at       = %s
          FROM candidate
         WHERE patent.patent_id = candidate.patent_id
        RETURNING patent.patent_id
        """,
        (
            professor_id,
            row["title_clean"],
            evidence_url or None,
            evidence_anchor or None,
            row["patent_number"],
            row["patent_number"],
            row["inventors_raw"],
            Jsonb(row["inventors_parsed"]),
            row["filing_date"],
            row["grant_date"],
            run_id,
            row["updated_at"],
        ),
    ).fetchone()
    if result is None:
        return None
    return str(result[0] if not isinstance(result, dict) else result["patent_id"])


def _upsert_title_only_patent_canonical(
    conn,
    *,
    row: dict[str, Any],
    run_id: UUID,
) -> str:
    """INSERT ... ON CONFLICT (patent_id) DO UPDATE title-only page rows."""
    result = conn.execute(
        """
        INSERT INTO patent (
            patent_id,
            patent_number,
            title_clean,
            title_raw,
            title_en,
            applicants_raw,
            applicants_parsed,
            inventors_raw,
            inventors_parsed,
            filing_date,
            publication_date,
            grant_date,
            patent_type,
            status,
            abstract_clean,
            technology_effect,
            ipc_codes,
            summary_text,
            summary_text_method,
            identity_status,
            quality_status,
            run_id,
            first_seen_at,
            updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (patent_id) DO UPDATE
           SET patent_number       = COALESCE(EXCLUDED.patent_number, patent.patent_number),
               title_clean         = COALESCE(NULLIF(EXCLUDED.title_clean, ''), patent.title_clean),
               inventors_raw       = COALESCE(EXCLUDED.inventors_raw, patent.inventors_raw),
               inventors_parsed    = COALESCE(EXCLUDED.inventors_parsed, patent.inventors_parsed),
               filing_date         = COALESCE(EXCLUDED.filing_date, patent.filing_date),
               grant_date          = COALESCE(EXCLUDED.grant_date, patent.grant_date),
               run_id              = EXCLUDED.run_id,
               updated_at          = EXCLUDED.updated_at
        RETURNING patent_id
        """,
        (
            row["patent_id"],
            row["patent_number"],
            row["title_clean"],
            row["title_raw"],
            row["title_en"],
            row["applicants_raw"],
            Jsonb(row["applicants_parsed"]),
            row["inventors_raw"],
            Jsonb(row["inventors_parsed"]),
            row["filing_date"],
            row["publication_date"],
            row["grant_date"],
            row["patent_type"],
            row["status"],
            row["abstract_clean"],
            row["technology_effect"],
            row["ipc_codes"],
            row["summary_text"],
            row["summary_text_method"],
            row["identity_status"],
            row["quality_status"],
            run_id,
            row["first_seen_at"],
            row["updated_at"],
        ),
    ).fetchone()

    if result is None:
        raise RuntimeError("title-only patent upsert did not return patent_id")
    return str(result[0] if not isinstance(result, dict) else result["patent_id"])


def _upsert_professor_patent_link(
    conn,
    *,
    professor_id: str,
    patent_id: str,
    evidence_url: str | None,
    evidence_anchor: str | None,
    match_reason: str,
    verified_by: str | None,
) -> None:
    verified_at = datetime.now(timezone.utc) if verified_by == "rule_auto" else None
    conn.execute(
        """
        INSERT INTO professor_patent_link (
            professor_id,
            patent_id,
            link_role,
            link_status,
            evidence_source_type,
            evidence_url,
            evidence_anchor,
            match_reason,
            verified_by,
            verified_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (professor_id, patent_id, link_role) DO UPDATE
           SET link_status          = EXCLUDED.link_status,
               evidence_source_type = EXCLUDED.evidence_source_type,
               evidence_url         = COALESCE(EXCLUDED.evidence_url, professor_patent_link.evidence_url),
               evidence_anchor      = COALESCE(EXCLUDED.evidence_anchor, professor_patent_link.evidence_anchor),
               match_reason         = EXCLUDED.match_reason,
               verified_by          = COALESCE(EXCLUDED.verified_by, professor_patent_link.verified_by),
               verified_at          = COALESCE(EXCLUDED.verified_at, professor_patent_link.verified_at),
               updated_at           = now()
        """,
        (
            professor_id,
            patent_id,
            _LINK_ROLE_INVENTOR,
            "verified",
            _LINK_EVIDENCE_SOURCE,
            evidence_url or None,
            evidence_anchor or None,
            match_reason,
            verified_by,
            verified_at,
        ),
    )


def _file_pipeline_issue(
    conn,
    *,
    issue_type: str,
    professor_id: str,
    stage: str,
    severity: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    evidence_snapshot = json.dumps(
        {
            "issue_type": issue_type,
            "message": message,
            "details": details,
        },
        ensure_ascii=False,
        default=_jsonify_default,
    )
    conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id,
            institution,
            stage,
            severity,
            description,
            evidence_snapshot,
            reported_by
        )
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            professor_id,
            None,
            stage,
            severity,
            f"[{issue_type}] {message}",
            evidence_snapshot,
            _REPORTED_BY,
        ),
    )


def _jsonify_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Unsupported type in pipeline_issue details: {type(value)!r}")


def _fetch_professors(
    conn,
    *,
    institution: str | None,
    limit: int | None,
    prof_id: str | None,
) -> list[dict[str, Any]]:
    # Mirrors paper/homepage_ingest._fetch_professors. V003 schema:
    # institution lives in professor_affiliation; homepage_url in
    # source_page via primary_official_profile_page_id FK.
    query = [
        "SELECT p.professor_id::text AS professor_id,",
        "       p.canonical_name,",
        "       COALESCE(primary_aff.institution, '') AS institution,",
        "       sp.url AS homepage_url",
        "  FROM professor p",
        "  LEFT JOIN LATERAL (",
        "    SELECT pa.institution",
        "    FROM professor_affiliation pa",
        "    WHERE pa.professor_id = p.professor_id",
        "    ORDER BY pa.is_primary DESC,",
        "             pa.is_current DESC,",
        "             pa.start_year DESC NULLS LAST,",
        "             pa.created_at DESC NULLS LAST,",
        "             pa.affiliation_id DESC",
        "    LIMIT 1",
        "  ) primary_aff ON TRUE",
        "  LEFT JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id",
        " WHERE sp.url IS NOT NULL",
    ]
    params: list[Any] = []
    if institution:
        query.append("AND primary_aff.institution ILIKE %s")
        params.append(f"%{institution}%")
    if prof_id:
        query.append("AND p.professor_id = %s")
        params.append(prof_id)
    if limit is not None:
        query.append("LIMIT %s")
        params.append(limit)

    rows = conn.execute(" ".join(query), tuple(params)).fetchall()
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            normalized_rows.append(row)
            continue
        normalized_rows.append(
            {
                "professor_id": row[0],
                "canonical_name": row[1],
                "institution": row[2],
                "homepage_url": row[3],
            }
        )
    return normalized_rows
