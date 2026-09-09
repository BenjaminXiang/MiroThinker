from __future__ import annotations

from typing import Any

import psycopg

from backend.seed_cron import (
    enqueue_due_seed_runs,
    shutdown_seed_cron_scheduler,
    start_seed_cron_scheduler,
)


def _pg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def _wipe_seeds(dsn: str) -> None:
    with psycopg.connect(_pg_dsn(dsn)) as conn:
        conn.execute("DELETE FROM professor_seed")
        conn.commit()


def _insert_seed(conn: Any, *, status: str, suffix: str) -> int:
    row = conn.execute(
        """
        INSERT INTO professor_seed (school, department, seed_url, last_run_status)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (
            "SUSTech",
            None,
            f"https://www.sustech.edu.cn/zh/letter/{suffix}",
            status,
        ),
    ).fetchone()
    return int(row[0])


def test_enqueue_due_seed_runs_skips_blocked_statuses_in_id_order(
    postgres_data_ready: str,
) -> None:
    _wipe_seeds(postgres_data_ready)
    triggered: list[int] = []
    with psycopg.connect(_pg_dsn(postgres_data_ready)) as conn:
        never_run = _insert_seed(conn, status="never_run", suffix="a")
        in_progress = _insert_seed(conn, status="in_progress", suffix="b")
        success = _insert_seed(conn, status="success", suffix="c")
        adapter_missing = _insert_seed(conn, status="adapter_missing", suffix="d")
        failure = _insert_seed(conn, status="failure", suffix="e")
        conn.commit()

        def fake_trigger(conn: Any, seed_id: int, *, schedule_seed_run: Any) -> dict[str, Any]:
            del conn, schedule_seed_run
            triggered.append(seed_id)
            return {
                "status_code": 202,
                "content": {
                    "seed_id": seed_id,
                    "run_id": f"run-{seed_id}",
                    "status": "in_progress",
                },
            }

        report = enqueue_due_seed_runs(conn, trigger_seed=fake_trigger)

    assert triggered == [never_run, success, failure]
    assert in_progress not in triggered
    assert adapter_missing not in triggered
    assert report.enqueued_seed_ids == [never_run, success, failure]
    assert report.skipped_count == 2


def test_seed_cron_scheduler_respects_disabled_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("ADMIN_PROFESSOR_SEED_CRON_ENABLED", "0")

    assert start_seed_cron_scheduler() is None


def test_seed_cron_scheduler_uses_schedule_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("ADMIN_PROFESSOR_SEED_CRON_ENABLED", "1")
    monkeypatch.setenv("ADMIN_PROFESSOR_SEED_CRON_DAY", "15")
    monkeypatch.setenv("ADMIN_PROFESSOR_SEED_CRON_HOUR", "3")
    monkeypatch.setenv("ADMIN_PROFESSOR_SEED_CRON_MINUTE", "7")
    monkeypatch.setenv("ADMIN_PROFESSOR_SEED_CRON_TIMEZONE", "Etc/UTC")

    scheduler = start_seed_cron_scheduler()
    try:
        assert scheduler is not None
        job = scheduler.get_job("professor_seed_monthly_recrawl")
        assert job is not None
        assert job.coalesce is True
        assert job.max_instances == 1
        trigger_text = str(job.trigger)
        assert "day='15'" in trigger_text
        assert "hour='3'" in trigger_text
        assert "minute='7'" in trigger_text
    finally:
        shutdown_seed_cron_scheduler(scheduler)
