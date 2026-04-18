# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.9' — sweep existing `research_topic` facts with the updated guard.

Round 7.9 landed `topic_quality.is_plausible_research_topic`. The guard catches
many noise shapes at write time, but a few classes still slip through on
previously-collected data in `miroflow_real`:
  * Journal-name-plus-year: "Conservation Biology，2023"
  * Bare journal name: "Nano Letters", "JACS"
  * Generic meta labels: "Research syntheses", "Research interests"
  * Numbered section fragments: "（1）3D"

This script re-applies the updated guard against every `status='active'`
research_topic fact, demotes rejections to `status='deprecated'`, and files
a `pipeline_issue` row (stage='research_directions', severity='low') for
audit trail. Safe, read-through-by-default: `--dry-run` prints the hits
without writing.

Usage:

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \
      uv run python scripts/run_topic_noise_cleanup.py --dry-run
    # then, if the sample looks right:
    DATABASE_URL=... uv run python scripts/run_topic_noise_cleanup.py --apply --confirm-real-db

Safety: refuses to run against `miroflow_real` unless `--confirm-real-db` is
explicitly passed. `ALLOW_MOCK_BACKFILL=1` gates `miroflow_test_mock` for
pytest fixtures.
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

from src.data_agents.professor.topic_quality import is_plausible_research_topic
from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_9_prime_cleanup"
_DESCRIPTION_TEMPLATE = (
    "research_topic rejected by updated guard: {value!r} (prof={professor_id})"
)


@dataclass
class CleanupStats:
    examined: int = 0
    rejected: int = 0
    demoted: int = 0
    issues_inserted: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 7.9' — re-apply updated research_topic guard to existing rows."
    )
    parser.add_argument(
        "--database-url", help="Postgres DSN. Defaults to DATABASE_URL env."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually demote rejects and insert pipeline_issue rows (default is dry-run).",
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
        help="Only process first N active rows (for quick smoke test).",
    )
    return parser.parse_args()


def _fetch_active_topics(conn, *, limit: int | None) -> list[dict]:
    sql = """
        SELECT f.fact_id, f.professor_id, f.value_raw, p.canonical_name,
               pa.institution
          FROM professor_fact f
          JOIN professor p ON p.professor_id = f.professor_id
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = f.professor_id AND pa.is_primary = true
         WHERE f.fact_type = 'research_topic'
           AND f.status = 'active'
         ORDER BY f.created_at
    """
    if limit is not None:
        sql += f"\n         LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def _demote(conn, fact_id) -> None:
    conn.execute(
        """
        UPDATE professor_fact
           SET status = 'deprecated',
               updated_at = now()
         WHERE fact_id = %s
        """,
        (fact_id,),
    )


def _file_issue(conn, row: dict) -> int:
    description = _DESCRIPTION_TEMPLATE.format(
        value=row["value_raw"][:80], professor_id=row["professor_id"]
    )
    snapshot = {
        "type": "research_directions_noise_report",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "professor": {
            "professor_id": row["professor_id"],
            "canonical_name": row["canonical_name"],
            "institution": row["institution"],
        },
        "fact": {
            "fact_id": str(row["fact_id"]),
            "value_raw": row["value_raw"],
        },
        "cleanup_round": "round_7_9_prime",
    }
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, institution, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (%s, %s, 'research_directions', 'low', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            row["professor_id"],
            row["institution"],
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
    samples: list[tuple[str, str, str]] = []

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        rows = _fetch_active_topics(conn, limit=args.limit)
        for row in rows:
            stats.examined += 1
            if is_plausible_research_topic(row["value_raw"]):
                continue
            stats.rejected += 1
            if len(samples) < 25:
                samples.append(
                    (row["professor_id"], row["canonical_name"], row["value_raw"])
                )
            if args.apply:
                _demote(conn, row["fact_id"])
                stats.issues_inserted += _file_issue(conn, row)
                stats.demoted += 1
        if not args.apply:
            conn.rollback()

    print()
    print("=== topic_noise cleanup summary ===")
    print(f"  examined            : {stats.examined}")
    print(f"  rejected            : {stats.rejected}")
    print(f"  apply               : {args.apply}")
    if args.apply:
        print(f"  demoted             : {stats.demoted}")
        print(f"  pipeline_issue rows : {stats.issues_inserted}")
    if samples:
        print("\nsample rejections (prof | name | value):")
        for pid, name, v in samples:
            print(f"  {pid} | {name!s:10.10} | {v[:60]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
