# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.18d — close Round 7.17 name_identity pipeline_issue queue.

Round 7.17 ran the LLM name-identity gate against every professor with a
canonical_name_en. Rejections had their canonical_name_en cleared to NULL
and an audit row filed in pipeline_issue (reported_by='round_7_17_scan',
stage='name_extraction', severity='medium').

Those 182 audit rows have been sitting in the queue ever since — the data
was already fixed at the time. This script closes them as resolved with a
verdict, so the unresolved-issues feed shows only genuinely-open work.

For each round_7_17_scan issue we check: is canonical_name_en still NULL
(gate decision took effect)?
  * YES → mark resolved, resolution_notes='gate cleared canonical_name_en'
  * NO  → the gate rejected but the field is still set (2 known edge cases).
          Bump severity to 'high' and leave unresolved for manual review.

Also closes the audit trails for round_7_18b_topic_split_backfill,
round_7_9_prime_cleanup, round_7_18_non_person_name_cleanup (medium-sev
soft-deletes) — those are already-applied cleanups whose queue entries
just need to be marked resolved.

Usage:

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \
      uv run python scripts/run_name_identity_issue_closure.py
    # then, if the sample looks right:
    DATABASE_URL=... uv run python scripts/run_name_identity_issue_closure.py --apply --confirm-real-db
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"

# (reported_by, resolution_note) for audit-trail bulk-resolves. These are
# rows that represent work ALREADY performed by an earlier script run;
# their presence in the unresolved queue is just bookkeeping noise.
_AUDIT_TRAIL_ROUND_LABELS = {
    "round_7_18b_topic_split_backfill": (
        "topic split backfill applied — audit trail"
    ),
    "round_7_9_prime_cleanup": (
        "topic noise cleanup applied — audit trail"
    ),
}

# Non-person-name cleanup: the 4 medium-sev soft-deletes can be closed
# (the professor was soft-deleted, data was handled). The 1 high-sev
# (Anita Zehrer·MCI... with 20 papers) must stay open for manual triage.
_NON_PERSON_MEDIUM_NOTE = "non-person soft-delete applied — audit trail"


@dataclass
class ClosureStats:
    r7_17_examined: int = 0
    r7_17_cleared_and_resolved: int = 0
    r7_17_bumped_to_high: int = 0
    audit_trail_resolved: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 7.18d — close Round 7.17 name_identity issues."
    )
    parser.add_argument("--database-url")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-real-db", action="store_true")
    return parser.parse_args()


def _resolve_issue(conn, issue_id, notes: str, *, round_label: str) -> None:
    conn.execute(
        """
        UPDATE pipeline_issue
           SET resolved = true,
               resolved_at = now(),
               resolution_notes = %s,
               resolution_round = %s
         WHERE issue_id = %s
        """,
        (notes, round_label, issue_id),
    )


def _bump_severity_to_high(conn, issue_id, notes: str) -> None:
    conn.execute(
        """
        UPDATE pipeline_issue
           SET severity = 'high',
               resolution_notes = %s
         WHERE issue_id = %s
        """,
        (notes, issue_id),
    )


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
        print("ALLOW_MOCK_BACKFILL=1 required.", file=sys.stderr)
        return 3

    stats = ClosureStats()

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        # --- round_7_17_scan: name_identity gate closures ---
        rows = conn.execute(
            """
            SELECT i.issue_id, i.professor_id, p.canonical_name,
                   p.canonical_name_en
              FROM pipeline_issue i
              JOIN professor p ON p.professor_id = i.professor_id
             WHERE i.reported_by = 'round_7_17_scan' AND i.resolved = false
             ORDER BY i.reported_at
            """
        ).fetchall()
        for row in rows:
            stats.r7_17_examined += 1
            if row["canonical_name_en"] is None:
                stats.r7_17_cleared_and_resolved += 1
                if args.apply:
                    _resolve_issue(
                        conn,
                        row["issue_id"],
                        notes="gate cleared canonical_name_en",
                        round_label="round_7_18d",
                    )
            else:
                stats.r7_17_bumped_to_high += 1
                if args.apply:
                    _bump_severity_to_high(
                        conn,
                        row["issue_id"],
                        notes=(
                            "gate rejected but canonical_name_en still set — "
                            "manual triage needed"
                        ),
                    )

        # --- audit-trail bulk closes ---
        for reported_by, note in _AUDIT_TRAIL_ROUND_LABELS.items():
            rowcount = conn.execute(
                """
                UPDATE pipeline_issue
                   SET resolved = true,
                       resolved_at = now(),
                       resolution_notes = %s,
                       resolution_round = 'round_7_18d'
                 WHERE reported_by = %s AND resolved = false
                """,
                (note, reported_by) if args.apply else (note, reported_by),
            ).rowcount
            if args.apply:
                stats.audit_trail_resolved += rowcount

        # --- non-person-name medium-sev close ---
        rowcount = conn.execute(
            """
            UPDATE pipeline_issue
               SET resolved = true,
                   resolved_at = now(),
                   resolution_notes = %s,
                   resolution_round = 'round_7_18d'
             WHERE reported_by = 'round_7_18_non_person_name_cleanup'
               AND severity = 'medium'
               AND resolved = false
            """,
            (_NON_PERSON_MEDIUM_NOTE,),
        ).rowcount
        if args.apply:
            stats.audit_trail_resolved += rowcount

        if not args.apply:
            conn.rollback()

    print()
    print("=== name_identity issue closure summary ===")
    print(f"  r7_17_scan examined      : {stats.r7_17_examined}")
    print(f"  cleared → resolved       : {stats.r7_17_cleared_and_resolved}")
    print(f"  bumped to severity=high  : {stats.r7_17_bumped_to_high}")
    print(f"  apply                    : {args.apply}")
    if args.apply:
        print(f"  audit-trail resolved     : {stats.audit_trail_resolved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
