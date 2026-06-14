from __future__ import annotations

from datetime import UTC, datetime

from backend.storage import seeds as seed_storage
from backend.storage.seeds import Seed


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
    assert "WHEN 'running' THEN 'in_progress'" in seed_storage._SELECT_COLUMNS
    assert "AS last_run_at" in seed_storage._SELECT_COLUMNS
    assert "DESC NULLS LAST" in seed_storage._SELECT_COLUMNS
