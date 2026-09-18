"""Build a real /api/canonical-v2/admin/jobs payload (+ per-task history) for the page harness.

Run from `apps/admin-console` so the console's editable dependency resolves `src.data_agents`:

    cd apps/admin-console
    uv run python ../../.agents/runs/connect-collection-line/jobs-page-harness/make_payload.py
    node ../../.agents/runs/connect-collection-line/jobs-page-harness/render_check.cjs

Environment: `JOBS_HARNESS_REPO` (repo root, default: two levels above the cwd),
`JOBS_HARNESS_OUT` (scratch dir, default `/tmp/jobs-harness`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from src.data_agents.canonical_v2.jobs import (
    SKIP_OUTSIDE_WINDOW,
    JobRunStore,
    JobRuntime,
)
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore

REPO = Path(os.environ.get("JOBS_HARNESS_REPO", Path.cwd().resolve().parents[1]))
OUT = Path(os.environ.get("JOBS_HARNESS_OUT", "/tmp/jobs-harness"))
SCRATCH = OUT / "scratch"
if SCRATCH.exists():
    shutil.rmtree(SCRATCH)
SCRATCH.mkdir(parents=True)
(SCRATCH / "settings.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

store = JobRunStore(SCRATCH / "jobs.sqlite3")
runtime = JobRuntime(
    store=store,
    settings_store=ManagedSettingsStore(path=SCRATCH / "settings.json", environ={}),
    lock_dir=SCRATCH / "locks",
    environ={},
    repo_root=REPO,
)


def succeeded(task_id: str, *, items: int, duration_ms: int) -> None:
    run_id = store.start_run(task_id=task_id, trigger_source="schedule", operator="scheduler")
    store.finish_run(run_id, status="succeeded", duration_ms=duration_ms, exit_code=0,
                     items_processed=items, items_failed=0, stdout='{"job_summary": {}}')


def failed(task_id: str, *, exit_code: int, stderr: str, duration_ms: int) -> None:
    run_id = store.start_run(task_id=task_id, trigger_source="manual", operator="ops")
    store.finish_run(run_id, status="failed", duration_ms=duration_ms, exit_code=exit_code, stderr=stderr)


succeeded("company-news-ingest", items=12, duration_ms=45123)
succeeded("company-official-product-capture", items=3, duration_ms=812440)
succeeded("paper-doi-verify", items=0, duration_ms=640)
store.record_skip(task_id="paper-search-backfill", trigger_source="schedule", operator="scheduler",
                  reason=SKIP_OUTSIDE_WINDOW)
# two consecutive failures -> breaker open, with an injection-shaped stderr excerpt
for _ in range(2):
    failed("paper-doi-verify", exit_code=1,
           stderr="<img src=x onerror=alert(1)> Traceback…\napi_key=abcdef123", duration_ms=2300)
succeeded("upload-company-import", items=204, duration_ms=98765)

payload = {
    "generated_at": "2026-09-19T04:05:06+00:00",
    "storage": runtime.storage_status(),
    "config": runtime.config_status(),
    "postgres": runtime.postgres_status(),
    "tasks": runtime.task_views(),
}
runs = {task.task_id: [run.as_dict() for run in runtime.history(task.task_id, limit=20)]
        for task in runtime._tasks}  # noqa: SLF001 - harness only
(OUT / "payload.json").write_text(json.dumps({"payload": payload, "runs": runs}, ensure_ascii=False),
                                 encoding="utf-8")
store.close()

print("repo root:", REPO)
print("tasks:", len(payload["tasks"]))
print("groups:", {task["task_id"]: task["group"] for task in payload["tasks"]})
print("ops available:", [task["available"] for task in payload["tasks"] if task["group"] == "ops"])
print("postgres:", payload["postgres"])
