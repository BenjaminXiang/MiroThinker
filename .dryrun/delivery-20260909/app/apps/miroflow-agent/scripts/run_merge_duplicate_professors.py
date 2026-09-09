# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.19b' — merge duplicate professor rows into one canonical keeper.

Concurrent scraping occasionally created multiple rows for the same
person. The Round 7.18c duplicate detection script surfaced the pairs
as pipeline_issue rows but stopped short of merging — the merge is
risky (FK cascades would wipe the orphaned references) and needs
explicit human intent.

This script merges a fixed, explicit map of {keeper_id: [merged_ids]}.
It does NOT auto-discover duplicates — that prevents accidental mis-merges
of same-name-different-person pairs (which are common: 冯娟, 李佳, 王飞
all have 2 legitimate profs at different Shenzhen institutions).

Merge steps per (keeper, merged_id):
  1. Re-target FK references: UPDATE professor_affiliation / _fact /
     _paper_link / _patent_link / _company_role / company_team_member /
     pipeline_issue SET professor_id = keeper WHERE professor_id = merged_id.
  2. Deduplicate post-merge (verified > candidate > rejected for
     paper_links; distinct for facts).
  3. Update merged_id row: identity_status='merged_into',
     merged_into_id=keeper. Cascade is inert because we re-targeted the
     FKs first.
  4. File pipeline_issue audit with before/after counts.

--dry-run default; --apply --confirm-real-db for writes.
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

from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_19b_prime_merge_duplicates"

# Explicit merge plan. Keeper on left, merged on right.
# Chosen by fact count × paper count heuristic — see task notes in the PR.
_MERGE_PLAN: dict[str, list[str]] = {
    # Jianwei Huang — all 3 at 港中深; keeper has the 19 verified papers
    "PROF-E9E478585196": ["PROF-32426BF6C9A5", "PROF-4B7FCCC6D97C"],
    # 陈伟津 — all 3 originally at 中山深圳; keeper has the non-UNKNOWN
    # institution after Round 7.18c / 7.19b
    "PROF-2DE6D05E4B58": ["PROF-81A564B2B58D", "PROF-5E788D51A278"],
}

# Tables with FK `professor_id` that need re-targeting
_FK_TABLES = (
    "professor_affiliation",
    "professor_fact",
    "professor_paper_link",
    "professor_patent_link",
    "professor_company_role",
    "pipeline_issue",
)
# Tables that reference professor_id but via different column
_ALT_FK_TABLES = (
    ("company_team_member", "resolved_professor_id"),
)


@dataclass
class MergeResult:
    keeper_id: str
    merged_id: str
    rows_moved: dict[str, int]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--database-url")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm-real-db", action="store_true")
    return p.parse_args()


def _move_fk(conn, table: str, column: str, *, merged: str, keeper: str) -> int:
    return conn.execute(
        f"UPDATE {table} SET {column} = %s WHERE {column} = %s",
        (keeper, merged),
    ).rowcount


def _dedupe_affiliations(conn, keeper: str) -> int:
    """Delete duplicate affiliations sharing (institution, title, dept).
    Keep newest updated_at via DISTINCT ON."""
    return conn.execute(
        """
        DELETE FROM professor_affiliation
         WHERE professor_id = %s
           AND affiliation_id NOT IN (
             SELECT DISTINCT ON (
               institution,
               coalesce(title, ''),
               coalesce(department, '')
             ) affiliation_id
               FROM professor_affiliation
              WHERE professor_id = %s
              ORDER BY
                institution,
                coalesce(title, ''),
                coalesce(department, ''),
                updated_at DESC
           )
        """,
        (keeper, keeper),
    ).rowcount


def _dedupe_facts(conn, keeper: str) -> int:
    """Delete duplicate facts: same (fact_type, value_raw, status). Keep newest."""
    return conn.execute(
        """
        DELETE FROM professor_fact
         WHERE professor_id = %s
           AND fact_id NOT IN (
             SELECT DISTINCT ON (fact_type, value_raw, status) fact_id
               FROM professor_fact
              WHERE professor_id = %s
              ORDER BY fact_type, value_raw, status, updated_at DESC
           )
        """,
        (keeper, keeper),
    ).rowcount


def _dedupe_paper_links(conn, keeper: str) -> int:
    """Delete duplicate paper_links: same paper_id. Keep verified over
    candidate/rejected, and newer within same status."""
    return conn.execute(
        """
        DELETE FROM professor_paper_link ppl
         WHERE ppl.professor_id = %s
           AND ppl.link_id NOT IN (
             SELECT DISTINCT ON (ppl2.paper_id) ppl2.link_id
               FROM professor_paper_link ppl2
              WHERE ppl2.professor_id = ppl.professor_id
              ORDER BY ppl2.paper_id,
                       CASE ppl2.link_status WHEN 'verified' THEN 1
                                              WHEN 'candidate' THEN 2
                                              WHEN 'rejected'  THEN 3 END,
                       ppl2.updated_at DESC
           )
        """,
        (keeper,),
    ).rowcount


def _mark_merged(conn, merged_id: str, keeper_id: str) -> None:
    conn.execute(
        """
        UPDATE professor
           SET identity_status = 'merged_into',
               merged_into_id = %s,
               updated_at = now()
         WHERE professor_id = %s
           AND identity_status = 'resolved'
        """,
        (keeper_id, merged_id),
    )


def _file_audit(conn, result: MergeResult) -> int:
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "cleanup_round": "round_7_19b_prime",
        "keeper": result.keeper_id,
        "merged": result.merged_id,
        "rows_moved": result.rows_moved,
    }
    return conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, stage, severity,
            description, evidence_snapshot, reported_by, resolved, resolved_at, resolution_round
        )
        VALUES (%s, 'affiliation', 'low', %s, %s::jsonb, %s, true, now(), 'round_7_19b_prime')
        ON CONFLICT DO NOTHING
        """,
        (
            result.keeper_id,
            f"merged {result.merged_id} → {result.keeper_id}",
            json.dumps(snapshot, ensure_ascii=False),
            _REPORTED_BY,
        ),
    ).rowcount


def main() -> int:
    args = _parse_args()
    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print("Refusing miroflow_real without --confirm-real-db.", file=sys.stderr)
        return 2
    if "miroflow_test_mock" in dsn and os.environ.get("ALLOW_MOCK_BACKFILL") != "1":
        print("ALLOW_MOCK_BACKFILL=1 required.", file=sys.stderr)
        return 3

    results: list[MergeResult] = []

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        for keeper, merged_list in _MERGE_PLAN.items():
            for merged in merged_list:
                # Check both rows exist and keeper is resolved
                k_row = conn.execute(
                    "SELECT identity_status FROM professor WHERE professor_id=%s",
                    (keeper,),
                ).fetchone()
                m_row = conn.execute(
                    "SELECT identity_status FROM professor WHERE professor_id=%s",
                    (merged,),
                ).fetchone()
                if not k_row or not m_row:
                    print(f"  skip {merged}→{keeper}: row not found")
                    continue
                if m_row["identity_status"] != "resolved":
                    print(f"  skip {merged}→{keeper}: merged already {m_row['identity_status']}")
                    continue

                rows_moved: dict[str, int] = {}
                for tbl in _FK_TABLES:
                    rows_moved[tbl] = _move_fk(
                        conn, tbl, "professor_id", merged=merged, keeper=keeper
                    )
                for tbl, col in _ALT_FK_TABLES:
                    rows_moved[f"{tbl}.{col}"] = _move_fk(
                        conn, tbl, col, merged=merged, keeper=keeper
                    )
                # Dedupe on keeper
                rows_moved["_dedup_affs"] = _dedupe_affiliations(conn, keeper)
                rows_moved["_dedup_facts"] = _dedupe_facts(conn, keeper)
                rows_moved["_dedup_papers"] = _dedupe_paper_links(conn, keeper)

                _mark_merged(conn, merged, keeper)
                _file_audit(
                    conn,
                    MergeResult(keeper_id=keeper, merged_id=merged, rows_moved=rows_moved),
                )
                results.append(MergeResult(keeper, merged, rows_moved))
                print(f"  merged {merged} → {keeper}  {rows_moved}")

        if not args.apply:
            conn.rollback()
            print("\n(dry-run — rolled back)")
        else:
            print(f"\napplied. {len(results)} merges committed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
