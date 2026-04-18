"""Round 7.5 addendum — backfill paper and professor_paper_link from real
paper_staging.jsonl files scattered across per-professor runs.

After `run_real_e2e_professor_backfill.py` lands 2877 professors, this script
harvests paper_staging records produced by the same real pipeline runs,
upserts `paper` rows, and links them via `professor_paper_link` with status
`candidate` (conservative — promotion to `verified` comes from a separate
policy evaluator).

Source: `logs/data_agents/**/paper_staging.jsonl`
Anchor key: `anchoring_professor_id` (PaperStagingRecord field). Records whose
anchoring_professor_id is NOT already in `miroflow_real.professor` are
skipped (we don't create rogue professor rows from paper staging alone).

Usage:

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \\
      uv run python scripts/run_real_e2e_paper_staging_backfill.py [--limit N]

Safety: refuses to run against miroflow_test_mock.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

import psycopg
from psycopg.rows import tuple_row

from src.data_agents.paper.canonical_writer import upsert_paper
from src.data_agents.paper.title_quality import is_plausible_paper_title
from src.data_agents.professor.canonical_writer import _upsert_professor_paper_link
from src.data_agents.storage.postgres.connection import resolve_dsn


_OFFICIAL_SOURCE_ALIASES = {
    "official_site",
    "official_linked_orcid",
    "official_linked_google_scholar",
}


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG_ROOT = REPO_ROOT / "logs" / "data_agents"


@dataclass
class PaperBackfillStats:
    files_scanned: int = 0
    total_records: int = 0
    skipped_missing_anchor: int = 0
    skipped_missing_title: int = 0
    skipped_implausible_title: int = 0
    skipped_professor_not_canonical: int = 0
    resolved_by_anchor_id: int = 0
    resolved_by_name_inst: int = 0
    papers_upserted_new: int = 0
    papers_upserted_existing: int = 0
    links_new: int = 0
    links_updated: int = 0
    errors: int = 0
    sources: Counter[str] = None

    def __post_init__(self):
        if self.sources is None:
            self.sources = Counter()


def _iter_staging_files(root: Path) -> Iterable[Path]:
    yield from sorted(root.rglob("paper_staging.jsonl"))


def _fetch_canonical_professor_ids(conn) -> set[str]:
    rows = conn.execute("SELECT professor_id FROM professor").fetchall()
    return {row[0] for row in rows}


def _build_name_institution_index(conn) -> dict[tuple[str, str], str]:
    """Map (canonical_name, institution) -> professor_id for fallback
    resolution when the paper_staging's anchoring_professor_id is stale
    (different build_professor_id output between runs)."""
    rows = conn.execute(
        """
        SELECT p.canonical_name, pa.institution, p.professor_id
          FROM professor p
          JOIN professor_affiliation pa
            ON pa.professor_id = p.professor_id AND pa.is_primary = true
        """
    ).fetchall()
    index: dict[tuple[str, str], str] = {}
    for name, institution, pid in rows:
        key = (name.strip(), (institution or "").strip())
        index[key] = pid
    return index


def _resolve_anchor(
    record: dict,
    canonical_ids: set[str],
    name_index: dict[tuple[str, str], str],
) -> tuple[str | None, str]:
    """Return (professor_id_or_None, resolution_kind)."""
    anchor_id = record.get("anchoring_professor_id")
    if anchor_id and anchor_id in canonical_ids:
        return anchor_id, "anchoring_id"
    # Fallback: name + institution
    name = (record.get("anchoring_professor_name") or "").strip()
    institution = (record.get("anchoring_institution") or "").strip()
    if name and institution:
        key = (name, institution)
        pid = name_index.get(key)
        if pid:
            return pid, "name_institution"
    return None, "unmatched"


def _classify_evidence(record: dict) -> str:
    """Map the staging record's source into a professor_paper_link.evidence_source_type.

    paper_staging records are almost all `source='openalex'` from
    paper_collector. They're not official-listing evidence; they're API-based
    author matches. Use the `_with_affiliation_match` variant and rely on
    downstream policy to promote to verified.
    """
    # All known sources go under academic_api_with_affiliation_match per
    # plan 005 §6.5. Future: distinguish official_publication_page etc.
    return "academic_api_with_affiliation_match"


def _process_record(
    conn,
    record: dict,
    canonical_ids: set[str],
    name_index: dict[tuple[str, str], str],
    stats: PaperBackfillStats,
) -> None:
    stats.total_records += 1

    anchor_id, kind = _resolve_anchor(record, canonical_ids, name_index)
    if kind == "unmatched":
        if not record.get("anchoring_professor_id"):
            stats.skipped_missing_anchor += 1
        else:
            stats.skipped_professor_not_canonical += 1
        return
    if kind == "anchoring_id":
        stats.resolved_by_anchor_id += 1
    else:
        stats.resolved_by_name_inst += 1

    title = (record.get("title") or "").strip()
    if not title:
        stats.skipped_missing_title += 1
        return
    if not is_plausible_paper_title(title):
        stats.skipped_implausible_title += 1
        return

    source = record.get("source") or "openalex"
    stats.sources[source] += 1

    # Map staging source → paper.canonical_source enum
    # Plan 005 §6.4: canonical_source IN (openalex, semantic_scholar, crossref, official_page, manual)
    if source in _OFFICIAL_SOURCE_ALIASES:
        canonical_source = "official_page"
    elif source in {"openalex", "semantic_scholar", "crossref", "official_page", "manual"}:
        canonical_source = source
    else:
        canonical_source = "openalex"

    source_url = record.get("source_url", "") or ""
    openalex_id = None
    arxiv_id = None
    if canonical_source == "openalex" and "openalex.org/" in source_url:
        openalex_id = source_url.rsplit("/", 1)[-1]
    if "arxiv.org/abs/" in source_url.lower():
        arxiv_id = source_url.rsplit("/", 1)[-1]

    authors = record.get("authors") or []
    authors_display = ", ".join(str(a) for a in authors if a)[:500] or None

    try:
        paper_report = upsert_paper(
            conn,
            title_clean=title,
            title_raw=title,
            doi=record.get("doi"),
            arxiv_id=arxiv_id,
            openalex_id=openalex_id,
            semantic_scholar_id=None,
            year=record.get("year"),
            venue=record.get("venue"),
            abstract_clean=record.get("abstract"),
            authors_display=authors_display,
            citation_count=record.get("citation_count"),
            canonical_source=canonical_source,
        )
    except Exception as exc:
        stats.errors += 1
        print(f"  [err] upsert_paper failed: title={title[:60]!r} err={exc}",
              file=sys.stderr)
        return

    if paper_report.is_new:
        stats.papers_upserted_new += 1
    else:
        stats.papers_upserted_existing += 1

    # Check if link already exists to count new vs updated.
    existing = conn.execute(
        "SELECT 1 FROM professor_paper_link WHERE professor_id=%s AND paper_id=%s",
        (anchor_id, paper_report.paper_id),
    ).fetchone()

    try:
        _upsert_professor_paper_link(
            conn,
            professor_id=anchor_id,
            paper_id=paper_report.paper_id,
            link_status="candidate",  # conservative default; upgrade separately
            evidence_source_type=_classify_evidence(record),
            evidence_page_id=None,
            evidence_api_source=f"{source}:{openalex_id or record.get('doi') or title[:40]}"[:200],
            match_reason="author match via paper_collector",
            author_name_match_score=Decimal("0.85"),
            topic_consistency_score=None,
            institution_consistency_score=None,
            is_officially_listed=False,
        )
    except Exception as exc:
        stats.errors += 1
        print(f"  [err] link upsert failed: prof={anchor_id} paper={paper_report.paper_id} err={exc}",
              file=sys.stderr)
        return

    if existing is None:
        stats.links_new += 1
    else:
        stats.links_updated += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill paper + professor_paper_link from real paper_staging.jsonl")
    parser.add_argument("--root", type=Path, default=DEFAULT_LOG_ROOT,
                        help=f"Log root to walk (default {DEFAULT_LOG_ROOT})")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N records total.")
    parser.add_argument("--commit-every", type=int, default=500,
                        help="Commit every N records processed.")
    args = parser.parse_args()

    dsn = resolve_dsn()
    if "miroflow_test_mock" in dsn and os.environ.get("ALLOW_MOCK_BACKFILL") != "1":
        print("ERROR: refusing to backfill into miroflow_test_mock by default. "
              "Set ALLOW_MOCK_BACKFILL=1 (pytest fixtures do this) or point "
              "DATABASE_URL at miroflow_real.", file=sys.stderr)
        return 3

    if not args.root.exists():
        print(f"ERROR: root not found: {args.root}", file=sys.stderr)
        return 2

    stats = PaperBackfillStats()
    processed = 0

    with psycopg.connect(dsn, row_factory=tuple_row) as conn:
        canonical_ids = _fetch_canonical_professor_ids(conn)
        name_index = _build_name_institution_index(conn)
        print(f"canonical professors: {len(canonical_ids)}")
        print(f"name-institution index: {len(name_index)}")
        print(f"scanning: {args.root}")
        print()

        for fp in _iter_staging_files(args.root):
            stats.files_scanned += 1
            try:
                for line in fp.open("r", encoding="utf-8"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        stats.errors += 1
                        continue
                    _process_record(conn, record, canonical_ids, name_index, stats)
                    processed += 1
                    if processed % args.commit_every == 0:
                        conn.commit()
                    if args.limit is not None and processed >= args.limit:
                        break
            except Exception as exc:
                stats.errors += 1
                print(f"  [err] reading {fp}: {exc}", file=sys.stderr)
                traceback.print_exc()
            if args.limit is not None and processed >= args.limit:
                break

        conn.commit()

    print()
    print("=== paper backfill summary ===")
    print(f"  files_scanned                    : {stats.files_scanned}")
    print(f"  total_records                    : {stats.total_records}")
    print(f"  skipped_missing_anchor           : {stats.skipped_missing_anchor}")
    print(f"  skipped_missing_title            : {stats.skipped_missing_title}")
    print(f"  skipped_implausible_title        : {stats.skipped_implausible_title}")
    print(f"  skipped_professor_not_canonical  : {stats.skipped_professor_not_canonical}")
    print(f"  resolved_by_anchor_id            : {stats.resolved_by_anchor_id}")
    print(f"  resolved_by_name_inst (fallback) : {stats.resolved_by_name_inst}")
    print(f"  papers_upserted_new              : {stats.papers_upserted_new}")
    print(f"  papers_upserted_existing         : {stats.papers_upserted_existing}")
    print(f"  links_new                        : {stats.links_new}")
    print(f"  links_updated                    : {stats.links_updated}")
    print(f"  errors                           : {stats.errors}")
    print("  sources:", dict(stats.sources))
    return 0 if stats.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
