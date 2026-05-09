from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi import HTTPException

from backend.api import pipeline

RUN_ID = UUID("22222222-2222-2222-2222-222222222222")
PAGE_ID = UUID("33333333-3333-3333-3333-333333333333")
CHILD_RUN_ID = UUID("44444444-4444-4444-4444-444444444444")


class _Result:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetchall(self) -> list[dict]:
        return self._rows

    def fetchone(self) -> dict | None:
        return self._rows[0] if self._rows else None


class _PipelineConn:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.params: list[object] = []
        self.commit_count = 0
        now = datetime(2026, 5, 4, 11, 0, tzinfo=timezone.utc)
        self.run_row = {
            "run_id": RUN_ID,
            "run_kind": "import_xlsx",
            "status": "succeeded",
            "run_scope": {"domain": "company", "source": "admin-console-upload"},
            "triggered_by": "admin-console",
            "started_at": now,
            "finished_at": now,
            "items_processed": 1025,
            "items_failed": 0,
            "error_summary": None,
            "total_count": 1,
        }
        self.page_row = {
            "page_id": PAGE_ID,
            "url": "admin-upload://company/hash",
            "title": "company.xlsx",
            "clean_text_path": "/tmp/company.xlsx",
            "fetched_at": now,
        }

    def execute(self, query: str, params: object = None) -> _Result:
        self.queries.append(query)
        self.params.append(params)
        sql = " ".join(query.split()).lower()
        if "insert into pipeline_run" in sql:
            return _Result([{"run_id": CHILD_RUN_ID}])
        if "from pipeline_run" in sql and "count(*) over" in sql:
            return _Result([self.run_row])
        if "from pipeline_run" in sql:
            return _Result([self.run_row])
        if "from source_page" in sql:
            return _Result([self.page_row])
        raise AssertionError(f"Unexpected query: {query}")

    def commit(self) -> None:
        self.commit_count += 1


def test_list_pipeline_runs_returns_recent_runs() -> None:
    conn = _PipelineConn()
    response = pipeline.list_pipeline_runs(
        domain="company",
        triggered_by="admin-console",
        limit=10,
        conn=conn,
    )

    assert response.total == 1
    assert response.items[0].run_id == str(RUN_ID)
    assert response.items[0].run_scope["domain"] == "company"
    assert response.items[0].items_processed == 1025
    assert "%(domain)s::text IS NULL" in conn.queries[0]


def test_get_pipeline_run_returns_source_pages() -> None:
    response = pipeline.get_pipeline_run(run_id=RUN_ID, conn=_PipelineConn())

    assert response.run_id == str(RUN_ID)
    assert response.source_pages[0].page_id == str(PAGE_ID)
    assert response.source_pages[0].url == "admin-upload://company/hash"


def test_get_pipeline_run_404_when_missing() -> None:
    class EmptyConn(_PipelineConn):
        def execute(self, query: str, params: object = None) -> _Result:
            if "FROM pipeline_run" in query or "from pipeline_run" in query:
                return _Result([])
            return super().execute(query, params)

    with pytest.raises(HTTPException) as exc:
        pipeline.get_pipeline_run(run_id=RUN_ID, conn=EmptyConn())

    assert exc.value.status_code == 404


class _CreatedTask:
    def add_done_callback(self, callback: object) -> None:
        self.callback = callback


def test_trigger_milvus_backfill_creates_child_run_and_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_coroutines: list[object] = []

    def fake_create_task(coroutine: object) -> _CreatedTask:
        created_coroutines.append(coroutine)
        close = getattr(coroutine, "close", None)
        if callable(close):
            close()
        return _CreatedTask()

    monkeypatch.setattr(pipeline.asyncio, "create_task", fake_create_task)

    conn = _PipelineConn()
    response = asyncio.run(
        pipeline.trigger_milvus_backfill(run_id=RUN_ID, conn=conn)
    )

    assert response.status == "scheduled"
    assert response.domain == "company"
    assert response.task_id == str(CHILD_RUN_ID)
    assert created_coroutines
    assert conn.commit_count == 1

    insert_params = next(
        params
        for query, params in zip(conn.queries, conn.params, strict=False)
        if "INSERT INTO pipeline_run" in query
    )
    assert insert_params[0] == "backfill_real"
    assert insert_params[3] == RUN_ID
    assert insert_params[4] == "admin-console"
    assert '"action": "milvus_backfill"' in insert_params[1]
    assert '"domain": "company"' in insert_params[1]


def test_trigger_milvus_backfill_can_schedule_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_coroutines: list[object] = []

    def fake_create_task(coroutine: object) -> _CreatedTask:
        created_coroutines.append(coroutine)
        close = getattr(coroutine, "close", None)
        if callable(close):
            close()
        return _CreatedTask()

    monkeypatch.setattr(pipeline.asyncio, "create_task", fake_create_task)

    conn = _PipelineConn()
    response = asyncio.run(
        pipeline.trigger_milvus_backfill(run_id=RUN_ID, dry_run=True, conn=conn)
    )

    assert response.status == "scheduled"
    assert created_coroutines
    insert_params = next(
        params
        for query, params in zip(conn.queries, conn.params, strict=False)
        if "INSERT INTO pipeline_run" in query
    )
    assert '"dry_run": true' in insert_params[1]


def test_trigger_retrieval_validation_creates_child_run_and_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_coroutines: list[object] = []

    def fake_create_task(coroutine: object) -> _CreatedTask:
        created_coroutines.append(coroutine)
        close = getattr(coroutine, "close", None)
        if callable(close):
            close()
        return _CreatedTask()

    monkeypatch.setattr(pipeline.asyncio, "create_task", fake_create_task)

    conn = _PipelineConn()
    response = asyncio.run(
        pipeline.trigger_retrieval_validation(run_id=RUN_ID, conn=conn)
    )

    assert response.status == "scheduled"
    assert response.domain == "company"
    assert response.task_id == str(CHILD_RUN_ID)
    assert response.parent_run_id == str(RUN_ID)
    assert created_coroutines
    assert conn.commit_count == 1

    insert_params = next(
        params
        for query, params in zip(conn.queries, conn.params, strict=False)
        if "INSERT INTO pipeline_run" in query
    )
    assert insert_params[0] == "answer_readiness_eval"
    assert '"action": "retrieval_validation"' in insert_params[1]
    assert f'"parent_run_id": "{RUN_ID}"' in insert_params[1]
    assert '"domain": "company"' in insert_params[1]


def test_trigger_retrieval_validation_rejects_non_import_runs() -> None:
    conn = _PipelineConn()
    conn.run_row["run_kind"] = "backfill_real"
    conn.run_row["run_scope"] = {"domain": "company", "action": "milvus_backfill"}

    with pytest.raises(HTTPException) as exc:
        asyncio.run(pipeline.trigger_retrieval_validation(run_id=RUN_ID, conn=conn))

    assert exc.value.status_code == 400


def test_trigger_retrieval_validation_rejects_running_import() -> None:
    conn = _PipelineConn()
    conn.run_row["status"] = "running"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(pipeline.trigger_retrieval_validation(run_id=RUN_ID, conn=conn))

    assert exc.value.status_code == 400


def test_parse_retrieval_validation_log_summarizes_result_and_gates() -> None:
    report = pipeline._parse_retrieval_validation_log(
        """
## HTTP chat E2E
### B-company
http_status=200
query_type= B_company_topic_search
answer_style= template
citations_count= 2
### C-followup-company
http_status=200
query_type= C_cross_domain_related
answer_style= template
citations_count= 0
## Done
log_file=/tmp/host-e2e-agentic-rag.txt
failures=0
result=PASS
"""
    )

    assert report["result"] == "PASS"
    assert report["failures"] == 0
    assert report["gates"] == [
        {
            "label": "B-company",
            "http_status": "200",
            "query_type": "B_company_topic_search",
            "answer_style": "template",
            "citations_count": 2,
        },
        {
            "label": "C-followup-company",
            "http_status": "200",
            "query_type": "C_cross_domain_related",
            "answer_style": "template",
            "citations_count": 0,
        },
    ]


def test_run_milvus_backfill_command_passes_dry_run_to_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Completed:
        returncode = 0
        stdout = '{"row_count": 10}'
        stderr = ""

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    summary = pipeline._run_milvus_backfill_command(domain="company", dry_run=True)

    assert summary["returncode"] == 0
    assert "--dry-run" in captured["command"]


def test_trigger_milvus_backfill_rejects_run_without_domain() -> None:
    conn = _PipelineConn()
    conn.run_row["run_scope"] = {"source": "admin-console-upload"}

    with pytest.raises(HTTPException) as exc:
        asyncio.run(pipeline.trigger_milvus_backfill(run_id=RUN_ID, conn=conn))

    assert exc.value.status_code == 400
