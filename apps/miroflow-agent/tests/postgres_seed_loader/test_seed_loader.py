"""Stand-alone test for the taxonomy + domain_tier seed loader.

Deliberately isolated from the V002 migration: we build the two target
tables by hand inside the test so this suite can validate the loader
independently of whichever alembic revision is current. Once V002 lands,
`alembic upgrade head` creates the same tables and seed_loader works
unchanged.

Skipped when DATABASE_URL is not set. The test uses its own schema
`seed_loader_test` to avoid polluting public tables.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from psycopg import sql

from src.data_agents.storage.postgres import seed_loader
from src.data_agents.storage.postgres.connection import resolve_dsn
from src.data_agents.taxonomy.domain_tier import DOMAIN_TIER_SEEDS
from src.data_agents.taxonomy.seed_data import TAXONOMY_SEEDS


SCHEMA = "seed_loader_test"
_REAL_DB_NAMES = ("miroflow_real",)


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    # Prefer DATABASE_URL_TEST (points at miroflow_test_mock) to keep real data isolated.
    # See docs/plans/2026-04-18-002-real-data-e2e-and-db-separation.md §4.
    dsn = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip(
            "Neither DATABASE_URL_TEST nor DATABASE_URL set; "
            "skipping Postgres seed_loader test"
        )
    if any(name in dsn for name in _REAL_DB_NAMES):
        pytest.fail(
            f"Refusing to run tests against a real-data database: {dsn!r}. "
            "Set DATABASE_URL_TEST to miroflow_test_mock (or similar)."
        )
    return resolve_dsn(dsn)


@pytest.fixture(scope="module")
def test_schema(pg_dsn: str):
    """Create a dedicated schema with the two target tables, drop at teardown."""
    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(SCHEMA))
        )
        cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(SCHEMA)))
        cur.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(SCHEMA)))

        # Minimal DDL mirroring V002's shape for these two tables.
        cur.execute("""
            CREATE TABLE taxonomy_vocabulary (
              code             TEXT PRIMARY KEY,
              namespace        TEXT NOT NULL,
              display_name     TEXT NOT NULL,
              display_name_en  TEXT,
              parent_code      TEXT REFERENCES taxonomy_vocabulary(code) ON DELETE SET NULL,
              description      TEXT,
              status           TEXT NOT NULL DEFAULT 'active',
              created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("""
            CREATE TABLE source_domain_tier_registry (
              domain                TEXT PRIMARY KEY,
              tier                  TEXT NOT NULL CHECK (tier IN ('official','trusted','unknown')),
              tier_reason           TEXT,
              is_official_for_scope TEXT,
              last_reviewed_at      TIMESTAMPTZ,
              created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

    yield SCHEMA

    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(SCHEMA)))


@pytest.fixture
def schema_dsn(pg_dsn: str, test_schema: str) -> str:
    """Return a DSN that sets search_path to the test schema."""
    separator = "&" if "?" in pg_dsn else "?"
    return f"{pg_dsn}{separator}options=-csearch_path%3D{test_schema}"


def test_seed_loader_prerequisite_check(pg_dsn: str):
    """Without the target tables in an empty schema, the loader refuses to run."""
    empty = "seed_loader_empty_probe"
    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(empty))
        )
        cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(empty)))
    try:
        separator = "&" if "?" in pg_dsn else "?"
        scoped = f"{pg_dsn}{separator}options=-csearch_path%3D{empty}"
        with pytest.raises(RuntimeError, match="prerequisite tables missing"):
            seed_loader.load_all(scoped)
    finally:
        with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(empty)))


def test_seed_loader_upserts_all_rows(schema_dsn: str):
    report = seed_loader.load_all(schema_dsn)
    assert report.taxonomy_upserted == len(TAXONOMY_SEEDS)
    assert report.domain_tier_upserted == len(DOMAIN_TIER_SEEDS)

    with psycopg.connect(schema_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM taxonomy_vocabulary")
        (tx_count,) = cur.fetchone()
        cur.execute("SELECT count(*) FROM source_domain_tier_registry")
        (dt_count,) = cur.fetchone()

    assert tx_count == len(TAXONOMY_SEEDS)
    assert dt_count == len(DOMAIN_TIER_SEEDS)


def test_seed_loader_is_idempotent(schema_dsn: str):
    """Running twice must not change counts and must not raise FK errors."""
    seed_loader.load_all(schema_dsn)
    seed_loader.load_all(schema_dsn)  # re-run

    with psycopg.connect(schema_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM taxonomy_vocabulary")
        (tx_count,) = cur.fetchone()
        cur.execute("SELECT count(*) FROM source_domain_tier_registry")
        (dt_count,) = cur.fetchone()

    assert tx_count == len(TAXONOMY_SEEDS)
    assert dt_count == len(DOMAIN_TIER_SEEDS)


def test_taxonomy_parent_fk_intact(schema_dsn: str):
    """Every parent_code referenced by a seed must actually exist in the table."""
    seed_loader.load_all(schema_dsn)
    with psycopg.connect(schema_dsn) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT child.code, child.parent_code
              FROM taxonomy_vocabulary child
              LEFT JOIN taxonomy_vocabulary parent
                ON parent.code = child.parent_code
             WHERE child.parent_code IS NOT NULL
               AND parent.code IS NULL
        """)
        orphans = cur.fetchall()
    assert orphans == [], f"orphaned parent_code references: {orphans}"


def test_domain_tier_values_are_valid(schema_dsn: str):
    """Every seeded tier must match the CHECK constraint."""
    seed_loader.load_all(schema_dsn)
    with psycopg.connect(schema_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT tier FROM source_domain_tier_registry ORDER BY tier"
        )
        tiers = [row[0] for row in cur.fetchall()]
    assert set(tiers).issubset({"official", "trusted", "unknown"})
    # we only seed 'official' and 'trusted' rows (unknown is a default-match)
    assert set(tiers) == {"official", "trusted"}
