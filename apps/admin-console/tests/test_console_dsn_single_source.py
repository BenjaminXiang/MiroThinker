"""A1/A3 — the console database has exactly one reader and one degradation path.

`DATABASE_URL` (then `DATABASE_URL_TEST`) is *the* console/collection database. `CANONICAL_V2_DATABASE_URL`
names the serving database of the V2 operations surface and is not a substitute: before this contract a
deployment carrying only that name showed a green gate probe and then 500-ed on the first read.

Fixture-driven: no live state directory is read or written, and no database is contacted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from tests.conftest import authorized_client

from backend.deps import resolve_console_dsn
from backend.main import _create_canonical_v2_route_shell
from src.data_agents.canonical_v2.jobs import (
    JobRunStore,
    JobRuntime,
    PostgresProbe,
    jobs_database_path,
)
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore


_PREFIX = "/api/canonical-v2/admin/seeds"


def _clear_console_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATABASE_URL", "DATABASE_URL_TEST", "CANONICAL_V2_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_resolver_prefers_database_url_then_the_test_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_console_env(monkeypatch)
    assert resolve_console_dsn() is None

    monkeypatch.setenv("DATABASE_URL_TEST", "postgresql://test/db")
    assert resolve_console_dsn() == "postgresql://test/db"

    monkeypatch.setenv("DATABASE_URL", "postgresql://runtime/db")
    assert resolve_console_dsn() == "postgresql://runtime/db"


def test_resolver_counts_blank_values_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_console_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "   ")
    monkeypatch.setenv("DATABASE_URL_TEST", "postgresql://test/db")
    assert resolve_console_dsn() == "postgresql://test/db"

    monkeypatch.setenv("DATABASE_URL_TEST", "")
    assert resolve_console_dsn() is None


def test_serving_database_name_is_not_a_console_database(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_console_env(monkeypatch)
    monkeypatch.setenv("CANONICAL_V2_DATABASE_URL", "postgresql://serving/db")
    assert resolve_console_dsn() is None


def test_probe_ignores_the_serving_database_name() -> None:
    probe = PostgresProbe(environ={"CANONICAL_V2_DATABASE_URL": "postgresql://serving/db"})
    assert probe.resolved_dsn() == (None, None)
    assert probe.available() is False

    named = PostgresProbe(environ={"DATABASE_URL": "postgresql://runtime/db"})
    assert named.resolved_dsn() == ("DATABASE_URL", "postgresql://runtime/db")


def _unconfigured_seed_client(tmp_path: Path) -> object:
    scratch = tmp_path / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    settings = scratch / "settings.json"
    settings.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    values = {"CANONICAL_V2_JOBS_DB": str(scratch / "jobs.sqlite3")}
    gate = JobRuntime(
        store=JobRunStore(jobs_database_path(values)),
        settings_store=ManagedSettingsStore(path=settings, environ={}),
        environ={},
        lock_dir=jobs_database_path(values).parent / "locks",
    )
    shell = _create_canonical_v2_route_shell()
    shell.state.canonical_v2_seed_gate = gate
    return authorized_client(shell)


@pytest.mark.parametrize("only_serving_name", [True, False])
def test_a_missing_configuration_is_a_stable_503_never_a_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, only_serving_name: bool
) -> None:
    _clear_console_env(monkeypatch)
    if only_serving_name:
        monkeypatch.setenv("CANONICAL_V2_DATABASE_URL", "postgresql://serving/db")

    http = _unconfigured_seed_client(tmp_path)
    for response in (http.get(_PREFIX), http.get(f"{_PREFIX}/1/runs")):
        assert response.status_code == 503, response.text
        assert response.json()["detail"] == "console_database_not_configured"


@pytest.mark.parametrize("configured", [True, False])
def test_the_boot_announcement_states_the_console_database_never_its_dsn(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    configured: bool,
) -> None:
    """The serving process owns the logging configuration, so the state is printed too.

    Same reasoning as the first-boot admin password: a line the operator cannot see in the
    boot log is a line that does not exist. The state only — never the DSN (or a credential).
    """

    _clear_console_env(monkeypatch)
    if configured:
        monkeypatch.setenv("DATABASE_URL", "postgresql://operator:hunter2@db.internal/miroflow")

    state = "configured" if configured else "unconfigured"
    with caplog.at_level(logging.INFO, logger="backend.main"):
        shell = _create_canonical_v2_route_shell()

    assert (shell.state.console_dsn is not None) is configured
    assert f"console_database={state}" in caplog.text
    printed = capsys.readouterr().out
    assert f"[canonical-v2] console_database={state}" in printed
    assert "hunter2" not in printed
    assert "db.internal" not in printed
