from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.types.json import Jsonb


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "alembic.ini"
NOW = datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 4, 18, 1, 0, tzinfo=timezone.utc)
SOURCE_LAYER_TABLES = {
    "seed_registry",
    "import_batch",
    "source_row_lineage",
    "source_page",
    "pipeline_run",
}


def _alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(APP_ROOT / "alembic"))
    return config


def _scalar(conn: psycopg.Connection, query: str, params: tuple[object, ...] = ()) -> object:
    return conn.execute(query, params).fetchone()[0]


def _table_names(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        """
    ).fetchall()
    return {row[0] for row in rows}


def _seed_registry_columns(conn: psycopg.Connection) -> dict[str, tuple[str, str, str, str | None]]:
    rows = conn.execute(
        """
        SELECT column_name, data_type, udt_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'seed_registry'
        """
    ).fetchall()
    return {
        row[0]: (row[1], row[2], row[3], row[4])
        for row in rows
    }


def _insert_seed(
    conn: psycopg.Connection,
    *,
    seed_id: str = "seed-001",
    seed_kind: str = "company_xlsx",
    scope_key: str = "company:acme",
    source_uri: str = "/tmp/acme.xlsx",
    priority: int = 100,
    refresh_policy: str = "manual",
    status: str = "active",
) -> str:
    conn.execute(
        """
        INSERT INTO seed_registry (
            seed_id,
            seed_kind,
            scope_key,
            source_uri,
            priority,
            refresh_policy,
            status,
            config
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            seed_id,
            seed_kind,
            scope_key,
            source_uri,
            priority,
            refresh_policy,
            status,
            Jsonb({"source": "test"}),
        ),
    )
    return seed_id


def _insert_import_batch(
    conn: psycopg.Connection,
    *,
    seed_id: str,
    file_content_hash: str = "hash-001",
    run_status: str = "running",
) -> object:
    return _scalar(
        conn,
        """
        INSERT INTO import_batch (
            seed_id,
            source_file,
            file_content_hash,
            started_at,
            run_status,
            error_summary
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING batch_id
        """,
        (
            seed_id,
            "/tmp/import.xlsx",
            file_content_hash,
            NOW,
            run_status,
            Jsonb({}),
        ),
    )


def _insert_lineage(
    conn: psycopg.Connection,
    *,
    batch_id: object,
    source_row_number: int = 1,
    resolution_status: str = "matched",
) -> object:
    return _scalar(
        conn,
        """
        INSERT INTO source_row_lineage (
            batch_id,
            source_row_number,
            target_entity_type,
            target_entity_id,
            resolution_status,
            resolution_reason,
            raw_row_jsonb
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING lineage_id
        """,
        (
            batch_id,
            source_row_number,
            "company",
            "COMP-001",
            resolution_status,
            "matched in test",
            Jsonb({"row": source_row_number}),
        ),
    )


def _insert_pipeline_run(
    conn: psycopg.Connection,
    *,
    run_kind: str = "import_xlsx",
    status: str = "running",
    seed_id: str | None = None,
    parent_run_id: object | None = None,
) -> object:
    return _scalar(
        conn,
        """
        INSERT INTO pipeline_run (
            run_kind,
            run_scope,
            seed_id,
            parent_run_id,
            started_at,
            finished_at,
            status,
            error_summary,
            triggered_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING run_id
        """,
        (
            run_kind,
            Jsonb({"seed_id": seed_id} if seed_id else {"scope": "global"}),
            seed_id,
            parent_run_id,
            NOW,
            LATER,
            status,
            Jsonb({}),
            "manual",
        ),
    )


def _insert_source_page(
    conn: psycopg.Connection,
    *,
    url: str = "https://example.com/profile",
    page_role: str = "official_profile",
    owner_scope_kind: str | None = "company",
    owner_scope_ref: str | None = "COMP-001",
    fetch_run_id: object | None = None,
) -> object:
    return _scalar(
        conn,
        """
        INSERT INTO source_page (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            fetched_at,
            http_status,
            content_hash,
            title,
            clean_text_path,
            is_official_source,
            fetch_run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING page_id
        """,
        (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            NOW,
            200,
            "content-hash",
            "Example",
            "/tmp/page.txt",
            True,
            fetch_run_id,
        ),
    )


def _assert_db_error(
    conn: psycopg.Connection,
    exc_type: type[BaseException],
    query: str,
    params: tuple[object, ...],
) -> None:
    with pytest.raises(exc_type):
        with conn.transaction():
            conn.execute(query, params)


def test_pgcrypto_extension_installed(pg_conn):
    count = _scalar(
        pg_conn,
        """
        SELECT count(*)
        FROM pg_extension
        WHERE extname = 'pgcrypto'
        """,
    )
    assert count == 1


def test_all_source_layer_tables_exist(pg_conn):
    assert SOURCE_LAYER_TABLES.issubset(_table_names(pg_conn))


def test_seed_registry_columns(pg_conn):
    columns = _seed_registry_columns(pg_conn)

    assert columns["seed_id"][0] == "text"
    assert columns["priority"][0] == "integer"
    assert columns["priority"][3] is not None
    assert "100" in columns["priority"][3]
    assert columns["created_at"][0] == "timestamp with time zone"
    assert columns["config"][1] == "jsonb"

    constraint_types = {
        row[0]
        for row in pg_conn.execute(
            """
            SELECT tc.constraint_type
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.table_name = 'seed_registry'
              AND kcu.column_name = 'seed_id'
            """
        ).fetchall()
    }
    assert "PRIMARY KEY" in constraint_types


def test_source_page_generated_url_host(pg_conn):
    _insert_source_page(
        pg_conn,
        url="https://www.SusTech.edu.cn/zh/faculty/X",
        owner_scope_kind="institution",
        owner_scope_ref="SUSTech",
    )

    url_host = _scalar(
        pg_conn,
        "SELECT url_host FROM source_page WHERE url = %s",
        ("https://www.SusTech.edu.cn/zh/faculty/X",),
    )
    assert url_host == "www.sustech.edu.cn"


def test_seed_registry_rejects_invalid_seed_kind(pg_conn):
    _assert_db_error(
        pg_conn,
        psycopg.errors.CheckViolation,
        """
        INSERT INTO seed_registry (
            seed_id,
            seed_kind,
            scope_key,
            source_uri,
            refresh_policy,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            "seed-invalid-kind",
            "bogus_kind",
            "scope:bogus",
            "/tmp/bogus.csv",
            "manual",
            "active",
        ),
    )


def test_seed_registry_rejects_invalid_refresh_policy(pg_conn):
    _assert_db_error(
        pg_conn,
        psycopg.errors.CheckViolation,
        """
        INSERT INTO seed_registry (
            seed_id,
            seed_kind,
            scope_key,
            source_uri,
            refresh_policy,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            "seed-invalid-refresh",
            "company_xlsx",
            "scope:refresh",
            "/tmp/bogus.csv",
            "yearly",
            "active",
        ),
    )


def test_seed_registry_rejects_invalid_status(pg_conn):
    _assert_db_error(
        pg_conn,
        psycopg.errors.CheckViolation,
        """
        INSERT INTO seed_registry (
            seed_id,
            seed_kind,
            scope_key,
            source_uri,
            refresh_policy,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            "seed-invalid-status",
            "company_xlsx",
            "scope:status",
            "/tmp/bogus.csv",
            "manual",
            "retired",
        ),
    )


def test_seed_registry_unique_scope(pg_conn):
    _insert_seed(
        pg_conn,
        seed_id="seed-scope-1",
        scope_key="scope:dup",
    )

    _assert_db_error(
        pg_conn,
        psycopg.errors.UniqueViolation,
        """
        INSERT INTO seed_registry (
            seed_id,
            seed_kind,
            scope_key,
            source_uri,
            refresh_policy,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            "seed-scope-2",
            "company_xlsx",
            "scope:dup",
            "/tmp/another.xlsx",
            "manual",
            "active",
        ),
    )


def test_import_batch_fk_to_seed(pg_conn):
    _assert_db_error(
        pg_conn,
        psycopg.errors.ForeignKeyViolation,
        """
        INSERT INTO import_batch (
            seed_id,
            source_file,
            file_content_hash,
            started_at,
            run_status
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            "missing-seed",
            "/tmp/import.xlsx",
            "hash-fk",
            NOW,
            "running",
        ),
    )


def test_import_batch_unique_dedup(pg_conn):
    seed_id = _insert_seed(pg_conn, seed_id="seed-dedup")
    _insert_import_batch(
        pg_conn,
        seed_id=seed_id,
        file_content_hash="same-hash",
    )

    _assert_db_error(
        pg_conn,
        psycopg.errors.UniqueViolation,
        """
        INSERT INTO import_batch (
            seed_id,
            source_file,
            file_content_hash,
            started_at,
            run_status
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            seed_id,
            "/tmp/import-2.xlsx",
            "same-hash",
            LATER,
            "running",
        ),
    )


def test_import_batch_rejects_invalid_run_status(pg_conn):
    seed_id = _insert_seed(pg_conn, seed_id="seed-batch-status")

    _assert_db_error(
        pg_conn,
        psycopg.errors.CheckViolation,
        """
        INSERT INTO import_batch (
            seed_id,
            source_file,
            file_content_hash,
            started_at,
            run_status
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            seed_id,
            "/tmp/import.xlsx",
            "hash-status",
            NOW,
            "queued",
        ),
    )


def test_source_row_lineage_cascade_delete(pg_conn):
    seed_id = _insert_seed(pg_conn, seed_id="seed-lineage-cascade")
    batch_id = _insert_import_batch(pg_conn, seed_id=seed_id)
    _insert_lineage(pg_conn, batch_id=batch_id)

    pg_conn.execute("DELETE FROM import_batch WHERE batch_id = %s", (batch_id,))

    remaining = _scalar(
        pg_conn,
        "SELECT count(*) FROM source_row_lineage WHERE batch_id = %s",
        (batch_id,),
    )
    assert remaining == 0


def test_source_row_lineage_rejects_invalid_resolution_status(pg_conn):
    seed_id = _insert_seed(pg_conn, seed_id="seed-lineage-status")
    batch_id = _insert_import_batch(pg_conn, seed_id=seed_id)

    _assert_db_error(
        pg_conn,
        psycopg.errors.CheckViolation,
        """
        INSERT INTO source_row_lineage (
            batch_id,
            source_row_number,
            target_entity_type,
            target_entity_id,
            resolution_status,
            raw_row_jsonb
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            batch_id,
            1,
            "company",
            "COMP-001",
            "unknown_status",
            Jsonb({"row": 1}),
        ),
    )


def test_source_page_rejects_invalid_page_role(pg_conn):
    _assert_db_error(
        pg_conn,
        psycopg.errors.CheckViolation,
        """
        INSERT INTO source_page (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            fetched_at
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            "https://example.com/invalid-role",
            "landing_page",
            "company",
            "COMP-001",
            NOW,
        ),
    )


def test_source_page_rejects_invalid_owner_scope_kind(pg_conn):
    _assert_db_error(
        pg_conn,
        psycopg.errors.CheckViolation,
        """
        INSERT INTO source_page (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            fetched_at
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            "https://example.com/invalid-owner",
            "official_profile",
            "faculty",
            "COMP-001",
            NOW,
        ),
    )


def test_source_page_allows_null_owner_scope_kind(pg_conn):
    page_id = _insert_source_page(
        pg_conn,
        url="https://example.com/no-owner",
        owner_scope_kind=None,
        owner_scope_ref=None,
    )

    stored_value = _scalar(
        pg_conn,
        "SELECT owner_scope_kind FROM source_page WHERE page_id = %s",
        (page_id,),
    )
    assert stored_value is None


def test_source_page_unique_url(pg_conn):
    _insert_source_page(pg_conn, url="https://example.com/duplicate")

    _assert_db_error(
        pg_conn,
        psycopg.errors.UniqueViolation,
        """
        INSERT INTO source_page (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            fetched_at
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            "https://example.com/duplicate",
            "official_profile",
            "company",
            "COMP-001",
            NOW,
        ),
    )


def test_pipeline_run_rejects_invalid_run_kind(pg_conn):
    _assert_db_error(
        pg_conn,
        psycopg.errors.CheckViolation,
        """
        INSERT INTO pipeline_run (
            run_kind,
            run_scope,
            started_at,
            status
        )
        VALUES (%s, %s, %s, %s)
        """,
        (
            "backfill_everything",
            Jsonb({"scope": "all"}),
            NOW,
            "running",
        ),
    )


def test_pipeline_run_rejects_invalid_status(pg_conn):
    _assert_db_error(
        pg_conn,
        psycopg.errors.CheckViolation,
        """
        INSERT INTO pipeline_run (
            run_kind,
            run_scope,
            started_at,
            status
        )
        VALUES (%s, %s, %s, %s)
        """,
        (
            "import_xlsx",
            Jsonb({"scope": "all"}),
            NOW,
            "queued",
        ),
    )


def test_pipeline_run_self_fk_parent(pg_conn):
    parent_run_id = _insert_pipeline_run(pg_conn, run_kind="import_xlsx", status="running")
    child_run_id = _insert_pipeline_run(
        pg_conn,
        run_kind="projection_build",
        status="running",
        parent_run_id=parent_run_id,
    )

    pg_conn.execute("DELETE FROM pipeline_run WHERE run_id = %s", (parent_run_id,))

    remaining_parent = _scalar(
        pg_conn,
        "SELECT parent_run_id FROM pipeline_run WHERE run_id = %s",
        (child_run_id,),
    )
    assert remaining_parent is None


def test_source_page_fetch_run_fk_set_null(pg_conn):
    run_id = _insert_pipeline_run(pg_conn, run_kind="roster_crawl", status="running")
    page_id = _insert_source_page(
        pg_conn,
        url="https://example.com/fetch-run",
        fetch_run_id=run_id,
    )

    pg_conn.execute("DELETE FROM pipeline_run WHERE run_id = %s", (run_id,))

    fetch_run_id = _scalar(
        pg_conn,
        "SELECT fetch_run_id FROM source_page WHERE page_id = %s",
        (page_id,),
    )
    assert fetch_run_id is None


def test_full_happy_path_insert(pg_conn):
    seed_id = _insert_seed(pg_conn, seed_id="seed-happy", scope_key="scope:happy")
    batch_id = _insert_import_batch(
        pg_conn,
        seed_id=seed_id,
        file_content_hash="hash-happy",
        run_status="succeeded",
    )
    lineage_id = _insert_lineage(
        pg_conn,
        batch_id=batch_id,
        source_row_number=7,
        resolution_status="created",
    )
    run_id = _insert_pipeline_run(
        pg_conn,
        run_kind="import_xlsx",
        status="succeeded",
        seed_id=seed_id,
    )
    page_id = _insert_source_page(
        pg_conn,
        url="https://example.com/happy-path",
        page_role="company_official_site",
        owner_scope_kind="company",
        owner_scope_ref="COMP-001",
        fetch_run_id=run_id,
    )

    counts = {
        "seed_registry": _scalar(pg_conn, "SELECT count(*) FROM seed_registry"),
        "import_batch": _scalar(pg_conn, "SELECT count(*) FROM import_batch"),
        "source_row_lineage": _scalar(pg_conn, "SELECT count(*) FROM source_row_lineage"),
        "pipeline_run": _scalar(pg_conn, "SELECT count(*) FROM pipeline_run"),
        "source_page": _scalar(pg_conn, "SELECT count(*) FROM source_page"),
    }
    assert counts == {
        "seed_registry": 1,
        "import_batch": 1,
        "source_row_lineage": 1,
        "pipeline_run": 1,
        "source_page": 1,
    }

    assert _scalar(
        pg_conn,
        "SELECT seed_id FROM import_batch WHERE batch_id = %s",
        (batch_id,),
    ) == seed_id
    assert _scalar(
        pg_conn,
        "SELECT batch_id FROM source_row_lineage WHERE lineage_id = %s",
        (lineage_id,),
    ) == batch_id
    assert _scalar(
        pg_conn,
        "SELECT seed_id FROM pipeline_run WHERE run_id = %s",
        (run_id,),
    ) == seed_id
    assert _scalar(
        pg_conn,
        "SELECT fetch_run_id FROM source_page WHERE page_id = %s",
        (page_id,),
    ) == run_id


def test_upgrade_downgrade_upgrade_cycle(pg_migrated, pg_dsn: str):
    del pg_migrated
    raw_database_url = os.environ.get("DATABASE_URL")
    if raw_database_url:
        os.environ["DATABASE_URL"] = raw_database_url

    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    with psycopg.connect(pg_dsn) as conn:
        assert SOURCE_LAYER_TABLES.issubset(_table_names(conn))
