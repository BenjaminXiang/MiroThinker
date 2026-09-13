"""Scratch launcher for the W2 smoke test on port 18291 (never 18188).

Builds the real Canonical V2 route shell, then installs a jobs runtime whose registry is the **real
declared table plus stub tasks**. Real tasks are never triggered by the smoke script (no web-search
or LLM quota is spent); the stub tasks exercise the gate end to end with fast, local commands.
"""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import sys

WORKTREE = Path(__file__).resolve().parents[2]
ADMIN = WORKTREE / "apps" / "admin-console"
AGENT = WORKTREE / "apps" / "miroflow-agent"
sys.path.insert(0, str(ADMIN))
sys.path.insert(0, str(AGENT))

from backend.main import _create_canonical_v2_route_shell  # noqa: E402
from src.data_agents.canonical_v2.jobs import (  # noqa: E402
    JOB_TASKS,
    JobRunStore,
    JobRuntime,
    JobTask,
)
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore  # noqa: E402


SCRATCH = Path(os.environ.get("W2_SCRATCH_DIR", "/var/tmp/w2-jobs-smoke-18291"))
PORT = int(os.environ.get("W2_SMOKE_PORT", "18291"))


def _stub(task_id: str, code: str, **overrides) -> JobTask:
    base = JobTask(
        task_id=task_id,
        label=f"桩任务 {task_id}",
        description="冒烟用桩任务（不消耗 web search / LLM 配额）",
        domain="company",
        argv_template=("python3", "-c", code),
        cwd_relative=".",
        timeout_seconds=30,
        schedule_cron="0 2 * * 1",
        schedule_display="每周一 02:00",
        collection_gated=True,
        quota="web_search",
        requires_postgres=False,
        window_bound=True,
    )
    return replace(base, **overrides)


STUB_TASKS = (
    _stub("stub-collect-ok", "print('{\"job_summary\": {\"items_processed\": 2, \"items_failed\": 0}}')"),
    _stub("stub-collect-slow", "import time; time.sleep(3)"),
    _stub("stub-collect-fail", "import sys; sys.stderr.write('smoke failure: api_key=smoke-sentinel\\n'); sys.exit(1)"),
    _stub(
        "stub-collect-pg",
        "print('never runs')",
        collection_gated=False,
        quota=None,
        requires_postgres=True,
    ),
)


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    settings_path = SCRATCH / "settings.json"
    if not settings_path.exists():
        settings_path.write_text('{"schema_version": 1}', encoding="utf-8")
    store = JobRunStore(SCRATCH / "jobs.sqlite3")
    runtime = JobRuntime(
        store=store,
        settings_store=ManagedSettingsStore(path=settings_path, environ={}),
        tasks=JOB_TASKS + STUB_TASKS,
        lock_dir=SCRATCH / "locks",
        repo_root=WORKTREE,
    )
    app = _create_canonical_v2_route_shell()
    app.state.canonical_v2_jobs_runtime = runtime

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
