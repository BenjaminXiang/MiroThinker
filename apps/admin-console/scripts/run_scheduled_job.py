"""Run one declared job through the same gate as the manual trigger.

Designed for cron on the customer serving node:

    run_scheduled_job.py company-news-ingest

It loads the managed settings/secrets, points the child at the job-only
collection database, triggers with ``trigger_source=schedule`` and waits for the
run to finish. It prints only task/run/status; no environment or secret values.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def _bundle_root() -> Path:
    # .../code/apps/admin-console/scripts/run_scheduled_job.py
    return Path(__file__).resolve().parents[4]


def _prepare_environment() -> dict[str, str]:
    bundle = _bundle_root()
    code = bundle / "code"
    os.chdir(bundle)
    sys.path.insert(0, str(code / "apps" / "admin-console"))
    sys.path.insert(0, str(code / "apps" / "miroflow-agent"))

    env = dict(os.environ)
    env.setdefault("CANONICAL_V2_ACCESS_LOG_DB", str(bundle / "var" / "access-logs.sqlite3"))
    env.setdefault("CANONICAL_V2_JOBS_DB", str(bundle / "var" / "jobs.sqlite3"))
    env.setdefault(
        "MIROTHINKER_JOB_DATABASE_URL",
        "postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1",
    )
    env.setdefault("MIROTHINKER_JOB_PYTHON", str(bundle / ".venv" / "bin" / "python"))
    env.setdefault("MIROTHINKER_JOB_TIMEZONE", "Asia/Shanghai")

    from src.data_agents.canonical_v2.managed_runtime import apply_managed_runtime_config

    apply_managed_runtime_config(environ=env)
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one declared canonical-v2 job once.")
    parser.add_argument("task_id")
    parser.add_argument("--dry-run", action="store_true", help="validate imports/env, do not trigger")
    args = parser.parse_args(argv)
    env = _prepare_environment()

    from backend.api.canonical_v2_jobs import build_job_runtime
    from src.data_agents.canonical_v2.jobs import (
        JOB_TASKS_BY_ID,
        SCHEDULE_TRIGGER,
        JobAlreadyRunningError,
        JobBreakerOpenError,
        JobParameterError,
        JobPostgresUnavailableError,
        JobsError,
    )

    task = JOB_TASKS_BY_ID.get(args.task_id)
    if task is None:
        print(f"unknown task: {args.task_id}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(
            f"dry-run task={task.task_id} schedule={task.schedule_display!r} "
            f"timeout={task.timeout_seconds}s"
        )
        return 0

    runtime = build_job_runtime(environ=env)
    try:
        outcome = runtime.trigger(
            args.task_id,
            trigger_source=SCHEDULE_TRIGGER,
            operator="scheduler",
        )
    except (
        JobAlreadyRunningError,
        JobBreakerOpenError,
        JobParameterError,
        JobPostgresUnavailableError,
        JobsError,
    ) as exc:
        print(f"trigger refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(
        f"triggered task={outcome.task_id} run={outcome.run_id} "
        f"status={outcome.status} skip={outcome.skip_reason or '-'}"
    )
    runtime.wait_for_idle(timeout=task.timeout_seconds + 120)
    print(f"finished task={outcome.task_id} run={outcome.run_id}")
    return 0 if outcome.status in {"succeeded", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
