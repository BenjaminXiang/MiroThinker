"""R3 — the shared gate: lock, switch, quota, breaker, PostgreSQL degradation, execution.

Locks: the second in-flight trigger is refused (same process and another process), switch-off and
quota-zero produce recorded empty runs, effective quotas reach the child and the run row, two
consecutive failures open the breaker (and a reset re-opens triggering), success resets the counter,
PG-required tasks degrade, scheduled runs respect the nightly window, timeouts fail cleanly, and the
child environment is never persisted.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from src.data_agents.canonical_v2.jobs import (
    MANUAL_TRIGGER,
    _spawn_subprocess,
    QUOTA_LLM_ENV,
    QUOTA_WEB_SEARCH_ENV,
    SCHEDULE_TRIGGER,
    JobAlreadyRunningError,
    JobBreakerOpenError,
    JobLock,
    JobParameterError,
    JobPostgresUnavailableError,
    JobRunStore,
    JobRuntime,
    JobTask,
    PostgresProbe,
    redact_secrets,
)
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore


SENTINEL_ENV_VALUE = "env-sentinel-3d7c1f"


def _task(task_id: str = "stub-task", **overrides) -> JobTask:
    base = JobTask(
        task_id=task_id,
        label="桩任务",
        description="stub",
        domain="company",
        argv_template=("python3", "-c", "print('{}')"),
        params={},
        cwd_relative=".",
        timeout_seconds=5,
        schedule_cron=None,
        schedule_display="手动",
        collection_gated=True,
        quota="web_search",
        requires_postgres=False,
        window_bound=True,
    )
    return replace(base, **overrides)


def _settings(tmp_path: Path, *, enabled: dict[str, bool] | None = None, **collection):
    payload = {
        "schema_version": 1,
        "collection": {
            "enabled": enabled or {"company": True, "paper": True, "patent": True, "professor": True},
            "max_web_searches_per_run": collection.get("max_web_searches_per_run", 7),
            "max_llm_calls_per_run": collection.get("max_llm_calls_per_run", 9),
            "window_start_hour_utc": collection.get("window_start_hour_utc", 0),
            "window_end_hour_utc": collection.get("window_end_hour_utc", 23),
        },
    }
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return ManagedSettingsStore(path=path, environ={})


class _Spawn:
    """Programmable child-process stand-in: records calls, blocks on demand."""

    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[dict] = []
        self.started = __import__("threading").Event()
        self.release = __import__("threading").Event()
        self.block = False

    def __call__(self, argv, *, cwd, env, timeout):
        self.calls.append({"argv": tuple(argv), "cwd": cwd, "env": dict(env), "timeout": timeout})
        if self.block:
            self.started.set()
            self.release.wait(10)
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


@pytest.fixture()
def runtime_factory(tmp_path: Path):
    created: list[JobRuntime] = []

    def build(
        *, tasks=None, settings=None, spawn=None, environ=None, probe=None, console_dsn=None
    ) -> JobRuntime:
        store = JobRunStore(tmp_path / "jobs.sqlite3")
        runtime = JobRuntime(
            store=store,
            settings_store=settings or _settings(tmp_path),
            tasks=tasks if tasks is not None else (_task(),),
            lock_dir=tmp_path / "locks",
            environ=environ if environ is not None else {},
            repo_root=tmp_path,
            spawn=spawn or _Spawn(),
            postgres_probe=probe,
            console_dsn=console_dsn,
        )
        created.append(runtime)
        return runtime

    yield build
    for runtime in created:
        runtime.close()


def test_successful_trigger_records_run_and_item_count(runtime_factory) -> None:
    spawn = _Spawn(stdout='noise\n{"job_summary": {"items_processed": 3, "items_failed": 1}}\n')
    runtime = runtime_factory(spawn=spawn)
    outcome = runtime.trigger("stub-task", operator="alice")
    assert outcome.status == "running"
    assert spawn.calls and spawn.calls[0]["argv"] == ("python3", "-c", "print('{}')")

    runtime.wait_for_idle(timeout=10)
    row = runtime.run_detail(outcome.run_id)
    assert row["status"] == "succeeded"
    assert row["items_processed"] == 3
    assert row["items_failed"] == 1
    assert row["duration_ms"] is not None
    assert row["operator"] == "alice"


def test_second_trigger_while_running_is_refused(runtime_factory) -> None:
    spawn = _Spawn()
    spawn.block = True
    runtime = runtime_factory(spawn=spawn)

    first = runtime.trigger("stub-task", operator="alice")
    assert spawn.started.wait(5)
    with pytest.raises(JobAlreadyRunningError) as excinfo:
        runtime.trigger("stub-task", operator="bob")
    assert excinfo.value.active_run_id == first.run_id

    spawn.release.set()
    runtime.wait_for_idle(timeout=10)
    history = runtime.history("stub-task")
    assert [row.status for row in history] == ["succeeded"]
    assert runtime.trigger("stub-task", operator="bob").status == "running"
    runtime.wait_for_idle(timeout=10)


def test_lock_excludes_another_process(tmp_path: Path, runtime_factory) -> None:
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "stub-task.lock"
    ready = tmp_path / "child-locked"
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import fcntl, pathlib, sys, time\n"
                f"handle = open({str(lock_path)!r}, 'w')\n"
                "fcntl.flock(handle, fcntl.LOCK_EX)\n"
                f"pathlib.Path({str(ready)!r}).write_text('locked')\n"
                "time.sleep(8)\n"
            ),
        ]
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "child process never took the lock"

        runtime = runtime_factory()
        with pytest.raises(JobAlreadyRunningError):
            runtime.trigger("stub-task", operator="alice")
        assert runtime.history("stub-task") == ()
        assert runtime.storage_status()["available"] is True
    finally:
        child.kill()
        child.wait(timeout=5)


def test_lock_release_after_a_finished_run_is_immediate(tmp_path: Path) -> None:
    lock = JobLock.try_acquire(tmp_path / "x.lock")
    assert lock is not None
    assert JobLock.try_acquire(tmp_path / "x.lock") is None
    lock.release()
    again = JobLock.try_acquire(tmp_path / "x.lock")
    assert again is not None
    again.release()


def test_switch_off_records_a_skip_without_spawning(runtime_factory, tmp_path: Path) -> None:
    spawn = _Spawn()
    settings = _settings(tmp_path, enabled={"company": False, "paper": True, "patent": True, "professor": True})
    runtime = runtime_factory(spawn=spawn, settings=settings)

    outcome = runtime.trigger("stub-task", operator="alice")
    assert outcome.status == "skipped"
    assert outcome.skip_reason == "switch_off"
    assert spawn.calls == []
    row = runtime.run_detail(outcome.run_id)
    assert row["status"] == "skipped"
    assert row["skip_reason"] == "switch_off"
    assert row["operator"] == "alice"


def test_quota_zero_records_a_skip(runtime_factory, tmp_path: Path) -> None:
    spawn = _Spawn()
    runtime = runtime_factory(
        spawn=spawn, settings=_settings(tmp_path, max_web_searches_per_run=0)
    )
    outcome = runtime.trigger("stub-task", operator="alice")
    assert (outcome.status, outcome.skip_reason) == ("skipped", "quota_exhausted")
    assert spawn.calls == []


def test_ops_task_without_quota_gate_runs_even_when_caps_are_zero(
    runtime_factory, tmp_path: Path
) -> None:
    spawn = _Spawn()
    ops_task = _task(
        "ops-task", collection_gated=False, quota=None, requires_postgres=False, window_bound=False
    )
    runtime = runtime_factory(
        tasks=(ops_task,), spawn=spawn, settings=_settings(tmp_path, max_web_searches_per_run=0)
    )
    assert runtime.trigger("ops-task").status == "running"
    runtime.wait_for_idle(timeout=10)
    assert runtime.run_detail(runtime.history("ops-task")[0].run_id)["status"] == "succeeded"


def test_effective_quotas_reach_the_child_and_the_run_row(runtime_factory, tmp_path: Path) -> None:
    spawn = _Spawn()
    runtime = runtime_factory(
        spawn=spawn,
        settings=_settings(tmp_path, max_web_searches_per_run=11, max_llm_calls_per_run=22),
    )
    runtime.trigger("stub-task", operator="alice")
    runtime.wait_for_idle(timeout=10)
    assert spawn.calls[0]["env"][QUOTA_WEB_SEARCH_ENV] == "11"
    assert spawn.calls[0]["env"][QUOTA_LLM_ENV] == "22"
    row = runtime.history("stub-task")[0]
    assert row.summary["quota"] == {"web_search": 11, "llm": 22}


def test_two_consecutive_failures_open_the_breaker(runtime_factory) -> None:
    spawn = _Spawn(returncode=1, stderr=f"boom api_key={SENTINEL_ENV_VALUE}\n")
    runtime = runtime_factory(spawn=spawn)
    for _ in range(2):
        runtime.trigger("stub-task", operator="alice")
        runtime.wait_for_idle(timeout=10)

    with pytest.raises(JobBreakerOpenError):
        runtime.trigger("stub-task", operator="alice")
    assert len(spawn.calls) == 2

    view = {task["task_id"]: task for task in runtime.task_views()}["stub-task"]
    assert view["failure_flag"] is True
    assert view["breaker_open"] is True
    assert view["consecutive_failures"] == 2

    runtime.reset_breaker("stub-task", operator="dave")
    assert runtime.trigger("stub-task", operator="alice").status == "running"
    runtime.wait_for_idle(timeout=10)


def test_success_resets_the_consecutive_failure_counter(runtime_factory) -> None:
    spawn = _Spawn(returncode=1, stderr="first failure\n")
    runtime = runtime_factory(spawn=spawn)
    runtime.trigger("stub-task")
    runtime.wait_for_idle(timeout=10)
    assert runtime.task_state("stub-task").consecutive_failures == 1

    spawn.returncode = 0
    runtime.trigger("stub-task")
    runtime.wait_for_idle(timeout=10)
    state = runtime.task_state("stub-task")
    assert state.consecutive_failures == 0
    assert state.breaker_open is False


def test_scheduled_trigger_outside_the_window_is_skipped(runtime_factory, tmp_path: Path) -> None:
    # window empty: start hour 5 == end hour 5 is invalid, so use an hour band that excludes now
    now_hour = datetime.now(UTC).hour
    start = (now_hour + 2) % 24
    end = (now_hour + 3) % 24
    if end <= start:
        start, end = 0, 1
    spawn = _Spawn()
    runtime = runtime_factory(
        spawn=spawn,
        settings=_settings(tmp_path, window_start_hour_utc=start, window_end_hour_utc=end),
    )
    outcome = runtime.trigger("stub-task", trigger_source=SCHEDULE_TRIGGER)
    if start < end and not (start <= now_hour < end):
        assert (outcome.status, outcome.skip_reason) == ("skipped", "outside_window")
        assert spawn.calls == []
    else:
        assert outcome.status == "running"
        runtime.wait_for_idle(timeout=10)


def test_manual_trigger_records_window_state_without_blocking(runtime_factory, tmp_path: Path) -> None:
    now_hour = datetime.now(UTC).hour
    start = (now_hour + 2) % 24
    end = (now_hour + 3) % 24
    if end <= start:
        start, end = 0, 1
    runtime = runtime_factory(
        spawn=_Spawn(),
        settings=_settings(tmp_path, window_start_hour_utc=start, window_end_hour_utc=end),
    )
    outcome = runtime.trigger("stub-task", trigger_source=MANUAL_TRIGGER)
    assert outcome.status == "running"
    runtime.wait_for_idle(timeout=10)
    row = runtime.history("stub-task")[0]
    assert row.window_bound is True
    assert row.inside_window is False


def test_timeout_fails_the_run_with_a_bounded_sample(runtime_factory) -> None:
    def spawn(argv, *, cwd, env, timeout):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)

    runtime = runtime_factory(spawn=spawn)
    runtime.trigger("stub-task")
    runtime.wait_for_idle(timeout=10)
    row = runtime.history("stub-task")[0]
    assert row.status == "failed"
    assert row.exit_code == 124
    assert "timed out after 5s" in (row.as_dict(include_samples=True)["stderr_excerpt"] or "")


def test_pg_required_task_degrades_without_postgres(runtime_factory) -> None:
    spawn = _Spawn()
    pg_task = _task("ops-task", collection_gated=False, quota=None, requires_postgres=True)
    runtime = runtime_factory(tasks=(pg_task,), spawn=spawn)
    view = runtime.task_views()[0]
    assert view["available"] is False
    assert view["unavailable_reason"] == "postgres_unavailable"

    with pytest.raises(JobPostgresUnavailableError):
        runtime.trigger("ops-task")
    assert spawn.calls == []
    assert runtime.history("ops-task") == ()


def test_pg_required_task_available_with_a_reachable_postgres(runtime_factory) -> None:
    class _Connection:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    connections: list[_Connection] = []

    def connect(dsn, *, connect_timeout):
        assert connect_timeout <= 5
        connection = _Connection()
        connections.append(connection)
        return connection

    probe = PostgresProbe(
        environ={"DATABASE_URL": "postgresql://example/db"}, connect=connect
    )
    pg_task = _task("ops-task", collection_gated=False, quota=None, requires_postgres=True)
    runtime = runtime_factory(tasks=(pg_task,), spawn=_Spawn(), probe=probe)
    assert runtime.task_views()[0]["available"] is True
    assert connections and connections[0].closed is True
    assert runtime.trigger("ops-task").status == "running"
    runtime.wait_for_idle(timeout=10)


def test_probe_is_cached_and_fail_soft() -> None:
    attempts: list[str] = []

    def broken_connect(dsn, *, connect_timeout):
        attempts.append(dsn)
        raise RuntimeError("connection refused")

    probe = PostgresProbe(environ={"DATABASE_URL": "postgresql://example/db"}, connect=broken_connect)
    assert probe.available() is False
    assert probe.available() is False
    assert len(attempts) == 1
    assert PostgresProbe(environ={}).available() is False


def test_unknown_task_and_invalid_params_are_refused(runtime_factory) -> None:
    from src.data_agents.canonical_v2.jobs import JobTaskUnknownError

    runtime = runtime_factory()
    with pytest.raises(JobTaskUnknownError):
        runtime.trigger("nope")
    with pytest.raises(JobParameterError):
        runtime.trigger("stub-task", params={"domain": "paper"})


def test_task_views_expose_cadence_gates_and_next_fire(runtime_factory) -> None:
    scheduled = _task(
        "company-news-ingest",
        schedule_cron="0 2 * * 1",
        schedule_display="每周一 02:00",
        quota="web_search",
    )
    runtime = runtime_factory(tasks=(scheduled,))
    view = runtime.task_views()[0]
    assert view["schedule_cron"] == "0 2 * * 1"
    assert view["schedule_display"] == "每周一 02:00"
    assert view["next_run_at"] is not None
    assert view["switch_enabled"] is True
    assert view["quota"] == "web_search"
    assert view["quota_limit"] == 7
    assert view["last_run"] is None
    assert view["failure_flag"] is False
    assert view["params"] == {}


def test_task_view_next_fire_is_null_for_manual_tasks(runtime_factory) -> None:
    runtime = runtime_factory(tasks=(_task("ops-task", schedule_cron=None, window_bound=False),))
    assert runtime.task_views()[0]["next_run_at"] is None


def test_child_environment_is_never_persisted(runtime_factory, tmp_path: Path) -> None:
    spawn = _Spawn(stdout=f"api_key={SENTINEL_ENV_VALUE}\n")
    runtime = runtime_factory(spawn=spawn, environ={"STUB_ENV_SENTINEL": SENTINEL_ENV_VALUE})
    runtime.trigger("stub-task")
    runtime.wait_for_idle(timeout=10)
    assert spawn.calls[0]["env"]["STUB_ENV_SENTINEL"] == SENTINEL_ENV_VALUE

    database_path = runtime.store.database_path
    row = runtime.history("stub-task")[0]
    assert SENTINEL_ENV_VALUE not in str(row.as_dict(include_samples=True))
    assert database_path.read_bytes().find(SENTINEL_ENV_VALUE.encode()) == -1
    assert redact_secrets(f"api_key={SENTINEL_ENV_VALUE}") == "api_key=[redacted]"


def test_a_resolved_console_dsn_reaches_the_child_as_database_url(
    runtime_factory,
) -> None:
    spawn = _Spawn()
    runtime = runtime_factory(spawn=spawn, environ={"DATABASE_URL": "postgresql://resolved/db"})
    runtime.trigger("stub-task")
    runtime.wait_for_idle(timeout=10)
    assert spawn.calls[0]["env"]["DATABASE_URL"] == "postgresql://resolved/db"


def test_the_test_name_stands_in_when_database_url_is_absent(runtime_factory) -> None:
    spawn = _Spawn()
    runtime = runtime_factory(spawn=spawn, environ={"DATABASE_URL_TEST": "postgresql://test/db"})
    runtime.trigger("stub-task")
    runtime.wait_for_idle(timeout=10)
    assert spawn.calls[0]["env"]["DATABASE_URL"] == "postgresql://test/db"


def test_no_resolved_dsn_sets_no_database_url_key(runtime_factory) -> None:
    spawn = _Spawn()
    runtime = runtime_factory(spawn=spawn, environ={})
    runtime.trigger("stub-task")
    runtime.wait_for_idle(timeout=10)
    assert "DATABASE_URL" not in spawn.calls[0]["env"]


def test_an_explicit_console_dsn_wins_over_the_probe_environment(runtime_factory) -> None:
    spawn = _Spawn()
    runtime = runtime_factory(spawn=spawn, console_dsn="postgresql://startup/db")
    runtime.trigger("stub-task")
    runtime.wait_for_idle(timeout=10)
    assert spawn.calls[0]["env"]["DATABASE_URL"] == "postgresql://startup/db"


def test_a_timed_out_spawn_leaves_no_grandchild_behind() -> None:
    """R5 — the timeout kill must reach the whole process group.

    ``uv run`` execs the real worker as a **grandchild**: a direct child that spawns a worker of its
    own, exactly like the declared tasks do. Before this regression the spawn helper killed only the
    direct child, so a timed-out run kept working (and spending quota) while the gate recorded
    `failed` and released the lock. Read-only evidence of the old behaviour:
    `.agents/runs/add-admin-upload-seeds/current-state.md` §2.1.
    """

    marker = f"w3-orphan-marker-{os.getpid()}-{int(time.time() * 1000)}"
    grandchild = f"import time;time.sleep(60)  # {marker}"
    linker = (
        "import subprocess, sys\n"
        f"subprocess.run([sys.executable, '-c', {grandchild!r}], check=False)\n"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        _spawn_subprocess(
            ("python3", "-c", linker), cwd=str(Path.cwd()), env=dict(os.environ), timeout=1
        )
    deadline = time.monotonic() + 5.0
    survivors = _processes_matching(marker)
    while survivors and time.monotonic() < deadline:
        time.sleep(0.2)
        survivors = _processes_matching(marker)
    assert survivors == [], f"process group kill left processes behind: {survivors}"


def _processes_matching(marker: str) -> list[str]:
    listing = subprocess.run(
        ["ps", "-eo", "pid,cmd"], text=True, capture_output=True, check=False
    ).stdout
    return [
        line.strip()
        for line in listing.splitlines()
        if marker in line and "ps -eo" not in line and "survivors" not in line
    ]
