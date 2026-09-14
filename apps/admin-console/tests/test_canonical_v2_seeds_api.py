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
    app = _create_canonical_v2_route_shell()
    app.state.canonical_v2_seed_gate = gate
    return TestClient(app)


def test_without_postgres_every_seed_endpoint_degrades(tmp_path: Path) -> None:
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
    monkeypatch.setattr(canonical_v2_seeds, "_seed_exists", lambda seed_id: seed_id == 7)
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
