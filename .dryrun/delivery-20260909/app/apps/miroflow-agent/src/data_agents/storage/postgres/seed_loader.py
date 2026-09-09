"""Load taxonomy_vocabulary and source_domain_tier_registry from static seeds.

Reads Python seed modules (data_agents/taxonomy/seed_data.py and
domain_tier.py) and upserts the rows into Postgres. Designed to be re-run
safely after every migration (ON CONFLICT DO UPDATE).

Runs standalone CLI:
    uv run python -m src.data_agents.storage.postgres.seed_loader

Or programmatically from a pipeline runner:
    from src.data_agents.storage.postgres import seed_loader
    seed_loader.load_all()

Precondition: V002 migration has created `taxonomy_vocabulary` and
`source_domain_tier_registry` tables. The loader runs a quick existence
check up-front and raises a clear error if they are missing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from psycopg import Connection

from ...taxonomy.domain_tier import DOMAIN_TIER_SEEDS
from ...taxonomy.seed_data import TAXONOMY_SEEDS
from .connection import connect


@dataclass(frozen=True)
class SeedReport:
    taxonomy_upserted: int
    domain_tier_upserted: int


def _ensure_tables(conn: Connection) -> None:
    required = ("taxonomy_vocabulary", "source_domain_tier_registry")
    with conn.cursor() as cur:
        # search_path-aware: find tables in any schema on the current search_path
        # so tests can run in an isolated schema without polluting public.
        cur.execute(
            """
            SELECT c.relname
              FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'r'
               AND n.nspname = ANY(current_schemas(false))
               AND c.relname = ANY(%s)
            """,
            (list(required),),
        )
        present = {row["relname"] for row in cur.fetchall()}
    missing = [t for t in required if t not in present]
    if missing:
        raise RuntimeError(
            f"seed_loader prerequisite tables missing: {missing}. "
            "Run `alembic upgrade head` first."
        )


def _upsert_taxonomy(conn: Connection) -> int:
    rows = [
        (
            s.code,
            s.namespace,
            s.display_name,
            s.display_name_en,
            s.parent_code,
            s.description,
        )
        for s in TAXONOMY_SEEDS
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO taxonomy_vocabulary
                (code, namespace, display_name, display_name_en, parent_code, description, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'active')
            ON CONFLICT (code) DO UPDATE
               SET namespace       = EXCLUDED.namespace,
                   display_name    = EXCLUDED.display_name,
                   display_name_en = EXCLUDED.display_name_en,
                   parent_code     = EXCLUDED.parent_code,
                   description     = EXCLUDED.description,
                   updated_at      = now()
            """,
            rows,
        )
    return len(rows)


def _upsert_domain_tier(conn: Connection) -> int:
    rows = [
        (
            s.domain,
            s.tier,
            s.tier_reason,
            s.is_official_for_scope,
        )
        for s in DOMAIN_TIER_SEEDS
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO source_domain_tier_registry
                (domain, tier, tier_reason, is_official_for_scope, last_reviewed_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (domain) DO UPDATE
               SET tier                  = EXCLUDED.tier,
                   tier_reason           = EXCLUDED.tier_reason,
                   is_official_for_scope = EXCLUDED.is_official_for_scope,
                   last_reviewed_at      = now()
            """,
            rows,
        )
    return len(rows)


def load_all(dsn: str | None = None) -> SeedReport:
    """Upsert all seed rows into Postgres. Idempotent."""
    with connect(dsn) as conn:
        _ensure_tables(conn)
        tx = _upsert_taxonomy(conn)
        dt = _upsert_domain_tier(conn)
        conn.commit()
    return SeedReport(taxonomy_upserted=tx, domain_tier_upserted=dt)


def _main() -> int:
    parser = argparse.ArgumentParser(description="Load taxonomy + domain-tier seeds.")
    parser.add_argument(
        "--dsn",
        help="Postgres DSN (overrides DATABASE_URL env).",
        default=None,
    )
    args = parser.parse_args()

    report = load_all(args.dsn)
    print(f"taxonomy_vocabulary: upserted {report.taxonomy_upserted} rows")
    print(f"source_domain_tier_registry: upserted {report.domain_tier_upserted} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
