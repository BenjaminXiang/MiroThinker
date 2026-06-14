"""Resolve existing professor-page-only papers by title and migrate links.

This backfill is intentionally page-first: professor-page links remain the
relationship evidence, while external metadata sources only create or reuse a
better canonical paper row.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_APP_ROOT / ".env")
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.paper.canonical_writer import (  # noqa: E402
    PaperUpsertReport,
    upsert_paper,
)
from src.data_agents.paper.quality_promotion import (  # noqa: E402
    NEEDS_ENRICHMENT,
    PARTIAL,
)
from src.data_agents.paper.title_cleaner import (  # noqa: E402
    clean_paper_title,
    clean_reference_like_paper_title,
)
from src.data_agents.paper.title_quality import is_plausible_paper_title  # noqa: E402
from src.data_agents.paper.title_resolver import (  # noqa: E402
    ResolvedPaper,
    resolve_paper_by_title,
)
from src.data_agents.professor.name_selection import (  # noqa: E402
    is_unsafe_professor_paper_evidence_identity,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
    require_real_run_id,
)
from src.data_agents.storage.postgres.paper_merge_alias import (  # noqa: E402
    PaperMergeAliasInput,
    upsert_paper_merge_alias,
)
from src.data_agents.storage.postgres.title_resolution_cache import (  # noqa: E402
    PostgresTitleResolutionCache,
)

logger = logging.getLogger("run_paper_title_enrichment_backfill")

_RUN_KIND = "backfill_real"
_TRIGGERED_BY = "paper_title_enrichment_backfill"
_DEFAULT_MIN_CONFIDENCE = 0.85
_SAMPLE_LIMIT = 10
_UNSAFE_PROFESSOR_NAMES_SQL = (
    "'面包屑'",
    "'highlighted news'",
    "'deep bit lab'",
    "'lab introduction'",
)
_UNSAFE_AFFILIATION_TITLE_PATTERNS_SQL = (
    "'%%inventor:%%'",
    "'%%inventors:%%'",
    "'%%us patent%%'",
    "'%%u.s. patent%%'",
    "'%%patent no%%'",
    "'%%patent number%%'",
    "'%%pct/%%'",
    "'%%modified peptide nucleic acids and their use%%'",
    "'%%授权发明专利%%'",
    "'%%发明专利%%'",
    "'%%专利号%%'",
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve existing prof_page_only papers by title, create/reuse richer "
            "canonical paper rows, and migrate official professor-page links."
        ),
    )
    parser.add_argument("--limit", type=int, default=None, help="Max papers to scan")
    parser.add_argument(
        "--seed-id",
        action="append",
        default=[],
        help="Restrict to papers linked to professors from the latest succeeded roster_crawl for this seed; repeatable.",
    )
    parser.add_argument(
        "--paper-id",
        action="append",
        default=[],
        help="Restrict to one prof_page_only paper_id; repeatable.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=_DEFAULT_MIN_CONFIDENCE,
        help="Minimum title resolver confidence required to migrate links.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Read candidate rows and report local title-quality planning counts "
            "without opening a pipeline_run, calling resolver providers, or "
            "writing database state."
        ),
    )
    parser.add_argument(
        "--reject-implausible",
        action="store_true",
        help=(
            "Mark implausible existing prof_page_only titles and their links as "
            "rejected. Without this flag, implausible titles are only reported."
        ),
    )
    parser.add_argument(
        "--disable-openalex-title-search",
        action="store_true",
        help=(
            "Disable OpenAlex title search for faster bounded reruns; "
            "Crossref, Semantic Scholar, DBLP, and optional arXiv still run."
        ),
    )
    parser.add_argument(
        "--disable-dblp-title-search",
        action="store_true",
        help=(
            "Disable DBLP title search for non-CS or broad institutional "
            "backfills where DBLP adds little coverage and can rate-limit."
        ),
    )
    parser.add_argument(
        "--disable-arxiv-title-search",
        action="store_true",
        help="Disable arXiv title search for faster bounded reruns.",
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(resolve_dsn(url), row_factory=dict_row)


def _open_http_client():
    return httpx.Client(timeout=30.0, trust_env=False)


def _build_select_sql(
    *,
    limit: int | None,
    seed_ids: tuple[str, ...],
    paper_ids: tuple[str, ...],
) -> tuple[str, tuple[Any, ...]]:
    ctes: list[str] = []
    joins = [
        "JOIN professor_paper_link ppl ON ppl.paper_id = p.paper_id",
        "JOIN professor prof ON prof.professor_id = ppl.professor_id",
    ]
    conditions = [
        "p.canonical_source = 'prof_page_only'",
        "COALESCE(p.identity_status, 'unverified') NOT IN ('rejected', 'merged')",
        "COALESCE(p.quality_status, 'needs_enrichment') != 'rejected'",
        "COALESCE(prof.identity_status, 'resolved') NOT IN ('needs_review', 'merged_into', 'inactive')",
        (
            "lower(prof.canonical_name) NOT IN ("
            + ", ".join(_UNSAFE_PROFESSOR_NAMES_SQL)
            + ")"
        ),
        (
            "NOT EXISTS ("
            " SELECT 1"
            " FROM professor_affiliation unsafe_aff"
            " WHERE unsafe_aff.professor_id = prof.professor_id"
            "   AND COALESCE(unsafe_aff.is_current, true) = true"
            "   AND unsafe_aff.title IS NOT NULL"
            "   AND lower(unsafe_aff.title) LIKE ANY (ARRAY["
            + ", ".join(_UNSAFE_AFFILIATION_TITLE_PATTERNS_SQL)
            + "])"
            ")"
        ),
        "ppl.link_status = 'verified'",
        "COALESCE(ppl.is_officially_listed, false) = true",
    ]
    params: list[Any] = []
    if seed_ids:
        ctes.extend(_seed_scope_ctes())
        joins.append(
            "JOIN seed_professors seed_scope "
            "ON seed_scope.professor_id = ppl.professor_id"
        )
        params.append(list(seed_ids))
    if paper_ids:
        conditions.append("p.paper_id = ANY(%s)")
        params.append(list(paper_ids))

    sql = ""
    if ctes:
        sql += "WITH " + ", ".join(ctes) + " "
    sql += (
        "SELECT p.paper_id, p.title_clean, p.title_raw, p.doi, p.arxiv_id, "
        "       p.openalex_id, p.year, p.venue, p.authors_display, "
        "       p.abstract_clean, p.summary_zh, p.quality_status, "
        "       jsonb_agg(jsonb_build_object("
        "           'link_id', ppl.link_id,"
        "           'professor_id', ppl.professor_id,"
        "           'canonical_name', prof.canonical_name,"
        "           'evidence_source_type', ppl.evidence_source_type,"
        "           'evidence_page_id', ppl.evidence_page_id,"
        "           'evidence_api_source', ppl.evidence_api_source,"
        "           'match_reason', ppl.match_reason,"
        "           'author_name_match_score', ppl.author_name_match_score,"
        "           'topic_consistency_score', ppl.topic_consistency_score,"
        "           'institution_consistency_score', ppl.institution_consistency_score,"
        "           'is_officially_listed', ppl.is_officially_listed"
        "       ) ORDER BY ppl.updated_at DESC NULLS LAST, ppl.link_id) AS links "
        "  FROM paper p "
        f" {' '.join(joins)} "
        f" WHERE {' AND '.join(conditions)} "
        " GROUP BY p.paper_id, p.title_clean, p.title_raw, p.doi, p.arxiv_id, "
        "          p.openalex_id, p.year, p.venue, p.authors_display, "
        "          p.abstract_clean, p.summary_zh, p.quality_status "
        " ORDER BY count(DISTINCT ppl.professor_id) DESC, "
        "          p.updated_at DESC NULLS LAST, p.paper_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _seed_scope_ctes() -> list[str]:
    return [
        (
            "latest_seed_run AS ("
            " SELECT DISTINCT ON (pr.run_scope->>'seed_id')"
            "        pr.run_id, pr.run_scope->>'seed_id' AS seed_id"
            " FROM pipeline_run pr"
            " WHERE pr.run_kind = 'roster_crawl'"
            "   AND pr.status = 'succeeded'"
            "   AND pr.run_scope->>'seed_id' = ANY(%s)"
            " ORDER BY pr.run_scope->>'seed_id',"
            "          (pr.run_scope->>'trigger_mode' = 'full') DESC NULLS LAST,"
            "          pr.started_at DESC NULLS LAST,"
            "          pr.created_at DESC NULLS LAST,"
            "          pr.run_id DESC"
            ")"
        ),
        (
            "seed_professors AS ("
            " SELECT DISTINCT lr.seed_id, pa.professor_id"
            " FROM professor_affiliation pa"
            " JOIN latest_seed_run lr ON lr.run_id = pa.run_id"
            ")"
        ),
    ]


def _process_rows(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    cache: PostgresTitleResolutionCache | None,
    http_client,
    run_id: UUID | str,
    args: argparse.Namespace,
    resolve_title=resolve_paper_by_title,
    upsert_paper_fn=upsert_paper,
) -> dict[str, Any]:
    report = _empty_report(run_id=run_id, args=args, rows_total=len(rows))
    for row in rows:
        row_dict = dict(row)
        paper_id = str(row_dict["paper_id"])
        title = clean_reference_like_paper_title(
            row_dict.get("title_clean") or row_dict.get("title_raw")
        )
        links = _coerce_links(row_dict.get("links"))
        links, unsafe_links = _partition_safe_links(links)
        if unsafe_links:
            report["unsafe_links_filtered"] += len(unsafe_links)
            report["unsafe_link_rows"] += 1
            for unsafe_link in unsafe_links:
                _append_sample(
                    report,
                    "unsafe_link_samples",
                    _unsafe_link_sample(paper_id=paper_id, title=title, link=unsafe_link),
                )
        report["papers_processed"] += 1
        if not title or not links:
            report["papers_unresolved"] += 1
            _append_sample(
                report,
                "unresolved_samples",
                {
                    "paper_id": paper_id,
                    "title": title,
                    "reason": (
                        "unsafe_professor_links"
                        if title and unsafe_links
                        else "missing_title_or_links"
                    ),
                },
            )
            continue
        if not is_plausible_paper_title(title):
            report["papers_unresolved"] += 1
            _append_sample(
                report,
                "unresolved_samples",
                {
                    "paper_id": paper_id,
                    "title": title,
                    "reason": "implausible_title",
                },
            )
            if args.reject_implausible and not args.dry_run:
                report["implausible_links_rejected"] += _reject_implausible_links(
                    conn,
                    paper_id=paper_id,
                    run_id=run_id,
                )
                report["implausible_papers_rejected"] += _reject_implausible_paper(
                    conn,
                    paper_id=paper_id,
                    run_id=run_id,
                )
                report["pipeline_issues_inserted"] += _file_implausible_title_issue(
                    conn,
                    row=row_dict,
                    run_id=run_id,
                )
                conn.commit()
            continue
        try:
            resolved = _resolved_from_existing_identifier(row_dict, title) or resolve_title(
                title,
                author_hint=_first_author_hint(links),
                year_hint=_optional_int(row_dict.get("year")),
                enable_openalex_title_search=not args.disable_openalex_title_search,
                enable_dblp_title_search=not args.disable_dblp_title_search,
                enable_arxiv_title_search=not args.disable_arxiv_title_search,
                http_client=http_client,
                cache=None if args.dry_run else cache,
            )
            if resolved is None or resolved.match_confidence < args.min_confidence:
                report["papers_unresolved"] += 1
                _append_sample(
                    report,
                    "unresolved_samples",
                    {
                        "paper_id": paper_id,
                        "title": title,
                        "reason": "no_confident_resolution",
                        "confidence": (
                            None if resolved is None else resolved.match_confidence
                        ),
                    },
                )
                continue

            report["papers_resolved"] += 1
            _append_sample(
                report,
                "resolved_samples",
                _resolved_sample(row_dict, resolved),
            )
            if args.dry_run:
                continue

            upsert_report = _upsert_resolved_paper(
                conn,
                row=row_dict,
                resolved=resolved,
                run_id=run_id,
                upsert_paper_fn=upsert_paper_fn,
            )
            report["paper_upserts"] += 1
            resolved_paper_id = upsert_report.paper_id
            report["enrichment_copies"] += _copy_page_only_enrichment(
                conn,
                old_row=row_dict,
                resolved_paper_id=resolved_paper_id,
                run_id=run_id,
            )
            report["full_text_pdf_upserts"] += _upsert_resolved_pdf_metadata(
                conn,
                resolved_paper_id=resolved_paper_id,
                resolved=resolved,
                run_id=run_id,
            )
            if resolved_paper_id == paper_id:
                report["in_place_updates"] += 1
                conn.commit()
                continue

            migrated_links = 0
            for link in links:
                migrated_links += _upsert_migrated_link(
                    conn,
                    link=link,
                    old_paper_id=paper_id,
                    resolved_paper_id=resolved_paper_id,
                    resolved=resolved,
                    run_id=run_id,
                )
            report["link_migrations"] += migrated_links
            if migrated_links:
                report["merge_aliases_written"] += _write_merge_alias(
                    conn,
                    old_paper_id=paper_id,
                    resolved_paper_id=resolved_paper_id,
                    resolved=resolved,
                    run_id=run_id,
                )
                report["old_links_rejected"] += _reject_old_links(
                    conn,
                    old_paper_id=paper_id,
                    resolved_paper_id=resolved_paper_id,
                    run_id=run_id,
                )
                report["page_only_papers_merged"] += _mark_page_only_merged(
                    conn,
                    old_paper_id=paper_id,
                    resolved_paper_id=resolved_paper_id,
                    run_id=run_id,
                )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to title-backfill paper %s: %s", paper_id, exc)
            report["papers_with_errors"] += 1
            _append_sample(
                report,
                "error_samples",
                {"paper_id": paper_id, "title": title, "error": str(exc)},
            )
            try:
                conn.rollback()
            except Exception:
                pass
    return report


def _build_plan_report(
    rows: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "plan_only": True,
        "limit": args.limit,
        "seed_id": list(args.seed_id),
        "paper_id": list(args.paper_id),
        "papers_total": len(rows),
        "resolver_candidates": 0,
        "implausible_titles": 0,
        "missing_title_or_links": 0,
        "unsafe_links_filtered": 0,
        "unsafe_link_rows": 0,
        "candidate_samples": [],
        "implausible_samples": [],
        "missing_samples": [],
        "unsafe_link_samples": [],
    }
    for row in rows:
        row_dict = dict(row)
        paper_id = str(row_dict.get("paper_id") or "")
        title = clean_reference_like_paper_title(
            row_dict.get("title_clean") or row_dict.get("title_raw")
        )
        links = _coerce_links(row_dict.get("links"))
        links, unsafe_links = _partition_safe_links(links)
        if unsafe_links:
            report["unsafe_links_filtered"] += len(unsafe_links)
            report["unsafe_link_rows"] += 1
            for unsafe_link in unsafe_links:
                _append_sample(
                    report,
                    "unsafe_link_samples",
                    _unsafe_link_sample(paper_id=paper_id, title=title, link=unsafe_link),
                )
        if not title or not links:
            report["missing_title_or_links"] += 1
            _append_sample(
                report,
                "missing_samples",
                {"paper_id": paper_id, "title": title},
            )
            continue
        sample = {
            "paper_id": paper_id,
            "title": title,
            "linked_professors": len(links),
        }
        if not is_plausible_paper_title(title):
            report["implausible_titles"] += 1
            _append_sample(report, "implausible_samples", sample)
            continue
        report["resolver_candidates"] += 1
        _append_sample(report, "candidate_samples", sample)
    return report


def _empty_report(
    *,
    run_id: UUID | str,
    args: argparse.Namespace,
    rows_total: int,
) -> dict[str, Any]:
    return {
        "run_id": str(run_id),
        "plan_only": bool(getattr(args, "plan_only", False)),
        "dry_run": bool(args.dry_run),
        "limit": args.limit,
        "seed_id": list(args.seed_id),
        "paper_id": list(args.paper_id),
        "min_confidence": args.min_confidence,
        "openalex_title_search_enabled": not args.disable_openalex_title_search,
        "dblp_title_search_enabled": not args.disable_dblp_title_search,
        "arxiv_title_search_enabled": not args.disable_arxiv_title_search,
        "papers_total": rows_total,
        "papers_processed": 0,
        "papers_resolved": 0,
        "papers_unresolved": 0,
        "papers_with_errors": 0,
        "paper_upserts": 0,
        "in_place_updates": 0,
        "link_migrations": 0,
        "merge_aliases_written": 0,
        "old_links_rejected": 0,
        "page_only_papers_merged": 0,
        "implausible_papers_rejected": 0,
        "implausible_links_rejected": 0,
        "pipeline_issues_inserted": 0,
        "enrichment_copies": 0,
        "full_text_pdf_upserts": 0,
        "unsafe_links_filtered": 0,
        "unsafe_link_rows": 0,
        "resolved_samples": [],
        "unresolved_samples": [],
        "unsafe_link_samples": [],
        "error_samples": [],
    }


def _append_sample(report: dict[str, Any], key: str, sample: dict[str, Any]) -> None:
    samples = report[key]
    if len(samples) < _SAMPLE_LIMIT:
        samples.append(sample)


def _resolved_sample(row: dict[str, Any], resolved: ResolvedPaper) -> dict[str, Any]:
    return {
        "old_paper_id": str(row["paper_id"]),
        "title": clean_reference_like_paper_title(
            row.get("title_clean") or row.get("title_raw")
        ),
        "match_source": resolved.match_source,
        "match_confidence": round(resolved.match_confidence, 4),
        "doi": resolved.doi,
        "openalex_id": resolved.openalex_id,
        "arxiv_id": resolved.arxiv_id,
        "pdf_url": resolved.pdf_url,
        "year": resolved.year,
    }


def _upsert_resolved_paper(
    conn: Any,
    *,
    row: dict[str, Any],
    resolved: ResolvedPaper,
    run_id: UUID | str,
    upsert_paper_fn,
) -> PaperUpsertReport:
    quality_status = _initial_quality_status(resolved)
    return upsert_paper_fn(
        conn,
        title_clean=resolved.title
        or clean_reference_like_paper_title(
            row.get("title_clean") or row.get("title_raw")
        ),
        title_raw=clean_paper_title(row.get("title_raw") or row.get("title_clean")),
        doi=resolved.doi,
        arxiv_id=resolved.arxiv_id,
        openalex_id=resolved.openalex_id,
        semantic_scholar_id=None,
        year=resolved.year or _optional_int(row.get("year")),
        venue=resolved.venue,
        abstract_clean=resolved.abstract,
        authors_display=_authors_display(resolved.authors)
        or _optional_str(row.get("authors_display")),
        citation_count=None,
        canonical_source=_canonical_source_for_resolved(resolved),
        run_id=run_id,
        title_resolution_source=resolved.match_source,
        quality_status=quality_status,
    )


def _resolved_from_existing_identifier(
    row: dict[str, Any],
    title: str,
) -> ResolvedPaper | None:
    doi = _optional_str(row.get("doi"))
    arxiv_id = _optional_str(row.get("arxiv_id"))
    openalex_id = _optional_str(row.get("openalex_id"))
    if not any((doi, arxiv_id, openalex_id)):
        return None

    if openalex_id:
        match_source = "openalex"
    elif arxiv_id:
        match_source = "arxiv"
    else:
        match_source = "doi_lookup"

    return ResolvedPaper(
        title=title,
        doi=doi,
        openalex_id=openalex_id,
        arxiv_id=arxiv_id,
        abstract=_optional_str(row.get("abstract_clean")),
        pdf_url=None,
        authors=_split_authors_display(row.get("authors_display")),
        year=_optional_int(row.get("year")),
        venue=_optional_str(row.get("venue")),
        match_confidence=1.0,
        match_source=match_source,
    )


def _canonical_source_for_resolved(resolved: ResolvedPaper) -> str:
    if resolved.match_source == "doi_lookup":
        return "crossref"
    return resolved.match_source


def _initial_quality_status(resolved: ResolvedPaper) -> str:
    if any(
        (
            resolved.year is not None,
            bool(resolved.venue),
            bool(resolved.abstract),
            bool(resolved.authors),
        )
    ):
        return PARTIAL
    return NEEDS_ENRICHMENT


def _copy_page_only_enrichment(
    conn: Any,
    *,
    old_row: dict[str, Any],
    resolved_paper_id: str,
    run_id: UUID | str,
) -> int:
    summary_zh = _optional_str(old_row.get("summary_zh"))
    old_quality_status = _optional_str(old_row.get("quality_status"))
    if not summary_zh and old_quality_status != "ready":
        return 0

    cursor = conn.execute(
        """
        UPDATE paper
           SET summary_zh = COALESCE(summary_zh, %s),
               quality_status = CASE
                   WHEN quality_status IN ('rejected', 'ready', 'needs_review')
                       THEN quality_status
                   WHEN %s = 'ready'
                       THEN 'ready'
                   ELSE quality_status
               END,
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
        """,
        (
            summary_zh,
            old_quality_status,
            require_real_run_id(run_id, writer_name="_copy_page_only_enrichment"),
            resolved_paper_id,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _upsert_resolved_pdf_metadata(
    conn: Any,
    *,
    resolved_paper_id: str,
    resolved: ResolvedPaper,
    run_id: UUID | str,
) -> int:
    pdf_url = _optional_str(resolved.pdf_url)
    if not pdf_url:
        return 0

    cursor = conn.execute(
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
        VALUES (%s, %s, NULL, %s, NULL, NULL, NULL, %s, now(), NULL, %s)
        ON CONFLICT (paper_id) DO UPDATE
           SET abstract = COALESCE(paper_full_text.abstract, EXCLUDED.abstract),
               pdf_url = COALESCE(
                   NULLIF(BTRIM(paper_full_text.pdf_url), ''),
                   EXCLUDED.pdf_url
               ),
               source = CASE
                   WHEN NULLIF(BTRIM(COALESCE(paper_full_text.pdf_url, '')), '') IS NULL
                       THEN EXCLUDED.source
                   ELSE paper_full_text.source
               END,
               fetched_at = CASE
                   WHEN NULLIF(BTRIM(COALESCE(paper_full_text.pdf_url, '')), '') IS NULL
                       THEN now()
                   ELSE paper_full_text.fetched_at
               END,
               fetch_error = CASE
                   WHEN NULLIF(BTRIM(COALESCE(paper_full_text.pdf_url, '')), '') IS NULL
                       THEN NULL
                   ELSE paper_full_text.fetch_error
               END,
               run_id = CASE
                   WHEN NULLIF(BTRIM(COALESCE(paper_full_text.pdf_url, '')), '') IS NULL
                       THEN EXCLUDED.run_id
                   ELSE paper_full_text.run_id
               END
        """,
        (
            resolved_paper_id,
            _optional_str(resolved.abstract),
            pdf_url,
            f"title_resolution:{resolved.match_source}",
            require_real_run_id(run_id, writer_name="_upsert_resolved_pdf_metadata"),
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 1)


def _upsert_migrated_link(
    conn: Any,
    *,
    link: dict[str, Any],
    old_paper_id: str,
    resolved_paper_id: str,
    resolved: ResolvedPaper,
    run_id: UUID | str,
) -> int:
    professor_id = _required_str(link.get("professor_id"), "professor_id")
    cursor = conn.execute(
        """
        INSERT INTO professor_paper_link (
            professor_id,
            paper_id,
            link_status,
            evidence_source_type,
            evidence_page_id,
            evidence_api_source,
            match_reason,
            author_name_match_score,
            topic_consistency_score,
            institution_consistency_score,
            is_officially_listed,
            verified_by,
            verified_at,
            run_id
        )
        VALUES (%s, %s, 'verified', %s, %s, %s, %s, %s, %s, %s, %s, 'rule_auto', %s, %s)
        ON CONFLICT (professor_id, paper_id) DO UPDATE
           SET link_status                    = 'verified',
               evidence_source_type           = EXCLUDED.evidence_source_type,
               evidence_page_id               = EXCLUDED.evidence_page_id,
               evidence_api_source            = EXCLUDED.evidence_api_source,
               match_reason                   = EXCLUDED.match_reason,
               author_name_match_score        = EXCLUDED.author_name_match_score,
               topic_consistency_score        = EXCLUDED.topic_consistency_score,
               institution_consistency_score  = EXCLUDED.institution_consistency_score,
               is_officially_listed           = EXCLUDED.is_officially_listed,
               verified_by                    = EXCLUDED.verified_by,
               verified_at                    = EXCLUDED.verified_at,
               run_id                         = COALESCE(EXCLUDED.run_id, professor_paper_link.run_id),
               rejected_at                    = NULL,
               rejected_reason                = NULL,
               updated_at                     = now()
        """,
        (
            professor_id,
            resolved_paper_id,
            _required_str(link.get("evidence_source_type"), "evidence_source_type"),
            _optional_str(link.get("evidence_page_id")),
            _optional_str(link.get("evidence_api_source")),
            _migrated_match_reason(link, old_paper_id, resolved),
            _decimal_or_default(link.get("author_name_match_score"), Decimal("0.85")),
            _optional_decimal(link.get("topic_consistency_score")),
            _optional_decimal(link.get("institution_consistency_score")),
            bool(link.get("is_officially_listed", True)),
            datetime.now(timezone.utc),
            require_real_run_id(run_id, writer_name="_upsert_migrated_link"),
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _migrated_match_reason(
    link: dict[str, Any],
    old_paper_id: str,
    resolved: ResolvedPaper,
) -> str:
    previous_reason = _optional_str(link.get("match_reason")) or "official_homepage_publication"
    return (
        f"{previous_reason}; title_enrichment_backfill:{resolved.match_source}:"
        f"{old_paper_id}"
    )


def _write_merge_alias(
    conn: Any,
    *,
    old_paper_id: str,
    resolved_paper_id: str,
    resolved: ResolvedPaper,
    run_id: UUID | str,
) -> int:
    upsert_paper_merge_alias(
        conn,
        PaperMergeAliasInput(
            old_paper_id=old_paper_id,
            canonical_paper_id=resolved_paper_id,
            merge_reason=f"title_enrichment_backfill:{resolved.match_source}",
            evidence_source="professor_page_title_enrichment",
            run_id=require_real_run_id(run_id, writer_name="_write_merge_alias"),
        ),
    )
    return 1


def _reject_old_links(
    conn: Any,
    *,
    old_paper_id: str,
    resolved_paper_id: str,
    run_id: UUID | str,
) -> int:
    cursor = conn.execute(
        """
        UPDATE professor_paper_link
           SET link_status = 'rejected',
               rejected_at = now(),
               rejected_reason = %s,
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND link_status != 'rejected'
        """,
        (
            f"merged_into_resolved_paper:{resolved_paper_id}",
            require_real_run_id(run_id, writer_name="_reject_old_links"),
            old_paper_id,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _mark_page_only_merged(
    conn: Any,
    *,
    old_paper_id: str,
    resolved_paper_id: str,
    run_id: UUID | str,
) -> int:
    cursor = conn.execute(
        """
        UPDATE paper
           SET identity_status = 'merged',
               quality_status = 'rejected',
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND paper_id != %s
           AND canonical_source = 'prof_page_only'
        """,
        (
            require_real_run_id(run_id, writer_name="_mark_page_only_merged"),
            old_paper_id,
            resolved_paper_id,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _reject_implausible_links(
    conn: Any,
    *,
    paper_id: str,
    run_id: UUID | str,
) -> int:
    cursor = conn.execute(
        """
        UPDATE professor_paper_link
           SET link_status = 'rejected',
               rejected_at = now(),
               rejected_reason = 'implausible_title',
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND link_status != 'rejected'
        """,
        (
            require_real_run_id(run_id, writer_name="_reject_implausible_links"),
            paper_id,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _reject_implausible_paper(
    conn: Any,
    *,
    paper_id: str,
    run_id: UUID | str,
) -> int:
    cursor = conn.execute(
        """
        UPDATE paper
           SET identity_status = 'rejected',
               quality_status = 'rejected',
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND canonical_source = 'prof_page_only'
        """,
        (
            require_real_run_id(run_id, writer_name="_reject_implausible_paper"),
            paper_id,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _file_implausible_title_issue(
    conn: Any,
    *,
    row: dict[str, Any],
    run_id: UUID | str,
) -> int:
    paper_id = str(row["paper_id"])
    title = clean_reference_like_paper_title(
        row.get("title_clean") or row.get("title_raw")
    )
    snapshot = {
        "run_id": str(require_real_run_id(run_id, writer_name="_file_implausible_title_issue")),
        "issue_type": "implausible_title",
        "paper_id": paper_id,
        "title": title,
        "canonical_source": row.get("canonical_source") or "prof_page_only",
    }
    cursor = conn.execute(
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
        VALUES (NULL, %s, 'paper_quality', 'medium', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            f"paper:{paper_id}",
            f"[implausible_title] {paper_id}: {title[:180]}",
            json.dumps(snapshot, ensure_ascii=False, default=str),
            _TRIGGERED_BY,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _first_author_hint(links: list[dict[str, Any]]) -> str | None:
    for link in links:
        if value := _optional_str(link.get("canonical_name")):
            return value
    return None


def _partition_safe_links(
    links: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    safe: list[dict[str, Any]] = []
    unsafe: list[dict[str, Any]] = []
    for link in links:
        if is_unsafe_professor_paper_evidence_identity(link.get("canonical_name")):
            unsafe.append(link)
        else:
            safe.append(link)
    return safe, unsafe


def _unsafe_link_sample(
    *,
    paper_id: str,
    title: str | None,
    link: dict[str, Any],
) -> dict[str, Any]:
    return {
        "paper_id": paper_id,
        "title": title,
        "professor_id": _optional_str(link.get("professor_id")),
        "canonical_name": _optional_str(link.get("canonical_name")),
    }


def _coerce_links(value: object) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _authors_display(authors: tuple[str, ...]) -> str | None:
    return ", ".join(item for item in authors if item) or None


def _split_authors_display(value: object) -> tuple[str, ...]:
    text = _optional_str(value)
    if text is None:
        return ()
    return tuple(item.strip() for item in text.split(",") if item.strip())


def _required_str(value: object, field_name: str) -> str:
    text = _optional_str(value)
    if text is None:
        raise ValueError(f"{field_name} is required")
    return text


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _decimal_or_default(value: object, default: Decimal) -> Decimal:
    parsed = _optional_decimal(value)
    return parsed if parsed is not None else default


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print("ERROR: DATABASE_URL not set. Run with DATABASE_URL=postgresql://...", file=sys.stderr)
        raise SystemExit(1)

    conn = _open_database_connection(dsn)
    http_client = None
    run_id: UUID | str | None = None
    try:
        sql, params = _build_select_sql(
            limit=args.limit,
            seed_ids=tuple(str(item) for item in args.seed_id),
            paper_ids=tuple(str(item) for item in args.paper_id),
        )
        if args.plan_only:
            rows = list(conn.execute(sql, params).fetchall())
            report = _build_plan_report(rows, args=args)
            print(json.dumps(report, ensure_ascii=False, default=str))
            return

        if args.dry_run:
            run_id = f"dry-run-{uuid4()}"
        else:
            run_id = open_pipeline_run(
                conn,
                run_kind=_RUN_KIND,
                run_scope={
                    "task": "paper_title_enrichment_backfill",
                    "limit": args.limit,
                    "seed_id": list(args.seed_id),
                    "paper_id": list(args.paper_id),
                    "dry_run": args.dry_run,
                    "min_confidence": args.min_confidence,
                    "reject_implausible": args.reject_implausible,
                    "openalex_title_search_enabled": (
                        not args.disable_openalex_title_search
                    ),
                    "dblp_title_search_enabled": not args.disable_dblp_title_search,
                    "arxiv_title_search_enabled": not args.disable_arxiv_title_search,
                },
                triggered_by=_TRIGGERED_BY,
            )
            run_id = require_real_run_id(
                run_id,
                writer_name="run_paper_title_enrichment_backfill",
            )
            conn.commit()

        rows = list(conn.execute(sql, params).fetchall())
        cache = None if args.dry_run else PostgresTitleResolutionCache(conn)
        http_client = _open_http_client()
        report = _process_rows(
            conn,
            rows,
            cache=cache,
            http_client=http_client,
            run_id=run_id,
            args=args,
        )
        if not args.dry_run:
            close_pipeline_run(
                conn,
                run_id,
                status="partial" if report["papers_with_errors"] else "succeeded",
                items_processed=report["papers_processed"],
                items_failed=report["papers_with_errors"],
            )
            conn.commit()
        print(json.dumps(report, ensure_ascii=False, default=str))
    except Exception as exc:
        if run_id is not None and not args.dry_run:
            conn.rollback()
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                error_summary={"message": str(exc)},
            )
            conn.commit()
        raise
    finally:
        close_http = getattr(http_client, "close", None)
        if callable(close_http):
            close_http()
        close_conn = getattr(conn, "close", None)
        if callable(close_conn):
            close_conn()


if __name__ == "__main__":
    main()
