from __future__ import annotations

from datetime import UTC, datetime

from backend.storage import seeds as seed_storage
from backend.storage.seeds import Seed
from src.data_agents.canonical_v2.jobs import JOB_TASKS_BY_ID


def test_seed_accepts_manual_interruption_failure_class() -> None:
    now = datetime(2026, 6, 12, tzinfo=UTC)

    seed = Seed.model_validate(
        {
            "id": 5,
            "school": "深圳大学",
            "department": "计算机与软件学院",
            "seed_url": "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
            "last_run_at": now,
            "last_run_status": "failure",
            "failure_class": "manual_interruption",
            "created_at": now,
            "updated_at": now,
        }
    )

    assert seed.failure_class == "manual_interruption"


def test_seed_accepts_unregistered_failure_class_without_breaking_list() -> None:
    now = datetime(2026, 6, 12, tzinfo=UTC)

    seed = Seed.model_validate(
        {
            "id": 6,
            "school": "深圳大学",
            "department": "计算机与软件学院",
            "seed_url": "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=2",
            "last_run_at": now,
            "last_run_status": "failure",
            "failure_class": "operator_interrupted",
            "created_at": now,
            "updated_at": now,
        }
    )

    assert seed.failure_class == "operator_interrupted"


def test_seed_select_projects_latest_failed_run_status() -> None:
    assert "CASE latest_pr.status" in seed_storage._SELECT_COLUMNS
    assert "WHEN 'failed' THEN 'failure'" in seed_storage._SELECT_COLUMNS
    assert "WHEN 'succeeded' THEN 'success'" in seed_storage._SELECT_COLUMNS
    assert "WHEN 'running' THEN" in seed_storage._SELECT_COLUMNS
    assert "AS last_run_at" in seed_storage._SELECT_COLUMNS
    assert "DESC NULLS LAST" in seed_storage._SELECT_COLUMNS


def test_a_stale_running_run_is_reported_as_interrupted() -> None:
    """The registry's own view of a killed run: `interrupted`, not `in_progress`."""

    columns = seed_storage._SELECT_COLUMNS
    assert "THEN 'interrupted'" in columns
    assert "ELSE 'in_progress'" in columns
    # The threshold is the rule: a stale `running` row is judged by its start (the created
    # time stands in when the start is missing), against a fixed window.
    assert "COALESCE(latest_pr.started_at, latest_pr.created_at)" in columns
    assert f"interval '{seed_storage.STALLED_RUN_AFTER_HOURS} hours'" in columns


def test_the_stall_threshold_is_wider_than_every_declared_task_timeout() -> None:
    longest = max(task.timeout_seconds for task in JOB_TASKS_BY_ID.values())
    assert seed_storage.STALLED_RUN_AFTER_HOURS * 3600 > longest


def test_seed_accepts_the_derived_interrupted_status() -> None:
    """The response model must accept what the SELECT derives, or every read 500s."""

    now = datetime(2026, 6, 12, tzinfo=UTC)

    seed = Seed.model_validate(
        {
            "id": 7,
            "school": "深圳大学",
            "department": None,
            "seed_url": "https://csse.szu.edu.cn/pages/teacherTeam/index?zc=3",
            "last_run_at": now,
            "last_run_status": "interrupted",
            "created_at": now,
            "updated_at": now,
        }
    )

    assert seed.last_run_status == "interrupted"


def test_interrupted_is_not_a_column_value() -> None:
    """It is derived at read time; the column's CHECK constraint keeps its five values."""

    assert "interrupted" not in seed_storage.VALID_LAST_RUN_STATUSES
    assert seed_storage.VALID_LAST_RUN_STATUSES == (
        "success",
        "failure",
        "in_progress",
        "never_run",
        "adapter_missing",
    )
