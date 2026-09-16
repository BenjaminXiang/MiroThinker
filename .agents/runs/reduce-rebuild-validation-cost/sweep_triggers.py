"""Sibling sweep: enumerate per-row deferred constraint triggers + per-row
validators on the canonical_v2 build path, with row counts and index support.

Read-only: connects to the given DB and only runs catalog/statistics queries.
Usage: uv run python sweep_triggers.py <dbname> [port]
"""

from __future__ import annotations

import json
import sys

import psycopg

DB = sys.argv[1] if len(sys.argv) > 1 else "miroflow_candidate_v2_20260913_r1"
PORT = sys.argv[2] if len(sys.argv) > 2 else "55458"
DSN = f"postgresql://miroflow@127.0.0.1:{PORT}/{DB}"

TRIGGERS_SQL = """
SELECT c.relname AS table_name,
       t.tgname AS trigger_name,
       t.tgdeferrable AS deferrable,
       t.tginitdeferred AS init_deferred,
       (t.tgtype & 1) <> 0 AS row_level,
       (t.tgtype & 2) <> 0 AS is_before,
       (t.tgtype & 4) <> 0 AS is_insert,
       p.proname AS func_name,
       (SELECT count(*) FROM pg_trigger x WHERE x.tgfoid = t.tgfoid AND NOT x.tgisinternal) AS mounts
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_proc p ON p.oid = t.tgfoid
WHERE n.nspname = 'knowledge' AND NOT t.tgisinternal
ORDER BY c.relname, t.tgname
"""

SIZES_SQL = """
SELECT c.relname AS table_name,
       c.reltuples::bigint AS est_rows
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'knowledge' AND c.relkind = 'r'
ORDER BY c.reltuples DESC, c.relname
"""

COUNT_SQL = "SELECT count(*) FROM knowledge.{}"

INDEXES_SQL = """
SELECT tablename, indexname, indexdef
FROM pg_indexes WHERE schemaname = 'knowledge' ORDER BY tablename, indexname
"""


def main() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        triggers = conn.execute(TRIGGERS_SQL).fetchall()
        sizes = {r[0]: r[1] for r in conn.execute(SIZES_SQL).fetchall()}
        counts: dict[str, int] = {}
        deferred_tables = sorted(
            {t[0] for t in triggers if t[2] and t[3] and t[4]}
        )
        for tbl in sorted(set(sizes) | set(deferred_tables)):
            if sizes.get(tbl, 0) <= 0:
                counts[tbl] = 0
                continue
            counts[tbl] = conn.execute(COUNT_SQL.format(tbl)).fetchone()[0]
        indexes = conn.execute(INDEXES_SQL).fetchall()

    out = {
        "database": DB,
        "row_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "triggers": [
            {
                "table": r[0],
                "trigger": r[1],
                "deferrable": r[2],
                "init_deferred": r[3],
                "row_level": r[4],
                "before": r[5],
                "insert": r[6],
                "func": r[7],
                "mounts": r[8],
                "rows": counts.get(r[0], 0),
            }
            for r in triggers
        ],
        "indexes": [{"table": r[0], "index": r[1], "def": r[2]} for r in indexes],
    }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
