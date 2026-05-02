from __future__ import annotations

import io
import logging
import asyncio
from uuid import UUID

import pytest
from fastapi import UploadFile

from backend.api import upload

RUN_ID = UUID("22222222-2222-2222-2222-222222222222")
PAGE_ID = UUID("33333333-3333-3333-3333-333333333333")


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetchone(self) -> dict | None:
        return self._rows[0] if self._rows else None


class _FakeUploadConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = None) -> _FakeResult:
        sql = " ".join(query.split())
        self.calls.append((sql, params))
        sql_lower = sql.lower()
        if sql_lower.startswith("insert into pipeline_run"):
            return _FakeResult([{"run_id": RUN_ID}])
        if sql_lower.startswith("insert into source_page"):
            return _FakeResult([{"page_id": PAGE_ID}])
        if sql_lower.startswith("select count"):
            return _FakeResult([{"total": 7}])
        raise AssertionError(f"Unexpected SQL: {sql}")


class _DummyTask:
    def add_done_callback(self, callback):
        self.callback = callback

    def result(self) -> None:
        return None


def test_upload_records_source_page_and_schedules_async_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    created_coroutines = []

    def fake_create_task(coro):
        created_coroutines.append(coro)
        coro.close()
        return _DummyTask()

    monkeypatch.setattr(upload.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(upload.tempfile, "gettempdir", lambda: str(tmp_path))
    conn = _FakeUploadConn()

    response = asyncio.run(
        upload._handle_upload(
            domain="paper",
            file=UploadFile(file=io.BytesIO(b"xlsx bytes"), filename="paper.xlsx"),
            conn=conn,
        )
    )

    assert response.task_id == str(RUN_ID)
    assert response.source_page_id == str(PAGE_ID)
    assert response.imported == 0
    assert response.total_in_store == 7
    assert len(created_coroutines) == 1

    source_page_call = next(call for call in conn.calls if "INSERT INTO source_page" in call[0])
    params = source_page_call[1]
    assert isinstance(params, dict)
    assert params["url"].startswith("admin-upload://paper/")
    assert params["filename"] == "paper.xlsx"
    assert params["task_id"] == RUN_ID


def test_upload_pipeline_task_logs_failure_without_reraising(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path,
) -> None:
    closed_runs = []

    async def fail_dispatch(**kwargs) -> None:
        raise RuntimeError("pipeline boom")

    def fake_close_background_run(task_id, *, status, error_summary=None) -> None:
        closed_runs.append((task_id, status, error_summary))

    monkeypatch.setattr(upload, "_dispatch_upload_pipeline", fail_dispatch)
    monkeypatch.setattr(upload, "_close_background_run", fake_close_background_run)

    with caplog.at_level(logging.ERROR):
        asyncio.run(
            upload._run_upload_pipeline_task(
                task_id=RUN_ID,
                domain="paper",
                source_page_id=PAGE_ID,
                upload_path=tmp_path / "paper.xlsx",
            )
        )

    assert closed_runs == [
        (RUN_ID, "failed", {"message": "pipeline boom"}),
    ]
    assert "Admin upload pipeline task failed" in caplog.text
