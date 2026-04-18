from __future__ import annotations

import hashlib
import os
from pathlib import Path
import runpy
import socket
import sys
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.deps import get_store
from backend.main import app
from src.data_agents.contracts import Evidence, ReleasedObject
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

TIMESTAMP = datetime(2026, 4, 1, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[3]
MIROFLOW_AGENT_ROOT = REPO_ROOT / "apps" / "miroflow-agent"
ALEMBIC_INI = MIROFLOW_AGENT_ROOT / "alembic.ini"
REAL_XLSX_PATH = REPO_ROOT / "docs" / "专辑项目导出1768807339.xlsx"
MERGED_PROFESSOR_JSONL = (
    REPO_ROOT / "logs" / "data_agents" / "professor" / "enriched_v3_merged.jsonl"
)
TEST_SEED_ID = "qimingpian-shenzhen-admin-console"
DATABASE_URL_SKIP_REASON = (
    "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping Postgres integration tests"
)
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"


def _evidence() -> Evidence:
    return Evidence(
        source_type="official_site",
        source_url="https://www.sustech.edu.cn",
        fetched_at=TIMESTAMP,
        snippet="Test evidence.",
    )


def _released_object(
    id: str,
    object_type: str = "professor",
    display_name: str = "Test",
    quality_status: str = "ready",
) -> ReleasedObject:
    return ReleasedObject(
        id=id,
        object_type=object_type,
        display_name=display_name,
        core_facts={"name": display_name},
        summary_fields={"profile_summary": "A test record."},
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
        quality_status=quality_status,
    )


def _raw_database_url() -> str:
    # Prefer DATABASE_URL_TEST (miroflow_test_mock). See
    # docs/plans/2026-04-18-002-real-data-e2e-and-db-separation.md §4.
    database_url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip(DATABASE_URL_SKIP_REASON)
    if "miroflow_real" in database_url:
        pytest.fail(
            f"Refusing to run tests against a real-data database: {database_url!r}. "
            "Set DATABASE_URL_TEST to a dedicated test database."
        )
    return database_url


def _psycopg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _ensure_socket_api_available() -> None:
    try:
        sock = socket.socket()
    except PermissionError:
        pytest.skip(NETWORK_SKIP_REASON)
    else:
        sock.close()


def _load_alembic() -> tuple[Any, type[Any]]:
    try:
        from alembic import command as alembic_command
        from alembic.config import Config
    except ImportError as exc:
        pytest.skip(f"Alembic not importable in this environment: {exc}")
    return alembic_command, Config


def _alembic_config() -> Any:
    _, Config = _load_alembic()
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIROFLOW_AGENT_ROOT / "alembic"))
    return config


def _xlsx_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_postgres_dependencies() -> tuple[Any, Any, Any, Any]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
        from src.data_agents.company.canonical_import import (
            import_company_xlsx_to_postgres,
        )
        from src.data_agents.storage.postgres import seed_loader
    except ImportError as exc:
        pytest.skip(f"Postgres dependencies not importable in this environment: {exc}")
    return psycopg, Jsonb, import_company_xlsx_to_postgres, seed_loader


def _ensure_seed_registry(conn: Any, *, seed_id: str, xlsx_path: Path) -> None:
    _, Jsonb, _, _ = _load_postgres_dependencies()
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
        ON CONFLICT (seed_id) DO UPDATE
           SET source_uri = EXCLUDED.source_uri,
               updated_at = now()
        """,
        (
            seed_id,
            "company_xlsx",
            "admin-console",
            f"file://{xlsx_path}",
            100,
            "manual",
            "active",
            Jsonb({"source": "admin-console-tests"}),
        ),
    )


def _batch_exists(conn: Any, *, seed_id: str, file_hash: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM import_batch
        WHERE seed_id = %s
          AND file_content_hash = %s
        LIMIT 1
        """,
        (seed_id, file_hash),
    ).fetchone()
    return row is not None


def _run_script_entrypoint(
    script_path: Path,
    *args: str,
    env_overrides: dict[str, str] | None = None,
) -> None:
    env_overrides = env_overrides or {}
    previous_env = {key: os.environ.get(key) for key in env_overrides}
    previous_argv = sys.argv[:]
    added_sys_path = False

    if str(MIROFLOW_AGENT_ROOT) not in sys.path:
        sys.path.insert(0, str(MIROFLOW_AGENT_ROOT))
        added_sys_path = True

    try:
        os.environ.update(env_overrides)
        sys.argv = [str(script_path), *args]
        try:
            runpy.run_path(str(script_path), run_name="__main__")
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
            if exit_code != 0:
                raise AssertionError(
                    f"{script_path.name} exited with status {exit_code}"
                ) from exc
    finally:
        sys.argv = previous_argv
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if added_sys_path:
            sys.path.remove(str(MIROFLOW_AGENT_ROOT))


def _clear_pg_pool_cache() -> None:
    try:
        from backend.deps import get_pg_pool
    except ImportError:
        return

    if get_pg_pool.cache_info().currsize:
        get_pg_pool().close()
        get_pg_pool.cache_clear()


def _promote_candidate_links_for_testing(pg_dsn: str) -> None:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(pg_dsn) as conn:
        conn.execute(
            """
            WITH ranked_candidates AS (
                SELECT
                    ppl.link_id,
                    row_number() OVER (
                        PARTITION BY ppl.professor_id
                        ORDER BY
                            p.citation_count DESC NULLS LAST,
                            p.year DESC NULLS LAST,
                            ppl.created_at ASC,
                            ppl.link_id ASC
                    ) AS rank_in_professor
                FROM professor_paper_link ppl
                JOIN paper p ON p.paper_id = ppl.paper_id
                WHERE ppl.link_status = 'candidate'
            )
            UPDATE professor_paper_link ppl
               SET link_status = 'verified',
                   verified_by = 'rule_auto',
                   verified_at = now(),
                   updated_at = now(),
                   match_reason = 'Promoted during admin-console test seeding to exercise verified-paper API flows.'
              FROM ranked_candidates rc
             WHERE rc.link_id = ppl.link_id
               AND rc.rank_in_professor = 1
            """
        )
        conn.commit()


@pytest.fixture()
def store(tmp_path) -> SqliteReleasedObjectStore:
    return SqliteReleasedObjectStore(tmp_path / "test.db")


@pytest.fixture()
def populated_store(store: SqliteReleasedObjectStore) -> SqliteReleasedObjectStore:
    professors = [
        _released_object("PROF-1", "professor", "靳玉乐", "ready"),
        _released_object("PROF-2", "professor", "李明", "ready"),
        _released_object("PROF-3", "professor", "王芳", "needs_review"),
    ]
    companies = [
        _released_object("COMP-1", "company", "深圳科创有限公司", "ready"),
    ]
    store.upsert_released_objects(professors + companies)
    return store


@pytest.fixture()
def client(populated_store: SqliteReleasedObjectStore) -> TestClient:
    app.dependency_overrides[get_store] = lambda: populated_store
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def postgres_data_ready() -> str:
    _ensure_socket_api_available()
    database_url = _raw_database_url()
    pg_dsn = _psycopg_dsn(database_url)
    alembic_command, _ = _load_alembic()
    psycopg, _, import_company_xlsx_to_postgres, seed_loader = (
        _load_postgres_dependencies()
    )
    config = _alembic_config()

    alembic_command.upgrade(config, "head")
    try:
        seed_loader.load_all(pg_dsn)
        with psycopg.connect(pg_dsn) as conn:
            _ensure_seed_registry(conn, seed_id=TEST_SEED_ID, xlsx_path=REAL_XLSX_PATH)
            conn.commit()

            file_hash = _xlsx_hash(REAL_XLSX_PATH)
            if not _batch_exists(conn, seed_id=TEST_SEED_ID, file_hash=file_hash):
                conn.commit()
                import_company_xlsx_to_postgres(
                    REAL_XLSX_PATH,
                    dsn=pg_dsn,
                    seed_id=TEST_SEED_ID,
                )

        yield pg_dsn
    finally:
        _clear_pg_pool_cache()
        alembic_command.downgrade(config, "base")


@pytest.fixture(scope="session")
def professor_data_ready(postgres_data_ready: str) -> str:
    script_env = {"DATABASE_URL": postgres_data_ready, "ALLOW_MOCK_BACKFILL": "1"}

    _run_script_entrypoint(
        MIROFLOW_AGENT_ROOT / "scripts" / "run_real_e2e_professor_backfill.py",
        "--source",
        str(MERGED_PROFESSOR_JSONL),
        "--limit",
        "10",
        env_overrides=script_env,
    )
    _run_script_entrypoint(
        MIROFLOW_AGENT_ROOT / "scripts" / "run_real_e2e_paper_staging_backfill.py",
        "--limit",
        "500",
        env_overrides=script_env,
    )
    _promote_candidate_links_for_testing(postgres_data_ready)

    _clear_pg_pool_cache()
    return postgres_data_ready


@pytest.fixture()
def postgres_client(postgres_data_ready: str) -> TestClient:
    del postgres_data_ready
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def professor_postgres_client(professor_data_ready: str) -> TestClient:
    del professor_data_ready
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
