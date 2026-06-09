from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from uuid import UUID

import httpx

from ..normalization import build_stable_id
from ..professor.canonical_writer import _upsert_professor_paper_link
from ..professor.homepage_publications import (
    HomepagePublication,
    _is_suspicious_rule_publication,
    _looks_like_author_list,
    extract_publications_from_html,
)
from ..storage.postgres.paper_full_text import (
    paper_full_text_exists,
    upsert_paper_full_text,
)
from ..storage.postgres.pipeline_run import close_pipeline_run, open_pipeline_run
from ..storage.postgres.title_resolution_cache import PostgresTitleResolutionCache
from .canonical_writer import upsert_paper
from .full_text_fetcher import fetch_and_extract_full_text
from .homepage_http import fetch_homepage_html
from .quality_promotion import NEEDS_ENRICHMENT
from .title_resolver import ResolvedPaper, resolve_paper_by_title

logger = logging.getLogger(__name__)

_DRY_RUN_SENTINEL_RUN_ID = UUID("00000000-0000-0000-0000-000000000000")
_AUTHOR_NAME_MATCH_SCORE = Decimal("1.0")
_LINK_MATCH_REASON = "homepage_title_resolution"
_LINK_MATCH_REASON_PAGE_ONLY = "prof_page_declaration"
_PROF_PAGE_ONLY_SOURCE = "prof_page_only"
_TIER2_PAGE_ROLES = frozenset({"official_profile", "official_publication_page"})
_TIER3_PAGE_ROLES = frozenset({"personal_homepage", "lab_homepage"})
_DEFAULT_PROF_PAGE_PDF_FETCH_CAP = 20
_AUTHOR_INITIAL_HINT_RE = re.compile(r"\b[A-Z]\.")
_PDF_FETCH_CAP_ERRORS = frozenset(
    {
        "pdf_too_large",
        "timeout",
        "pdf_content_type_disallowed",
        "redirect_cap_exceeded",
    }
)


def _synthesize_page_only_resolution(
    publication,
    *,
    canonical_name: str,
) -> ResolvedPaper:
    """Build a synthetic ResolvedPaper from prof-page data only.

    Used when external title resolution (Crossref / OpenAlex / S2) fails
    to find the publication — typically the preprint case (paper recently
    accepted but not yet indexed in external DBs). Per Paper Review
    §3.1 P4 and OpenSpec change `prof-paper-patent-from-page-flow` spec
    Requirement "Preprint listed on professor page", the system MUST
    still create a paper canonical record with page-only data and let
    enrichment fill in DOI / abstract / etc. on the next cron run.
    """
    authors_text = (publication.authors_text or "").strip()
    if authors_text:
        authors = tuple(_split_page_authors(authors_text)) or (
            f"{canonical_name} et al.",
        )
    else:
        authors = (f"{canonical_name} et al.",)
    return ResolvedPaper(
        title=publication.clean_title,
        doi=None,
        openalex_id=None,
        arxiv_id=None,
        abstract=None,
        pdf_url=getattr(publication, "pdf_url", None),
        authors=authors,
        year=publication.year,
        venue=publication.venue_text,
        match_confidence=1.0,
        match_source=_PROF_PAGE_ONLY_SOURCE,
    )


def _split_page_authors(authors_text: str) -> list[str]:
    """Best-effort author split from prof-page free-text. Conservative;
    keeps original text if no clear delimiter detected."""
    candidates = [
        item.strip()
        for item in authors_text.replace(";", ",").replace("、", ",").split(",")
    ]
    return [c for c in candidates if c]


def _attach_professor_page_pdf_url(
    resolved: ResolvedPaper,
    publication,
) -> ResolvedPaper:
    pdf_url = getattr(publication, "pdf_url", None)
    if not pdf_url:
        return resolved
    return replace(resolved, pdf_url=pdf_url)


def _homepage_evidence_source_type(prof: dict[str, Any]) -> str | None:
    page_role = str(prof.get("homepage_page_role") or "").strip()
    if page_role in _TIER2_PAGE_ROLES:
        return "prof_homepage_tier2"
    if page_role in _TIER3_PAGE_ROLES:
        return "prof_homepage_tier3"
    return None


def _is_direct_professor_page_pdf(resolved: ResolvedPaper) -> bool:
    if not resolved.pdf_url:
        return False
    parsed = urlparse(resolved.pdf_url)
    hostname = (parsed.hostname or "").lower()
    return not (hostname.endswith("arxiv.org") and parsed.path.startswith("/pdf/"))


def _is_pdf_fetch_cap_error(fetch_error: str | None) -> bool:
    return fetch_error in _PDF_FETCH_CAP_ERRORS


def _is_malformed_publication_title(publication) -> bool:
    if _is_suspicious_rule_publication(publication):
        return True
    clean_title = str(getattr(publication, "clean_title", "") or "").strip()
    if not clean_title:
        return True
    has_explicit_author_syntax = (
        any(mark in clean_title for mark in (",", "，", ";", "；", "*", "#", "†", "‡"))
        or _AUTHOR_INITIAL_HINT_RE.search(clean_title) is not None
    )
    if not has_explicit_author_syntax or not _looks_like_author_list(clean_title):
        return False
    return not bool(str(getattr(publication, "authors_text", "") or "").strip())


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
    prof_page_pdf_fetch_cap: int | None = _DEFAULT_PROF_PAGE_PDF_FETCH_CAP,
    publication_extractor: Callable[..., list[HomepagePublication]] | None = None,
) -> IngestReport:
    started_at = time.monotonic()
    run_id = _DRY_RUN_SENTINEL_RUN_ID
    profs_processed = 0
    profs_skipped = 0
    papers_linked_total = 0
    full_text_fetched_total = 0
    pipeline_issues_filed = 0
    profs_with_errors = 0
    prof_page_pdf_fetches_started = 0
    run_opened = False
    active_publication_extractor = (
        publication_extractor or extract_publications_from_html
    )
    publication_extraction_mode = (
        "custom" if publication_extractor is not None else "rule"
    )

    try:
        if not dry_run:
            run_id = open_pipeline_run(
                conn,
                run_kind="backfill_real",
                run_scope={
                    "task": "homepage_paper_ingest",
                    "institution": institution,
                    "limit": limit,
                    "prof_id": prof_id,
                    "resume_checkpoint_path": (
                        str(resume_checkpoint_path)
                        if resume_checkpoint_path is not None
                        else None
                    ),
                    "publication_extraction_mode": publication_extraction_mode,
                },
                triggered_by="homepage_paper_ingest",
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

            # psycopg3：嵌套 transaction() 自动用 SAVEPOINT；不需要 savepoint=True kwarg
            with conn.transaction():
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

                    publications = active_publication_extractor(
                        html,
                        page_url=prof["homepage_url"],
                    )
                    evidence_source_type = _homepage_evidence_source_type(prof)
                    if publications and evidence_source_type is None:
                        pipeline_issues_filed += 1
                        prof_pipeline_issues += 1
                        prof_had_error = True
                        checkpoint_status = "failed"
                        if not dry_run:
                            _file_pipeline_issue(
                                conn,
                                run_id=run_id,
                                issue_type="missing_homepage_tier",
                                professor_id=professor_id,
                                message=(
                                    "Professor homepage page_role is missing or "
                                    "not mappable to paper evidence tier"
                                ),
                                details={
                                    "homepage_url": prof["homepage_url"],
                                    "homepage_page_role": prof.get(
                                        "homepage_page_role"
                                    ),
                                    "publications_count": len(publications),
                                },
                            )
                        continue

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
                    page_only_count = 0
                    for publication in publications:
                        if _is_malformed_publication_title(publication):
                            pipeline_issues_filed += 1
                            prof_pipeline_issues += 1
                            prof_had_error = True
                            if not dry_run:
                                _file_pipeline_issue(
                                    conn,
                                    run_id=run_id,
                                    issue_type="malformed_publication_title",
                                    professor_id=professor_id,
                                    message=(
                                        "Homepage publication clean_title looks like "
                                        "an author list, so title resolution was "
                                        "skipped"
                                    ),
                                    details={
                                        "homepage_url": prof["homepage_url"],
                                        "raw_title": getattr(
                                            publication,
                                            "raw_title",
                                            None,
                                        ),
                                        "clean_title": publication.clean_title,
                                        "authors_text": publication.authors_text,
                                        "venue_text": publication.venue_text,
                                    },
                                )
                            continue

                        resolved = resolve_paper_by_title(
                            publication.clean_title,
                            author_hint=prof["canonical_name"],
                            year_hint=publication.year,
                            enable_arxiv_title_search=False,
                            web_search=None,
                            cache=cache,
                        )
                        is_page_only = resolved is None
                        if is_page_only:
                            # Preprint case (Paper Review §3.1 P4): no
                            # external DB hit — create record from
                            # page-only data; enrichment fills later.
                            unresolved_count += 1
                            page_only_count += 1
                            resolved = _synthesize_page_only_resolution(
                                publication,
                                canonical_name=prof["canonical_name"],
                            )
                        resolved = _attach_professor_page_pdf_url(
                            resolved,
                            publication,
                        )

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
                                title_resolution_source=resolved.match_source,
                                quality_status=NEEDS_ENRICHMENT,
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
                                evidence_source_type=evidence_source_type,
                                evidence_page_id=None,
                                evidence_api_source=None,
                                match_reason=(
                                    _LINK_MATCH_REASON_PAGE_ONLY
                                    if is_page_only
                                    else _LINK_MATCH_REASON
                                ),
                                author_name_match_score=_AUTHOR_NAME_MATCH_SCORE,
                                topic_consistency_score=None,
                                institution_consistency_score=None,
                                is_officially_listed=True,
                                run_id=run_id,
                            )

                        if paper_full_text_exists(conn, actual_paper_id):
                            continue

                        is_prof_page_pdf = _is_direct_professor_page_pdf(resolved)
                        if (
                            is_prof_page_pdf
                            and prof_page_pdf_fetch_cap is not None
                            and prof_page_pdf_fetches_started >= prof_page_pdf_fetch_cap
                        ):
                            pipeline_issues_filed += 1
                            prof_pipeline_issues += 1
                            prof_had_error = True
                            if not dry_run:
                                _file_pipeline_issue(
                                    conn,
                                    run_id=run_id,
                                    issue_type="pdf_fetch_cap_exceeded",
                                    professor_id=professor_id,
                                    message=(
                                        "Professor-page PDF fetch cap exceeded for "
                                        f"{resolved.pdf_url}"
                                    ),
                                    details={
                                        "paper_id": actual_paper_id,
                                        "paper_title": resolved.title,
                                        "pdf_url": resolved.pdf_url,
                                        "prof_page_pdf_fetch_cap": (
                                            prof_page_pdf_fetch_cap
                                        ),
                                    },
                                )
                            continue
                        if is_prof_page_pdf:
                            prof_page_pdf_fetches_started += 1

                        extract = fetch_and_extract_full_text(
                            resolved,
                            paper_id=actual_paper_id,
                        )
                        if extract.fetch_error is None:
                            full_text_fetched_total += 1
                        elif (
                            is_prof_page_pdf
                            and _is_pdf_fetch_cap_error(extract.fetch_error)
                        ):
                            pipeline_issues_filed += 1
                            prof_pipeline_issues += 1
                            prof_had_error = True
                            if not dry_run:
                                _file_pipeline_issue(
                                    conn,
                                    run_id=run_id,
                                    issue_type="pdf_fetch_cap_violation",
                                    professor_id=professor_id,
                                    message=(
                                        "Professor-page PDF fetch violated configured "
                                        f"fetch policy for {resolved.pdf_url}"
                                    ),
                                    details={
                                        "paper_id": actual_paper_id,
                                        "paper_title": resolved.title,
                                        "pdf_url": resolved.pdf_url,
                                        "fetch_error": extract.fetch_error,
                                    },
                                )
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
                status="failed",
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
    # V003 schema: professor.institution / homepage_url 已迁出主表。
    # institution 走 professor_affiliation 多对多；homepage_url 走 source_page
    # via primary_official_profile_page_id FK。
    query = [
        "SELECT p.professor_id::text AS professor_id,",
        "       p.canonical_name,",
        "       COALESCE(primary_aff.institution, '') AS institution,",
        "       sp.url AS homepage_url,",
        "       sp.page_role AS homepage_page_role",
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
                "homepage_page_role": row[4],
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
