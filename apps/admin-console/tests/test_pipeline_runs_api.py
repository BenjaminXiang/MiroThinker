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
BATCH_ID = UUID("55555555-5555-5555-5555-555555555555")


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
        if "from company_enrichment_batch" in sql:
            return _Result([])
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


def test_get_pipeline_run_returns_company_enrichment_batch_status() -> None:
    now = datetime(2026, 5, 4, 11, 5, tzinfo=timezone.utc)

    class EnrichmentConn(_PipelineConn):
        def execute(self, query: str, params: object = None) -> _Result:
            sql = " ".join(query.split()).lower()
            if "from company_enrichment_batch" in sql:
                return _Result(
                    [
                        {
                            "batch_id": BATCH_ID,
                            "status": "running",
                            "current_stage": "generic_web_source_judgment",
                            "companies_total": 100,
                            "companies_selected": 100,
                            "companies_processed": 37,
                            "companies_succeeded": 35,
                            "companies_failed": 2,
                            "query_count": 12,
                            "source_result_count": 44,
                            "accepted_source_count": 8,
                            "rejected_source_count": 16,
                            "product_count": 6,
                            "scenario_count": 3,
                            "official_product_count": 2,
                            "funding_event_count": 4,
                            "vector_refreshed_count": 35,
                            "llm_failure_count": 1,
                            "status_counts": {"succeeded": 35, "failed": 2},
                            "current_stage_counts": {
                                "generic_web_source_judgment": 37
                            },
                            "miss_reasons": {"no_results": 5},
                            "official_failure_reasons": {"http_403": 2},
                            "rejected_candidate_reasons": {
                                "candidate_belongs_to_other_company": 4
                            },
                            "source_counts_by_adapter": {
                                "iyiou": {
                                    "query_count": 3,
                                    "result_count": 20,
                                    "accepted_count": 5,
                                    "rejected_count": 7,
                                }
                            },
                            "company_diagnostics": [
                                {
                                    "company_id": "COMP-001",
                                    "status": "partial",
                                    "current_stage": "source_product_extract",
                                    "miss_reason": "synthesis_no_facts",
                                    "last_error": None,
                                    "query_count": 3,
                                    "source_result_count": 20,
                                    "accepted_source_count": 5,
                                    "rejected_source_count": 7,
                                    "product_count": 0,
                                    "scenario_count": 0,
                                    "official_product_count": 0,
                                    "funding_event_count": 1,
                                    "vector_refreshed": False,
                                    "stage_status": {
                                        "official_product_capture": {
                                            "miss_reason": "http_403"
                                        }
                                    },
                                    "updated_at": now,
                                }
                            ],
                            "company_diagnostics_truncated": False,
                            "last_error": "fetch timeout",
                            "runner_pid": 4321,
                            "runner_log_path": "/var/log/company-batch.log",
                            "runner_heartbeat_at": now,
                            "runner_last_seen_at": now,
                            "last_completed_company_id": "COMP-001",
                            "miss_reason_buckets": {
                                "no_search_results": 5,
                                "webpage_unavailable": 2,
                            },
                            "quality_report": {
                                "headline": "35/100 companies completed",
                                "sample_company_ids": ["COMP-001"],
                            },
                            "created_at": now,
                            "started_at": now,
                            "finished_at": None,
                            "updated_at": now,
                        }
                    ]
                )
            return super().execute(query, params)

    response = pipeline.get_pipeline_run(run_id=RUN_ID, conn=EnrichmentConn())

    assert response.company_enrichment_batches[0].batch_id == str(BATCH_ID)
    assert response.company_enrichment_batches[0].status == "running"
    assert (
        response.company_enrichment_batches[0].current_stage
        == "generic_web_source_judgment"
    )
    assert response.company_enrichment_batches[0].companies_selected == 100
    assert response.company_enrichment_batches[0].companies_processed == 37
    assert response.company_enrichment_batches[0].companies_succeeded == 35
    assert response.company_enrichment_batches[0].companies_failed == 2
    assert response.company_enrichment_batches[0].query_count == 12
    assert response.company_enrichment_batches[0].source_result_count == 44
    assert response.company_enrichment_batches[0].accepted_source_count == 8
    assert response.company_enrichment_batches[0].rejected_source_count == 16
    assert response.company_enrichment_batches[0].product_count == 6
    assert response.company_enrichment_batches[0].scenario_count == 3
    assert response.company_enrichment_batches[0].official_product_count == 2
    assert response.company_enrichment_batches[0].funding_event_count == 4
    assert response.company_enrichment_batches[0].vector_refreshed_count == 35
    assert response.company_enrichment_batches[0].llm_failure_count == 1
    assert response.company_enrichment_batches[0].status_counts == {
        "succeeded": 35,
        "failed": 2,
    }
    assert response.company_enrichment_batches[0].current_stage_counts == {
        "generic_web_source_judgment": 37
    }
    assert response.company_enrichment_batches[0].miss_reasons == {"no_results": 5}
    assert response.company_enrichment_batches[0].official_failure_reasons == {
        "http_403": 2
    }
    assert response.company_enrichment_batches[0].rejected_candidate_reasons == {
        "candidate_belongs_to_other_company": 4
    }
    assert response.company_enrichment_batches[0].source_counts_by_adapter == {
        "iyiou": {
            "query_count": 3,
            "result_count": 20,
            "accepted_count": 5,
            "rejected_count": 7,
        }
    }
    assert (
        response.company_enrichment_batches[0].company_diagnostics[0].company_id
        == "COMP-001"
    )
    assert (
        response.company_enrichment_batches[0]
        .company_diagnostics[0]
        .stage_status["official_product_capture"]["miss_reason"]
        == "http_403"
    )
    assert not response.company_enrichment_batches[0].company_diagnostics_truncated
    assert response.company_enrichment_batches[0].last_error == "fetch timeout"
    assert response.company_enrichment_batches[0].runner_pid == 4321
    assert (
        response.company_enrichment_batches[0].runner_log_path
        == "/var/log/company-batch.log"
    )
    assert response.company_enrichment_batches[0].last_completed_company_id == "COMP-001"
    assert response.company_enrichment_batches[0].miss_reason_buckets == {
        "no_search_results": 5,
        "webpage_unavailable": 2,
    }
    assert response.company_enrichment_batches[0].quality_report["headline"] == (
        "35/100 companies completed"
    )


def test_get_company_enrichment_batch_returns_progress_percent() -> None:
    now = datetime(2026, 5, 4, 11, 5, tzinfo=timezone.utc)

    class BatchConn(_PipelineConn):
        def execute(self, query: str, params: object = None) -> _Result:
            sql = " ".join(query.split()).lower()
            if "from company_enrichment_batch" in sql:
                return _Result(
                    [
                        {
                            "batch_id": BATCH_ID,
                            "status": "queued",
                            "current_stage": "queued",
                            "companies_total": 100,
                            "companies_selected": 80,
                            "companies_processed": 20,
                            "companies_succeeded": 18,
                            "companies_failed": 2,
                            "query_count": 0,
                            "source_result_count": 0,
                            "accepted_source_count": 0,
                            "rejected_source_count": 0,
                            "product_count": 0,
                            "scenario_count": 0,
                            "official_product_count": 0,
                            "funding_event_count": 0,
                            "vector_refreshed_count": 0,
                            "llm_failure_count": 0,
                            "status_counts": {"succeeded": 18, "failed": 2},
                            "current_stage_counts": {"queued": 60},
                            "miss_reasons": {"no_results": 2},
                            "official_failure_reasons": {},
                            "rejected_candidate_reasons": {},
                            "source_counts_by_adapter": {},
                            "company_diagnostics": [],
                            "company_diagnostics_truncated": False,
                            "last_error": None,
                            "runner_pid": None,
                            "runner_log_path": None,
                            "runner_heartbeat_at": None,
                            "runner_last_seen_at": None,
                            "last_completed_company_id": None,
                            "miss_reason_buckets": {"no_search_results": 2},
                            "quality_report": {},
                            "created_at": now,
                            "started_at": None,
                            "finished_at": None,
                            "updated_at": now,
                        }
                    ]
                )
            return super().execute(query, params)

    response = pipeline.get_company_enrichment_batch(
        batch_id=BATCH_ID,
        conn=BatchConn(),
    )

    assert response.batch_id == str(BATCH_ID)
    assert response.progress_percent == 25.0
    assert response.companies_processed == 20
    assert response.companies_selected == 80
    assert response.miss_reason_buckets == {"no_search_results": 2}


def test_get_company_enrichment_batch_uses_same_rollup_sql_as_pipeline_detail() -> None:
    now = datetime(2026, 5, 4, 11, 5, tzinfo=timezone.utc)

    class BatchConn(_PipelineConn):
        def execute(self, query: str, params: object = None) -> _Result:
            sql = " ".join(query.split()).lower()
            self.queries.append(query)
            self.params.append(params)
            if "from company_enrichment_batch" in sql:
                return _Result(
                    [
                        {
                            "batch_id": BATCH_ID,
                            "status": "running",
                            "current_stage": "news_iyiou",
                            "companies_total": 10,
                            "companies_selected": 10,
                            "companies_processed": 3,
                            "companies_succeeded": 2,
                            "companies_failed": 1,
                            "query_count": 5,
                            "source_result_count": 20,
                            "accepted_source_count": 4,
                            "rejected_source_count": 6,
                            "product_count": 1,
                            "scenario_count": 1,
                            "official_product_count": 0,
                            "funding_event_count": 2,
                            "vector_refreshed_count": 0,
                            "llm_failure_count": 1,
                            "status_counts": {"partial": 3},
                            "current_stage_counts": {"news_iyiou": 3},
                            "miss_reasons": {"all_results_rejected": 2},
                            "official_failure_reasons": {"timeout": 1},
                            "rejected_candidate_reasons": {
                                "candidate_belongs_to_other_company": 2
                            },
                            "source_counts_by_adapter": {
                                "pitchhub_36kr": {
                                    "query_count": 2,
                                    "result_count": 8,
                                    "accepted_count": 1,
                                    "rejected_count": 4,
                                }
                            },
                            "company_diagnostics": [],
                            "company_diagnostics_truncated": False,
                            "last_error": None,
                            "runner_pid": 6789,
                            "runner_log_path": "/tmp/company-batch.log",
                            "runner_heartbeat_at": now,
                            "runner_last_seen_at": now,
                            "last_completed_company_id": "COMP-003",
                            "miss_reason_buckets": {},
                            "quality_report": {},
                            "created_at": now,
                            "started_at": now,
                            "finished_at": None,
                            "updated_at": now,
                        }
                    ]
                )
            return super().execute(query, params)

    conn = BatchConn()
    response = pipeline.get_company_enrichment_batch(batch_id=BATCH_ID, conn=conn)
    compact_sql = " ".join(conn.queries[0].split()).lower()

    assert response.source_counts_by_adapter["pitchhub_36kr"]["result_count"] == 8
    assert response.official_failure_reasons == {"timeout": 1}
    assert response.rejected_candidate_reasons == {
        "candidate_belongs_to_other_company": 2
    }
    assert response.llm_failure_count == 1
    assert "'{}'::jsonb as source_counts_by_adapter" not in compact_sql
    assert "source_counts as" in compact_sql
    assert "llm_rollup as" in compact_sql


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
    conn.run_row["run_scope"] = {"domain": "paper", "source": "admin-console-upload"}
    response = asyncio.run(
        pipeline.trigger_retrieval_validation(run_id=RUN_ID, conn=conn)
    )

    assert response.status == "scheduled"
    assert response.domain == "paper"
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
    assert '"domain": "paper"' in insert_params[1]


def test_trigger_retrieval_validation_rejects_company_upload_runs() -> None:
    conn = _PipelineConn()
    conn.run_row["run_scope"] = {
        "domain": "company",
        "source": "admin-console-upload",
        "result_summary": {
            "enrichment": {"batch_id": str(BATCH_ID), "status": "queued"}
        },
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(pipeline.trigger_retrieval_validation(run_id=RUN_ID, conn=conn))

    assert exc.value.status_code == 400
    assert "Company XLSX uploads use company enrichment batches" in str(
        exc.value.detail
    )


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


def test_start_company_enrichment_batch_creates_child_run_and_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_coroutines: list[object] = []

    def fake_create_task(coroutine: object) -> _CreatedTask:
        created_coroutines.append(coroutine)
        close = getattr(coroutine, "close", None)
        if callable(close):
            close()
        return _CreatedTask()

    class BatchConn(_PipelineConn):
        def execute(self, query: str, params: object = None) -> _Result:
            sql = " ".join(query.split()).lower()
            if "from company_enrichment_batch" in sql:
                return _Result(
                    [
                        {
                            "batch_id": BATCH_ID,
                            "status": "queued",
                            "upload_task_id": RUN_ID,
                            "companies_selected": 100,
                        }
                    ]
                )
            return super().execute(query, params)

    monkeypatch.setattr(pipeline.asyncio, "create_task", fake_create_task)

    response = asyncio.run(
        pipeline.start_company_enrichment_batch(
            batch_id=BATCH_ID,
            request=pipeline.CompanyEnrichmentBatchStartRequest(
                limit=50,
                chunk_size=10,
                stage_preset="high_trust_sources",
                include_failed=True,
                skip_milvus=True,
            ),
            conn=BatchConn(),
        )
    )

    assert response.status == "scheduled"
    assert response.domain == "company"
    assert response.task_id == str(CHILD_RUN_ID)
    assert response.parent_run_id == str(RUN_ID)
    assert created_coroutines


def test_restart_stale_company_enrichment_batch_marks_stale_and_schedules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_coroutines: list[object] = []
    stale_heartbeat = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)

    def fake_create_task(coroutine: object) -> _CreatedTask:
        created_coroutines.append(coroutine)
        close = getattr(coroutine, "close", None)
        if callable(close):
            close()
        return _CreatedTask()

    class BatchConn(_PipelineConn):
        def execute(self, query: str, params: object = None) -> _Result:
            sql = " ".join(query.split()).lower()
            self.queries.append(query)
            self.params.append(params)
            if "from company_enrichment_batch" in sql:
                return _Result(
                    [
                        {
                            "batch_id": BATCH_ID,
                            "status": "running",
                            "upload_task_id": RUN_ID,
                            "companies_selected": 100,
                            "runner_heartbeat_at": stale_heartbeat,
                        }
                    ]
                )
            if sql.startswith("update company_enrichment_batch"):
                return _Result([])
            if sql.startswith("update company_enrichment_company_state"):
                return _Result([])
            return super().execute(query, params)

    monkeypatch.setattr(pipeline.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(
        pipeline,
        "_is_runner_stale",
        lambda *, status, heartbeat_at: status == "running",
    )

    response = asyncio.run(
        pipeline.restart_stale_company_enrichment_batch(
            batch_id=BATCH_ID,
            request=pipeline.CompanyEnrichmentBatchStartRequest(
                limit=50,
                chunk_size=10,
                include_failed=True,
            ),
            conn=BatchConn(),
        )
    )

    assert response.status == "scheduled"
    assert response.task_id == str(CHILD_RUN_ID)
    assert created_coroutines


def test_run_company_enrichment_batch_command_builds_cli_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Completed:
        returncode = 0
        stdout = '{"status":"succeeded","companies_processed":50}'
        stderr = ""

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    summary = pipeline._run_company_enrichment_batch_command(
        batch_id=BATCH_ID,
        limit=50,
        chunk_size=10,
        stage_preset="high_trust_sources",
        include_failed=True,
        skip_milvus=True,
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert command[:3] == ["uv", "run", "python"]
    assert "--batch-id" in command
    assert str(BATCH_ID) in command
    assert "--limit" in command
    assert "50" in command
    assert "--chunk-size" in command
    assert "10" in command
    assert "--skip-generic-serper" in command
    assert "--include-failed" in command
    assert "--skip-milvus" in command
    assert summary["returncode"] == 0


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
