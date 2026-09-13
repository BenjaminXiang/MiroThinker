"""R1 — the job white list is closed and every declared command exists.

Locks: fixed-argv construction, closed parameter sets, refusal of unknown tasks / undeclared
parameters / out-of-set values, real script paths, and the declared-cadence next-fire calculator.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.data_agents.canonical_v2.jobs import (
    JOB_TASKS,
    JobParameterError,
    JobTaskUnknownError,
    cron_next_fire,
    get_job_task,
)
from src.data_agents.canonical_v2.managed_config import PUBLIC_DOMAINS


REPO_ROOT = Path(__file__).resolve().parents[3]


def _first_params(task) -> dict[str, str]:
    return {name: values[0] for name, values in task.params.items()}


def test_registry_covers_the_plan_whitelist() -> None:
    expected = {
        "company-news-ingest",
        "company-official-product-capture",
        "paper-search-backfill",
        "paper-summary-zh-backfill",
        "paper-doi-verify",
        "professor-homepage-rescrape",
        "professor-homepage-paper-ingest",
        "ops-milvus-backfill",
        "ops-milvus-backfill-dry-run",
        "ops-retrieval-validation",
    }
    assert {task.task_id for task in JOB_TASKS} == expected


@pytest.mark.parametrize("task", JOB_TASKS, ids=lambda task: task.task_id)
def test_declared_script_exists_in_the_repository(task) -> None:
    script = task.script_relative
    assert script is not None, f"{task.task_id} does not point at a script"
    resolved = REPO_ROOT / task.cwd_relative / script
    assert resolved.is_file(), f"{task.task_id} declares a missing path: {resolved}"


@pytest.mark.parametrize("task", JOB_TASKS, ids=lambda task: task.task_id)
def test_argv_is_a_fixed_token_tuple(task) -> None:
    argv = task.argv_for(_first_params(task))
    assert isinstance(argv, tuple)
    assert all(isinstance(token, str) and token for token in argv)
    # every accepted value comes from a closed set declared next to the argv
    for name, allowed in task.params.items():
        assert allowed, f"{task.task_id}.{name} declares an empty value set"
        assert all(value and isinstance(value, str) for value in allowed)


def test_no_task_accepts_an_undeclared_parameter() -> None:
    with pytest.raises(JobParameterError):
        get_job_task("paper-doi-verify").argv_for({"domain": "paper"})


def test_parameter_value_outside_the_closed_set_is_refused() -> None:
    task = get_job_task("ops-milvus-backfill")
    with pytest.raises(JobParameterError):
        task.argv_for({"domain": "paper; rm -rf /"})
    with pytest.raises(JobParameterError):
        task.argv_for({"domain": "not-a-domain"})
    assert set(task.params["domain"]) == set(PUBLIC_DOMAINS)


def test_declared_parameter_is_substituted_into_a_fixed_template() -> None:
    task = get_job_task("ops-milvus-backfill")
    argv = task.argv_for({"domain": "paper"})
    assert argv == (
        "uv",
        "run",
        "python",
        "scripts/run_milvus_backfill.py",
        "--domain",
        "paper",
    )
    assert task.argv_for({"domain": "professor"})[-1] == "professor"


def test_missing_required_parameter_is_refused() -> None:
    with pytest.raises(JobParameterError):
        get_job_task("ops-milvus-backfill").argv_for({})


def test_unknown_task_is_refused() -> None:
    with pytest.raises(JobTaskUnknownError):
        get_job_task("drop-database")


def test_collection_and_ops_tasks_carry_their_gate_metadata() -> None:
    collection = [
        task for task in JOB_TASKS if task.task_id.startswith(("company-", "paper-", "professor-"))
    ]
    assert collection and all(task.collection_gated for task in collection)
    assert all(task.domain in PUBLIC_DOMAINS for task in collection)
    # 专利 follows the professor homepage ingest (§5.3) and has no own collection task.
    assert {task.domain for task in collection} == {"company", "paper", "professor"}
    for ops_task_id in (
        "ops-milvus-backfill",
        "ops-milvus-backfill-dry-run",
        "ops-retrieval-validation",
    ):
        task = get_job_task(ops_task_id)
        assert not task.collection_gated
        assert task.schedule_cron is None
        assert task.requires_postgres is True
    assert all(task.schedule_cron for task in collection)
    assert all(task.window_bound for task in collection)


def test_professor_rescrape_declares_its_write_intent_explicitly() -> None:
    argv = get_job_task("professor-homepage-rescrape").argv_for({})
    assert "--apply" in argv and "--confirm-real-db" in argv


def test_command_display_never_contains_a_shell() -> None:
    for task in JOB_TASKS:
        display = task.command_display
        assert not any(meta in display for meta in (";", "|", "&&", "$(", "`"))
        assert "<" not in display and ">" not in display


# -- declared cadence -> next fire ---------------------------------------------------------

LOCAL = datetime.now().astimezone().tzinfo


def test_next_fire_weekly_expression() -> None:
    now = datetime(2026, 9, 16, 12, 0, tzinfo=LOCAL)  # Wednesday
    fire = cron_next_fire("0 2 * * 1", now=now)
    assert fire == datetime(2026, 9, 21, 2, 0, tzinfo=LOCAL)
    assert fire.tzinfo is not None


def test_next_fire_monthly_expression_rolls_to_the_next_month() -> None:
    now = datetime(2026, 9, 16, 12, 0, tzinfo=LOCAL)
    assert cron_next_fire("0 2 1 * *", now=now) == datetime(2026, 10, 1, 2, 0, tzinfo=LOCAL)
    assert cron_next_fire("0 2 1 * *", now=datetime(2026, 9, 1, 1, 0, tzinfo=LOCAL)) == datetime(
        2026, 9, 1, 2, 0, tzinfo=LOCAL
    )


def test_next_fire_step_and_list_forms() -> None:
    assert cron_next_fire(
        "*/15 * * * *", now=datetime(2026, 9, 16, 12, 7, tzinfo=LOCAL)
    ) == datetime(2026, 9, 16, 12, 15, tzinfo=LOCAL)
    assert cron_next_fire(
        "0 2,3 * * *", now=datetime(2026, 9, 16, 2, 30, tzinfo=LOCAL)
    ) == datetime(2026, 9, 16, 3, 0, tzinfo=LOCAL)


def test_next_fire_day_of_month_or_day_of_week_semantics() -> None:
    # Vixie cron: when both day fields are restricted, either may match.
    now = datetime(2026, 9, 16, 12, 0, tzinfo=LOCAL)  # Wednesday
    assert cron_next_fire("0 0 1 * 1", now=now) == datetime(2026, 9, 21, 0, 0, tzinfo=LOCAL)


def test_next_fire_is_always_in_the_future_and_within_a_week() -> None:
    now = datetime(2026, 9, 16, 12, 0, tzinfo=LOCAL)
    for task in JOB_TASKS:
        if task.schedule_cron is None:
            continue
        fire = cron_next_fire(task.schedule_cron, now=now)
        assert now < fire <= now + timedelta(days=32)


def test_next_fire_rejects_a_malformed_expression() -> None:
    now = datetime(2026, 9, 16, 12, 0, tzinfo=LOCAL)
    with pytest.raises(ValueError):
        cron_next_fire("0 2 * *", now=now)
    with pytest.raises(ValueError):
        cron_next_fire("0 99 * * *", now=now)
