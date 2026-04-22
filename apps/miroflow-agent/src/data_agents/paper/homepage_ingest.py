from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from ..normalization import build_stable_id
from ..professor.canonical_writer import _upsert_professor_paper_link
from ..professor.homepage_publications import extract_publications_from_html
from ..storage.postgres.paper_full_text import (
    paper_full_text_exists,
    upsert_paper_full_text,
)
from ..storage.postgres.pipeline_run import close_pipeline_run, open_pipeline_run
from ..storage.postgres.title_resolution_cache import PostgresTitleResolutionCache
from .canonical_writer import upsert_paper
from .full_text_fetcher import fetch_and_extract_full_text
from .homepage_http import fetch_homepage_html
from .title_resolver import resolve_paper_by_title

logger = logging.getLogger(__name__)

_DRY_RUN_SENTINEL_RUN_ID = UUID("00000000-0000-0000-0000-000000000000")
_AUTHOR_NAME_MATCH_SCORE = Decimal("1.0")
_LINK_MATCH_REASON = "homepage_title_resolution"


@dataclass(frozen=True, slots=True)
class IngestReport:
    run_id: UUID
    profs_total: int
    profs_processed: int
    profs_skipped: int
    papers_linked_total: int
    full_text_fetched_total: int
    pipeline_issues_filed: int
    run_duration_seconds: float


def _file_pipeline_issue(
    conn,
    *,
    run_id,
    issue_type,
    professor_id,
    message,
    details=None,
) -> None:
    evidence_snapshot = json.dumps(
        {
            "run_id": str(run_id),
            "issue_type": issue_type,
            "message": message,
            "details": details,
        },
        ensure_ascii=False,
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
            "paper_attribution",
            "medium",
            f"[{issue_type}] {message}",
            evidence_snapshot,
            "homepage_paper_ingest",
        ),
    )


def run_homepage_paper_ingest(
    conn,
    *,
    institution=None,
    limit=None,
    dry_run=False,
    resume_checkpoint_path: Path | None = None,
    prof_id: str | None = None,
) -> IngestReport:
    started_at = time.monotonic()
    run_id = _DRY_RUN_SENTINEL_RUN_ID
    profs_processed = 0
    profs_skipped = 0
    papers_linked_total = 0
    full_text_fetched_total = 0
    pipeline_issues_filed = 0
    profs_with_errors = 0
    run_opened = False

    try:
        if not dry_run:
            run_id = open_pipeline_run(
                conn,
                run_kind="homepage_paper_ingest",
                run_scope={
                    "institution": institution,
                    "limit": limit,
                    "prof_id": prof_id,
                    "resume_checkpoint_path": (
                        str(resume_checkpoint_path)
                        if resume_checkpoint_path is not None
                        else None
                    ),
                },
            )
            run_opened = True

        resume_set = _load_resume_set(resume_checkpoint_path)
        professors = _fetch_professors(
            conn,
            institution=institution,
            limit=limit,
            prof_id=prof_id,
        )

        for prof in professors:
            professor_id = str(prof["professor_id"])
            if professor_id in resume_set:
                profs_skipped += 1
                continue

            profs_processed += 1
            prof_pipeline_issues = 0
            prof_had_error = False
            prof_papers_linked = 0
            checkpoint_status = "succeeded"

            with conn.transaction(savepoint=True):
                try:
                    try:
                        html = fetch_homepage_html(prof["homepage_url"])
                    except (
                        httpx.HTTPStatusError,
                        httpx.ConnectError,
                        httpx.TimeoutException,
                    ) as exc:
                        prof_had_error = True
                        checkpoint_status = "failed"
                        pipeline_issues_filed += 1
                        prof_pipeline_issues += 1
                        logger.warning(
                            "Homepage fetch failed for %s (%s): %s",
                            professor_id,
                            prof["homepage_url"],
                            exc,
                        )
                        if not dry_run:
                            _file_pipeline_issue(
                                conn,
                                run_id=run_id,
                                issue_type="homepage_fetch_error",
                                professor_id=professor_id,
                                message=str(exc),
                                details={"homepage_url": prof["homepage_url"]},
                            )
                        _append_checkpoint_line(
                            resume_checkpoint_path,
                            prof_id=professor_id,
                            status=checkpoint_status,
                            papers_linked=prof_papers_linked,
                            pipeline_issues=prof_pipeline_issues,
                            dry_run=dry_run,
                        )
                        profs_with_errors += 1
                        continue

                    publications = extract_publications_from_html(
                        html,
                        page_url=prof["homepage_url"],
                    )
                    if 0 < len(publications) < 3:
                        pipeline_issues_filed += 1
                        prof_pipeline_issues += 1
                        prof_had_error = True
                        if not dry_run:
                            _file_pipeline_issue(
                                conn,
                                run_id=run_id,
                                issue_type="publications_under_threshold",
                                professor_id=professor_id,
                                message=(
                                    "Extracted fewer than 3 publications from homepage"
                                ),
                                details={
                                    "homepage_url": prof["homepage_url"],
                                    "publications_count": len(publications),
                                },
                            )

                    cache = None if dry_run else PostgresTitleResolutionCache(conn)
                    unresolved_count = 0
                    for publication in publications:
                        resolved = resolve_paper_by_title(
                            publication.clean_title,
                            author_hint=prof["canonical_name"],
                            year_hint=publication.year,
                            web_search=None,
                            cache=cache,
                        )
                        if resolved is None:
                            unresolved_count += 1
                            continue

                        derived_paper_id = _derive_paper_id(
                            publication.clean_title,
                            resolved_doi=resolved.doi,
                            resolved_arxiv_id=resolved.arxiv_id,
                        )
                        papers_linked_total += 1
                        prof_papers_linked += 1

                        actual_paper_id = derived_paper_id
                        if not dry_run:
                            paper_report = upsert_paper(
                                conn,
                                title_clean=publication.clean_title,
                                title_raw=resolved.title,
                                doi=resolved.doi,
                                arxiv_id=resolved.arxiv_id,
                                openalex_id=resolved.openalex_id,
                                semantic_scholar_id=None,
                                year=resolved.year,
                                venue=resolved.venue,
                                abstract_clean=resolved.abstract,
                                authors_display=_authors_display(resolved.authors),
                                citation_count=None,
                                canonical_source=resolved.match_source,
                                run_id=run_id,
                            )
                            actual_paper_id = getattr(
                                paper_report,
                                "paper_id",
                                derived_paper_id,
                            )
                            _upsert_professor_paper_link(
                                conn,
                                professor_id=professor_id,
                                paper_id=actual_paper_id,
                                link_status="verified",
                                evidence_source_type="personal_homepage",
                                evidence_page_id=None,
                                evidence_api_source=None,
                                match_reason=_LINK_MATCH_REASON,
                                author_name_match_score=_AUTHOR_NAME_MATCH_SCORE,
                                topic_consistency_score=None,
                                institution_consistency_score=None,
                                is_officially_listed=True,
                                run_id=run_id,
                            )

                        if paper_full_text_exists(conn, actual_paper_id):
                            continue

                        extract = fetch_and_extract_full_text(
                            resolved,
                            paper_id=actual_paper_id,
                        )
                        if extract.fetch_error is None:
                            full_text_fetched_total += 1
                        if not dry_run:
                            upsert_paper_full_text(
                                conn,
                                paper_id=actual_paper_id,
                                extract=extract,
                                run_id=run_id,
                            )

                    if publications and unresolved_count == len(publications):
                        pipeline_issues_filed += 1
                        prof_pipeline_issues += 1
                        prof_had_error = True
                        if not dry_run:
                            _file_pipeline_issue(
                                conn,
                                run_id=run_id,
                                issue_type="all_titles_unresolvable",
                                professor_id=professor_id,
                                message="All homepage publication titles were unresolvable",
                                details={"publications_count": len(publications)},
                            )
                except Exception as exc:  # noqa: BLE001
                    prof_had_error = True
                    checkpoint_status = "failed"
                    pipeline_issues_filed += 1
                    prof_pipeline_issues += 1
                    logger.exception(
                        "Professor processing crashed for %s: %s",
                        professor_id,
                        exc,
                    )
                    if not dry_run:
                        _file_pipeline_issue(
                            conn,
                            run_id=run_id,
                            issue_type="prof_processing_crashed",
                            professor_id=professor_id,
                            message=str(exc),
                            details={"homepage_url": prof["homepage_url"]},
                        )

            if prof_had_error:
                profs_with_errors += 1
            _append_checkpoint_line(
                resume_checkpoint_path,
                prof_id=professor_id,
                status=checkpoint_status,
                papers_linked=prof_papers_linked,
                pipeline_issues=prof_pipeline_issues,
                dry_run=dry_run,
            )

    except KeyboardInterrupt:
        if run_opened:
            close_pipeline_run(
                conn,
                run_id,
                status="cancelled",
            )
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
                items_failed=profs_with_errors,
            )

    return IngestReport(
        run_id=run_id,
        profs_total=len(professors),
        profs_processed=profs_processed,
        profs_skipped=profs_skipped,
        papers_linked_total=papers_linked_total,
        full_text_fetched_total=full_text_fetched_total,
        pipeline_issues_filed=pipeline_issues_filed,
        run_duration_seconds=time.monotonic() - started_at,
    )


def _authors_display(authors: tuple[str, ...]) -> str | None:
    if not authors:
        return None
    return ", ".join(author for author in authors if author)


def _append_checkpoint_line(
    checkpoint_path: Path | None,
    *,
    prof_id: str,
    status: str,
    papers_linked: int,
    pipeline_issues: int,
    dry_run: bool,
) -> None:
    if dry_run or checkpoint_path is None:
        return

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "prof_id": prof_id,
        "status": status,
        "papers_linked": papers_linked,
        "pipeline_issues": pipeline_issues,
    }
    with checkpoint_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def _derive_paper_id(
    clean_title: str,
    *,
    resolved_doi: str | None,
    resolved_arxiv_id: str | None,
) -> str:
    if resolved_doi:
        return build_stable_id("paper", f"doi:{resolved_doi}")
    if resolved_arxiv_id:
        return build_stable_id("paper", f"arxiv:{resolved_arxiv_id}")
    title_sha1 = hashlib.sha1(clean_title.encode("utf-8")).hexdigest()
    return build_stable_id("paper", f"title:{title_sha1}")


def _fetch_professors(
    conn,
    *,
    institution: str | None,
    limit: int | None,
    prof_id: str | None,
) -> list[dict[str, Any]]:
    query = [
        "SELECT professor_id, canonical_name, institution, homepage_url",
        "FROM professor",
        "WHERE homepage_url IS NOT NULL",
    ]
    params: list[Any] = []
    if institution:
        query.append("AND institution ILIKE %s")
        params.append(f"%{institution}%")
    if prof_id:
        query.append("AND professor_id = %s")
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


def _load_resume_set(checkpoint_path: Path | None) -> set[str]:
    if checkpoint_path is None or not checkpoint_path.exists():
        return set()

    prof_ids: set[str] = set()
    with checkpoint_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Ignoring corrupted checkpoint line: %r", line)
                continue
            if not isinstance(payload, dict):
                continue
            value = payload.get("prof_id")
            if isinstance(value, str) and value:
                prof_ids.add(value)
    return prof_ids
