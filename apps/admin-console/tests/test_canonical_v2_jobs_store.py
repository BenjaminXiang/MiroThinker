"""R2 — serving-side job run history: persistence, queries, breaker bookkeeping, hygiene.

Locks: run rows round-trip, skip rows carry their reason and operator, history filters/order,
per-task summaries drive the red dot, consecutive-failure bookkeeping opens the breaker, reopen is
idempotent, excerpts are bounded and credential-redacted, and no environment/secret is persisted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.data_agents.canonical_v2.jobs import JobRunStore, redact_secrets


SECRET = "sk-live-9f8e7d6c5b4a3210"


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 14, 1, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture()
def store(tmp_path: Path) -> JobRunStore:
    instance = JobRunStore(tmp_path / "jobs.sqlite3", clock=_Clock())
    yield instance
    instance.close()


def test_run_round_trip_records_status_duration_and_counts(store: JobRunStore) -> None:
    run_id = store.start_run(
        task_id="company-news-ingest",
        trigger_source="manual",
        operator="alice",
        window_bound=True,
        inside_window=False,
    )
    running = store.run(run_id)
    assert running is not None
    assert running.status == "running"
    assert running.finished_at is None
    assert running.operator == "alice"
    assert running.window_bound is True
    assert running.inside_window is False

    store.finish_run(
        run_id,
        status="succeeded",
        duration_ms=1234,
        exit_code=0,
        items_processed=3,
        items_failed=0,
        summary={"job_summary": {"items_processed": 3}},
        stdout="done\n",
        stderr="",
    )
    finished = store.run(run_id)
    assert finished is not None
    assert (finished.status, finished.duration_ms, finished.exit_code) == (
        "succeeded",
        1234,
        0,
    )
    assert finished.items_processed == 3
    assert finished.items_failed == 0
    assert finished.summary == {"job_summary": {"items_processed": 3}}
    assert finished.finished_at is not None


def test_skip_row_carries_reason_and_operator(store: JobRunStore) -> None:
    run_id = store.record_skip(
        task_id="paper-doi-verify",
        trigger_source="manual",
        operator="bob",
        reason="switch_off",
        window_bound=True,
    )
    row = store.run(run_id)
    assert row is not None
    assert row.status == "skipped"
    assert row.skip_reason == "switch_off"
    assert row.operator == "bob"
    assert row.finished_at is not None
    assert row.exit_code is None


def test_history_filters_orders_and_paginates(store: JobRunStore) -> None:
    for index in range(3):
        run_id = store.start_run(
            task_id="paper-doi-verify",
            trigger_source="manual",
            operator="alice",
        )
        store.finish_run(
            run_id,
            status="failed" if index == 0 else "succeeded",
            duration_ms=10 + index,
            exit_code=1 if index == 0 else 0,
        )
    other = store.start_run(
        task_id="company-news-ingest", trigger_source="manual", operator="alice"
    )
    store.finish_run(other, status="succeeded", duration_ms=5, exit_code=0)

    history = store.history(task_id="paper-doi-verify", limit=10)
    assert [row.task_id for row in history] == ["paper-doi-verify"] * 3
    assert history == tuple(sorted(history, key=lambda row: row.started_at, reverse=True))

    failures = store.history(task_id="paper-doi-verify", status="failed")
    assert len(failures) == 1 and failures[0].status == "failed"

    assert len(store.history(limit=2)) == 2
    assert len(store.history(offset=3)) == 1
    assert store.total() == 4
    assert store.total(task_id="paper-doi-verify") == 3
    assert store.total(status="failed") == 1


def test_summaries_report_red_dot_and_breaker_state(store: JobRunStore) -> None:
    ok_run = store.start_run(
        task_id="paper-doi-verify", trigger_source="manual", operator="alice"
    )
    store.finish_run(ok_run, status="failed", duration_ms=10, exit_code=1)
    summaries = store.summaries(["paper-doi-verify", "company-news-ingest"])
    assert summaries["paper-doi-verify"].failure_flag is True
    assert summaries["paper-doi-verify"].last_run is not None
    assert summaries["paper-doi-verify"].state.consecutive_failures == 1
    assert summaries["company-news-ingest"].failure_flag is False
    assert summaries["company-news-ingest"].last_run is None


def test_two_consecutive_failures_open_the_breaker_and_success_resets(store: JobRunStore) -> None:
    for _ in range(2):
        run_id = store.start_run(
            task_id="paper-doi-verify", trigger_source="schedule", operator="anonymous"
        )
        store.finish_run(run_id, status="failed", duration_ms=10, exit_code=1)
    state = store.task_state("paper-doi-verify")
    assert state.consecutive_failures == 2
    assert state.breaker_open is True
    assert state.breaker_opened_at is not None
    assert store.summaries(["paper-doi-verify"])["paper-doi-verify"].failure_flag is True

    recovery = store.start_run(
        task_id="paper-doi-verify", trigger_source="manual", operator="carol"
    )
    store.finish_run(recovery, status="succeeded", duration_ms=10, exit_code=0)
    state = store.task_state("paper-doi-verify")
    assert state.consecutive_failures == 0
    assert state.breaker_open is False
    assert state.last_success_at is not None


def test_skipped_runs_do_not_touch_the_breaker(store: JobRunStore) -> None:
    store.record_skip(
        task_id="paper-doi-verify",
        trigger_source="manual",
        operator="alice",
        reason="quota_exhausted",
    )
    state = store.task_state("paper-doi-verify")
    assert state.consecutive_failures == 0
    assert state.breaker_open is False


def test_breaker_reset_is_visible_in_history(store: JobRunStore) -> None:
    for _ in range(2):
        run_id = store.start_run(
            task_id="paper-doi-verify", trigger_source="manual", operator="alice"
        )
        store.finish_run(run_id, status="failed", duration_ms=10, exit_code=1)
    store.record_breaker_reset(task_id="paper-doi-verify", operator="dave")
    state = store.task_state("paper-doi-verify")
    assert state.breaker_open is False
    assert state.consecutive_failures == 0
    reset_rows = [
        row
        for row in store.history(task_id="paper-doi-verify", limit=10)
        if row.status == "breaker_reset"
    ]
    assert reset_rows and reset_rows[0].operator == "dave"


def test_reopening_the_store_keeps_history(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite3"
    first = JobRunStore(path)
    run_id = first.start_run(
        task_id="paper-doi-verify", trigger_source="manual", operator="alice"
    )
    first.finish_run(run_id, status="succeeded", duration_ms=7, exit_code=0, items_processed=2)
    first.close()

    second = JobRunStore(path)
    row = second.run(run_id)
    assert row is not None
    assert row.items_processed == 2
    assert row.status == "succeeded"
    second.close()


def test_symlinked_database_path_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "real.sqlite3"
    target.write_bytes(b"")
    link = tmp_path / "jobs.sqlite3"
    link.symlink_to(target)
    with pytest.raises(OSError):
        JobRunStore(link)


def test_excerpts_are_bounded_and_redacted(store: JobRunStore) -> None:
    run_id = store.start_run(
        task_id="paper-doi-verify", trigger_source="manual", operator="alice"
    )
    store.finish_run(
        run_id,
        status="failed",
        duration_ms=10,
        exit_code=1,
        stdout=("line\n" * 4000) + f"api_key={SECRET}\n",
        stderr=f"Traceback ...\nAuthorization: Bearer {SECRET}\n" + ("x" * 20000),
        summary={"job_summary": {"api_key": SECRET}},
    )
    row = store.run(run_id)
    assert row is not None
    payload = row.as_dict(include_samples=True)
    assert len(payload["stdout_excerpt"]) <= 4001
    assert len(payload["stderr_excerpt"]) <= 4001
    assert SECRET not in payload["stdout_excerpt"]
    assert SECRET not in payload["stderr_excerpt"]
    assert "[redacted]" in payload["stdout_excerpt"]
    assert SECRET not in str(payload["summary"])
    assert store.database_path.read_bytes().find(SECRET.encode()) == -1


def test_redact_secrets_keeps_ordinary_text_intact() -> None:
    text = "processed 12 papers\nstatus=ok\n"
    assert redact_secrets(text) == text
    assert SECRET not in redact_secrets(f'{{"api_key": "{SECRET}"}}')
