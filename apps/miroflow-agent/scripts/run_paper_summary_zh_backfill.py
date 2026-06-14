"""Backfill paper.summary_zh from paper.abstract_clean via Gemma4."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env")
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.paper.abstract_translator import (  # noqa: E402
    judge_summary_boilerplate,
    translate_abstract_to_zh,
)
from src.data_agents.paper.enrichment import enrich_paper_with_hybrid_sources  # noqa: E402
from src.data_agents.paper.full_text_fetcher import (  # noqa: E402
    fetch_pdf_url_full_text,
)
from src.data_agents.paper.models import (  # noqa: E402
    PaperAuthorMetadata,
    PaperIdentifierContradiction,
    PaperMetadataEnrichment,
)
from src.data_agents.paper.quality_promotion import (  # noqa: E402
    NEEDS_ENRICHMENT,
    NEEDS_REVIEW,
    PaperEnrichmentSignals,
    evaluate_paper_promotion,
)
from src.data_agents.paper.text_sanitizer import (  # noqa: E402
    sanitize_json_for_postgres,
    sanitize_optional_text_for_postgres,
    sanitize_text_for_postgres,
)
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)
from src.data_agents.storage.postgres.paper_full_text import (  # noqa: E402
    upsert_paper_full_text,
)

logger = logging.getLogger("run_paper_summary_zh_backfill")

_AUTHOR_LIST_HEAD_RE = re.compile(
    r"^[A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+)*"
    r"(?:\s*,\s*[A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+)*){2,}"
)
_CITATION_METADATA_RE = re.compile(
    r"\b(?:Proceedings of the|Annual Meeting of the|Conference on|"
    r"International Joint Conference|Association for Computational Linguistics)\b",
    re.IGNORECASE,
)
_PUBLISHER_NOTE_RE = re.compile(
    r"^\s*(?:please note|the publisher is not responsible|"
    r"proceedings of the national academy of sciences|international audience)\b",
    re.IGNORECASE,
)
_TRUNCATED_FRAGMENT_RE = re.compile(r"\[\s*\.\.\.\s*\]")
_LEADING_FRAGMENT_RE = re.compile(
    r"^\s*(?:and|or|but)\b",
    re.IGNORECASE,
)
_VENUE_ONLY_RE = re.compile(
    r"^\s*[A-Z][A-Za-z&/ .'-]+Conference\s+\d{4},\s+"
    r"[A-Z][A-Za-z .'-]+,\s+[A-Za-z .'-]+,\s+"
    r"(?:\d{1,2}-\d{1,2}\s+[A-Z][A-Za-z]+\s+\d{4}|"
    r"[A-Z][A-Za-z]+\s+\d{1,2}-\d{1,2},\s+\d{4})\s*$"
)
_AUTHOR_AFFILIATION_RE = re.compile(
    r"^\s*[A-Z][A-Za-z'’.-]+[a-z]?\*?"
    r".{0,220}\b[a-z]\s+"
    r"(?:School|Department|University|Institute|College)\b",
    re.IGNORECASE,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill paper.summary_zh from English abstracts via Gemma4.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max papers to process")
    only_group = parser.add_mutually_exclusive_group()
    only_group.add_argument(
        "--only-missing",
        dest="only_missing",
        action="store_true",
        help="Only process papers missing summary_zh (default)",
    )
    only_group.add_argument(
        "--all",
        dest="only_missing",
        action="store_false",
        help="Process all papers with abstract_clean and overwrite summary_zh",
    )
    parser.set_defaults(only_missing=True)
    parser.add_argument(
        "--resume",
        nargs="?",
        const="",
        default=None,
        help="Checkpoint JSONL path to skip already-processed paper_ids",
    )
    parser.add_argument(
        "--professor-id",
        action="append",
        default=[],
        help="Restrict to papers linked to this professor_id; repeatable.",
    )
    parser.add_argument(
        "--institution",
        action="append",
        default=[],
        help="Restrict to papers linked to professors at this institution; repeatable.",
    )
    parser.add_argument(
        "--paper-id",
        action="append",
        default=[],
        help="Restrict to one paper_id; repeatable.",
    )
    parser.add_argument(
        "--paper-id-file",
        action="append",
        default=[],
        help="Read paper_id values from a text file; one ID per line, repeatable.",
    )
    parser.add_argument(
        "--seed-id",
        action="append",
        default=[],
        help=(
            "Restrict to papers linked to professors from the latest succeeded "
            "roster_crawl for this seed_id; repeatable."
        ),
    )
    parser.add_argument(
        "--enrich-doi-metadata",
        action="store_true",
        help=(
            "Before summary generation, use DOI enrichment to fill missing "
            "abstract/venue/year/citation fields."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    try:
        args.paper_id = _merge_unique_ids(
            [*args.paper_id, *_read_paper_id_files(tuple(args.paper_id_file))]
        )
    except OSError as exc:
        parser.error(str(exc))
    return args


def _read_paper_id_files(paths: tuple[str, ...]) -> list[str]:
    paper_ids: list[str] = []
    for item in paths:
        path = Path(item)
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                value = line.strip()
                if not value or value.startswith("#"):
                    continue
                paper_ids.append(value)
    return paper_ids


def _merge_unique_ids(values: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return merged


def _open_database_connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _open_llm_client():
    import httpx
    from openai import OpenAI

    settings = resolve_professor_llm_settings("gemma4", include_profile=True)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        http_client=httpx.Client(timeout=90.0, trust_env=False),
        timeout=90.0,
    )
    extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
    return client, settings["local_llm_model"], extra_body


def _resolve_checkpoint_path(resume_arg: str | None, run_id: str) -> Path:
    if resume_arg:
        return Path(resume_arg)
    base = _REPO_ROOT / "logs" / "data_agents" / "paper" / "summary_zh_runs"
    return base / f"{run_id}.jsonl"


def _load_resume_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    paper_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping corrupted resume line: %s", line[:80])
                continue
            if isinstance(row, dict) and isinstance(row.get("paper_id"), str):
                paper_ids.add(row["paper_id"])
    return paper_ids


def _append_checkpoint(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_select_sql(
    *,
    only_missing: bool,
    limit: int | None,
    professor_ids: tuple[str, ...] = (),
    paper_ids: tuple[str, ...] = (),
    institutions: tuple[str, ...] = (),
    seed_ids: tuple[str, ...] = (),
    include_doi_enrichment: bool = False,
) -> tuple[str, tuple[Any, ...]]:
    abstract_expr = (
        "COALESCE(NULLIF(trim(p.abstract_clean), ''), "
        "NULLIF(trim(pft.abstract), ''), "
        "NULLIF(trim(pft.intro), ''))"
    )
    if include_doi_enrichment:
        conditions = [
            "("
            f"({abstract_expr} IS NOT NULL) "
            "OR (p.doi IS NOT NULL AND length(trim(p.doi)) > 0) "
            "OR (p.arxiv_id IS NOT NULL AND length(trim(p.arxiv_id)) > 0) "
            "OR (p.openalex_id IS NOT NULL AND length(trim(p.openalex_id)) > 0)"
            ")",
        ]
    else:
        conditions = [
            f"{abstract_expr} IS NOT NULL",
        ]
    conditions.extend(
        [
            "COALESCE(p.identity_status, 'unverified') NOT IN ('rejected', 'merged')",
            "COALESCE(p.quality_status, 'needs_enrichment') != 'rejected'",
        ]
    )
    params: list[Any] = []
    if only_missing:
        conditions.append("(p.summary_zh IS NULL OR length(trim(p.summary_zh)) = 0)")
    ctes: list[str] = []
    join_parts = ["LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id"]
    if professor_ids or institutions or seed_ids:
        join_parts.append("JOIN professor_paper_link ppl ON ppl.paper_id = p.paper_id")
        conditions.append("ppl.link_status = 'verified'")
    if seed_ids:
        ctes.extend(_seed_scope_ctes())
        join_parts.append(
            "JOIN seed_professors seed_scope "
            "ON seed_scope.professor_id = ppl.professor_id"
        )
        params.append(list(seed_ids))
    if institutions:
        join_parts.append(
            "JOIN professor_affiliation pa ON pa.professor_id = ppl.professor_id"
        )
        conditions.append("pa.institution = ANY(%s)")
        params.append(list(institutions))
    if professor_ids:
        conditions.append("ppl.professor_id = ANY(%s)")
        params.append(list(professor_ids))
    if paper_ids:
        conditions.append("p.paper_id = ANY(%s)")
        params.append(list(paper_ids))
    sql = ""
    if ctes:
        sql += "WITH " + ", ".join(ctes) + " "
    sql += (
        "SELECT DISTINCT p.paper_id, p.title_clean, p.title_raw, p.doi, p.arxiv_id, "
        "p.openalex_id, p.year, p.venue, p.authors_display, p.abstract_clean, "
        "pft.abstract AS full_text_abstract, "
        "pft.intro AS full_text_intro, "
        f"{abstract_expr} AS abstract_for_summary, "
        "CASE "
        "WHEN NULLIF(trim(p.abstract_clean), '') IS NOT NULL THEN 'paper.abstract_clean' "
        "WHEN NULLIF(trim(pft.abstract), '') IS NOT NULL THEN 'paper_full_text.abstract' "
        "WHEN NULLIF(trim(pft.intro), '') IS NOT NULL THEN 'paper_full_text.intro' "
        "ELSE NULL END AS abstract_for_summary_source, "
        "p.summary_zh, p.quality_status, p.citation_count "
        "  FROM paper p "
        f"{' '.join(join_parts)} "
        f" WHERE {' AND '.join(conditions)} "
        " ORDER BY p.paper_id"
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
            "          (COALESCE(pr.run_scope->>'trigger_mode', '') = 'full') DESC,"
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


def _metadata_updates_from_enrichment(
    row: dict[str, Any],
    enrichment: PaperMetadataEnrichment,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    abstract = sanitize_optional_text_for_postgres(enrichment.abstract)
    if not _is_usable_abstract(row.get("abstract_clean")) and _is_usable_abstract(abstract):
        updates["abstract_clean"] = abstract
    venue = sanitize_optional_text_for_postgres(enrichment.venue)
    if not str(row.get("venue") or "").strip() and venue:
        updates["venue"] = venue
    if row.get("year") is None and enrichment.publication_date:
        year = _year_from_publication_date(enrichment.publication_date)
        if year is not None:
            updates["year"] = year
    if row.get("citation_count") is None and enrichment.citation_count is not None:
        updates["citation_count"] = enrichment.citation_count
    if not str(row.get("authors_display") or "").strip():
        authors_display = _authors_display_from_enrichment(enrichment.authors)
        if authors_display:
            updates["authors_display"] = authors_display
    return updates


def _persist_metadata_enrichment(
    conn: Any,
    *,
    paper_id: str,
    updates: dict[str, Any],
    quality_status: str,
    run_id: str,
) -> None:
    conn.execute(
        """
        UPDATE paper
           SET abstract_clean = COALESCE(%s, abstract_clean),
               venue = COALESCE(venue, %s),
               year = COALESCE(year, %s),
               citation_count = COALESCE(citation_count, %s),
               authors_display = COALESCE(authors_display, %s),
               quality_status = %s,
               updated_at = now(),
               run_id = %s
         WHERE paper_id = %s
        """,
        (
            sanitize_optional_text_for_postgres(updates.get("abstract_clean")),
            sanitize_optional_text_for_postgres(updates.get("venue")),
            updates.get("year"),
            updates.get("citation_count"),
            sanitize_optional_text_for_postgres(updates.get("authors_display")),
            quality_status,
            run_id,
            paper_id,
        ),
    )


def _authors_display_from_enrichment(
    authors: tuple[PaperAuthorMetadata, ...],
) -> str | None:
    names = [
        name
        for author in authors
        if (name := sanitize_optional_text_for_postgres(author.display_name))
    ]
    return sanitize_optional_text_for_postgres(", ".join(names))


def _file_identifier_contradiction_issue(
    conn: Any,
    *,
    paper_id: str,
    row: dict[str, Any],
    enrichment: PaperMetadataEnrichment,
    run_id: str,
) -> int:
    contradictions = tuple(enrichment.identifier_contradictions)
    if not contradictions:
        return 0
    snapshot = {
        "run_id": str(run_id),
        "issue_type": "identifier_contradiction",
        "paper_id": paper_id,
        "title": row.get("title_clean") or row.get("title_raw"),
        "canonical_doi": row.get("doi"),
        "canonical_arxiv_id": row.get("arxiv_id"),
        "enrichment_sources": enrichment.enrichment_sources,
        "contradictions": [
            _identifier_contradiction_to_dict(item) for item in contradictions
        ],
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
        VALUES (NULL, %s, 'paper_quality', 'high', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            f"paper:{paper_id}",
            f"[identifier_contradiction] {paper_id}",
            json.dumps(sanitize_json_for_postgres(snapshot), ensure_ascii=False),
            "run_paper_summary_zh_backfill",
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _identifier_contradiction_to_dict(
    contradiction: PaperIdentifierContradiction,
) -> dict[str, str]:
    return {
        "identifier_type": contradiction.identifier_type,
        "canonical_value": contradiction.canonical_value,
        "source_value": contradiction.source_value,
        "source": contradiction.source,
    }


def _doi_pdf_source(enrichment: PaperMetadataEnrichment) -> str:
    for source in enrichment.enrichment_sources:
        source_text = str(source or "").strip()
        if source_text:
            return f"doi_pdf:{source_text}"
    return "doi_pdf"


def _year_from_publication_date(value: str | None) -> int | None:
    if not value:
        return None
    prefix = value.strip()[:4]
    if not prefix.isdigit():
        return None
    year = int(prefix)
    return year if 1800 <= year <= 2100 else None


def _persist_summary_zh(
    conn: Any,
    *,
    paper_id: str,
    summary_zh: str,
    quality_status: str,
    run_id: str,
) -> None:
    conn.execute(
        """
        UPDATE paper
           SET summary_zh = %s,
               quality_status = %s,
               updated_at = now(),
               run_id = %s
         WHERE paper_id = %s
        """,
        (sanitize_text_for_postgres(summary_zh) or "", quality_status, run_id, paper_id),
    )


def _reject_summary_zh(
    conn: Any,
    *,
    paper_id: str,
    quality_status: str,
    run_id: str,
) -> None:
    conn.execute(
        """
        UPDATE paper
           SET summary_zh = NULL,
               quality_status = %s,
               updated_at = now(),
               run_id = %s
         WHERE paper_id = %s
        """,
        (quality_status, run_id, paper_id),
    )


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print(
            "ERROR: DATABASE_URL not set. Run with DATABASE_URL=postgresql://...",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = _open_database_connection(dsn)
    if args.dry_run:
        run_id = f"dry-run-{uuid4()}"
    else:
        run_id = str(
            open_pipeline_run(
                conn,
                run_kind="backfill_real",
                run_scope={
                    "task": "paper_summary_zh_backfill",
                    "only_missing": args.only_missing,
                    "limit": args.limit,
                    "resume": args.resume,
                    "professor_ids": args.professor_id,
                    "institutions": args.institution,
                    "paper_ids": args.paper_id,
                    "paper_id_files": args.paper_id_file,
                    "seed_ids": args.seed_id,
                    "enrich_doi_metadata": args.enrich_doi_metadata,
                    "dry_run": args.dry_run,
                },
                triggered_by="run_paper_summary_zh_backfill",
            )
        )
        conn.commit()

    resume_path: Path | None = None
    if args.resume is not None:
        resume_path = _resolve_checkpoint_path(args.resume, run_id)
    resume_ids = _load_resume_ids(resume_path) if resume_path else set()
    checkpoint_path = resume_path or _resolve_checkpoint_path(None, run_id)

    llm, llm_model, extra_body = _open_llm_client()
    sql, params = _build_select_sql(
        only_missing=args.only_missing,
        limit=args.limit,
        professor_ids=tuple(args.professor_id or ()),
        paper_ids=tuple(args.paper_id or ()),
        institutions=tuple(args.institution or ()),
        seed_ids=tuple(args.seed_id or ()),
        include_doi_enrichment=args.enrich_doi_metadata,
    )
    rows = conn.execute(sql, params).fetchall()

    started_at = time.monotonic()
    report: dict[str, Any] = {
        "run_id": run_id,
        "papers_total": len(rows),
        "papers_processed": 0,
        "papers_skipped": 0,
        "summaries_written": 0,
        "summaries_rejected": 0,
        "metadata_enrichment_attempted": 0,
        "metadata_enriched": 0,
        "full_text_enrichment_attempted": 0,
        "full_text_enriched": 0,
        "abstract_clean_backfilled_from_full_text": 0,
        "identifier_contradictions": 0,
        "pipeline_issues_inserted": 0,
        "papers_with_errors": 0,
        "dry_run": args.dry_run,
    }

    for row in rows:
        row_dict = dict(row)
        paper_id = str(row_dict["paper_id"])
        if paper_id in resume_ids:
            report["papers_skipped"] += 1
            continue

        if (
            args.enrich_doi_metadata
            and _row_needs_metadata_enrichment(row_dict)
            and _row_has_metadata_identifier(row_dict)
        ):
            report["metadata_enrichment_attempted"] += 1
            try:
                has_identifier_contradiction = False
                enrichment = enrich_paper_with_hybrid_sources(
                    str(row_dict["doi"]) if row_dict.get("doi") else None,
                    arxiv_id=(
                        str(row_dict["arxiv_id"])
                        if row_dict.get("arxiv_id")
                        else None
                    ),
                    openalex_id=(
                        str(row_dict["openalex_id"])
                        if row_dict.get("openalex_id")
                        else None
                    ),
                )
                if enrichment is not None:
                    if enrichment.identifier_contradictions:
                        has_identifier_contradiction = True
                        row_dict["quality_status"] = NEEDS_REVIEW
                        report["identifier_contradictions"] += len(
                            enrichment.identifier_contradictions
                        )
                        if not args.dry_run:
                            report[
                                "pipeline_issues_inserted"
                            ] += _file_identifier_contradiction_issue(
                                conn,
                                paper_id=paper_id,
                                row=row_dict,
                                enrichment=enrichment,
                                run_id=run_id,
                            )
                    updates = _metadata_updates_from_enrichment(row_dict, enrichment)
                    if updates:
                        row_dict.update(updates)
                        if has_identifier_contradiction:
                            next_quality_status = NEEDS_REVIEW
                        else:
                            promotion = evaluate_paper_promotion(
                                current_status=_current_quality_status(row_dict),
                                signals=_paper_enrichment_signals(
                                    row_dict,
                                    summary_zh=row_dict.get("summary_zh"),
                                    summary_zh_boilerplate_rejected=False,
                                ),
                            )
                            next_quality_status = promotion.next_status
                        if not args.dry_run:
                            _persist_metadata_enrichment(
                                conn,
                                paper_id=paper_id,
                                updates=updates,
                                quality_status=next_quality_status,
                                run_id=run_id,
                            )
                            conn.commit()
                        row_dict["quality_status"] = next_quality_status
                        report["metadata_enriched"] += 1
                    if not _abstract_for_summary(row_dict) and enrichment.pdf_url:
                        report["full_text_enrichment_attempted"] += 1
                        source = _doi_pdf_source(enrichment)
                        extract = fetch_pdf_url_full_text(
                            enrichment.pdf_url,
                            paper_id=paper_id,
                            source=source,
                        )
                        if not args.dry_run:
                            upsert_paper_full_text(
                                conn,
                                paper_id=paper_id,
                                extract=extract,
                                run_id=run_id,
                            )
                            conn.commit()
                        extract_abstract = sanitize_text_for_postgres(extract.abstract)
                        extract_intro = sanitize_text_for_postgres(extract.intro)
                        if _is_usable_abstract(extract_abstract):
                            row_dict["full_text_abstract"] = extract_abstract
                            row_dict[
                                "abstract_for_summary_source"
                            ] = "paper_full_text.abstract"
                            full_text_updates: dict[str, Any] = {}
                            if not _is_usable_abstract(row_dict.get("abstract_clean")):
                                full_text_updates["abstract_clean"] = extract_abstract
                            if full_text_updates:
                                row_dict.update(full_text_updates)
                                promotion = evaluate_paper_promotion(
                                    current_status=_current_quality_status(row_dict),
                                    signals=_paper_enrichment_signals(
                                        row_dict,
                                        summary_zh=row_dict.get("summary_zh"),
                                        summary_zh_boilerplate_rejected=False,
                                    ),
                                )
                                if not args.dry_run:
                                    _persist_metadata_enrichment(
                                        conn,
                                        paper_id=paper_id,
                                        updates=full_text_updates,
                                        quality_status=promotion.next_status,
                                        run_id=run_id,
                                    )
                                    conn.commit()
                                row_dict["quality_status"] = promotion.next_status
                                report[
                                    "abstract_clean_backfilled_from_full_text"
                                ] += 1
                            report["metadata_enriched"] += 0 if updates else 1
                            report["full_text_enriched"] += 1
                        elif _is_usable_abstract(extract_intro):
                            row_dict["full_text_intro"] = extract_intro
                            row_dict[
                                "abstract_for_summary_source"
                            ] = "paper_full_text.intro"
                            report["full_text_enriched"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Paper %s DOI enrichment crashed: %s", paper_id, exc)
                report["papers_with_errors"] += 1
                try:
                    conn.rollback()
                except Exception:
                    pass
                _append_checkpoint(
                    checkpoint_path,
                    {"paper_id": paper_id, "status": "metadata_error", "error": str(exc)},
                )
                continue

        try:
            if _backfill_abstract_clean_from_existing_full_text(
                conn,
                row=row_dict,
                paper_id=paper_id,
                run_id=run_id,
                dry_run=args.dry_run,
            ):
                if not args.dry_run:
                    conn.commit()
                report["abstract_clean_backfilled_from_full_text"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Paper %s full-text abstract backfill crashed: %s", paper_id, exc
            )
            report["papers_with_errors"] += 1
            try:
                conn.rollback()
            except Exception:
                pass
            _append_checkpoint(
                checkpoint_path,
                {
                    "paper_id": paper_id,
                    "status": "full_text_abstract_backfill_error",
                    "error": str(exc),
                },
            )
            continue

        abstract = _abstract_for_summary(row_dict)
        if not abstract or not str(abstract).strip():
            report["papers_skipped"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "skipped_no_abstract"},
            )
            continue
        report["papers_processed"] += 1
        try:
            summary_zh = translate_abstract_to_zh(
                str(abstract),
                llm_client=llm,
                llm_model=llm_model,
                extra_body=extra_body,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Paper %s summary_zh generation crashed: %s", paper_id, exc)
            report["papers_with_errors"] += 1
            try:
                conn.rollback()
            except Exception:
                pass
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "error", "error": str(exc)},
            )
            continue

        if summary_zh:
            is_boilerplate = judge_summary_boilerplate(
                summary_zh,
                llm_client=llm,
                llm_model=llm_model,
                extra_body=extra_body,
            )
            if is_boilerplate:
                if not args.dry_run:
                    try:
                        rejection_status = _summary_rejection_quality_status(row_dict)
                        _reject_summary_zh(
                            conn,
                            paper_id=paper_id,
                            quality_status=rejection_status,
                            run_id=run_id,
                        )
                        conn.commit()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Reject persist failed for paper %s: %s", paper_id, exc)
                        report["papers_with_errors"] += 1
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        _append_checkpoint(
                            checkpoint_path,
                            {
                                "paper_id": paper_id,
                                "status": "persist_error",
                                "error": str(exc),
                            },
                        )
                        continue
                report["summaries_rejected"] += 1
                _append_checkpoint(
                    checkpoint_path,
                    {"paper_id": paper_id, "status": "rejected_boilerplate"},
                )
                continue

            promotion = evaluate_paper_promotion(
                current_status=_current_quality_status(row_dict),
                signals=_paper_enrichment_signals(
                    row_dict,
                    summary_zh=summary_zh,
                    summary_zh_boilerplate_rejected=False,
                ),
            )
            next_quality_status = (
                NEEDS_REVIEW
                if _current_quality_status(row_dict) == NEEDS_REVIEW
                else promotion.next_status
            )
            if not args.dry_run:
                try:
                    _persist_summary_zh(
                        conn,
                        paper_id=paper_id,
                        summary_zh=summary_zh,
                        quality_status=next_quality_status,
                        run_id=run_id,
                    )
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Persist failed for paper %s: %s", paper_id, exc)
                    report["papers_with_errors"] += 1
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    _append_checkpoint(
                        checkpoint_path,
                        {
                            "paper_id": paper_id,
                            "status": "persist_error",
                            "error": str(exc),
                        },
                    )
                    continue
            report["summaries_written"] += 1
            _append_checkpoint(
                checkpoint_path,
                {
                    "paper_id": paper_id,
                    "status": "dry_run_success" if args.dry_run else "written",
                    "chars": len(summary_zh),
                    "abstract_source": row_dict.get("abstract_for_summary_source"),
                },
            )
        else:
            if not args.dry_run:
                try:
                    rejection_status = _summary_rejection_quality_status(row_dict)
                    _reject_summary_zh(
                        conn,
                        paper_id=paper_id,
                        quality_status=rejection_status,
                        run_id=run_id,
                    )
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Reject persist failed for paper %s: %s", paper_id, exc)
                    report["papers_with_errors"] += 1
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    _append_checkpoint(
                        checkpoint_path,
                        {
                            "paper_id": paper_id,
                            "status": "persist_error",
                            "error": str(exc),
                        },
                    )
                    continue
            report["summaries_rejected"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "rejected"},
            )

    report["duration_seconds"] = round(time.monotonic() - started_at, 2)
    close_status = (
        "partial"
        if report["papers_with_errors"] or report["summaries_rejected"]
        else "succeeded"
    )
    if not args.dry_run:
        try:
            close_pipeline_run(
                conn,
                run_id,
                status=close_status,
                items_processed=report["papers_processed"],
                items_failed=report["papers_with_errors"] + report["summaries_rejected"],
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            print(
                json.dumps(
                    {"warn": "close_pipeline_run failed", "error": str(exc)},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )

    print(json.dumps(report, ensure_ascii=False))


def _current_quality_status(row: dict[str, Any]) -> str:
    return str(row.get("quality_status") or NEEDS_ENRICHMENT).strip() or NEEDS_ENRICHMENT


def _paper_enrichment_signals(
    row: dict[str, Any],
    *,
    summary_zh: str | None,
    summary_zh_boilerplate_rejected: bool,
) -> PaperEnrichmentSignals:
    return PaperEnrichmentSignals(
        has_title=bool(str(row.get("title_clean") or row.get("title_raw") or "").strip()),
        has_year=row.get("year") is not None,
        has_venue=bool(str(row.get("venue") or "").strip()),
        has_authors=bool(str(row.get("authors_display") or "").strip()),
        has_abstract=_has_usable_true_abstract(row),
        has_summary_zh=bool(str(summary_zh or "").strip()),
        summary_zh_boilerplate_rejected=summary_zh_boilerplate_rejected,
    )


def _summary_rejection_quality_status(row: dict[str, Any]) -> str:
    promotion = evaluate_paper_promotion(
        current_status=_current_quality_status(row),
        signals=_paper_enrichment_signals(
            row,
            summary_zh=None,
            summary_zh_boilerplate_rejected=True,
        ),
    )
    return promotion.next_status


def _backfill_abstract_clean_from_existing_full_text(
    conn: Any,
    *,
    row: dict[str, Any],
    paper_id: str,
    run_id: str,
    dry_run: bool,
) -> bool:
    full_text_abstract = (
        sanitize_text_for_postgres(str(row.get("full_text_abstract") or "").strip())
        or ""
    )
    if not _is_usable_abstract(full_text_abstract):
        return False
    if _is_usable_abstract(row.get("abstract_clean")):
        return False

    updates = {"abstract_clean": full_text_abstract}
    row.update(updates)
    row.setdefault("abstract_for_summary_source", "paper_full_text.abstract")
    promotion = evaluate_paper_promotion(
        current_status=_current_quality_status(row),
        signals=_paper_enrichment_signals(
            row,
            summary_zh=row.get("summary_zh"),
            summary_zh_boilerplate_rejected=False,
        ),
    )
    if not dry_run:
        _persist_metadata_enrichment(
            conn,
            paper_id=paper_id,
            updates=updates,
            quality_status=promotion.next_status,
            run_id=run_id,
        )
    row["quality_status"] = promotion.next_status
    return True


def _row_needs_metadata_enrichment(row: dict[str, Any]) -> bool:
    return any(
        [
            not _has_usable_true_abstract(row),
            row.get("year") is None,
            not str(row.get("venue") or "").strip(),
            not str(row.get("authors_display") or "").strip(),
        ]
    )


def _row_has_metadata_identifier(row: dict[str, Any]) -> bool:
    return any(
        str(row.get(key) or "").strip() for key in ("doi", "arxiv_id", "openalex_id")
    )


def _abstract_for_summary(row: dict[str, Any]) -> str | None:
    for key, source in (
        ("abstract_for_summary", None),
        ("abstract_clean", "paper.abstract_clean"),
        ("full_text_abstract", "paper_full_text.abstract"),
        ("full_text_intro", "paper_full_text.intro"),
    ):
        value = sanitize_text_for_postgres(str(row.get(key) or "").strip()) or ""
        if _is_usable_abstract(value):
            row[key] = value
            if source and not row.get("abstract_for_summary_source"):
                row["abstract_for_summary_source"] = source
            return value
    return None


def _has_usable_true_abstract(row: dict[str, Any]) -> bool:
    return _is_usable_abstract(row.get("abstract_clean")) or _is_usable_abstract(
        row.get("full_text_abstract")
    )


def _is_usable_abstract(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if len(text) < 30:
        return False
    if _PUBLISHER_NOTE_RE.search(text):
        return False
    if _TRUNCATED_FRAGMENT_RE.search(text):
        return False
    if _LEADING_FRAGMENT_RE.search(text):
        return False
    if _VENUE_ONLY_RE.search(text):
        return False
    if _AUTHOR_AFFILIATION_RE.search(text):
        return False
    if _CITATION_METADATA_RE.search(text) and _AUTHOR_LIST_HEAD_RE.search(text):
        return False
    return True


if __name__ == "__main__":
    main()
