"""Contract tests for the destructive Alembic database-target boundary."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
import runpy
from typing import Any

from alembic import context as alembic_context
from alembic.config import Config
import pytest
import sqlalchemy


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_ENV = APP_ROOT / "alembic" / "env.py"
DISPOSABLE_URL = (
    "postgresql+psycopg://miroflow:secret@isolated-lab:5432/"
    "miroflow_s1_disposable_contract"
)
DISPOSABLE_DATABASE = "miroflow_s1_disposable_contract"
DISPOSABLE_MARKER = (
    "miroflow:destructive-target:v1:disposable:"
    "miroflow_s1_disposable_contract"
)


@dataclass
class _AlembicRun:
    engine_urls: list[str] = field(default_factory=list)
    identity_queries: list[str] = field(default_factory=list)
    identity_transaction_rollbacks: int = 0
    migrations_run: int = 0


class _ScalarResult:
    def __init__(self, value: str | None) -> None:
        self._value = value

    def scalar_one(self) -> str | None:
        return self._value


class _Connection:
    def __init__(
        self,
        run: _AlembicRun,
        current_database: str,
        database_marker: str | None,
    ) -> None:
        self._run = run
        self._current_database = current_database
        self._database_marker = database_marker

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def exec_driver_sql(self, statement: str) -> _ScalarResult:
        self._run.identity_queries.append(statement)
        if statement == "SELECT current_database()":
            return _ScalarResult(self._current_database)
        return _ScalarResult(self._database_marker)

    def rollback(self) -> None:
        self._run.identity_transaction_rollbacks += 1


class _Connectable:
    def __init__(
        self,
        run: _AlembicRun,
        current_database: str,
        database_marker: str | None,
    ) -> None:
        self._run = run
        self._current_database = current_database
        self._database_marker = database_marker

    def connect(self) -> _Connection:
        return _Connection(
            self._run,
            self._current_database,
            self._database_marker,
        )


def _run_alembic_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    explicit_url: str | None,
    expected_database: str | None,
    target_kind: str | None,
    environment: dict[str, str] | None = None,
    connected_database: str = DISPOSABLE_DATABASE,
    database_marker: str | None = DISPOSABLE_MARKER,
) -> _AlembicRun:
    for name in (
        "ALEMBIC_DATABASE_URL",
        "ALEMBIC_EXPECTED_DATABASE",
        "ALEMBIC_TARGET_KIND",
        "DATABASE_URL",
        "DATABASE_URL_TEST",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in (environment or {}).items():
        monkeypatch.setenv(name, value)

    config = Config()
    if explicit_url is not None:
        config.set_main_option("sqlalchemy.url", explicit_url)
    if expected_database is not None:
        config.set_main_option("miroflow.expected_database", expected_database)
    if target_kind is not None:
        config.set_main_option("miroflow.target_kind", target_kind)

    run = _AlembicRun()

    def _engine_from_config(
        section: dict[str, Any],
        *,
        prefix: str,
        poolclass: type[Any],
    ) -> _Connectable:
        del prefix, poolclass
        run.engine_urls.append(section["sqlalchemy.url"])
        return _Connectable(run, connected_database, database_marker)

    monkeypatch.setattr(alembic_context, "config", config, raising=False)
    monkeypatch.setattr(alembic_context, "is_offline_mode", lambda: False)
    monkeypatch.setattr(alembic_context, "configure", lambda **_kwargs: None)
    monkeypatch.setattr(alembic_context, "begin_transaction", nullcontext)
    monkeypatch.setattr(
        alembic_context,
        "run_migrations",
        lambda: setattr(run, "migrations_run", run.migrations_run + 1),
    )
    monkeypatch.setattr(sqlalchemy, "engine_from_config", _engine_from_config)

    runpy.run_path(str(ALEMBIC_ENV), run_name="__s1_alembic_env_contract__")
    return run


def test_explicit_disposable_target_wins_over_conflicting_generic_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run_alembic_env(
        monkeypatch,
        explicit_url=DISPOSABLE_URL,
        expected_database=DISPOSABLE_DATABASE,
        target_kind="disposable",
        environment={
            "DATABASE_URL": (
                "postgresql+psycopg://miroflow:secret@localhost:15432/miroflow_real"
            ),
            "DATABASE_URL_TEST": (
                "postgresql+psycopg://miroflow:secret@elsewhere:5432/other_test"
            ),
        },
    )

    assert run.engine_urls == [DISPOSABLE_URL]
    assert run.migrations_run == 1


def test_generic_database_url_is_not_an_explicit_destructive_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="explicit"):
        _run_alembic_env(
            monkeypatch,
            explicit_url=None,
            expected_database=None,
            target_kind=None,
            environment={
                "DATABASE_URL": (
                    "postgresql+psycopg://miroflow:secret@localhost:15432/"
                    "miroflow_real"
                )
            },
        )


def test_known_non_disposable_target_is_rejected_before_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="forbidden|non-disposable"):
        _run_alembic_env(
            monkeypatch,
            explicit_url=(
                "postgresql+psycopg://miroflow:secret@localhost:15432/miroflow_real"
            ),
            expected_database="miroflow_real",
            target_kind="disposable",
            environment={
                "DATABASE_URL": (
                    "postgresql+psycopg://miroflow:secret@localhost:15432/"
                    "miroflow_real"
                )
            },
        )


def test_conflicting_explicit_target_sources_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="ambiguous|conflict"):
        _run_alembic_env(
            monkeypatch,
            explicit_url=DISPOSABLE_URL,
            expected_database=DISPOSABLE_DATABASE,
            target_kind="disposable",
            environment={
                "ALEMBIC_DATABASE_URL": (
                    "postgresql+psycopg://miroflow:secret@isolated-lab:5432/"
                    "other_disposable"
                ),
                "ALEMBIC_EXPECTED_DATABASE": "other_disposable",
                "ALEMBIC_TARGET_KIND": "disposable",
                "DATABASE_URL": (
                    "postgresql+psycopg://miroflow:secret@localhost:15432/"
                    "miroflow_real"
                ),
            },
        )


def test_expected_database_must_match_explicit_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="expected|identity"):
        _run_alembic_env(
            monkeypatch,
            explicit_url=DISPOSABLE_URL,
            expected_database="different_disposable",
            target_kind="disposable",
            environment={"DATABASE_URL": DISPOSABLE_URL},
        )


def test_connected_database_identity_must_match_before_migrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="expected|identity"):
        _run_alembic_env(
            monkeypatch,
            explicit_url=DISPOSABLE_URL,
            expected_database=DISPOSABLE_DATABASE,
            target_kind="disposable",
            environment={"DATABASE_URL": DISPOSABLE_URL},
            connected_database="unexpected_database",
        )


@pytest.mark.parametrize(
    "database_marker",
    [
        None,
        (
            "miroflow:destructive-target:v1:isolated-candidate:"
            "miroflow_s1_disposable_contract"
        ),
    ],
)
def test_database_side_target_marker_must_match_before_migrations(
    monkeypatch: pytest.MonkeyPatch,
    database_marker: str | None,
) -> None:
    with pytest.raises(RuntimeError, match="marker|identity"):
        _run_alembic_env(
            monkeypatch,
            explicit_url=DISPOSABLE_URL,
            expected_database=DISPOSABLE_DATABASE,
            target_kind="disposable",
            database_marker=database_marker,
        )


def test_approved_target_identity_is_checked_before_migrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run_alembic_env(
        monkeypatch,
        explicit_url=DISPOSABLE_URL,
        expected_database=DISPOSABLE_DATABASE,
        target_kind="disposable",
    )

    assert run.identity_queries == [
        "SELECT current_database()",
        (
            "SELECT shobj_description(oid, 'pg_database') FROM pg_database "
            "WHERE datname = current_database()"
        ),
    ]
    assert run.identity_transaction_rollbacks == 1
    assert run.migrations_run == 1
