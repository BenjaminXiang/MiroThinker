"""Round 7.5 — backfill real professor canonical rows from existing enriched.jsonl.

Reads `logs/data_agents/professor/enriched.jsonl` (produced by earlier real
pipeline_v2/v3 runs — NOT mock data; see docs/plans/2026-04-18-002 §3.2),
reconstructs `EnrichedProfessorProfile` instances, and calls
`canonical_writer.write_professor_bundle` to land canonical rows in
`miroflow_real`.

Paper staging is NOT loaded in this first pass; a follow-up round will
harvest paper_staging.jsonl per-professor and populate professor_paper_link.

Usage:

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \\
      uv run python scripts/run_real_e2e_professor_backfill.py [--limit N] [--dry-run]

Safety: set `ALLOW_MOCK_BACKFILL=1` to write into `miroflow_test_mock`
(only useful from pytest fixtures that seed the sandbox). Default refuses
to touch the mock DB to avoid accidental cross-contamination.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import tuple_row
from pydantic import ValidationError

from src.data_agents.professor.canonical_writer import (
    ProfessorCanonicalReport,
    upsert_source_page_for_url,
    write_professor_bundle,
)
from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.name_selection import is_obvious_non_person_name
from src.data_agents.storage.postgres.connection import resolve_dsn


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENRICHED = REPO_ROOT / "logs" / "data_agents" / "professor" / "enriched.jsonl"


@dataclass
class BackfillStats:
    total_read: int = 0
    skipped_non_structured: int = 0
    skipped_validation: int = 0
    skipped_junk_name: int = 0
    nulled_junk_name_en: int = 0
    written: int = 0
    updated: int = 0
    errors: int = 0
    affiliations_total: int = 0
    facts_total: int = 0
    per_institution: Counter[str] = None

    def __post_init__(self):
        if self.per_institution is None:
            self.per_institution = Counter()


def _infer_page_role(url: str, profile_url: str) -> str:
    """Map a URL to a `source_page.page_role` CHECK value."""
    if url == profile_url:
        return "official_profile"
    # Simple heuristics — good enough for the aggregate enriched.jsonl.
    if "roster" in url or "faculty_member" in url or "teacher" in url:
        return "roster_seed"
    if "publication" in url or "publications" in url:
        return "official_publication_page"
    if url.endswith(".pdf"):
        return "cv_pdf"
    if "homepage" in url or "personal" in url:
        return "personal_homepage"
    return "official_profile"  # default — these are prof-adjacent real pages


def _is_official_host(url: str) -> bool:
    try:
        host = urlsplit(url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    return host.endswith(".edu.cn") or host.endswith(".gov.cn") or host.endswith(".ac.cn")


def _process_one(conn, raw: dict, stats: BackfillStats) -> None:
    stats.total_read += 1
    if raw.get("extraction_status") != "structured":
        stats.skipped_non_structured += 1
        return

    # Defensive: v3 extraction occasionally dumps the whole profile HTML into
    # the `name` field when the scraper can't isolate the name (seen in CUHK
    # English pages). Reject absurdly long names so the btree index stays
    # happy and the transaction doesn't abort.
    raw_name = (raw.get("name") or "").strip().lstrip("\u200b\ufeff")
    if len(raw_name) > 100 or "\n" in raw_name or "Publications" in raw_name:
        stats.skipped_validation += 1
        print(
            f"  [skip] implausible name (len={len(raw_name)}): {raw_name[:80]!r}...",
            file=sys.stderr,
        )
        return

    if is_obvious_non_person_name(raw_name):
        stats.skipped_junk_name += 1
        print(
            f"  [skip] junk name caught by guard: {raw_name!r} (inst={raw.get('institution')!r})",
            file=sys.stderr,
        )
        return

    raw_name_en = (raw.get("name_en") or "").strip()
    if raw_name_en and is_obvious_non_person_name(raw_name_en):
        raw = dict(raw)
        raw["name_en"] = None
        stats.nulled_junk_name_en += 1

    # Pydantic reconstruction. Any legacy fields are tolerated because the
    # model has defaults and model_validate ignores extras if extra='allow'
    # (default in Pydantic v2). Failures bucket into skipped_validation.
    try:
        enriched = EnrichedProfessorProfile.model_validate(raw)
    except ValidationError as exc:
        stats.skipped_validation += 1
        print(
            f"  [skip] validation failed: name={raw.get('name')!r} err={str(exc)[:180]}",
            file=sys.stderr,
        )
        return

    # Upsert primary profile page + any other evidence URLs (source_page rows).
    primary_page_id = None
    fetched_at = datetime.now(timezone.utc)
    try:
        primary_page_id = upsert_source_page_for_url(
            conn,
            url=enriched.profile_url,
            page_role="official_profile",
            owner_scope_kind="professor",
            owner_scope_ref=None,  # professor_id computed inside bundle
            fetched_at=fetched_at,
            is_official_source=_is_official_host(enriched.profile_url),
        )
        # Also upsert roster_source as a page with role=roster_seed
        if enriched.roster_source and enriched.roster_source != enriched.profile_url:
            upsert_source_page_for_url(
                conn,
                url=enriched.roster_source,
                page_role="roster_seed",
                owner_scope_kind="institution",
                owner_scope_ref=enriched.institution,
                fetched_at=fetched_at,
                is_official_source=_is_official_host(enriched.roster_source),
            )
        # Upsert other evidence URLs best-effort
        for evidence_url in (enriched.evidence_urls or [])[:5]:
            if evidence_url in {enriched.profile_url, enriched.roster_source}:
                continue
            try:
                upsert_source_page_for_url(
                    conn,
                    url=evidence_url,
                    page_role=_infer_page_role(evidence_url, enriched.profile_url),
                    owner_scope_kind="professor",
                    owner_scope_ref=None,
                    fetched_at=fetched_at,
                    is_official_source=_is_official_host(evidence_url),
                )
            except Exception as sub_exc:  # pragma: no cover
                print(f"  [warn] evidence page upsert failed: {evidence_url} ({sub_exc})",
                      file=sys.stderr)
    except Exception as exc:
        stats.errors += 1
        print(f"  [err] source_page upsert failed: {enriched.profile_url} ({exc})",
              file=sys.stderr)
        traceback.print_exc()
        return

    # Write canonical bundle
    try:
        report: ProfessorCanonicalReport = write_professor_bundle(
            conn,
            enriched=enriched,
            paper_staging=None,
            official_profile_page_id=primary_page_id,
        )
        if report.is_new_professor:
            stats.written += 1
        else:
            stats.updated += 1
        stats.affiliations_total += report.affiliations_written
        stats.facts_total += report.facts_written
        stats.per_institution[enriched.institution] += 1
    except Exception as exc:
        stats.errors += 1
        print(f"  [err] write_professor_bundle: name={enriched.name} err={exc}",
              file=sys.stderr)
        traceback.print_exc()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill professor canonical rows from real enriched.jsonl.")
    parser.add_argument("--source", type=Path, default=DEFAULT_ENRICHED,
                        help=f"Path to enriched.jsonl (default {DEFAULT_ENRICHED})")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process first N structured records (smoke test).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse + validate only; do not write to DB.")
    parser.add_argument("--commit-every", type=int, default=50,
                        help="Commit the transaction every N records (default 50).")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"ERROR: source file not found: {args.source}", file=sys.stderr)
        return 2

    dsn = resolve_dsn()
    if "miroflow_test_mock" in dsn and os.environ.get("ALLOW_MOCK_BACKFILL") != "1":
        print("ERROR: refusing to backfill into miroflow_test_mock by default. "
              "Set ALLOW_MOCK_BACKFILL=1 (pytest fixtures do this) or point "
              "DATABASE_URL at miroflow_real for production runs.", file=sys.stderr)
        return 3

    print(f"Reading: {args.source}")
    print(f"Target DSN: {dsn}")
    print(f"Dry run: {args.dry_run}")
    print()

    stats = BackfillStats()
    structured_seen = 0

    # canonical_writer uses positional row[0] access → tuple_row, not dict_row.
    with psycopg.connect(dsn, row_factory=tuple_row) as conn:
        for line_no, line in enumerate(args.source.open("r", encoding="utf-8"), 1):
            if line.strip() == "":
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"  [err] line {line_no} parse: {exc}", file=sys.stderr)
                stats.errors += 1
                continue

            if raw.get("extraction_status") != "structured":
                stats.total_read += 1
                stats.skipped_non_structured += 1
                continue

            if args.limit is not None and structured_seen >= args.limit:
                break
            structured_seen += 1

            if args.dry_run:
                stats.total_read += 1
                try:
                    EnrichedProfessorProfile.model_validate(raw)
                    stats.written += 1
                except ValidationError:
                    stats.skipped_validation += 1
                continue

            # Per-record savepoint so one bad record (aborted transaction)
            # doesn't cascade into subsequent inserts.
            try:
                with conn.transaction():
                    _process_one(conn, raw, stats)
            except Exception as exc:
                # _process_one already incremented stats.errors and logged;
                # the savepoint rolls back and we keep going.
                print(f"  [rollback] record level failure: {exc!r}", file=sys.stderr)

            if (stats.written + stats.updated) % args.commit_every == 0:
                conn.commit()

        if not args.dry_run:
            conn.commit()

    print()
    print("=== backfill summary ===")
    print(f"  total_read             : {stats.total_read}")
    print(f"  skipped_non_structured : {stats.skipped_non_structured}")
    print(f"  skipped_validation     : {stats.skipped_validation}")
    print(f"  skipped_junk_name      : {stats.skipped_junk_name}")
    print(f"  nulled_junk_name_en    : {stats.nulled_junk_name_en}")
    print(f"  written (new)          : {stats.written}")
    print(f"  updated (existing)     : {stats.updated}")
    print(f"  errors                 : {stats.errors}")
    print(f"  affiliations total     : {stats.affiliations_total}")
    print(f"  facts total            : {stats.facts_total}")
    print()
    print("Per-institution (top 10):")
    for inst, cnt in stats.per_institution.most_common(10):
        print(f"  {inst}: {cnt}")
    return 0 if stats.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
