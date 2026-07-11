"""Stand-alone test for the taxonomy + domain_tier seed loader.

Deliberately isolated from the V002 migration: we build the two target
tables by hand inside the test so this suite can validate the loader
independently of whichever alembic revision is current. Once V002 lands,
`alembic upgrade head` creates the same tables and seed_loader works
unchanged.

Skipped when no database target is configured. The test uses its own schema
`seed_loader_test`, but still requires the shared destructive-target proof before
creating or dropping that schema.
"""

from __future__ import annotations

import os

from alembic.config import Config
import psycopg
import pytest
from psycopg import sql

from src.data_agents.storage.database_target import (
    DatabaseTargetSafetyError,
    DestructiveDatabaseTarget,
    resolve_destructive_database_target,
)
from src.data_agents.storage.postgres import seed_loader
from src.data_agents.storage.postgres.connection import resolve_dsn
from src.data_agents.taxonomy.domain_tier import DOMAIN_TIER_SEEDS
from src.data_agents.taxonomy.seed_data import TAXONOMY_SEEDS


SCHEMA = "seed_loader_test"


def _destructive_target() -> DestructiveDatabaseTarget:
    dedicated_names = (
        "ALEMBIC_DATABASE_URL",
        "ALEMBIC_EXPECTED_DATABASE",
        "ALEMBIC_TARGET_KIND",
    )
    if not any(os.environ.get(name) for name in dedicated_names):
        if os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST"):
            pytest.fail(
                "An explicit destructive database target is required; Generic "
                "DATABASE_URL values cannot select the seed-loader test database."
            )
        pytest.skip("No explicit destructive database target is configured")

    try:
        return resolve_destructive_database_target(Config(), os.environ)
    except DatabaseTargetSafetyError as exc:
        pytest.fail(str(exc))


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    target = _destructive_target()
    dsn = resolve_dsn(target.url)
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT current_database(), "
            "shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone()
        if row is None:
            pytest.fail("Could not read the explicit database target identity")
        target.verify_database_identity(
            actual_database=row[0],
            database_marker=row[1],
        )
    return dsn


def test_pg_dsn_refuses_generic_database_url_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_EXPECTED_DATABASE", raising=False)
    monkeypatch.delenv("ALEMBIC_TARGET_KIND", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://miroflow:secret@example:5432/production_copy",
    )

    with pytest.raises(pytest.fail.Exception, match="explicit|Generic"):
        _destructive_target()


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
        tx_row = cur.fetchone()
        assert tx_row is not None
        (tx_count,) = tx_row
        cur.execute("SELECT count(*) FROM source_domain_tier_registry")
        dt_row = cur.fetchone()
        assert dt_row is not None
        (dt_count,) = dt_row

    assert tx_count == len(TAXONOMY_SEEDS)
    assert dt_count == len(DOMAIN_TIER_SEEDS)


def test_seed_loader_is_idempotent(schema_dsn: str):
    """Running twice must not change counts and must not raise FK errors."""
    seed_loader.load_all(schema_dsn)
    seed_loader.load_all(schema_dsn)  # re-run

    with psycopg.connect(schema_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM taxonomy_vocabulary")
        tx_row = cur.fetchone()
        assert tx_row is not None
        (tx_count,) = tx_row
        cur.execute("SELECT count(*) FROM source_domain_tier_registry")
        dt_row = cur.fetchone()
        assert dt_row is not None
        (dt_count,) = dt_row

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
