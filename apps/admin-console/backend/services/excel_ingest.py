"""Structured ingestion for analysed operator workbooks.

`excel_structure` decides the domain and column mapping; this module writes
the mapped rows into the raw collection tables. It deliberately uses the
seed-only collection DSN so a serving node does not need the build-time
`DATABASE_URL`.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any, Iterable

import psycopg

from backend.console_dsn import resolve_seed_dsn
from backend.services.excel_structure import SheetAnalysis, stable_upload_id


class ExcelIngestError(ValueError):
    pass


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date(value: Any) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _collection_dsn() -> str:
    dsn = resolve_seed_dsn()
    if not dsn:
        raise ExcelIngestError("collection database is not configured")
    return dsn


def _upsert_company(conn: Any, row: dict[str, Any]) -> str:
    name = _text(row.get("company_name"))
    if not name:
        raise ExcelIngestError("missing company_name")
    credit = _text(row.get("credit_code"))
    website = _text(row.get("website"))
    summary = _text(row.get("description"))
    existing = None
    if credit:
        existing = conn.execute(
            "SELECT company_id FROM company WHERE unified_credit_code = %s",
            (credit,),
        ).fetchone()
    if existing:
        company_id = str(existing[0])
        conn.execute(
            """
            UPDATE company
               SET canonical_name = %s,
                   website = COALESCE(%s, website),
                   profile_summary = COALESCE(%s, profile_summary),
                   quality_status = 'needs_review',
                   updated_at = now()
             WHERE company_id = %s
            """,
            (name, website, summary, company_id),
        )
        return company_id
    company_id = stable_upload_id("company-upload", credit or name)
    conn.execute(
        """
        INSERT INTO company (
            company_id, unified_credit_code, canonical_name, registered_name,
            aliases, website, profile_summary, country, identity_status,
            quality_status
        ) VALUES (%s, %s, %s, %s, '[]'::jsonb, %s, %s, '国内', 'needs_review',
                  'needs_review')
        ON CONFLICT (company_id) DO UPDATE
           SET canonical_name = EXCLUDED.canonical_name,
               unified_credit_code = COALESCE(EXCLUDED.unified_credit_code, company.unified_credit_code),
               website = COALESCE(EXCLUDED.website, company.website),
               profile_summary = COALESCE(EXCLUDED.profile_summary, company.profile_summary),
               quality_status = 'needs_review',
               updated_at = now()
        """,
        (company_id, credit, name, name, website, summary),
    )
    return company_id


def _patent_type(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    if "发明" in text:
        return "发明"
    if "实用新型" in text:
        return "实用新型"
    if "外观" in text:
        return "外观"
    if "PCT" in text.upper():
        return "PCT"
    return "其他"


def _upsert_patent(conn: Any, row: dict[str, Any]) -> str:
    title = _text(row.get("title"))
    if not title:
        raise ExcelIngestError("missing patent title")
    number = _text(row.get("patent_number"))
    existing = None
    if number:
        existing = conn.execute(
            "SELECT patent_id FROM patent WHERE patent_number = %s", (number,)
        ).fetchone()
    if existing:
        patent_id = str(existing[0])
        conn.execute(
            """
            UPDATE patent
               SET title_clean = %s,
                   applicants_raw = COALESCE(%s, applicants_raw),
                   inventors_raw = COALESCE(%s, inventors_raw),
                   filing_date = COALESCE(%s, filing_date),
                   publication_date = COALESCE(%s, publication_date),
                   status = COALESCE(%s, status),
                   abstract_clean = COALESCE(%s, abstract_clean),
                   quality_status = 'needs_review',
                   updated_at = now()
             WHERE patent_id = %s
            """,
            (
                title,
                _text(row.get("applicants")),
                _text(row.get("inventors")),
                _date(row.get("filing_date")),
                _date(row.get("publication_date")),
                _text(row.get("status")),
                _text(row.get("abstract")),
                patent_id,
            ),
        )
        return patent_id
    patent_id = stable_upload_id("patent-upload", number or title)
    conn.execute(
        """
        INSERT INTO patent (
            patent_id, patent_number, title_clean, title_raw,
            applicants_raw, inventors_raw, filing_date, publication_date,
            patent_type, status, abstract_clean, quality_status, identity_status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'needs_review',
                  'unverified')
        ON CONFLICT (patent_id) DO UPDATE
           SET title_clean = EXCLUDED.title_clean,
               applicants_raw = COALESCE(EXCLUDED.applicants_raw, patent.applicants_raw),
               quality_status = 'needs_review',
               updated_at = now()
        """,
        (
            patent_id,
            number,
            title,
            title,
            _text(row.get("applicants")),
            _text(row.get("inventors")),
            _date(row.get("filing_date")),
            _date(row.get("publication_date")),
            _patent_type(row.get("patent_type")),
            _text(row.get("status")),
            _text(row.get("abstract")),
        ),
    )
    return patent_id


def _upsert_paper(conn: Any, row: dict[str, Any]) -> str:
    title = _text(row.get("title"))
    if not title:
        raise ExcelIngestError("missing paper title")
    doi = _text(row.get("doi"))
    existing = None
    if doi:
        existing = conn.execute(
            "SELECT paper_id FROM paper WHERE doi = %s", (doi,)
        ).fetchone()
    if existing:
        paper_id = str(existing[0])
        conn.execute(
            """
            UPDATE paper
               SET title_clean = %s,
                   year = COALESCE(%s, year),
                   venue = COALESCE(%s, venue),
                   abstract_clean = COALESCE(%s, abstract_clean),
                   authors_display = COALESCE(%s, authors_display),
                   quality_status = 'needs_review',
                   updated_at = now()
             WHERE paper_id = %s
            """,
            (
                title,
                _int(row.get("year")),
                _text(row.get("venue")),
                _text(row.get("abstract")),
                _text(row.get("authors")),
                paper_id,
            ),
        )
        return paper_id
    paper_id = stable_upload_id("paper-upload", doi or title)
    conn.execute(
        """
        INSERT INTO paper (
            paper_id, title_clean, title_raw, doi, arxiv_id, year, venue,
            abstract_clean, authors_display, authors_raw, citation_count,
            canonical_source, quality_status, identity_status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, 'manual',
                  'needs_review', 'unverified')
        ON CONFLICT (paper_id) DO UPDATE
           SET title_clean = EXCLUDED.title_clean,
               doi = COALESCE(EXCLUDED.doi, paper.doi),
               abstract_clean = COALESCE(EXCLUDED.abstract_clean, paper.abstract_clean),
               quality_status = 'needs_review',
               updated_at = now()
        """,
        (
            paper_id,
            title,
            title,
            doi,
            _text(row.get("arxiv_id")),
            _int(row.get("year")),
            _text(row.get("venue")),
            _text(row.get("abstract")),
            _text(row.get("authors")),
            json.dumps(row.get("authors") or [], ensure_ascii=False),
            _int(row.get("citation_count")),
        ),
    )
    return paper_id


def _upsert_professor(conn: Any, row: dict[str, Any]) -> str:
    name = _text(row.get("name"))
    if not name:
        raise ExcelIngestError("missing professor name")
    school = _text(row.get("school")) or ""
    professor_id = stable_upload_id("professor-upload", f"{name}|{school}")
    summary_parts = [
        _text(row.get("research")),
        _text(row.get("summary")),
        _text(row.get("title")),
    ]
    summary = "；".join(part for part in summary_parts if part) or None
    conn.execute(
        """
        INSERT INTO professor (
            professor_id, canonical_name, canonical_name_zh, aliases,
            discipline_family, identity_status, profile_summary,
            quality_status, lifecycle_state, paper_count, citation_count
        ) VALUES (%s, %s, %s, '{}'::text[], 'other', 'needs_review', %s,
                  'needs_review', 'active', %s, %s)
        ON CONFLICT (professor_id) DO UPDATE
           SET canonical_name = EXCLUDED.canonical_name,
               profile_summary = COALESCE(EXCLUDED.profile_summary, professor.profile_summary),
               quality_status = 'needs_review',
               updated_at = now()
        """,
        (
            professor_id,
            name,
            name,
            summary,
            _int(row.get("paper_count")),
            _int(row.get("citation_count")),
        ),
    )
    homepage = _text(row.get("homepage"))
    if school and homepage:
        existing = conn.execute(
            "SELECT id FROM professor_seed WHERE seed_url = %s", (homepage,)
        ).fetchone()
        if existing is None:
            next_id = conn.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM professor_seed"
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO professor_seed (
                    id, school, department, seed_url, last_run_status
                ) VALUES (%s, %s, %s, %s, 'never_run')
                ON CONFLICT DO NOTHING
                """,
                (next_id, school, _text(row.get("department")), homepage),
            )
    return professor_id


def ingest_analysis(
    analysis: SheetAnalysis,
    rows: Iterable[dict[str, Any]],
    *,
    operator: str,
) -> dict[str, Any]:
    dsn = _collection_dsn()
    inserted = updated = skipped = 0
    errors: list[str] = []
    ids: list[str] = []
    with psycopg.connect(dsn) as conn:
        for index, row in enumerate(rows, start=1):
            try:
                if analysis.domain == "company":
                    before = _text(row.get("credit_code"))
                    existed = bool(
                        before
                        and conn.execute(
                            "SELECT 1 FROM company WHERE unified_credit_code = %s",
                            (before,),
                        ).fetchone()
                    )
                    ids.append(_upsert_company(conn, row))
                elif analysis.domain == "patent":
                    before = _text(row.get("patent_number"))
                    existed = bool(
                        before
                        and conn.execute(
                            "SELECT 1 FROM patent WHERE patent_number = %s", (before,)
                        ).fetchone()
                    )
                    ids.append(_upsert_patent(conn, row))
                elif analysis.domain == "paper":
                    before = _text(row.get("doi"))
                    existed = bool(
                        before
                        and conn.execute(
                            "SELECT 1 FROM paper WHERE doi = %s", (before,)
                        ).fetchone()
                    )
                    ids.append(_upsert_paper(conn, row))
                elif analysis.domain == "professor":
                    existed = False
                    ids.append(_upsert_professor(conn, row))
                else:
                    skipped += 1
                    continue
                if existed:
                    updated += 1
                else:
                    inserted += 1
            except Exception as exc:  # noqa: BLE001 - per-row boundary
                skipped += 1
                if len(errors) < 5:
                    errors.append(f"row {index}: {type(exc).__name__}: {exc}")
        conn.commit()
    return {
        "domain": analysis.domain,
        "rows_parsed": inserted + updated + skipped,
        "rows_inserted": inserted,
        "rows_updated": updated,
        "rows_skipped": skipped,
        "ids": ids[:20],
        "errors": errors,
        "operator": operator,
    }


__all__ = ["ExcelIngestError", "ingest_analysis"]
