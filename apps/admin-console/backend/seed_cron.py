from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.api.seeds import (
    _schedule_seed_run,
    shutdown_seed_run_executor,
    trigger_seed_run,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SeedCronReport:
    enqueued_seed_ids: list[int]
    skipped_count: int
    failed_seed_ids: list[int]


TriggerSeed = Callable[..., dict[str, Any]]


def enqueue_due_seed_runs(
    conn: Any,
    *,
    trigger_seed: TriggerSeed = trigger_seed_run,
    schedule_seed_run: Callable[..., None] = _schedule_seed_run,
) -> SeedCronReport:
    rows = conn.execute(
        """
        SELECT id
          FROM professor_seed
         ORDER BY id ASC
        """
    ).fetchall()
    seed_ids = [int(row["id"] if isinstance(row, dict) else row[0]) for row in rows]
    eligible_rows = conn.execute(
        """
        SELECT id
          FROM professor_seed
         WHERE last_run_status NOT IN ('in_progress', 'adapter_missing')
         ORDER BY id ASC
        """
    ).fetchall()
    eligible_seed_ids = [
        int(row["id"] if isinstance(row, dict) else row[0]) for row in eligible_rows
    ]

    enqueued: list[int] = []
    failed: list[int] = []
    for seed_id in eligible_seed_ids:
        try:
            outcome = trigger_seed(
                conn,
                seed_id,
                schedule_seed_run=schedule_seed_run,
            )
        except Exception:
            logger.exception("Professor seed cron trigger failed for seed %s", seed_id)
            failed.append(seed_id)
            continue
        if int(outcome.get("status_code") or 0) == 202:
            enqueued.append(seed_id)
        else:
            failed.append(seed_id)

    return SeedCronReport(
        enqueued_seed_ids=enqueued,
        skipped_count=max(0, len(seed_ids) - len(eligible_seed_ids)),
        failed_seed_ids=failed,
    )


def run_monthly_seed_cron() -> SeedCronReport:
    from backend.deps import get_pg_pool

    pool = get_pg_pool()
    with pool.connection() as conn:
        return enqueue_due_seed_runs(conn)


def start_seed_cron_scheduler() -> BackgroundScheduler | None:
    if not _cron_enabled():
        logger.info("Professor seed cron disabled")
        return None
    scheduler = BackgroundScheduler(timezone=_cron_timezone())
    scheduler.add_job(
        run_monthly_seed_cron,
        trigger=CronTrigger(
            day=_cron_day(),
            hour=_cron_hour(),
            minute=_cron_minute(),
            timezone=_cron_timezone(),
        ),
        id="professor_seed_monthly_recrawl",
        name="Professor seed monthly recrawl",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(
        "Professor seed cron started: day=%s hour=%s minute=%s timezone=%s",
        _cron_day(),
        _cron_hour(),
        _cron_minute(),
        _cron_timezone(),
    )
    return scheduler


def shutdown_seed_cron_scheduler(scheduler: BackgroundScheduler | None) -> None:
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
    shutdown_seed_run_executor()


def _cron_enabled() -> bool:
    raw = os.environ.get("ADMIN_PROFESSOR_SEED_CRON_ENABLED", "1")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _cron_day() -> str:
    return os.environ.get("ADMIN_PROFESSOR_SEED_CRON_DAY", "1")


def _cron_hour() -> int:
    return _int_env("ADMIN_PROFESSOR_SEED_CRON_HOUR", 2)


def _cron_minute() -> int:
    return _int_env("ADMIN_PROFESSOR_SEED_CRON_MINUTE", 0)


def _cron_timezone() -> str:
    return os.environ.get("ADMIN_PROFESSOR_SEED_CRON_TIMEZONE", "Etc/UTC")


def _int_env(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using %d", key, raw, default)
        return default
