"""R6 — professor-seed surface: CRUD reuse, bounded gated trigger, run polling, degradation.

The registry lives in Postgres, so the CRUD cases run only when `DATABASE_URL_TEST` points at a
disposable database (the repository convention; `miroflow_real` is refused by `conftest`). The
trigger and degradation cases never touch a database: the gate is injected.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from tests.conftest import authorized_client

from backend.main import _create_canonical_v2_route_shell
from src.data_agents.canonical_v2.jobs import JobRunStore, JobRuntime
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore
from src.data_agents.canonical_v2.jobs import JOB_TASKS_BY_ID


_PREFIX = "/api/canonical-v2/admin/seeds"
_SEED_URL = "https://example.edu.cn/sz/roster"


class _StubProbe:
    def __init__(self, available: bool) -> None:
        self._available = available

    def available(self) -> bool:
        return self._available

    def resolved_dsn(self) -> tuple[str | None, str | None]:
        return None, None

    def describe(self) -> dict[str, Any]:
        return {"available": self._available, "source": None, "checked_at": None}


class _RecordingSpawn:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv, *, cwd, env, timeout):  # noqa: ANN001
        self.calls.append(list(argv))

        class _Completed:
            returncode = 0
            stdout = '{"job_summary": {"items_processed": 1, "items_failed": 0, "seed_id": 1}}'
            stderr = ""

        return _Completed()


def _seed_client(tmp_path: Path, *, postgres: bool, spawn: Any = None) -> TestClient:
    scratch = tmp_path / "seed-scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    settings = scratch / "settings.json"
    settings.write_text('{"schema_version": 1}', encoding="utf-8")
    gate = JobRuntime(
        store=JobRunStore(scratch / "jobs.sqlite3"),
        settings_store=ManagedSettingsStore(path=settings, environ={}),
        lock_dir=scratch / "locks",
        repo_root=tmp_path,
        environ={},
        spawn=spawn or _RecordingSpawn(),
        postgres_probe=_StubProbe(postgres),
    )
    shell = _create_canonical_v2_route_shell()
    shell.state.canonical_v2_seed_gate = gate
    return authorized_client(shell)


def test_without_postgres_every_seed_endpoint_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Degradation *with a configured database* is the reachability case: the
    # missing-configuration case answers console_database_not_configured.
    monkeypatch.setenv("DATABASE_URL", "postgresql://configured/unreachable")
    http = _seed_client(tmp_path, postgres=False)
    assert http.get("/api/health").status_code == 200
    assert http.get(_PREFIX).status_code == 503
    assert http.get(f"{_PREFIX}/1").status_code == 503
    assert http.post(_PREFIX, json={"school": "S", "seed_url": _SEED_URL}).status_code == 503
    assert (
        http.put(f"{_PREFIX}/1", json={"school": "S", "seed_url": _SEED_URL}).status_code
        == 503
    )
    assert http.delete(f"{_PREFIX}/1").status_code == 503
    assert http.post(f"{_PREFIX}/1/trigger", json={"mode": "preview"}).status_code == 503
    assert http.get(f"{_PREFIX}/1/runs").status_code == 503
    for response in (
        http.get(_PREFIX),
        http.post(f"{_PREFIX}/1/trigger", json={"mode": "preview"}),
    ):
        assert response.json()["detail"] == "seeds_require_postgres"


def test_a_sample_trigger_without_a_limit_is_refused(tmp_path: Path) -> None:
    http = _seed_client(tmp_path, postgres=True)
    response = http.post(f"{_PREFIX}/1/trigger", json={"mode": "sample"})
    assert response.status_code == 422


def test_an_out_of_set_mode_or_limit_is_refused(tmp_path: Path) -> None:
    http = _seed_client(tmp_path, postgres=True)
    assert http.post(f"{_PREFIX}/1/trigger", json={"mode": "everything"}).status_code == 422
    assert (
        http.post(f"{_PREFIX}/1/trigger", json={"mode": "sample", "limit": 1000}).status_code == 422
    )
    assert (
        http.post(f"{_PREFIX}/1/trigger", json={"mode": "full", "limit": 20}).status_code == 422
    )


def test_trigger_goes_through_the_declared_task(tmp_path: Path, monkeypatch) -> None:
    from backend.api import canonical_v2_seeds

    spawn = _RecordingSpawn()
    http = _seed_client(tmp_path, postgres=True, spawn=spawn)
    monkeypatch.setattr(
        canonical_v2_seeds, "_seed_exists", lambda seed_id, request: seed_id == 7
    )
    gate = http.app.state.canonical_v2_seed_gate

    assert http.post(f"{_PREFIX}/7/trigger", json={"mode": "preview"}).status_code == 202
    preview = http.post(f"{_PREFIX}/7/trigger", json={"mode": "preview"}).json()
    assert preview["task_id"] == "admin-seed-refresh"
    assert preview["status"] in {"running", "skipped"}
    assert http.post(f"{_PREFIX}/8/trigger", json={"mode": "preview"}).status_code == 404

    sample = http.post(f"{_PREFIX}/7/trigger", json={"mode": "sample", "limit": 20})
    assert sample.status_code == 202
    assert sample.json()["task_id"] == "admin-seed-refresh-sample"

    gate.wait_for_idle(timeout=10)
    assert spawn.calls, "the gate must have spawned the declared task"
    assert tuple(spawn.calls[0][:6]) == (
        "uv",
        "run",
        "python",
        "scripts/run_admin_seed_refresh.py",
        "--seed-id",
        "7",
    )
    runs = http.get(f"{_PREFIX}/7/runs")
    assert runs.status_code == 200
    assert runs.json()["total"] >= 1
    for task_id in set(canonical_v2_seeds.REFRESH_TASK_MODES.values()):
        task = JOB_TASKS_BY_ID[task_id]
        assert task.argv_template[0] == "uv"
        assert task.cwd_relative == "apps/miroflow-agent"
        assert task.collection_gated is True


def test_seed_runs_carry_the_outcome_fields(tmp_path: Path, monkeypatch) -> None:
    """E3 — one run tells the page *why* it failed; missing fields degrade to null."""

    from backend.api import canonical_v2_seeds

    http = _seed_client(tmp_path, postgres=True)
    monkeypatch.setattr(
        canonical_v2_seeds, "_seed_exists", lambda seed_id, request: seed_id == 7
    )
    gate = http.app.state.canonical_v2_seed_gate

    assert http.post(f"{_PREFIX}/7/trigger", json={"mode": "preview"}).status_code == 202
    gate.wait_for_idle(timeout=10)

    listed = http.get(f"{_PREFIX}/7/runs")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] >= 1
    for run in payload["runs"]:
        assert run["status"] == "succeeded"
        assert run["exit_code"] == 0
        assert run["stderr_excerpt"] == ""


@pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")),
    reason="No test database configured (DATABASE_URL_TEST); skipping seed CRUD integration",
)
def test_seed_crud_round_trip(tmp_path: Path) -> None:
    from src.data_agents.canonical_v2.jobs import PostgresProbe

    database_url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL", "")
    if "miroflow_real" in database_url:
        pytest.skip("refusing to run against a real-data database")

    http = _seed_client(tmp_path, postgres=False)
    http.app.state.canonical_v2_seed_gate._probe = PostgresProbe(  # noqa: SLF001
        {"DATABASE_URL_TEST": database_url}
    )

    unique_url = f"{_SEED_URL}?w3={os.getpid()}"
    created = http.post(
        _PREFIX, json={"school": "W3 测试大学", "department": "测试学院", "seed_url": unique_url}
    )
    assert created.status_code == 201, created.text
    seed_id = created.json()["id"]

    listed = http.get(_PREFIX)
    assert listed.status_code == 200
    assert any(item["id"] == seed_id for item in listed.json())

    fetched = http.get(f"{_PREFIX}/{seed_id}")
    assert fetched.status_code == 200
    assert fetched.json()["school"] == "W3 测试大学"

    updated = http.put(
        f"{_PREFIX}/{seed_id}",
        json={"school": "W3 测试大学（改）", "seed_url": unique_url},
    )
    assert updated.status_code == 200
    assert updated.json()["school"] == "W3 测试大学（改）"

    duplicate = http.post(
        _PREFIX, json={"school": "另一所", "seed_url": unique_url}
    )
    assert duplicate.status_code == 409

    deleted = http.delete(f"{_PREFIX}/{seed_id}")
    assert deleted.status_code == 204
    assert http.get(f"{_PREFIX}/{seed_id}").status_code == 404


def _insert_running_run(pg_dsn: str, *, seed_id: int, age: str) -> str:
    """One `running` roster_crawl run for this seed, back-dated by `age` (a Postgres interval)."""

    import psycopg

    from src.data_agents.storage.postgres.pipeline_run import open_pipeline_run

    with psycopg.connect(pg_dsn) as conn:
        run_id = open_pipeline_run(
            conn,
            run_kind="roster_crawl",
            run_scope={
                "source": "admin-console-test",
                "domain": "professor",
                "action": "single_seed_run",
                "seed_id": str(seed_id),
            },
            triggered_by="admin-console-test",
        )
        conn.execute(
            """
            UPDATE pipeline_run
               SET started_at = now() - %s::interval, created_at = now() - %s::interval
             WHERE run_id = %s
            """,
            (age, age, run_id),
        )
        conn.commit()
    return str(run_id)


@pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")),
    reason="No test database configured (DATABASE_URL_TEST); skipping the interrupted-run integration",
)
def test_a_killed_run_reads_as_interrupted_not_in_progress(tmp_path: Path) -> None:
    """A `running` row past the stall window is a killed run, and the registry says so.

    The presentation rule only: the row keeps its own status, the registry reports
    `interrupted` instead of "进行中" (see the 2026-09-19 collection-line log).
    """

    import psycopg

    from src.data_agents.canonical_v2.jobs import PostgresProbe
    from src.data_agents.storage.postgres.connection import resolve_dsn
    from src.data_agents.storage.postgres.pipeline_run import close_pipeline_run

    database_url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL", "")
    if "miroflow_real" in database_url:
        pytest.skip("refusing to run against a real-data database")
    pg_dsn = resolve_dsn(database_url)

    http = _seed_client(tmp_path, postgres=False)
    http.app.state.canonical_v2_seed_gate._probe = PostgresProbe(  # noqa: SLF001
        {"DATABASE_URL_TEST": database_url}
    )

    unique_url = f"{_SEED_URL}?interrupted={os.getpid()}"
    created = http.post(
        _PREFIX, json={"school": "中断态测试大学", "department": "测试学院", "seed_url": unique_url}
    )
    assert created.status_code == 201, created.text
    seed_id = created.json()["id"]

    run_ids: list[str] = []
    try:
        run_ids.append(_insert_running_run(pg_dsn, seed_id=seed_id, age="7 hours"))
        stale = http.get(f"{_PREFIX}/{seed_id}")
        assert stale.status_code == 200, stale.text
        assert stale.json()["last_run_status"] == "interrupted"

        listed = http.get(_PREFIX)
        assert listed.status_code == 200
        assert [
            row["last_run_status"] for row in listed.json() if row["id"] == seed_id
        ] == ["interrupted"]

        live_run = _insert_running_run(pg_dsn, seed_id=seed_id, age="1 minute")
        run_ids.append(live_run)
        live = http.get(f"{_PREFIX}/{seed_id}")
        assert live.json()["last_run_status"] == "in_progress"

        # A terminal status is never re-read as interrupted, however old the run is.
        with psycopg.connect(pg_dsn) as conn:
            close_pipeline_run(conn, live_run, status="failed")
            conn.commit()
        finished = http.get(f"{_PREFIX}/{seed_id}")
        assert finished.json()["last_run_status"] == "failure"
    finally:
        with psycopg.connect(pg_dsn) as conn:
            for run_id in run_ids:
                conn.execute("DELETE FROM pipeline_run WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM professor_seed WHERE id = %s", (seed_id,))
            conn.commit()
