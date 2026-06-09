"""Backfill paper.summary_zh from paper.abstract_clean via Gemma4."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.paper.abstract_translator import (  # noqa: E402
    _zh_char_ratio,
    judge_summary_boilerplate,
    translate_abstract_to_zh,
)
from src.data_agents.paper.enrichment import enrich_paper_with_hybrid_sources  # noqa: E402
from src.data_agents.paper.models import (  # noqa: E402
    PaperIdentifierContradiction,
    PaperMetadataEnrichment,
)
from src.data_agents.paper.quality_promotion import (  # noqa: E402
    NEEDS_ENRICHMENT,
    NEEDS_REVIEW,
    PaperEnrichmentSignals,
    evaluate_paper_promotion,
)
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings  # noqa: E402
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)

logger = logging.getLogger("run_paper_summary_zh_backfill")


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
        "--enrich-doi-metadata",
        action="store_true",
        help=(
            "Before summary generation, use DOI enrichment to fill missing "
            "abstract/venue/year/citation fields."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


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
    include_doi_enrichment: bool = False,
) -> tuple[str, tuple[Any, ...]]:
    if include_doi_enrichment:
        conditions = [
            "("
            "(p.abstract_clean IS NOT NULL AND length(trim(p.abstract_clean)) > 0) "
            "OR (p.doi IS NOT NULL AND length(trim(p.doi)) > 0) "
            "OR (p.arxiv_id IS NOT NULL AND length(trim(p.arxiv_id)) > 0)"
            ")",
        ]
    else:
        conditions = [
            "p.abstract_clean IS NOT NULL",
            "length(trim(p.abstract_clean)) > 0",
        ]
    params: list[Any] = []
    if only_missing:
        conditions.append("(p.summary_zh IS NULL OR length(trim(p.summary_zh)) = 0)")
    join_sql = ""
    if professor_ids or institutions:
        join_sql = " JOIN professor_paper_link ppl ON ppl.paper_id = p.paper_id "
    if institutions:
        join_sql += (
            " JOIN professor_affiliation pa ON pa.professor_id = ppl.professor_id "
        )
        conditions.append("pa.institution = ANY(%s)")
        params.append(list(institutions))
    if professor_ids:
        conditions.append("ppl.professor_id = ANY(%s)")
        params.append(list(professor_ids))
    if paper_ids:
        conditions.append("p.paper_id = ANY(%s)")
        params.append(list(paper_ids))
    sql = (
        "SELECT DISTINCT p.paper_id, p.title_clean, p.title_raw, p.doi, p.arxiv_id, "
        "p.year, p.venue, p.authors_display, p.abstract_clean, p.summary_zh, "
        "p.quality_status, p.citation_count "
        "  FROM paper p "
        f"{join_sql}"
        f" WHERE {' AND '.join(conditions)} "
        " ORDER BY p.paper_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _metadata_updates_from_enrichment(
    row: dict[str, Any],
    enrichment: PaperMetadataEnrichment,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if not str(row.get("abstract_clean") or "").strip() and enrichment.abstract:
        updates["abstract_clean"] = enrichment.abstract
    if not str(row.get("venue") or "").strip() and enrichment.venue:
        updates["venue"] = enrichment.venue
    if row.get("year") is None and enrichment.publication_date:
        year = _year_from_publication_date(enrichment.publication_date)
        if year is not None:
            updates["year"] = year
    if row.get("citation_count") is None and enrichment.citation_count is not None:
        updates["citation_count"] = enrichment.citation_count
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
           SET abstract_clean = COALESCE(abstract_clean, %s),
               venue = COALESCE(venue, %s),
               year = COALESCE(year, %s),
               citation_count = COALESCE(citation_count, %s),
               quality_status = %s,
               updated_at = now(),
               run_id = %s
         WHERE paper_id = %s
        """,
        (
            updates.get("abstract_clean"),
            updates.get("venue"),
            updates.get("year"),
            updates.get("citation_count"),
            quality_status,
            run_id,
            paper_id,
        ),
    )


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
            json.dumps(snapshot, ensure_ascii=False),
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
        (summary_zh, quality_status, run_id, paper_id),
    )


def _reject_summary_zh(
    conn: Any,
    *,
    paper_id: str,
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
        ("rejected", run_id, paper_id),
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
    checkpoint_path = _resolve_checkpoint_path(None, run_id)

    llm, llm_model, extra_body = _open_llm_client()
    sql, params = _build_select_sql(
        only_missing=args.only_missing,
        limit=args.limit,
        professor_ids=tuple(args.professor_id or ()),
        paper_ids=tuple(args.paper_id or ()),
        institutions=tuple(args.institution or ()),
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
            and not str(row_dict.get("abstract_clean") or "").strip()
            and (
                str(row_dict.get("doi") or "").strip()
                or str(row_dict.get("arxiv_id") or "").strip()
            )
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

        abstract = row_dict.get("abstract_clean")
        if not abstract or not str(abstract).strip():
            report["papers_skipped"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "skipped_no_abstract"},
            )
            continue
        if _zh_char_ratio(str(abstract)) > 0.6:
            report["papers_skipped"] += 1
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "skipped_already_zh"},
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
                        _reject_summary_zh(
                            conn,
                            paper_id=paper_id,
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
                },
            )
        else:
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
        has_abstract=bool(str(row.get("abstract_clean") or "").strip()),
        has_summary_zh=bool(str(summary_zh or "").strip()),
        summary_zh_boilerplate_rejected=summary_zh_boilerplate_rejected,
    )


if __name__ == "__main__":
    main()
