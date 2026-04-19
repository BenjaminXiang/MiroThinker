# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.18b — split compound research_topic facts into atomic topics.

Scraped research_directions sometimes pack 2+ topics into one fact:

    "计算神经科学，机器学习，人工智能，数据科学，生物图像分析"

This hurts downstream retrieval: a single long embedding dilutes the signal
for each atomic topic, and faceted aggregation over-counts the long string
as a single unique topic.

This script finds active `research_topic` facts whose `value_raw` contains
a compound separator (`，,、;；`), runs each through
`split_compound_research_topic`, and if the split produces ≥2 atomic pieces,
deprecates the original fact and inserts the atomic pieces as new facts
(copying `source_page_id`, `evidence_span`, `confidence`).

Garbage pieces ("等", "其他", "研究兴趣") are dropped by the updated
`is_plausible_research_topic` guard.

Safe by default: `--dry-run` prints what would happen. `--apply` writes.

Usage:

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \
      uv run python scripts/run_topic_split_backfill.py
    # then, if the sample looks right:
    DATABASE_URL=... uv run python scripts/run_topic_split_backfill.py --apply --confirm-real-db

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

from src.data_agents.professor.topic_quality import split_compound_research_topic
from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_18b_topic_split_backfill"


@dataclass
class BackfillStats:
    examined: int = 0
    splittable: int = 0
    total_atomic_inserted: int = 0
    originals_deprecated: int = 0
    garbage_deprecated: int = 0
    issues_inserted: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 7.18b — split compound research_topic facts."
    )
    parser.add_argument(
        "--database-url", help="Postgres DSN. Defaults to DATABASE_URL env."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write splits and deprecate originals (default dry-run).",
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
        help="Only process first N candidate rows (for smoke test).",
    )
    return parser.parse_args()


def _fetch_candidate_facts(conn, *, limit: int | None) -> list[dict]:
    """Active research_topic facts whose value_raw looks compound."""
    sql = """
        SELECT f.fact_id,
               f.professor_id,
               f.value_raw,
               f.source_page_id,
               f.evidence_span,
               f.confidence
          FROM professor_fact f
          JOIN professor p ON p.professor_id = f.professor_id
         WHERE f.fact_type = 'research_topic'
           AND f.status = 'active'
           AND p.identity_status = 'resolved'
           AND f.value_raw ~ '[，,、;；]'
         ORDER BY f.created_at
    """
    if limit is not None:
        sql += f"\n         LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def _deprecate(conn, fact_id) -> None:
    conn.execute(
        """
        UPDATE professor_fact
           SET status = 'deprecated',
               updated_at = now()
         WHERE fact_id = %s
        """,
        (fact_id,),
    )


def _insert_atomic(conn, *, source: dict, value_raw: str) -> None:
    conn.execute(
        """
        INSERT INTO professor_fact (
            professor_id, fact_type, value_raw,
            source_page_id, evidence_span, confidence, status
        )
        VALUES (%s, 'research_topic', %s, %s, %s, %s, 'active')
        """,
        (
            source["professor_id"],
            value_raw,
            source["source_page_id"],
            source["evidence_span"],
            source["confidence"],
        ),
    )


def _file_issue(conn, row: dict, *, atomic_pieces: list[str]) -> int:
    description = (
        f"research_topic split: {row['value_raw'][:80]!r} → "
        f"{len(atomic_pieces)} atomic topics"
    )
    snapshot = {
        "type": "topic_split_backfill_report",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "fact_id": str(row["fact_id"]),
        "professor_id": row["professor_id"],
        "original_value": row["value_raw"],
        "atomic_pieces": atomic_pieces,
        "cleanup_round": "round_7_18b",
    }
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (%s, 'research_directions', 'low', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            row["professor_id"],
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
            "Refusing mock DB by default. Set ALLOW_MOCK_BACKFILL=1.",
            file=sys.stderr,
        )
        return 3

    stats = BackfillStats()
    samples: list[tuple[str, list[str]]] = []

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        rows = _fetch_candidate_facts(conn, limit=args.limit)
        for row in rows:
            stats.examined += 1
            atomic = split_compound_research_topic(row["value_raw"])
            if not atomic:
                # All pieces rejected — deprecate original, no atomic replacements
                stats.garbage_deprecated += 1
                if args.apply:
                    _deprecate(conn, row["fact_id"])
                continue
            if len(atomic) == 1 and atomic[0] == row["value_raw"].strip():
                # Not actually splittable after trim
                continue
            stats.splittable += 1
            if len(samples) < 15:
                samples.append((row["value_raw"], atomic))
            if args.apply:
                _deprecate(conn, row["fact_id"])
                stats.originals_deprecated += 1
                for piece in atomic:
                    _insert_atomic(conn, source=row, value_raw=piece)
                    stats.total_atomic_inserted += 1
                stats.issues_inserted += _file_issue(
                    conn, row, atomic_pieces=atomic
                )
        if not args.apply:
            conn.rollback()

    print()
    print("=== topic split backfill summary ===")
    print(f"  examined (compound rows)   : {stats.examined}")
    print(f"  splittable (≥2 atomic)     : {stats.splittable}")
    print(f"  garbage_deprecated         : {stats.garbage_deprecated}")
    print(f"  apply                      : {args.apply}")
    if args.apply:
        print(f"  originals deprecated       : {stats.originals_deprecated}")
        print(f"  atomic pieces inserted     : {stats.total_atomic_inserted}")
        print(f"  pipeline_issue rows        : {stats.issues_inserted}")
    if samples:
        print("\nsample splits:")
        for orig, pieces in samples:
            print(f"  {orig!r}")
            for p in pieces:
                print(f"      → {p!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
