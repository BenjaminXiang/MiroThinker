"""Measure per-row validator cost of the canonical_v2 build path on a DB copy.

Read/measure-only helper for `reduce-rebuild-validation-cost` step 1. It never
writes to the tables it measures: each validator function is mounted on a
scratch table that only carries the columns the function reads from NEW
(`release_id`, `decision_id`, `assertion_id`), so the measured work is exactly
the function body plus PostgreSQL's deferred-event dispatch.

The live serving database is never a target: pass the copy created with
`CREATE DATABASE <copy> TEMPLATE miroflow_candidate_v2_20260913_r1`.

Usage:
    uv run python measure_trigger_commit.py <dbname> --rows 300 --label before
    uv run python measure_trigger_commit.py <dbname> --rows 3000 --label after

Output: one JSON document per family on stdout (and a summary table on stderr).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import psycopg

SCRATCH_SCHEMA = "measure_trigger_commit"

FAMILIES: tuple[dict[str, Any], ...] = (
    {
        "name": "field_assertion_human_review",
        "scratch_table": "canonical_decision_assertion",
        "function": "knowledge.validate_field_human_review_binding",
        "trigger": "trg_validate_field_human_review_assertion_binding",
        "timing": "AFTER_INSERT_DEFERRED",
        "columns": ("release_id", "decision_id"),
        "source_table": "knowledge.canonical_decision",
        "source_columns": ("release_id", "decision_id"),
    },
    {
        "name": "field_decision_human_review",
        "scratch_table": "canonical_decision",
        "function": "knowledge.validate_field_human_review_binding",
        "trigger": "trg_validate_field_human_review_binding",
        "timing": "AFTER_INSERT_DEFERRED",
        "columns": ("release_id", "decision_id"),
        "source_table": "knowledge.canonical_decision",
        "source_columns": ("release_id", "decision_id"),
    },
    {
        "name": "relationship_assertion_human_review",
        "scratch_table": "relationship_decision_assertion",
        "function": "knowledge.validate_relationship_human_review_binding",
        "trigger": "trg_validate_relationship_human_review_assertion_binding",
        "timing": "AFTER_INSERT_DEFERRED",
        "columns": ("release_id", "decision_id"),
        "source_table": "knowledge.canonical_decision",
        "source_columns": ("release_id", "decision_id"),
    },
    {
        "name": "identity_assertion_human_review",
        "scratch_table": "identity_decision_assertion",
        "function": "knowledge.validate_identity_human_review_binding",
        "trigger": "trg_validate_identity_human_review_assertion_binding",
        "timing": "AFTER_INSERT_DEFERRED",
        "columns": ("release_id", "decision_id"),
        "source_table": "knowledge.identity_decision",
        "source_columns": ("release_id", "decision_id"),
    },
    {
        "name": "field_assertion_temporal",
        "scratch_table": "canonical_decision_assertion",
        "function": "knowledge.validate_field_temporal_binding",
        "trigger": "trg_validate_field_assertion_temporal_binding",
        "timing": "AFTER_INSERT_DEFERRED",
        "columns": ("release_id", "decision_id"),
        "source_table": "knowledge.canonical_decision_assertion",
        "source_columns": ("release_id", "decision_id"),
    },
    {
        "name": "identity_decision_resolution_release",
        "scratch_table": "identity_decision",
        "function": "knowledge.validate_identity_resolution_release",
        "trigger": "trg_validate_identity_resolution_release",
        "timing": "AFTER_INSERT_DEFERRED",
        "columns": ("release_id", "decision_id"),
        "source_table": "knowledge.identity_decision",
        "source_columns": ("release_id", "decision_id"),
    },
    {
        "name": "domain_inclusion_assertion_owner",
        "scratch_table": "domain_inclusion_decision_assertion",
        "function": "knowledge.validate_domain_inclusion_assertion_owner",
        "trigger": "trg_validate_domain_inclusion_assertion_owner",
        "timing": "BEFORE_INSERT_ROW",
        "columns": ("release_id", "decision_id", "assertion_id"),
        "source_table": "knowledge.domain_inclusion_decision",
        "source_columns": (
            "release_id",
            "decision_id",
            "(SELECT min(assertion_id) FROM "
            "knowledge.domain_inclusion_decision_assertion a "
            "WHERE a.release_id = d.release_id AND a.decision_id = d.decision_id)",
        ),
    },
)

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS {trigger} ON {scratch_schema}.{table}
"""

CREATE_TRIGGER_DEFERRED = """
CREATE CONSTRAINT TRIGGER {trigger} AFTER INSERT ON {scratch_schema}.{table}
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION {function}()
"""

CREATE_TRIGGER_ROW = """
CREATE TRIGGER {trigger} BEFORE INSERT ON {scratch_schema}.{table}
FOR EACH ROW EXECUTE FUNCTION {function}()
"""


def _scratch_ddl(family: dict[str, Any]) -> str:
    table = family["scratch_table"]
    columns = ", ".join(f"{column} text NOT NULL" for column in family["columns"])
    return (
        f"DROP TABLE IF EXISTS {SCRATCH_SCHEMA}.{table} CASCADE; "
        f"CREATE TABLE {SCRATCH_SCHEMA}.{table} ({columns})"
    )


def _source_choice(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    """Pick a real release / decision / assertion triple from the build tables."""
    release_id, decision_id = conn.execute(
        "SELECT release_id, min(decision_id) FROM knowledge.canonical_decision "
        "WHERE method <> 'human_review' GROUP BY release_id "
        "ORDER BY count(*) DESC LIMIT 1"
    ).fetchone()
    assertion_id = conn.execute(
        "SELECT min(assertion_id) FROM knowledge.canonical_decision_assertion "
        "WHERE release_id = %s AND decision_id = %s",
        (release_id, decision_id),
    ).fetchone()[0]
    return {
        "release_id": release_id,
        "decision_id": decision_id,
        "assertion_id": assertion_id,
    }


def measure(
    conn: psycopg.Connection[Any],
    family: dict[str, Any],
    rows: int,
    source: dict[str, Any],
) -> dict[str, Any]:
    table = family["scratch_table"]
    with conn.cursor() as cur:
        cur.execute(_scratch_ddl(family))
        cur.execute(
            DROP_TRIGGER.format(
                trigger=family["trigger"], scratch_schema=SCRATCH_SCHEMA, table=table
            )
        )
        mount = (
            CREATE_TRIGGER_DEFERRED
            if family["timing"] == "AFTER_INSERT_DEFERRED"
            else CREATE_TRIGGER_ROW
        )
        cur.execute(
            mount.format(
                trigger=family["trigger"],
                scratch_schema=SCRATCH_SCHEMA,
                table=table,
                function=family["function"],
            )
        )
    conn.commit()

    select_list = ", ".join(family["source_columns"])
    alias = "d" if family["source_table"].endswith("domain_inclusion_decision") else ""
    insert_sql = (
        f"INSERT INTO {SCRATCH_SCHEMA}.{table} ({', '.join(family['columns'])}) "
        f"SELECT {select_list} FROM {family['source_table']} {alias}".rstrip()
        + " WHERE release_id = %s LIMIT %s"
    )

    insert_started = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(insert_sql, (source["release_id"], rows))
    insert_seconds = time.perf_counter() - insert_started

    commit_started = time.perf_counter()
    conn.commit()
    commit_seconds = time.perf_counter() - commit_started

    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {SCRATCH_SCHEMA}.{table}")
        inserted = cur.fetchone()[0]
        cur.execute(
            DROP_TRIGGER.format(
                trigger=family["trigger"], scratch_schema=SCRATCH_SCHEMA, table=table
            )
        )
    conn.commit()

    return {
        "family": family["name"],
        "scratch_table": table,
        "function": family["function"],
        "timing": family["timing"],
        "rows": inserted,
        "insert_seconds": round(insert_seconds, 4),
        "commit_seconds": round(commit_seconds, 4),
        "us_per_row_commit": (
            round(commit_seconds / inserted * 1e6, 2) if inserted else None
        ),
        "release_id": source["release_id"],
        "decision_id": source["decision_id"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("--port", default="55458")
    parser.add_argument("--rows", type=int, default=300)
    parser.add_argument("--label", default="unlabelled")
    parser.add_argument("--only", default=None, help="substring filter on family name")
    args = parser.parse_args()

    dsn = f"postgresql://miroflow@127.0.0.1:{args.port}/{args.database}"
    results = []
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA IF NOT EXISTS {SCRATCH_SCHEMA}")
    with psycopg.connect(dsn) as conn:
        source = _source_choice(conn)
        conn.rollback()
        for family in FAMILIES:
            if args.only and args.only not in family["name"]:
                continue
            result = measure(conn, family, args.rows, source)
            result["label"] = args.label
            result["database"] = args.database
            results.append(result)
            print(json.dumps(result), flush=True)
    for result in results:
        print(
            f"{result['label']:>7s} {result['family']:<40s} rows={result['rows']:>6d} "
            f"insert={result['insert_seconds']:>8.3f}s "
            f"commit={result['commit_seconds']:>9.3f}s "
            f"us/row={result['us_per_row_commit']}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
