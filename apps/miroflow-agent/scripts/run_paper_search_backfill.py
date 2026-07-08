"""Backfill paper.abstract_clean + summary_zh for ``needs_enrichment`` rows
using the ``paper-search-mcp`` (openags) multi-source search.

Target population
-----------------
``paper.quality_status = 'needs_enrichment'`` AND
``identity_status NOT IN ('rejected','merged')``.

The existing ``run_paper_summary_zh_backfill.py`` enriches rows that already
carry a DOI / arXiv / OpenAlex identifier via
``enrich_paper_with_hybrid_sources``. The overwhelming majority of the
``needs_enrichment`` backlog (≈13.2k of 13.26k at the time this script was
written) has **no** identifier at all — only a title plus authors. Those
rows are unreachable for the existing enrichment because every per-source
helper requires an identifier.

This script fills that gap by performing **title-based discovery** across
the openags academic-platform connectors (Crossref / OpenAlex / Europe PMC /
Semantic Scholar / arXiv), matching the best hit back to the canonical row
via a normalized-title similarity threshold, and then:

  1. writing ``abstract_clean`` from the first source that returned one,
  2. optionally fetching arXiv full text into ``paper_full_text`` when an
     arXiv id was discovered,
  3. generating ``summary_zh`` via the shared DeepSeek profile, and
  4. re-running ``evaluate_paper_promotion`` so newly-complete rows promote
     to ``ready`` (forward-monotonic — never degrades an existing ``ready``).

Contracts honored
-----------------
* Evidence traceability — every fetched abstract carries its source name and
  URL in the checkpoint JSONL plus the run report.
* Dedup anchors — DOI > arXiv id > normalized title.
* Forward-monotonic quality status — ``UPDATE ... WHERE quality_status <>
  'ready'`` so a re-run can never degrade a previously-promoted row.
* Polite pool — openags searchers are patched at runtime to advertise the
  ``PAPER_SEARCH_MCP_UNPAYWALL_EMAIL`` mailto in their User-Agent.
* Local LLM profile — uses ``resolve_professor_llm_settings(None)`` (the
  default DeepSeek-v4-pro profile). ``LOCAL_LLM_MODEL`` is never set here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from psycopg.rows import dict_row

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env")
# openags polite-pool mailto + unpaywall email
load_dotenv(_REPO_ROOT.parent.parent / ".paper_search_env", override=False)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.paper.abstract_translator import (  # noqa: E402
    judge_summary_boilerplate,
    translate_abstract_to_zh,
)
from src.data_agents.paper.enrichment import enrich_paper_with_hybrid_sources  # noqa: E402
from src.data_agents.paper.full_text_fetcher import fetch_pdf_url_full_text  # noqa: E402
from src.data_agents.paper.models import PaperMetadataEnrichment  # noqa: E402
from src.data_agents.paper.quality_promotion import (  # noqa: E402
    NEEDS_ENRICHMENT,
    READY,
    PaperEnrichmentSignals,
    evaluate_paper_promotion,
)
from src.data_agents.paper.source_text_quality import (  # noqa: E402
    is_usable_paper_source_text,
)
from src.data_agents.paper.text_sanitizer import (  # noqa: E402
    sanitize_optional_text_for_postgres,
    sanitize_text_for_postgres,
)
from src.data_agents.professor.llm_profiles import (  # noqa: E402
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)
from src.data_agents.storage.postgres.paper_full_text import (  # noqa: E402
    upsert_paper_full_text,
)
from src.data_agents.storage.postgres.pipeline_run import (  # noqa: E402
    close_pipeline_run,
    open_pipeline_run,
)

logger = logging.getLogger("run_paper_search_backfill")

_POLITE_EMAIL_DEFAULT = "xiangl3@mail.sustech.edu.cn"
_TITLE_SIMILARITY_THRESHOLD = 0.85
_ARXIV_ID_RE = re.compile(r"(?:ar[xX]iv(?:\.org/(?:abs|pdf)/)?[/:]?)?(\d{4}\.\d{4,5}(?:v\d+)?)")
_CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
_TITLE_SEARCH_SOURCES_DEFAULT = "crossref,openalex,europepmc,semantic,arxiv"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill paper.abstract_clean + summary_zh for needs_enrichment "
            "rows via openags paper-search-mcp title discovery."
        ),
    )
    parser.add_argument("--limit", type=int, default=None, help="Max papers to process")
    parser.add_argument(
        "--shard",
        default=None,
        help=(
            "Process a shard 'k/N' — papers where hashtext(paper_id) % N == k. "
            "Enables N parallel workers on disjoint paper sets (no OFFSET instability)."
        ),
    )
    parser.add_argument(
        "--paper-id-file",
        default=None,
        help="Restrict to paper_ids listed in a file (JSONL with paper_id/id). For targeted enrichment.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No DB writes — report what would have been fetched/promoted.",
    )
    parser.add_argument(
        "--sources",
        default=_TITLE_SEARCH_SOURCES_DEFAULT,
        help=(
            "Comma-separated openags source list for title discovery. "
            f"Default: {_TITLE_SEARCH_SOURCES_DEFAULT}"
        ),
    )
    parser.add_argument(
        "--skip-full-text",
        action="store_true",
        help="Skip arXiv PDF full-text fetch (abstracts + summary_zh only).",
    )
    parser.add_argument(
        "--max-results-per-source",
        type=int,
        default=3,
        help="max_results_per_source passed to openags search_papers.",
    )
    parser.add_argument(
        "--llm-profile",
        default=None,
        help="Override LLM profile (defaults to the shared DeepSeek profile).",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    return args


# ---------------------------------------------------------------------------
# Helpers — text / identifiers
# ---------------------------------------------------------------------------

def _normalize_title(text: str | None) -> str:
    if not text:
        return ""
    cleaned = unicodedata.normalize("NFKC", text).casefold()
    cleaned = re.sub(r"[^0-9a-z一-鿿㐀-䶿 ]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _title_similarity(a: str | None, b: str | None) -> float:
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # stdlib SequenceMatcher on tokens is good enough for near-exact matches.
    from difflib import SequenceMatcher

    return SequenceMatcher(None, na, nb).ratio()


def _has_cjk(text: str | None) -> bool:
    return bool(text) and bool(_CJK_RE.search(text or ""))


def _extract_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    match = _ARXIV_ID_RE.search(value)
    if match:
        return match.group(1)
    return None


def _is_usable_abstract(value: object) -> bool:
    return is_usable_paper_source_text(value)


def _current_quality_status(row: dict[str, Any]) -> str:
    return str(row.get("quality_status") or NEEDS_ENRICHMENT).strip() or NEEDS_ENRICHMENT


def _has_usable_true_abstract(row: dict[str, Any]) -> bool:
    return _is_usable_abstract(row.get("abstract_clean")) or _is_usable_abstract(
        row.get("full_text_abstract")
    )


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


# ---------------------------------------------------------------------------
# Helpers — openags runtime mailto patch
# ---------------------------------------------------------------------------

def _polite_email() -> str:
    return (
        os.environ.get("PAPER_SEARCH_MCP_UNPAYWALL_EMAIL")
        or os.environ.get("UNPAYWALL_EMAIL")
        or _POLITE_EMAIL_DEFAULT
    )


def _patch_openags_mailto() -> set[str]:
    """Replace the hardcoded ``openags@example.com`` User-Agent on every
    searcher that exposes a ``requests.Session``. Returns the set of searcher
    classes actually patched (for the run report)."""
    email = _polite_email()
    ua = f"mirothinker-paper-backfill/1.0 (mailto:{email})"
    patched: set[str] = set()
    try:
        from paper_search_mcp import server as psm_server  # noqa: E402
    except Exception as exc:  # pragma: no cover — import-time only
        logger.warning("paper_search_mcp import failed, mailto patch skipped: %s", exc)
        return patched

    for attr in dir(psm_server):
        obj = getattr(psm_server, attr, None)
        session = getattr(obj, "session", None)
        if obj is None or session is None:
            continue
        try:
            headers = getattr(session, "headers", None)
            if headers is None:
                continue
            headers["User-Agent"] = ua
            # Crossref also sends a `mailto` query param from its class
            # constant; override per-instance so future calls honor it.
            if isinstance(getattr(obj, "USER_AGENT", None), str):
                try:
                    object.__setattr__(obj, "USER_AGENT", ua)
                except (AttributeError, TypeError):
                    pass
            patched.add(type(obj).__name__)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not patch User-Agent on %s: %s", attr, exc)
    return patched


# ---------------------------------------------------------------------------
# Discovery + abstract resolution
# ---------------------------------------------------------------------------

async def _title_search(query: str, *, sources: str, max_per_source: int) -> dict[str, Any]:
    from paper_search_mcp.server import search_papers

    try:
        return await search_papers(
            query,
            max_results_per_source=max_per_source,
            sources=sources,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("openags search_papers crashed for query=%r: %s", query[:80], exc)
        return {
            "query": query,
            "sources_requested": sources,
            "sources_used": [],
            "source_results": {},
            "errors": {"search_papers": str(exc)},
            "papers": [],
            "total": 0,
            "raw_total": 0,
        }


def _ranked_candidates(
    search_result: dict[str, Any],
    *,
    target_title: str,
    target_doi: str | None,
    target_arxiv_id: str | None,
    target_year: int | None,
) -> list[dict[str, Any]]:
    """Return search hits ranked by anchor strength (DOI > arXiv > title)."""
    scored: list[tuple[float, dict[str, Any]]] = []
    target_doi_norm = (target_doi or "").strip().lower()
    for paper in search_result.get("papers") or []:
        doi = (paper.get("doi") or "").strip().lower()
        title = paper.get("title") or ""
        arxiv_id = _extract_arxiv_id(
            " ".join(
                str(x)
                for x in (
                    paper.get("paper_id"),
                    paper.get("url"),
                    paper.get("pdf_url"),
                    title,
                )
                if x
            )
        )
        score = 0.0
        if target_doi_norm and doi and doi == target_doi_norm:
            score = 1.0
        elif target_arxiv_id and arxiv_id and arxiv_id == target_arxiv_id:
            score = 0.95
        else:
            score = _title_similarity(target_title, title)
        # year tiebreaker (small bonus, never penalty)
        if target_year and paper.get("published_date"):
            try:
                year_str = str(paper["published_date"])[:4]
                if year_str.isdigit() and int(year_str) == int(target_year):
                    score += 0.03
            except (TypeError, ValueError):
                pass
        scored.append((min(score, 1.0), paper))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {**paper, "_match_score": round(score, 4)}
        for score, paper in scored
        if score >= _TITLE_SIMILARITY_THRESHOLD
    ]


def _pick_abstract(candidates: list[dict[str, Any]]) -> tuple[str | None, str | None, str | None]:
    """Return (abstract, source_name, source_url) from the first candidate
    with a usable abstract. EuropePMC is preferred when present."""
    source_priority = ("europepmc", "openalex", "semantic", "crossref", "arxiv", "pmc")
    by_source: dict[str, dict[str, Any]] = {}
    for paper in candidates:
        src = str(paper.get("source") or "").strip().lower()
        if src and src not in by_source:
            by_source[src] = paper

    # First pass: preferred source order
    for src in source_priority:
        paper = by_source.get(src)
        if not paper:
            continue
        abstract = sanitize_text_for_postgres(paper.get("abstract") or "")
        if _is_usable_abstract(abstract):
            return abstract, src, paper.get("url") or paper.get("doi")

    # Second pass: any candidate
    for paper in candidates:
        abstract = sanitize_text_for_postgres(paper.get("abstract") or "")
        if _is_usable_abstract(abstract):
            return (
                abstract,
                str(paper.get("source") or "unknown"),
                paper.get("url") or paper.get("doi"),
            )
    return None, None, None


def _first_discovered_doi(candidates: list[dict[str, Any]]) -> str | None:
    for paper in candidates:
        doi = (paper.get("doi") or "").strip()
        if doi:
            return doi
    return None


def _first_discovered_arxiv_id(candidates: list[dict[str, Any]]) -> str | None:
    for paper in candidates:
        arxiv_id = _extract_arxiv_id(
            " ".join(
                str(x)
                for x in (paper.get("paper_id"), paper.get("url"), paper.get("pdf_url"))
                if x
            )
        )
        if arxiv_id:
            return arxiv_id
    return None


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------

def _identifier_collides(
    conn: Any,
    *,
    column: str,
    value: str,
    paper_id: str,
) -> bool:
    """Return True if another paper row already owns this identifier value.

    Guards against the ``uq_paper_doi`` / ``uq_paper_arxiv_id`` unique
    constraints: a discovered DOI that belongs to a duplicate row must not
    be written back here (that's a dedup/merge concern, not an enrichment
    concern). We still keep the abstract + summary_zh we found.
    """
    if not value:
        return False
    row = conn.execute(
        f"SELECT 1 FROM paper WHERE {column} = %s AND paper_id <> %s LIMIT 1",
        (value, paper_id),
    ).fetchone()
    return row is not None


def _persist_abstract_and_metadata(
    conn: Any,
    *,
    paper_id: str,
    updates: dict[str, Any],
    quality_status: str,
    run_id: str,
) -> None:
    """Write abstract_clean + auxiliary metadata + quality_status in one
    forward-monotone UPDATE (never touches rows already in ``ready``)."""
    # Drop discovered identifiers that collide with another row — writing
    # them would trip uq_paper_doi / uq_paper_arxiv_id and roll back the
    # whole abstract write. The abstract + summary_zh are still valuable.
    safe_updates = dict(updates)
    for column in ("doi", "arxiv_id", "openalex_id"):
        value = str(safe_updates.get(column) or "").strip()
        if value and _identifier_collides(conn, column=column, value=value, paper_id=paper_id):
            logger.debug(
                "Dropping colliding %s=%s for paper %s (owned by another row)",
                column,
                value,
                paper_id,
            )
            safe_updates[column] = None

    conn.execute(
        """
        UPDATE paper
           SET abstract_clean = COALESCE(%s, abstract_clean),
               venue = COALESCE(NULLIF(trim(venue), ''), %s),
               year = COALESCE(year, %s),
               doi = COALESCE(NULLIF(trim(doi), ''), %s),
               arxiv_id = COALESCE(NULLIF(trim(arxiv_id), ''), %s),
               openalex_id = COALESCE(NULLIF(trim(openalex_id), ''), %s),
               authors_display = COALESCE(NULLIF(trim(authors_display), ''), %s),
               citation_count = COALESCE(citation_count, %s),
               quality_status = CASE
                   WHEN paper.quality_status = 'ready' THEN 'ready'
                   ELSE %s
               END,
               updated_at = now(),
               run_id = %s
         WHERE paper_id = %s
           AND paper.quality_status <> 'ready'
        """,
        (
            sanitize_optional_text_for_postgres(safe_updates.get("abstract_clean")),
            sanitize_optional_text_for_postgres(safe_updates.get("venue")),
            safe_updates.get("year"),
            sanitize_optional_text_for_postgres(safe_updates.get("doi")),
            sanitize_optional_text_for_postgres(safe_updates.get("arxiv_id")),
            sanitize_optional_text_for_postgres(safe_updates.get("openalex_id")),
            sanitize_optional_text_for_postgres(safe_updates.get("authors_display")),
            safe_updates.get("citation_count"),
            quality_status,
            run_id,
            paper_id,
        ),
    )


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
               quality_status = CASE
                   WHEN paper.quality_status = 'ready' THEN 'ready'
                   ELSE %s
               END,
               updated_at = now(),
               run_id = %s
         WHERE paper_id = %s
           AND paper.quality_status <> 'ready'
        """,
        (sanitize_text_for_postgres(summary_zh) or "", quality_status, run_id, paper_id),
    )


def _record_evidence_issue(
    conn: Any,
    *,
    paper_id: str,
    source_type: str,
    source_url: str | None,
    abstract_len: int,
    run_id: str,
) -> None:
    """Persist a lightweight evidence trail in pipeline_issue."""
    snapshot = {
        "run_id": str(run_id),
        "issue_type": "paper_search_abstract_evidence",
        "paper_id": paper_id,
        "source_type": source_type,
        "source_url": source_url,
        "abstract_len": abstract_len,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        conn.execute(
            """
            INSERT INTO pipeline_issue (
                professor_id, institution, stage, severity,
                description, evidence_snapshot, reported_by
            )
            VALUES (NULL, %s, 'paper_quality', 'info', %s, %s::jsonb, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                f"paper:{paper_id}",
                f"[paper_search_backfill] abstract via {source_type} ({abstract_len} chars)",
                json.dumps(snapshot, ensure_ascii=False),
                "run_paper_search_backfill",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Evidence insert failed for %s: %s", paper_id, exc)


# ---------------------------------------------------------------------------
# Main per-paper processing
# ---------------------------------------------------------------------------

def _process_paper(
    conn: Any,
    *,
    row: dict[str, Any],
    run_id: str,
    args: argparse.Namespace,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None,
    report: dict[str, Any],
    checkpoint_path: Path,
) -> None:
    paper_id = str(row["paper_id"])
    title = str(row.get("title_clean") or row.get("title_raw") or "").strip()
    if not title:
        report["papers_skipped_no_title"] += 1
        _append_checkpoint(checkpoint_path, {"paper_id": paper_id, "status": "skipped_no_title"})
        return

    target_doi = (row.get("doi") or "").strip() or None
    target_arxiv = (row.get("arxiv_id") or "").strip() or None
    target_year = row.get("year")

    # ---- 1. Discovery -------------------------------------------------------
    discovery_source = None
    discovery_url: str | None = None
    abstract_candidate: str | None = None
    discovered_doi = target_doi
    discovered_arxiv = target_arxiv
    enrichment_metadata: dict[str, Any] = {}

    # 1a. Title search via openags
    search_result = asyncio.run(
        _title_search(
            title,
            sources=args.sources,
            max_per_source=args.max_results_per_source,
        )
    )
    report["search_calls"] += 1
    report["source_result_counts"].setdefault("totals", {})
    for src, count in (search_result.get("source_results") or {}).items():
        report["source_result_counts"]["totals"][src] = (
            report["source_result_counts"]["totals"].get(src, 0) + int(count or 0)
        )
    for src, err in (search_result.get("errors") or {}).items():
        report["search_errors"].setdefault(src, 0)
        report["search_errors"][src] += 1
        samples = report["search_error_samples"].setdefault(src, [])
        if len(samples) < 3:
            samples.append({"paper_id": paper_id, "error": str(err)[:200]})

    candidates = _ranked_candidates(
        search_result,
        target_title=title,
        target_doi=target_doi,
        target_arxiv_id=target_arxiv,
        target_year=target_year,
    )
    if candidates:
        report["papers_with_match"] += 1
        top = candidates[0]
        report["top_match_scores"].append(float(top.get("_match_score") or 0.0))
        if not discovered_doi:
            discovered_doi = _first_discovered_doi(candidates)
        if not discovered_arxiv:
            discovered_arxiv = _first_discovered_arxiv_id(candidates)
        abstract_candidate, discovery_source, discovery_url = _pick_abstract(candidates)
        if discovery_source:
            report["abstract_source_counts"][discovery_source] = (
                report["abstract_source_counts"].get(discovery_source, 0) + 1
            )

    # 1b. Existing in-repo hybrid enrichment (richer metadata) when we now
    # have any identifier. This is what surfaces venue/year/citation/pdf_url
    # cleanly.
    enrichment: PaperMetadataEnrichment | None = None
    if discovered_doi or discovered_arxiv or row.get("openalex_id"):
        try:
            enrichment = enrich_paper_with_hybrid_sources(
                discovered_doi,
                arxiv_id=discovered_arxiv,
                openalex_id=(str(row["openalex_id"]) if row.get("openalex_id") else None),
            )
        except Exception as exc:  # noqa: BLE001
            report["enrichment_errors"] += 1
            logger.debug("Hybrid enrichment crashed for %s: %s", paper_id, exc)

    if enrichment is not None:
        if _is_usable_abstract(enrichment.abstract) and not _is_usable_abstract(abstract_candidate):
            abstract_candidate = sanitize_text_for_postgres(enrichment.abstract)
            discovery_source = discovery_source or "hybrid_enrichment"
            discovery_url = discovery_url or enrichment.source_url
        if enrichment.doi and not discovered_doi:
            discovered_doi = enrichment.doi
        if enrichment.arxiv_id and not discovered_arxiv:
            discovered_arxiv = enrichment.arxiv_id
        for key, value in (
            ("venue", enrichment.venue),
            ("year", _year_from_publication_date(enrichment.publication_date)),
            ("citation_count", enrichment.citation_count),
            ("authors_display", _authors_display(enrichment.authors)),
            ("doi", discovered_doi),
            ("arxiv_id", discovered_arxiv),
            ("openalex_id", row.get("openalex_id")),
        ):
            if value is not None and str(value).strip():
                enrichment_metadata[key] = value
        report["enrichment_hits"] += 1

    if not _is_usable_abstract(abstract_candidate):
        report["papers_no_abstract"] += 1
        _append_checkpoint(
            checkpoint_path,
            {
                "paper_id": paper_id,
                "status": "no_abstract_found",
                "candidates": len(candidates),
                "sources_used": search_result.get("sources_used"),
            },
        )
        return

    enrichment_metadata["abstract_clean"] = abstract_candidate
    report["abstracts_found"] += 1

    # ---- 2. Persist abstract + metadata ------------------------------------
    row["abstract_clean"] = abstract_candidate
    row["doi"] = discovered_doi or row.get("doi")
    row["arxiv_id"] = discovered_arxiv or row.get("arxiv_id")
    if enrichment_metadata.get("venue"):
        row["venue"] = enrichment_metadata["venue"]
    if enrichment_metadata.get("year"):
        row["year"] = enrichment_metadata["year"]
    if enrichment_metadata.get("authors_display"):
        row["authors_display"] = enrichment_metadata["authors_display"]

    promotion = evaluate_paper_promotion(
        current_status=_current_quality_status(row),
        signals=_paper_enrichment_signals(
            row,
            summary_zh=row.get("summary_zh"),
            summary_zh_boilerplate_rejected=False,
        ),
    )
    pre_summary_status = promotion.next_status

    if not args.dry_run:
        try:
            _persist_abstract_and_metadata(
                conn,
                paper_id=paper_id,
                updates=enrichment_metadata,
                quality_status=pre_summary_status,
                run_id=run_id,
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            report["persist_errors"] += 1
            conn.rollback()
            logger.warning("Abstract persist failed for %s: %s", paper_id, exc)
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "abstract_persist_error", "error": str(exc)},
            )
            return
        _record_evidence_issue(
            conn,
            paper_id=paper_id,
            source_type=discovery_source or "unknown",
            source_url=discovery_url,
            abstract_len=len(abstract_candidate),
            run_id=run_id,
        )
        conn.commit()
    row["quality_status"] = pre_summary_status

    # ---- 3. arXiv full text (optional) -------------------------------------
    if not args.skip_full_text and discovered_arxiv:
        report["full_text_attempts"] += 1
        try:
            pdf_url = f"https://arxiv.org/pdf/{discovered_arxiv}"
            extract = fetch_pdf_url_full_text(
                pdf_url,
                paper_id=paper_id,
                source=f"paper_search_mcp:arxiv:{discovered_arxiv}",
            )
            if not args.dry_run:
                upsert_paper_full_text(conn, paper_id=paper_id, extract=extract, run_id=run_id)
                conn.commit()
            if _is_usable_abstract(extract.abstract) and not _is_usable_abstract(
                row.get("abstract_clean")
            ):
                row["abstract_clean"] = sanitize_text_for_postgres(extract.abstract)
            if _is_usable_abstract(extract.abstract) or _is_usable_abstract(extract.intro):
                report["full_text_success"] += 1
        except Exception as exc:  # noqa: BLE001
            report["full_text_errors"] += 1
            logger.debug("arXiv full-text fetch failed for %s: %s", paper_id, exc)

    # ---- 4. summary_zh via local LLM ---------------------------------------
    abstract_for_summary = (
        sanitize_text_for_postgres(row.get("abstract_clean") or "")
        or sanitize_text_for_postgres(row.get("full_text_abstract") or "")
        or sanitize_text_for_postgres(row.get("full_text_intro") or "")
    )
    if not _is_usable_abstract(abstract_for_summary):
        _append_checkpoint(
            checkpoint_path,
            {
                "paper_id": paper_id,
                "status": "abstract_only_no_summary",
                "abstract_source": discovery_source,
            },
        )
        return

    try:
        summary_zh = translate_abstract_to_zh(
            str(abstract_for_summary),
            llm_client=llm_client,
            llm_model=llm_model,
            extra_body=extra_body,
        )
    except Exception as exc:  # noqa: BLE001
        report["summary_errors"] += 1
        logger.warning("summary_zh generation crashed for %s: %s", paper_id, exc)
        _append_checkpoint(
            checkpoint_path,
            {"paper_id": paper_id, "status": "summary_error", "error": str(exc)[:200]},
        )
        return

    if not summary_zh:
        report["summary_empty"] += 1
        _append_checkpoint(
            checkpoint_path,
            {"paper_id": paper_id, "status": "summary_empty", "abstract_source": discovery_source},
        )
        return

    is_boilerplate = False
    try:
        is_boilerplate = judge_summary_boilerplate(
            summary_zh,
            llm_client=llm_client,
            llm_model=llm_model,
            extra_body=extra_body,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("boilerplate judge crashed for %s: %s", paper_id, exc)

    if is_boilerplate:
        report["summary_rejected_boilerplate"] += 1
        _append_checkpoint(
            checkpoint_path,
            {
                "paper_id": paper_id,
                "status": "rejected_boilerplate",
                "abstract_source": discovery_source,
            },
        )
        return

    post_promotion = evaluate_paper_promotion(
        current_status=_current_quality_status(row),
        signals=_paper_enrichment_signals(
            row,
            summary_zh=summary_zh,
            summary_zh_boilerplate_rejected=False,
        ),
    )
    final_status = post_promotion.next_status

    if not args.dry_run:
        try:
            _persist_summary_zh(
                conn,
                paper_id=paper_id,
                summary_zh=summary_zh,
                quality_status=final_status,
                run_id=run_id,
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            report["persist_errors"] += 1
            conn.rollback()
            logger.warning("summary persist failed for %s: %s", paper_id, exc)
            _append_checkpoint(
                checkpoint_path,
                {"paper_id": paper_id, "status": "summary_persist_error", "error": str(exc)},
            )
            return

    report["summaries_written"] += 1
    if final_status == READY:
        report["promoted_to_ready"] += 1
    _append_checkpoint(
        checkpoint_path,
        {
            "paper_id": paper_id,
            "status": "dry_run_success" if args.dry_run else "written",
            "abstract_source": discovery_source,
            "abstract_chars": len(abstract_for_summary),
            "summary_chars": len(summary_zh),
            "quality_status": final_status,
            "promoted": final_status == READY,
        },
    )


def _year_from_publication_date(value: str | None) -> int | None:
    if not value:
        return None
    prefix = value.strip()[:4]
    if not prefix.isdigit():
        return None
    year = int(prefix)
    return year if 1800 <= year <= 2100 else None


def _authors_display(authors: tuple[Any, ...]) -> str | None:
    names = [
        name
        for author in authors
        if (
            name := sanitize_optional_text_for_postgres(
                getattr(author, "display_name", None)
            )
        )
    ]
    return sanitize_optional_text_for_postgres(", ".join(names)) if names else None


def _append_checkpoint(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def _open_llm_client(profile_name: str | None):
    settings = resolve_professor_llm_settings(profile_name, include_profile=True)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        http_client=httpx.Client(timeout=90.0, trust_env=False),
        timeout=90.0,
    )
    extra_body = build_non_thinking_extra_body(settings["local_llm_model"])
    return client, settings["local_llm_model"], extra_body


def _select_papers(
    conn: Any,
    *,
    limit: int | None,
    shard: tuple[int, int] | None = None,
    paper_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT p.paper_id, p.title_clean, p.title_raw, p.doi, p.arxiv_id, "
        "p.openalex_id, p.year, p.venue, p.authors_display, p.abstract_clean, "
        "p.summary_zh, p.quality_status, p.citation_count, "
        "pft.abstract AS full_text_abstract, pft.intro AS full_text_intro "
        "FROM paper p "
        "LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id "
        "WHERE p.quality_status = 'needs_enrichment' "
        "AND COALESCE(p.identity_status, 'unverified') NOT IN ('rejected', 'merged') "
    )
    params: list[Any] = []
    if paper_ids is not None:
        sql += "AND p.paper_id = ANY(%s) "
        params.append(list(paper_ids))
    if shard is not None:
        shard_k, shard_n = shard
        sql += "AND mod(abs(hashtext(p.paper_id)), %s) = %s "
        params += [shard_n, shard_k]
    sql += "ORDER BY p.paper_id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    dsn = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DATABASE_URL_TEST")
        or "postgresql://miroflow:miroflow@localhost:15432/miroflow_real"
    )
    if "+psycopg" in dsn:
        dsn = dsn.replace("postgresql+psycopg://", "postgresql://")

    patched = _patch_openags_mailto()
    logger.info("Patched openags mailto on searchers: %s", sorted(patched) or "<none>")

    conn = psycopg.connect(dsn, row_factory=dict_row)
    if args.dry_run:
        run_id = f"dry-run-{uuid4()}"
    else:
        run_id = str(
            open_pipeline_run(
                conn,
                run_kind="backfill_real",
                run_scope={
                    "task": "paper_search_backfill",
                    "limit": args.limit,
                    "sources": args.sources,
                    "skip_full_text": args.skip_full_text,
                    "max_results_per_source": args.max_results_per_source,
                    "dry_run": args.dry_run,
                },
                triggered_by="run_paper_search_backfill",
            )
        )
        conn.commit()

    checkpoint_path = (
        _REPO_ROOT / "logs" / "data_agents" / "paper" / "paper_search_runs" / f"{run_id}.jsonl"
    )

    llm_client, llm_model, extra_body = _open_llm_client(args.llm_profile)

    shard: tuple[int, int] | None = None
    if args.shard:
        k_str, _, n_str = args.shard.partition("/")
        shard = (int(k_str), int(n_str))
    paper_ids: set[str] | None = None
    if args.paper_id_file:
        import json as _json
        ids: set[str] = set()
        for line in Path(args.paper_id_file).read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = _json.loads(line)
                pid = obj.get("paper_id") or obj.get("id") or ""
                if pid:
                    ids.add(pid)
            except (ValueError, KeyError):
                ids.add(line)  # plain ID per line
        paper_ids = ids or None
        logger.info("Loaded %d paper_ids from %s", len(ids), args.paper_id_file)
    rows = _select_papers(conn, limit=args.limit, shard=shard, paper_ids=paper_ids)
    started_at = time.monotonic()

    # Baseline counts so we can compute deltas + assert no ready degradation.
    pre_counts: dict[str, int] = {}
    for r in conn.execute(
        """
        SELECT quality_status, count(*)::int AS count
        FROM paper
        WHERE identity_status NOT IN ('rejected','merged')
        GROUP BY 1
        """
    ).fetchall():
        pre_counts[str(r["quality_status"])] = int(r["count"])
    pre_ready = pre_counts.get("ready", 0)
    logger.info(
        "Baseline ready=%d, needs_enrichment=%d",
        pre_ready,
        pre_counts.get("needs_enrichment", 0),
    )

    report: dict[str, Any] = {
        "run_id": run_id,
        "papers_total": len(rows),
        "papers_processed": 0,
        "papers_skipped_no_title": 0,
        "papers_no_abstract": 0,
        "papers_with_match": 0,
        "abstracts_found": 0,
        "abstract_source_counts": {},
        "source_result_counts": {},
        "search_errors": {},
        "search_error_samples": {},
        "search_calls": 0,
        "enrichment_hits": 0,
        "enrichment_errors": 0,
        "full_text_attempts": 0,
        "full_text_success": 0,
        "full_text_errors": 0,
        "summaries_written": 0,
        "summary_errors": 0,
        "summary_empty": 0,
        "summary_rejected_boilerplate": 0,
        "promoted_to_ready": 0,
        "persist_errors": 0,
        "top_match_scores": [],
        "baseline_ready": pre_ready,
        "polite_email": _polite_email(),
        "patched_searchers": sorted(patched),
        "dry_run": args.dry_run,
        "sources": args.sources,
        "skip_full_text": args.skip_full_text,
    }

    for row in rows:
        try:
            _process_paper(
                conn,
                row=row,
                run_id=run_id,
                args=args,
                llm_client=llm_client,
                llm_model=llm_model,
                extra_body=extra_body,
                report=report,
                checkpoint_path=checkpoint_path,
            )
            report["papers_processed"] += 1
        except Exception as exc:  # noqa: BLE001
            report["persist_errors"] += 1
            conn.rollback()
            logger.warning("Paper %s crashed: %s", row.get("paper_id"), exc)
            _append_checkpoint(
                checkpoint_path,
                {
                    "paper_id": str(row.get("paper_id")),
                    "status": "crashed",
                    "error": str(exc)[:300],
                },
            )

    # Final assertion: no ready paper degraded.
    post_ready = int(
        conn.execute(
            """
            SELECT count(*)::int AS count FROM paper
            WHERE quality_status = 'ready'
              AND identity_status NOT IN ('rejected','merged')
            """
        ).fetchone()["count"]
    )
    report["post_ready"] = post_ready
    report["ready_delta"] = post_ready - pre_ready
    report["ready_degraded"] = post_ready < pre_ready
    report["duration_seconds"] = round(time.monotonic() - started_at, 2)

    close_status = "partial" if report["persist_errors"] else "succeeded"
    if not args.dry_run:
        try:
            close_pipeline_run(
                conn,
                run_id,
                status=close_status,
                items_processed=report["papers_processed"],
                items_failed=report["persist_errors"],
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("close_pipeline_run failed: %s", exc)

    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
