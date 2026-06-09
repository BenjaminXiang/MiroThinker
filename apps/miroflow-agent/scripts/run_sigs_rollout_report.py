#!/usr/bin/env python3
"""Read-only rollout report for SIGS professor and paper collection."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_INSTITUTION = "清华大学深圳国际研究生院"


def _open_conn(dsn: str):
    return psycopg.connect(dsn, row_factory=dict_row)


def build_report(
    conn: Any,
    *,
    institution: str = DEFAULT_INSTITUTION,
    sample_limit: int = 20,
) -> dict[str, Any]:
    alembic_version = _fetch_scalar_dict(
        conn,
        "SELECT version_num FROM alembic_version",
        key="version_num",
        default="",
    )
    seeds = _fetchall(
        conn,
        """
        SELECT id, school, department, seed_url, last_run_status
          FROM professor_seed
         WHERE school = %s
            OR seed_url ILIKE '%%sigs.tsinghua.edu.cn%%'
         ORDER BY id
        """,
        (institution,),
    )
    professors = _fetchone(
        conn,
        """
        SELECT count(DISTINCT p.professor_id)::int AS total,
               count(DISTINCT p.professor_id)
                   FILTER (WHERE p.quality_status = 'ready')::int AS ready,
               count(DISTINCT p.professor_id)
                   FILTER (WHERE sp.page_id IS NOT NULL)::int AS with_primary_page
          FROM professor p
          JOIN professor_affiliation pa ON pa.professor_id = p.professor_id
          LEFT JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id
         WHERE pa.institution = %s
        """,
        (institution,),
    )
    source_pages = _fetchone(
        conn,
        """
        SELECT count(*)::int AS pages,
               count(*) FILTER (
                   WHERE clean_text_path IS NOT NULL AND clean_text_path <> ''
               )::int AS pages_with_clean_text,
               count(*) FILTER (WHERE is_official_source)::int AS official_pages
          FROM source_page sp
         WHERE sp.url ILIKE '%%sigs.tsinghua.edu.cn%%'
        """,
    )
    paper_links = _fetchone(
        conn,
        """
        WITH sigs_prof AS (
            SELECT DISTINCT p.professor_id
              FROM professor p
              JOIN professor_affiliation pa ON pa.professor_id = p.professor_id
             WHERE pa.institution = %s
        )
        SELECT count(*)::int AS links,
               count(*) FILTER (WHERE link_status = 'verified')::int AS verified,
               count(*) FILTER (WHERE is_officially_listed)::int AS officially_listed
          FROM professor_paper_link ppl
          JOIN sigs_prof sp ON sp.professor_id = ppl.professor_id
        """,
        (institution,),
    )
    papers = _fetchone(
        conn,
        """
        WITH sigs_prof AS (
            SELECT DISTINCT p.professor_id
              FROM professor p
              JOIN professor_affiliation pa ON pa.professor_id = p.professor_id
             WHERE pa.institution = %s
        ), linked AS (
            SELECT DISTINCT ppl.paper_id
              FROM professor_paper_link ppl
              JOIN sigs_prof sp ON sp.professor_id = ppl.professor_id
             WHERE ppl.link_status IN ('verified', 'candidate')
        )
        SELECT count(*)::int AS linked_papers,
               count(*) FILTER (
                   WHERE p.abstract_clean IS NOT NULL
                     AND length(trim(p.abstract_clean)) > 0
               )::int AS with_abstract,
               count(*) FILTER (
                   WHERE p.summary_zh IS NOT NULL
                     AND length(trim(p.summary_zh)) > 0
               )::int AS with_summary_zh,
               count(*) FILTER (WHERE p.quality_status = 'ready')::int AS ready,
               count(*) FILTER (WHERE p.canonical_source = 'prof_page_only')::int
                   AS page_only,
               count(*) FILTER (WHERE p.canonical_source = 'dblp')::int AS dblp
          FROM linked l
          JOIN paper p ON p.paper_id = l.paper_id
        """,
        (institution,),
    )
    papers_by_source = _fetch_key_counts(
        conn,
        """
        WITH sigs_prof AS (
            SELECT DISTINCT p.professor_id
              FROM professor p
              JOIN professor_affiliation pa ON pa.professor_id = p.professor_id
             WHERE pa.institution = %s
        ), linked AS (
            SELECT DISTINCT ppl.paper_id
              FROM professor_paper_link ppl
              JOIN sigs_prof sp ON sp.professor_id = ppl.professor_id
             WHERE ppl.link_status IN ('verified', 'candidate')
        )
        SELECT p.canonical_source, count(*)::int AS row_count
          FROM linked l
          JOIN paper p ON p.paper_id = l.paper_id
         GROUP BY p.canonical_source
         ORDER BY row_count DESC, p.canonical_source
        """,
        "canonical_source",
        (institution,),
    )
    title_resolution_sources = _fetch_key_counts(
        conn,
        """
        WITH sigs_prof AS (
            SELECT DISTINCT p.professor_id
              FROM professor p
              JOIN professor_affiliation pa ON pa.professor_id = p.professor_id
             WHERE pa.institution = %s
        ), linked AS (
            SELECT DISTINCT ppl.paper_id
              FROM professor_paper_link ppl
              JOIN sigs_prof sp ON sp.professor_id = ppl.professor_id
             WHERE ppl.link_status IN ('verified', 'candidate')
        )
        SELECT COALESCE(prc.match_source, p.canonical_source) AS title_match_source,
               count(*)::int AS row_count
          FROM linked l
          JOIN paper p ON p.paper_id = l.paper_id
          LEFT JOIN paper_title_resolution_cache prc
            ON prc.title_sha1 = encode(
                digest(
                    convert_to(
                        trim(regexp_replace(
                            regexp_replace(
                                lower(coalesce(p.title_clean, p.title_raw, '')),
                                '[^[:alnum:]_[:space:]]',
                                ' ',
                                'g'
                            ),
                            '[[:space:]]+',
                            ' ',
                            'g'
                        )),
                        'UTF8'
                    ),
                    'sha1'
                ),
                'hex'
            )
         GROUP BY COALESCE(prc.match_source, p.canonical_source)
         ORDER BY row_count DESC, title_match_source
        """,
        "title_match_source",
        (institution,),
    )
    issues = _fetchall(
        conn,
        """
        SELECT stage, severity, count(*)::int AS n
          FROM pipeline_issue
         WHERE institution = %s
            OR evidence_snapshot::text ILIKE %s
            OR evidence_snapshot::text ILIKE '%%sigs.tsinghua.edu.cn%%'
         GROUP BY stage, severity
         ORDER BY n DESC, stage, severity
         LIMIT 50
        """,
        (institution, f"%{institution}%"),
    )
    missing_summary_samples = _fetchall(
        conn,
        """
        WITH sigs_prof AS (
            SELECT DISTINCT p.professor_id
              FROM professor p
              JOIN professor_affiliation pa ON pa.professor_id = p.professor_id
             WHERE pa.institution = %s
        ), linked AS (
            SELECT ppl.paper_id, count(DISTINCT ppl.professor_id)::int AS professor_count
              FROM professor_paper_link ppl
              JOIN sigs_prof sp ON sp.professor_id = ppl.professor_id
             WHERE ppl.link_status IN ('verified', 'candidate')
             GROUP BY ppl.paper_id
        )
        SELECT p.paper_id,
               p.title_clean,
               p.canonical_source,
               p.quality_status,
               length(p.abstract_clean)::int AS abstract_len,
               linked.professor_count
          FROM linked
          JOIN paper p ON p.paper_id = linked.paper_id
         WHERE p.abstract_clean IS NOT NULL
           AND length(trim(p.abstract_clean)) > 0
           AND (p.summary_zh IS NULL OR length(trim(p.summary_zh)) = 0)
         ORDER BY linked.professor_count DESC, p.updated_at DESC NULLS LAST, p.paper_id
         LIMIT %s
        """,
        (institution, sample_limit),
    )

    papers = dict(papers)
    papers["summary_zh_gap"] = max(
        int(papers.get("with_abstract") or 0) - int(papers.get("with_summary_zh") or 0),
        0,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "institution": institution,
        "alembic_version": alembic_version,
        "readiness": {
            "v040_applied": str(alembic_version) >= "V040",
            "has_sigs_seed": bool(seeds),
        },
        "seeds": seeds,
        "professors": professors,
        "source_pages": source_pages,
        "paper_links": paper_links,
        "papers": papers,
        "papers_by_canonical_source": papers_by_source,
        "title_resolution_sources": title_resolution_sources,
        "pipeline_issue_counts": issues,
        "missing_summary_samples": missing_summary_samples,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = args.database_url or os.environ.get("DATABASE_URL")
    if not dsn:
        sys.stderr.write("DATABASE_URL is required for SIGS rollout report.\n")
        raise SystemExit(1)
    with _open_conn(dsn) as conn:
        payload = build_report(
            conn,
            institution=args.institution,
            sample_limit=args.sample_limit,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a read-only SIGS professor/paper rollout report.",
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--institution", default=DEFAULT_INSTITUTION)
    parser.add_argument("--sample-limit", type=int, default=20)
    return parser.parse_args(argv)


def _fetchone(conn: Any, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    row = conn.execute(query, params).fetchone()
    return dict(row or {})


def _fetchall(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _fetch_scalar_dict(
    conn: Any,
    query: str,
    *,
    key: str,
    default: Any,
) -> Any:
    row = conn.execute(query).fetchone()
    if not row:
        return default
    return row.get(key, default) if isinstance(row, dict) else row[0]


def _fetch_key_counts(
    conn: Any,
    query: str,
    key: str,
    params: tuple[Any, ...] = (),
) -> dict[str, int]:
    rows = _fetchall(conn, query, params)
    return {
        str(row.get(key) or "unknown"): int(row.get("row_count") or 0)
        for row in rows
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
