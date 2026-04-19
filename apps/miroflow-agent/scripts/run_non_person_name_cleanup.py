# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.18 — sweep professor rows whose canonical_name is clearly not a person.

The Round 7.18 guard extensions (`name_selection.is_obvious_non_person_name`
and `looks_like_profile_blob`) now catch patterns seen in `miroflow_real`:
  * Page section headings: "师资力量", "综合新闻"
  * Stuck-on Chinese field labels: "陈怀海 性别： 男", "倪江群职称：教授"
  * Long multi-field strings glued by "·": "Prof. Dr. Anita Zehrer·MCI The ..."

This script re-applies the updated guard against every `identity_status='resolved'`
professor row and:

  * If the row has NO verified paper links (safe case): flip `identity_status`
    to `'inactive'` (soft delete, reversible) and file a pipeline_issue
    (severity='medium', stage='name_extraction') for audit.
  * If the row HAS verified paper links (risky case — Anita Zehrer·MCI... has
    20 papers): leave `identity_status` alone and file a pipeline_issue
    (severity='high') for manual triage. Orphaning 20 paper_links would lose
    real data; a human has to decide.

Safe, read-through-by-default: `--dry-run` prints the hits without writing.

Usage:

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \
      uv run python scripts/run_non_person_name_cleanup.py --dry-run
    # then, if the sample looks right:
    DATABASE_URL=... uv run python scripts/run_non_person_name_cleanup.py --apply --confirm-real-db

Safety: refuses to run against `miroflow_real` unless `--confirm-real-db` is
explicitly passed. `ALLOW_MOCK_BACKFILL=1` gates `miroflow_test_mock`.
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

from src.data_agents.professor.name_selection import (
    is_obvious_non_person_name,
    looks_like_profile_blob,
)
from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_18_non_person_name_cleanup"


@dataclass
class CleanupStats:
    examined: int = 0
    rejected: int = 0
    soft_deleted: int = 0
    flagged_for_manual: int = 0
    issues_inserted: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 7.18 — re-apply non-person-name guard to existing professors."
    )
    parser.add_argument(
        "--database-url", help="Postgres DSN. Defaults to DATABASE_URL env."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually soft-delete safe cases and insert pipeline_issue rows "
        "(default is dry-run).",
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
        help="Only process first N active professors (for quick smoke test).",
    )
    return parser.parse_args()


def _fetch_active_professors(conn, *, limit: int | None) -> list[dict]:
    sql = """
        SELECT p.professor_id,
               p.canonical_name,
               pa.institution,
               (SELECT count(*)
                  FROM professor_paper_link
                 WHERE professor_id = p.professor_id
                   AND link_status = 'verified')::int AS n_verified_papers
          FROM professor p
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = p.professor_id AND pa.is_primary = true
         WHERE p.identity_status = 'resolved'
         ORDER BY p.created_at
    """
    if limit is not None:
        sql += f"\n         LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def _soft_delete(conn, professor_id) -> None:
    conn.execute(
        """
        UPDATE professor
           SET identity_status = 'inactive',
               updated_at = now()
         WHERE professor_id = %s
        """,
        (professor_id,),
    )


def _file_issue(conn, row: dict, *, severity: str, verdict: str) -> int:
    description = (
        f"non-person canonical_name: {row['canonical_name']!r} "
        f"(prof={row['professor_id']}, verdict={verdict})"
    )
    snapshot = {
        "type": "non_person_name_report",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "professor": {
            "professor_id": row["professor_id"],
            "canonical_name": row["canonical_name"],
            "institution": row["institution"],
            "n_verified_papers": row["n_verified_papers"],
        },
        "cleanup_round": "round_7_18",
        "verdict": verdict,
    }
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, institution, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (%s, %s, 'name_extraction', %s, %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            row["professor_id"],
            row["institution"],
            severity,
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
    safe_samples: list[tuple[str, str, str]] = []
    risky_samples: list[tuple[str, str, str, int]] = []

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        rows = _fetch_active_professors(conn, limit=args.limit)
        for row in rows:
            stats.examined += 1
            name = row["canonical_name"]
            if not (
                is_obvious_non_person_name(name) or looks_like_profile_blob(name)
            ):
                continue
            stats.rejected += 1
            is_risky = row["n_verified_papers"] > 0
            if is_risky:
                stats.flagged_for_manual += 1
                if len(risky_samples) < 25:
                    risky_samples.append(
                        (
                            row["professor_id"],
                            name,
                            row["institution"] or "",
                            row["n_verified_papers"],
                        )
                    )
                if args.apply:
                    stats.issues_inserted += _file_issue(
                        conn, row, severity="high", verdict="manual_review"
                    )
            else:
                stats.soft_deleted += 1
                if len(safe_samples) < 25:
                    safe_samples.append(
                        (row["professor_id"], name, row["institution"] or "")
                    )
                if args.apply:
                    _soft_delete(conn, row["professor_id"])
                    stats.issues_inserted += _file_issue(
                        conn, row, severity="medium", verdict="soft_delete"
                    )
        if not args.apply:
            conn.rollback()

    print()
    print("=== non-person-name cleanup summary ===")
    print(f"  examined            : {stats.examined}")
    print(f"  rejected            : {stats.rejected}")
    print(f"  soft_deleted        : {stats.soft_deleted}")
    print(f"  flagged_for_manual  : {stats.flagged_for_manual}")
    print(f"  apply               : {args.apply}")
    if args.apply:
        print(f"  pipeline_issue rows : {stats.issues_inserted}")
    if safe_samples:
        print("\nsafe (0 papers → soft-deleted):")
        for pid, name, inst in safe_samples:
            print(f"  {pid} | {inst!s:25.25} | {name!r}")
    if risky_samples:
        print("\nrisky (has papers → manual triage):")
        for pid, name, inst, nv in risky_samples:
            print(f"  {pid} | {inst!s:25.25} | papers={nv:3d} | {name!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
