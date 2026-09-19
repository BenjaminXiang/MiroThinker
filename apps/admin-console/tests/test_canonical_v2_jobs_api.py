"""R4 — HTTP surface: list / trigger / history / detail / reset + degradation.

Locks: the declared list payload (cadence, next fire, gates, PG degradation), accepted triggers,
refusals with stable codes (409 already-running, 404 unknown, 422 injected parameter, 409 breaker),
the failure-sample endpoint, storage-unset degradation, and the `/jobs` page.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from backend.main import app
from tests.conftest import TEST_ADMIN_USERNAME, authorized_client
from src.data_agents.canonical_v2.jobs import (
    JOB_TASKS,
    JobRunStore,
    JobRuntime,
    JobTask,
)
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore


_PREFIX = "/api/canonical-v2/admin/jobs"
_STATE = "canonical_v2_jobs_runtime"


def _settings(path: Path) -> ManagedSettingsStore:
    path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    return ManagedSettingsStore(path=path, environ={})


def _stub_task(task_id: str, code: str, **overrides) -> JobTask:
    base = JobTask(
        task_id=task_id,
        label="桩任务",
        description="stub",
        group="ops",
        operator_hint="桩任务，只出现在测试里。",
        domain="company",
        argv_template=("python3", "-c", code),
        params={},
        cwd_relative=".",
        timeout_seconds=15,
        schedule_cron=None,
        schedule_display="手动",
        collection_gated=True,
        quota="web_search",
        requires_postgres=False,
        window_bound=False,
    )
    return replace(base, **overrides)


@pytest.fixture()
def jobs_runtime(tmp_path: Path):
    store = JobRunStore(tmp_path / "jobs.sqlite3")
    stubs = (
        _stub_task("stub-ok", "print('{\"job_summary\": {\"items_processed\": 2}}')"),
        _stub_task("stub-slow", "import time; time.sleep(3)"),
        _stub_task("stub-fail", "import sys; sys.stderr.write('boom\\n'); sys.exit(1)"),
        _stub_task(
            "stub-pg",
            "print('never')",
            collection_gated=False,
            quota=None,
            requires_postgres=True,
        ),
    )
    runtime = JobRuntime(
        store=store,
        settings_store=_settings(tmp_path / "settings.json"),
        # The real declared table plus the stub tasks: the list endpoint is exercised against the
        # real white list (cadence, gates, PG degradation) and the runtime against fast stubs.
        tasks=JOB_TASKS + stubs,
        lock_dir=tmp_path / "locks",
        environ={},
        repo_root=tmp_path,
    )
    app.state.__setattr__(_STATE, runtime)
    with authorized_client() as client:
        yield client, runtime
    app.state.__delattr__(_STATE) if hasattr(app.state, _STATE) else None
    runtime.close()


def _history(client: TestClient, task_id: str, *, status: str | None = None) -> dict:
    params = {"limit": 20}
    if status:
        params["status"] = status
    response = client.get(f"{_PREFIX}/{task_id}/runs", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _wait_for_status(client: TestClient, task_id: str, expected: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = _history(client, task_id)
        if last["runs"] and last["runs"][0]["status"] == expected:
            return last["runs"][0]
        time.sleep(0.1)
    raise AssertionError(f"{task_id} never reached {expected}: {last}")


def test_list_serves_the_real_declared_table_with_cadence_and_gates(jobs_runtime) -> None:
    client, _ = jobs_runtime
    response = client.get(_PREFIX)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["storage"]["available"] is True
    ids = {task["task_id"] for task in payload["tasks"]}
    assert ids == {task.task_id for task in JOB_TASKS} | {
        "stub-ok",
        "stub-slow",
        "stub-fail",
        "stub-pg",
    }
    by_id = {task["task_id"]: task for task in payload["tasks"]}
    news = by_id["company-news-ingest"]
    assert news["schedule_cron"] == "0 2 * * 1"
    assert news["next_run_at"] is not None
    assert news["switch_enabled"] is True
    assert news["quota"] == "web_search"
    assert news["available"] is True
    assert news["last_run"] is None
    assert news["failure_flag"] is False
    # The operator-facing columns the page renders instead of the script path.
    assert news["group"] == "collection"
    assert news["operator_hint"]
    seed_task = by_id["admin-seed-refresh"]
    assert seed_task["group"] == "seed"
    assert seed_task["token_params"] == ["seed_id"]
    for ops_task_id in ("ops-milvus-backfill", "ops-retrieval-validation"):
        assert by_id[ops_task_id]["available"] is False
        assert by_id[ops_task_id]["requires_postgres"] is True
        assert by_id[ops_task_id]["next_run_at"] is None
    assert by_id["ops-milvus-backfill"]["params"] == {
        "domain": ["company", "paper", "patent", "professor"]
    }
    assert payload["postgres"]["available"] is False


def test_trigger_is_accepted_and_lands_in_history(jobs_runtime) -> None:
    client, _ = jobs_runtime
    response = client.post(f"{_PREFIX}/stub-ok/run", json={}, headers={"X-Remote-User": "alice"})
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "running"
    row = _wait_for_status(client, "stub-ok", "succeeded")
    assert row["items_processed"] == 2
    assert row["operator"] == TEST_ADMIN_USERNAME
    assert row["duration_ms"] is not None
    assert row["trigger_source"] == "manual"

    detail = client.get(f"{_PREFIX}/runs/{body['run_id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "succeeded"
    assert detail.json()["command"] == ["python3", "-c", "print('{\"job_summary\": {\"items_processed\": 2}}')"]


def test_second_trigger_while_running_is_refused_with_409(jobs_runtime) -> None:
    client, _ = jobs_runtime
    first = client.post(f"{_PREFIX}/stub-slow/run", json={})
    assert first.status_code == 202, first.text
    second = client.post(f"{_PREFIX}/stub-slow/run", json={})
    assert second.status_code == 409, second.text
    assert second.json()["detail"] == "job_already_running"
    _wait_for_status(client, "stub-slow", "succeeded", timeout=30)


def test_unknown_task_is_404(jobs_runtime) -> None:
    client, _ = jobs_runtime
    response = client.post(f"{_PREFIX}/not-a-task/run", json={})
    assert response.status_code == 404
    assert response.json()["detail"] == "job_unknown_task"


def test_undeclared_parameter_is_422(jobs_runtime) -> None:
    client, _ = jobs_runtime
    response = client.post(
        f"{_PREFIX}/stub-ok/run", json={"params": {"domain": "paper; rm -rf /"}}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "job_invalid_params"


def test_failing_task_shows_red_dot_and_exposes_a_failure_sample(jobs_runtime) -> None:
    client, _ = jobs_runtime
    client.post(f"{_PREFIX}/stub-fail/run", json={})
    _wait_for_status(client, "stub-fail", "failed")

    listed = client.get(_PREFIX).json()["tasks"]
    row = [task for task in listed if task["task_id"] == "stub-fail"][0]
    assert row["failure_flag"] is True
    assert row["consecutive_failures"] == 1
    assert row["breaker_open"] is False

    failures = _history(client, "stub-fail", status="failed")["runs"]
    assert failures and failures[0]["status"] == "failed"
    detail = client.get(f"{_PREFIX}/runs/{failures[0]['run_id']}").json()
    assert "boom" in detail["stderr_excerpt"]
    assert detail["exit_code"] == 1


def test_breaker_refuses_further_triggers_and_reset_reopens(jobs_runtime) -> None:
    client, _ = jobs_runtime
    for _ in range(2):
        client.post(f"{_PREFIX}/stub-fail/run", json={})
        _wait_for_status(client, "stub-fail", "failed")
    blocked = client.post(f"{_PREFIX}/stub-fail/run", json={})
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "job_breaker_open"

    reset = client.post(f"{_PREFIX}/stub-fail/reset", headers={"X-Remote-User": "dave"})
    assert reset.status_code == 200
    assert reset.json()["breaker_open"] is False
    row = [task for task in client.get(_PREFIX).json()["tasks"] if task["task_id"] == "stub-fail"][0]
    assert row["breaker_open"] is False
    assert row["failure_flag"] is True  # the last run still failed

    accepted = client.post(f"{_PREFIX}/stub-fail/run", json={})
    assert accepted.status_code == 202, accepted.text
    _wait_for_status(client, "stub-fail", "failed")


def test_postgres_required_task_is_503_and_hidden(jobs_runtime) -> None:
    client, _ = jobs_runtime
    response = client.post(f"{_PREFIX}/stub-pg/run", json={})
    assert response.status_code == 503
    assert response.json()["detail"] == "job_postgres_unavailable"
    assert _history(client, "stub-pg")["runs"] == []


def test_unknown_run_detail_is_404(jobs_runtime) -> None:
    client, _ = jobs_runtime
    response = client.get(f"{_PREFIX}/runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_reset_on_unknown_task_is_404(jobs_runtime) -> None:
    client, _ = jobs_runtime
    response = client.post(f"{_PREFIX}/not-a-task/reset")
    assert response.status_code == 404


def test_jobs_page_is_served(jobs_runtime) -> None:
    client, _ = jobs_runtime
    response = client.get("/jobs")
    assert response.status_code == 200
    assert "任务运维" in response.text
    assert _PREFIX in response.text
    # The page explains itself and renders the four operator groups from the declared groups;
    # the script path and the ids live behind 技术细节, so the payload keys must be read.
    for marker in (
        "这个页面做什么",
        "日常采集",
        "数据导入",
        "教授采集源",
        "operator_hint",
        "技术细节",
        "立即运行",
        "复位熔断",
        "去 Seed 管理页",
    ):
        assert marker in response.text


def test_jobs_page_folds_the_build_group_away(jobs_runtime) -> None:
    """The three engineering actions live in a collapsed 高级操作 block, not flat in the list."""

    client, _ = jobs_runtime
    response = client.get("/jobs")
    assert response.status_code == 200
    document = response.text

    for marker in (
        # the collapsed group: summary line + the one-line status it carries
        '<details class="group-advanced"><summary>',
        "高级操作：数据更新与检索自检（一般不需要手动执行）",
        "最近一次：尚未运行",
        # plain-language purpose and step guide
        "你导入了新数据或刚跑完采集后，用下面三步让检索能看到新内容，并确认检索正常。",
        "建议顺序：① 预演（看影响范围）→ ② 更新检索索引 → ③ 检索自检。耗时从几十秒到几分钟不等。",
        # the reason that replaces the 需构建库 tag while the task is unavailable
        "当前不可用：需要本机数据库",
        # tags in plain words, and the column / footer the operator reads
        "会消耗网络检索额度",
        "会消耗大模型调用额度",
        "仅在允许的时间段运行",
        "受采集开关控制",
        "<th>运行安排</th>",
        "运行安排由系统固定，页面只能查看；手动执行与自动执行受同样的安全限制："
        "同一任务不会重复运行，连续失败会自动暂停。",
    ):
        assert marker in document, marker
    # the old engineering wording is gone from the page
    for gone in ("构建与运维", "需构建库", "需要构建期数据库", "节奏（下次运行）", "从未运行"):
        assert gone not in document, gone
    # the three labels the collapsed group renders come from the declared table
    labels = {task["task_id"]: task["label"] for task in client.get(_PREFIX).json()["tasks"]}
    assert labels["ops-milvus-backfill-dry-run"] == "更新检索索引 · 预演"
    assert labels["ops-milvus-backfill"] == "更新检索索引"
    assert labels["ops-retrieval-validation"] == "检索自检"


def test_unset_storage_degrades_to_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CANONICAL_V2_JOBS_DB", raising=False)
    monkeypatch.delenv("CANONICAL_V2_ACCESS_LOG_DB", raising=False)
    if hasattr(app.state, _STATE):
        delattr(app.state, _STATE)
    with authorized_client() as client:
        response = client.get(_PREFIX)
    assert response.status_code == 503
    assert response.json()["detail"] == "jobs_storage_unavailable"
    if hasattr(app.state, _STATE):
        delattr(app.state, _STATE)
