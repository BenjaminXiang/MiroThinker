from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa

from src.data_agents.storage.database_target import set_alembic_database_url


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
BASELINE_REVISION = "C2_0001"
VERSION_TABLE = "canonical_v2_alembic_version"
BUSINESS_SCHEMAS = frozenset(
    {
        "landing",
        "knowledge",
        "professor",
        "company",
        "paper",
        "patent",
        "publish",
        "ops",
    }
)
LEGACY_PUBLIC_TABLES = frozenset(
    {
        "professor",
        "company",
        "paper",
        "patent",
        "pipeline_run",
        "source_page",
        "professor_paper",
    }
)


def _migration_config(
    *,
    database_url: str | None = None,
    expected_database: str | None = None,
    target_kind: str | None = None,
    backup_gate_root: str | None = None,
) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    if database_url is not None:
        set_alembic_database_url(config, database_url)
    if expected_database is not None:
        config.set_main_option("miroflow.expected_database", expected_database)
    if target_kind is not None:
        config.set_main_option("miroflow.target_kind", target_kind)
    if backup_gate_root is not None:
        config.set_main_option("miroflow.backup_gate_root", backup_gate_root)
    return config


def _required_integration_environment() -> tuple[str, str, str, str]:
    names = (
        "CANONICAL_V2_TEST_DATABASE_URL",
        "CANONICAL_V2_TEST_EXPECTED_DATABASE",
        "CANONICAL_V2_TEST_TARGET_KIND",
        "CANONICAL_V2_TEST_BACKUP_GATE_ROOT",
    )
    values = tuple(os.environ.get(name) for name in names)
    if not all(values):
        pytest.skip(
            "Canonical V2 baseline integration requires all four explicit "
            "CANONICAL_V2_TEST_* settings"
        )
    return values  # type: ignore[return-value]


def _business_schemas(connection: sa.Connection) -> set[str]:
    rows = connection.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name = ANY(CAST(:schemas AS text[]))"
        ),
        {"schemas": sorted(BUSINESS_SCHEMAS)},
    )
    return {str(row[0]) for row in rows}


def _business_tables(connection: sa.Connection) -> set[tuple[str, str]]:
    rows = connection.execute(
        sa.text(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema = ANY(CAST(:schemas AS text[]))"
        ),
        {"schemas": sorted(BUSINESS_SCHEMAS)},
    )
    return {(str(row[0]), str(row[1])) for row in rows}


def test_canonical_v2_history_has_one_clean_base_not_a_v042_extension() -> None:
    assert ALEMBIC_INI.is_file()
    assert SCRIPT_LOCATION.is_dir()

    scripts = ScriptDirectory.from_config(_migration_config())
    revisions = tuple(scripts.walk_revisions())
    baseline = scripts.get_revision(BASELINE_REVISION)

    assert baseline is not None
    assert baseline.down_revision is None
    assert baseline.branch_labels == {"canonical_v2"}
    assert all("V042" not in revision.path for revision in revisions)
    assert sum(revision.down_revision is None for revision in revisions) == 1


def test_real_disposable_round_trips_empty_namespace_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url, expected_database, target_kind, backup_gate_root = (
        _required_integration_environment()
    )
    assert target_kind == "disposable"

    for name in (
        "ALEMBIC_DATABASE_URL",
        "ALEMBIC_EXPECTED_DATABASE",
        "ALEMBIC_TARGET_KIND",
        "CANONICAL_V2_BACKUP_GATE_ROOT",
        "DATABASE_URL_TEST",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://miroflow:do-not-use@localhost:15432/miroflow_real",
    )
    config = _migration_config(
        database_url=database_url,
        expected_database=expected_database,
        target_kind=target_kind,
        backup_gate_root=backup_gate_root,
    )
    engine = sa.create_engine(database_url)
    current_head = ScriptDirectory.from_config(config).get_current_head()
    assert current_head is not None

    try:
        with engine.connect() as connection:
            actual_database = connection.execute(
                sa.text("SELECT current_database()")
            ).scalar_one()
            assert actual_database == expected_database
            marker = connection.execute(
                sa.text(
                    "SELECT shobj_description(oid, 'pg_database') FROM pg_database "
                    "WHERE datname = current_database()"
                )
            ).scalar_one()
            assert marker == (
                f"miroflow:destructive-target:v1:disposable:{expected_database}"
            )

        command.downgrade(config, "base")
        with engine.connect() as connection:
            assert _business_schemas(connection) == set()

        command.upgrade(config, BASELINE_REVISION)
        with engine.connect() as connection:
            assert _business_schemas(connection) == BUSINESS_SCHEMAS
            assert _business_tables(connection) == set()
            version = connection.execute(
                sa.text(f"SELECT version_num FROM public.{VERSION_TABLE}")
            ).scalar_one()
            assert version == BASELINE_REVISION
            public_tables = {
                str(row[0])
                for row in connection.execute(
                    sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            }
            assert public_tables == {VERSION_TABLE}
            assert public_tables.isdisjoint(LEGACY_PUBLIC_TABLES)

        command.downgrade(config, "base")
        with engine.connect() as connection:
            assert _business_schemas(connection) == set()
            assert _business_tables(connection) == set()

        command.upgrade(config, BASELINE_REVISION)
        with engine.connect() as connection:
            assert _business_schemas(connection) == BUSINESS_SCHEMAS
            assert _business_tables(connection) == set()
            assert (
                connection.execute(
                    sa.text(f"SELECT version_num FROM public.{VERSION_TABLE}")
                ).scalar_one()
                == BASELINE_REVISION
            )
    finally:
        command.upgrade(config, current_head)
        engine.dispose()
