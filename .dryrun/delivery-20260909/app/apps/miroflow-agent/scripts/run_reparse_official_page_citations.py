"""Round 7.15 — LLM-reparse ``official_page`` papers whose authors_display
is NULL.

The ``official_site`` scraper stuffed the raw citation string into
``paper.title_clean`` without splitting authors / title / venue / year.
This script pulls those rows, asks Gemma to parse each into structured
fields, and UPDATEs ``paper`` in place. Rows where the LLM judges
``is_paper=false`` are left unchanged (to be surfaced to human review
via the Round 8c admin UI).

Usage::

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \\
      uv run python scripts/run_reparse_official_page_citations.py \\
        [--limit N] [--dry-run]

Safety: refuses to write to ``miroflow_test_mock`` unless
``ALLOW_MOCK_BACKFILL=1`` is set.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import tuple_row

from src.data_agents.paper.citation_parser import (
    CitationInput,
    parse_citations,
)
from src.data_agents.professor.llm_profiles import (
    render_professor_llm_profile_names,
    resolve_professor_llm_settings,
)
from src.data_agents.storage.postgres.connection import resolve_dsn

_DEFAULT_LLM_PROFILE = "gemma4"


@dataclass
class ReparseStats:
    papers_examined: int = 0
    papers_updated: int = 0
    papers_flagged_non_paper: int = 0
    papers_low_confidence: int = 0
    llm_errors: int = 0
    samples_updated: list[tuple[str, list[str], str | None, int | None]] = field(default_factory=list)
    samples_flagged: list[tuple[str, str, str]] = field(default_factory=list)


def _load_targets(conn, *, limit: int | None) -> list[tuple[str, str]]:
    sql = """
        SELECT paper_id, title_clean
          FROM paper
         WHERE canonical_source='official_page'
           AND (authors_display IS NULL OR authors_display='')
         ORDER BY paper_id
    """
    if limit is not None:
        sql += f"\n         LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def _apply_parse(
    conn,
    *,
    paper_id: str,
    raw_title: str,
    result,  # ParsedCitation
    dry_run: bool,
    stats: ReparseStats,
) -> None:
    if result.error is not None:
        stats.llm_errors += 1
    if not result.is_paper:
        if result.confidence < 0.7 and result.confidence > 0.0:
            stats.papers_low_confidence += 1
        else:
            stats.papers_flagged_non_paper += 1
        if len(stats.samples_flagged) < 10:
            stats.samples_flagged.append(
                (paper_id, raw_title[:80], result.reasoning[:100])
            )
        return
    authors_csv = ", ".join(result.authors)[:500] or None
    clean_title = (result.title or raw_title).strip()[:500]
    if not clean_title:
        clean_title = raw_title[:500]
    venue = (result.venue or None)
    if venue:
        venue = venue.strip()[:300] or None
    year = result.year if isinstance(result.year, int) and 1800 <= result.year <= 2100 else None

    if not dry_run:
        conn.execute(
            """
            UPDATE paper
               SET title_clean=%s,
                   authors_display=COALESCE(%s, authors_display),
                   venue=COALESCE(%s, venue),
                   year=COALESCE(%s, year),
                   updated_at=now()
             WHERE paper_id=%s
            """,
            (clean_title, authors_csv, venue, year, paper_id),
        )
    stats.papers_updated += 1
    if len(stats.samples_updated) < 10:
        stats.samples_updated.append(
            (paper_id, result.authors[:4], venue, year)
        )


def _run(args: argparse.Namespace) -> int:
    dsn_sa = resolve_dsn()
    if (
        "miroflow_test_mock" in dsn_sa
        and os.environ.get("ALLOW_MOCK_BACKFILL") != "1"
    ):
        print(
            "ERROR: refusing to write to miroflow_test_mock. "
            "Set ALLOW_MOCK_BACKFILL=1 or point DATABASE_URL at miroflow_real.",
            file=sys.stderr,
        )
        return 3
    pg_dsn = dsn_sa.replace("postgresql+psycopg://", "postgresql://", 1)

    for key in ("all_proxy", "ALL_PROXY", "http_proxy", "HTTP_PROXY",
                "https_proxy", "HTTPS_PROXY"):
        os.environ.pop(key, None)

    llm_settings = resolve_professor_llm_settings(
        profile_name=args.llm_profile, include_profile=True
    )
    print(f"[reparse] llm profile = {llm_settings['llm_profile']}")

    from openai import OpenAI

    client = OpenAI(
        base_url=llm_settings["local_llm_base_url"],
        api_key=llm_settings["local_llm_api_key"] or "EMPTY",
        timeout=60.0,
    )
    model = llm_settings["local_llm_model"]
    print(f"[reparse] endpoint = {llm_settings['local_llm_base_url']}  model = {model}")

    stats = ReparseStats()
    BATCH = 10

    with psycopg.connect(pg_dsn, row_factory=tuple_row) as conn:
        targets = _load_targets(conn, limit=args.limit)
        print(f"[reparse] papers to reparse: {len(targets)}")

        for i in range(0, len(targets), BATCH):
            batch = targets[i : i + BATCH]
            stats.papers_examined += len(batch)
            inputs = [
                CitationInput(index=idx, raw_string=title)
                for idx, (_, title) in enumerate(batch)
            ]
            try:
                results = parse_citations(
                    items=inputs, llm_client=client, llm_model=model
                )
            except Exception as exc:
                print(f"  [err] batch failed at i={i}: {exc}", file=sys.stderr)
                traceback.print_exc()
                stats.llm_errors += len(batch)
                continue

            for (paper_id, raw_title), result in zip(batch, results):
                _apply_parse(
                    conn,
                    paper_id=paper_id,
                    raw_title=raw_title,
                    result=result,
                    dry_run=args.dry_run,
                    stats=stats,
                )

            if not args.dry_run and (i // BATCH + 1) % 5 == 0:
                conn.commit()
            examined = min(i + BATCH, len(targets))
            if examined % 100 == 0 or examined == len(targets):
                print(
                    f"  [progress] {examined}/{len(targets)}  "
                    f"updated={stats.papers_updated} "
                    f"flagged_non_paper={stats.papers_flagged_non_paper} "
                    f"low_conf={stats.papers_low_confidence} "
                    f"llm_errors={stats.llm_errors}"
                )

        if not args.dry_run:
            conn.commit()

    print()
    print("=== reparse summary ===")
    print(f"  papers_examined           : {stats.papers_examined}")
    print(f"  papers_updated            : {stats.papers_updated}")
    print(f"  papers_flagged_non_paper  : {stats.papers_flagged_non_paper}")
    print(f"  papers_low_confidence     : {stats.papers_low_confidence}")
    print(f"  llm_errors                : {stats.llm_errors}")
    if stats.samples_updated:
        print("\nsample updates:")
        for pid, authors, venue, year in stats.samples_updated:
            print(f"  {pid}  authors={authors}  venue={venue!r}  year={year}")
    if stats.samples_flagged:
        print("\nsample non-paper flags (for human review):")
        for pid, title, reason in stats.samples_flagged:
            print(f"  {pid}  {title!r}  reason={reason!r}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Round 7.15 LLM reparse of official_page citation strings."
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process first N papers (for smoke test).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and report without updating DB.")
    parser.add_argument(
        "--llm-profile",
        type=str,
        default=_DEFAULT_LLM_PROFILE,
        help=f"LLM profile (default {_DEFAULT_LLM_PROFILE}). "
             f"Available: {render_professor_llm_profile_names()}",
    )
    args = parser.parse_args()
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
