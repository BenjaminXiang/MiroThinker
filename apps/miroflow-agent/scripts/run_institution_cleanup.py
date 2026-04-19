# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.18c — strip scraper-pollution from affiliation institution field.

Fixes primary affiliations like "中山大学（深圳） 陈伟津" and flags the
scraper-generated duplicate rows (same canonical_name, one with the
contaminated institution and one with "UNKNOWN_INSTITUTION") for manual
review. Does NOT auto-merge duplicate professor rows — downstream data
(facts, paper links) would need to be migrated first, and that's a
human-eyes-only decision.

Usage:

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \
      uv run python scripts/run_institution_cleanup.py
    # then, if the sample looks right:
    DATABASE_URL=... uv run python scripts/run_institution_cleanup.py --apply --confirm-real-db
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

from src.data_agents.professor.institution_cleanup import (
    strip_trailing_person_name,
)
from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_18c_institution_cleanup"


@dataclass
class CleanupStats:
    examined: int = 0
    stripped: int = 0
    duplicate_pairs_flagged: int = 0
    issues_inserted: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 7.18c — strip personal names glued onto institution."
    )
    parser.add_argument("--database-url")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-real-db", action="store_true")
    return parser.parse_args()


def _fetch_affiliations(conn) -> list[dict]:
    return conn.execute(
        """
        SELECT pa.affiliation_id, pa.professor_id, pa.institution,
               pa.is_primary, p.canonical_name, p.identity_status
          FROM professor_affiliation pa
          JOIN professor p ON p.professor_id = pa.professor_id
         ORDER BY pa.created_at
        """
    ).fetchall()


def _update_institution(conn, affiliation_id, new_institution: str) -> None:
    conn.execute(
        """
        UPDATE professor_affiliation
           SET institution = %s, updated_at = now()
         WHERE affiliation_id = %s
        """,
        (new_institution, affiliation_id),
    )


def _find_duplicate_pairs(conn) -> list[dict]:
    """Professor pairs sharing canonical_name where one has UNKNOWN_INSTITUTION."""
    return conn.execute(
        """
        WITH grouped AS (
          SELECT p.canonical_name,
                 array_agg(p.professor_id ORDER BY p.created_at) AS professor_ids,
                 array_agg(pa.institution ORDER BY p.created_at) AS institutions
            FROM professor p
            JOIN professor_affiliation pa
              ON pa.professor_id = p.professor_id AND pa.is_primary = true
           WHERE p.identity_status = 'resolved'
           GROUP BY p.canonical_name
          HAVING count(*) > 1
             AND bool_or(pa.institution = 'UNKNOWN_INSTITUTION')
        )
        SELECT canonical_name, professor_ids, institutions
          FROM grouped
        """
    ).fetchall()


def _file_issue(conn, *, professor_id: str, description: str, snapshot: dict) -> int:
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, stage, severity, description, evidence_snapshot, reported_by
        )
        VALUES (%s, 'affiliation', 'high', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            professor_id,
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
            "Refusing miroflow_real without --confirm-real-db.",
            file=sys.stderr,
        )
        return 2
    if "miroflow_test_mock" in dsn and os.environ.get("ALLOW_MOCK_BACKFILL") != "1":
        print("ALLOW_MOCK_BACKFILL=1 required for mock DB.", file=sys.stderr)
        return 3

    stats = CleanupStats()
    strip_samples: list[tuple[str, str, str]] = []
    duplicate_samples: list[dict] = []

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        rows = _fetch_affiliations(conn)
        for row in rows:
            stats.examined += 1
            cleaned = strip_trailing_person_name(row["institution"])
            if cleaned == row["institution"] or cleaned is None:
                continue
            stats.stripped += 1
            strip_samples.append(
                (row["professor_id"], row["institution"], cleaned)
            )
            if args.apply:
                _update_institution(conn, row["affiliation_id"], cleaned)

        # Duplicate detection
        dup_rows = _find_duplicate_pairs(conn)
        for row in dup_rows:
            stats.duplicate_pairs_flagged += 1
            snapshot = {
                "canonical_name": row["canonical_name"],
                "professor_ids": row["professor_ids"],
                "institutions": row["institutions"],
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "cleanup_round": "round_7_18c",
            }
            duplicate_samples.append(snapshot)
            description = (
                f"duplicate professor rows for canonical_name={row['canonical_name']!r}: "
                f"{len(row['professor_ids'])} rows, one has UNKNOWN_INSTITUTION"
            )
            if args.apply:
                stats.issues_inserted += _file_issue(
                    conn,
                    professor_id=row["professor_ids"][0],
                    description=description,
                    snapshot=snapshot,
                )

        if not args.apply:
            conn.rollback()

    print()
    print("=== institution cleanup summary ===")
    print(f"  examined affiliations     : {stats.examined}")
    print(f"  stripped personal names   : {stats.stripped}")
    print(f"  duplicate pairs flagged   : {stats.duplicate_pairs_flagged}")
    print(f"  apply                     : {args.apply}")
    if args.apply:
        print(f"  pipeline_issue rows       : {stats.issues_inserted}")
    if strip_samples:
        print("\nstripped samples (prof | before | after):")
        for pid, before, after in strip_samples:
            print(f"  {pid} | {before!r} → {after!r}")
    if duplicate_samples:
        print("\nduplicate pairs (need manual merge):")
        for snap in duplicate_samples:
            print(
                f"  canonical_name={snap['canonical_name']!r} "
                f"ids={snap['professor_ids']} "
                f"institutions={snap['institutions']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
