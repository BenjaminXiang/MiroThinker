# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.12' — sweep paper.title_clean with the updated title-quality guard.

Round 7.12' adds a rule-based ``paper.title_clean`` guard that catches author
lists and editorial bios pasted into the title field. This script re-applies
that guard to existing ``paper`` rows, prints the hits by default, and can
optionally null out rejected titles while filing a ``pipeline_issue`` audit row.

Usage:

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \
      uv run python scripts/run_bad_title_cleanup.py --confirm-real-db
    # then, if the sample looks right:
    DATABASE_URL=... uv run python scripts/run_bad_title_cleanup.py --apply --confirm-real-db
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from src.data_agents.paper.title_quality import is_plausible_paper_title
from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_12_prime_title_cleanup"
_UNKNOWN_INSTITUTION = "UNKNOWN_INSTITUTION"


@dataclass
class CleanupStats:
    examined: int = 0
    rejected: int = 0
    nulled: int = 0
    issues_inserted: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 7.12' — re-apply the paper title guard to existing rows."
    )
    parser.add_argument(
        "--database-url", help="Postgres DSN. Defaults to DATABASE_URL env."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually null out bad titles and insert pipeline_issue rows.",
    )
    parser.add_argument(
        "--confirm-real-db",
        action="store_true",
        help="Required if the DSN targets miroflow_real.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N paper rows.",
    )
    return parser.parse_args()


def _fetch_papers(conn, *, limit: int | None) -> list[dict]:
    sql = """
        SELECT p.paper_id,
               p.title_clean,
               p.year,
               p.venue,
               p.canonical_source,
               ppl.link_id,
               ppl.professor_id,
               prof.canonical_name,
               pa.institution
          FROM paper p
          LEFT JOIN LATERAL (
              SELECT link_id, professor_id
                FROM professor_paper_link
               WHERE paper_id = p.paper_id
               ORDER BY (link_status = 'verified') DESC, created_at
               LIMIT 1
          ) ppl ON true
          LEFT JOIN professor prof
            ON prof.professor_id = ppl.professor_id
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = ppl.professor_id AND pa.is_primary = true
         WHERE p.title_clean IS NOT NULL
         ORDER BY p.first_seen_at
    """
    if limit is not None:
        sql += f"\n         LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def _paper_title_is_nullable(conn) -> bool:
    row = conn.execute(
        """
        SELECT is_nullable
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'paper'
           AND column_name = 'title_clean'
        """
    ).fetchone()
    return bool(row and row["is_nullable"] == "YES")


def _null_title(conn, paper_id: str) -> None:
    conn.execute(
        """
        UPDATE paper
           SET title_clean = NULL,
               updated_at = now()
         WHERE paper_id = %s
        """,
        (paper_id,),
    )


def _file_issue(conn, row: dict) -> int:
    description = f"paper.title_clean rejected by guard: {row['title_clean']!r}"
    snapshot = {
        "type": "paper_title_quality_report",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "paper": {
            "paper_id": row["paper_id"],
            "title_clean": row["title_clean"],
            "year": row["year"],
            "venue": row["venue"],
            "canonical_source": row["canonical_source"],
        },
        "linked_professor": {
            "professor_id": row["professor_id"],
            "canonical_name": row["canonical_name"],
            "institution": row["institution"],
            "link_id": str(row["link_id"]) if row["link_id"] is not None else None,
        },
        "cleanup_round": "round_7_12_prime",
    }
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, link_id, institution, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (%s, %s, %s, 'paper_quality', 'low', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            row["professor_id"],
            row["link_id"],
            row["institution"] or _UNKNOWN_INSTITUTION,
            description,
            json.dumps(snapshot, ensure_ascii=False),
            _REPORTED_BY,
        ),
    )
    return cursor.rowcount


def main() -> int:
    args = _parse_args()

    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print(
            "Refusing to run against miroflow_real without --confirm-real-db.",
            file=sys.stderr,
        )
        return 2
    if "miroflow_test_mock" in dsn and os.environ.get("ALLOW_MOCK_BACKFILL") != "1":
        print(
            "Refusing mock DB by default. Set ALLOW_MOCK_BACKFILL=1 "
            "(pytest fixtures do this).",
            file=sys.stderr,
        )
        return 3

    stats = CleanupStats()
    samples: list[tuple[str, str, str, str]] = []

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        if args.apply and not _paper_title_is_nullable(conn):
            print(
                "Refusing --apply because paper.title_clean is still NOT NULL in this DB.",
                file=sys.stderr,
            )
            return 4
        rows = _fetch_papers(conn, limit=args.limit)
        for row in rows:
            stats.examined += 1
            if is_plausible_paper_title(row["title_clean"]):
                continue
            stats.rejected += 1
            if len(samples) < 25:
                samples.append(
                    (
                        row["paper_id"],
                        row["canonical_name"] or "",
                        row["institution"] or "",
                        row["title_clean"],
                    )
                )
            if args.apply:
                _null_title(conn, row["paper_id"])
                stats.issues_inserted += _file_issue(conn, row)
                stats.nulled += 1
        if not args.apply:
            conn.rollback()

    print()
    print("=== bad_title cleanup summary ===")
    print(f"  examined            : {stats.examined}")
    print(f"  rejected            : {stats.rejected}")
    print(f"  apply               : {args.apply}")
    if args.apply:
        print(f"  title_clean nulled  : {stats.nulled}")
        print(f"  pipeline_issue rows : {stats.issues_inserted}")
    if samples:
        print("\nsample rejections (paper_id | professor | institution | title):")
        for paper_id, name, institution, title in samples:
            print(
                f"  {paper_id} | {name!s:10.10} | {institution!s:25.25} | {title[:80]!r}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
