from __future__ import annotations

import io
import logging
import asyncio
import hashlib
from contextlib import contextmanager
from uuid import UUID

import pytest
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook

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
        if sql_lower.startswith("update pipeline_run"):
            return _FakeResult([])
        if sql_lower.startswith("insert into source_page"):
            return _FakeResult([{"page_id": PAGE_ID}])
        if sql_lower.startswith("insert into pipeline_issue"):
            return _FakeResult([])
        if sql_lower.startswith("select pg_advisory_xact_lock"):
            return _FakeResult([])
        if "from pipeline_run" in sql_lower and "file_content_hash" in sql_lower:
            return _FakeResult([])
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
    monkeypatch.setenv("MIROTHINKER_ADMIN_UPLOAD_DIR", str(tmp_path / "admin-uploads"))
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

    pipeline_call = next(call for call in conn.calls if "INSERT INTO pipeline_run" in call[0])
    assert isinstance(pipeline_call[1], tuple)
    assert pipeline_call[1][0] == "import_xlsx"

    source_page_call = next(call for call in conn.calls if "INSERT INTO source_page" in call[0])
    params = source_page_call[1]
    assert isinstance(params, dict)
    assert params["url"].startswith("admin-upload://paper/")
    assert str(RUN_ID) in params["url"]
    assert params["filename"] == "paper.xlsx"
    assert params["task_id"] == RUN_ID
    assert str(tmp_path / "admin-uploads" / "paper") in params["upload_path"]
    assert str(RUN_ID) in params["upload_path"]


def test_upload_dry_run_records_scope_and_schedules_dry_run_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    created_coroutines = []

    def fake_create_task(coro):
        created_coroutines.append(coro)
        coro.close()
        return _DummyTask()

    monkeypatch.setattr(upload.asyncio, "create_task", fake_create_task)
    monkeypatch.setenv("MIROTHINKER_ADMIN_UPLOAD_DIR", str(tmp_path / "admin-uploads"))
    conn = _FakeUploadConn()

    response = asyncio.run(
        upload._handle_upload(
            domain="company",
            file=UploadFile(file=io.BytesIO(b"xlsx bytes"), filename="company.xlsx"),
            conn=conn,
            dry_run=True,
        )
    )

    assert response.dry_run is True
    assert response.task_id == str(RUN_ID)
    assert len(created_coroutines) == 1

    pipeline_call = next(call for call in conn.calls if "INSERT INTO pipeline_run" in call[0])
    assert isinstance(pipeline_call[1], tuple)
    assert '"dry_run": true' in pipeline_call[1][1]


def test_upload_rejects_file_larger_than_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_create_task(coro):
        coro.close()
        raise AssertionError("oversized uploads must be rejected before scheduling")

    monkeypatch.setattr(upload.asyncio, "create_task", fake_create_task)
    monkeypatch.setenv("MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES", "4")
    conn = _FakeUploadConn()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            upload._handle_upload(
                domain="company",
                file=UploadFile(file=io.BytesIO(b"12345"), filename="company.xlsx"),
                conn=conn,
            )
        )

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail["code"] == "upload_too_large"
    assert exc_info.value.detail["max_bytes"] == 4
    assert not conn.calls


def test_company_upload_rejects_active_duplicate_file_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    created_coroutines = []
    content = b"xlsx bytes"
    digest = hashlib.sha256(content).hexdigest()

    class DuplicateConn(_FakeUploadConn):
        def execute(self, query: str, params: object = None) -> _FakeResult:
            sql = " ".join(query.split())
            sql_lower = sql.lower()
            self.calls.append((sql, params))
            if "from pipeline_run" in sql_lower and "file_content_hash" in sql_lower:
                assert isinstance(params, dict)
                assert params["domain"] == "company"
                assert params["file_content_hash"] == digest
                return _FakeResult(
                    [
                        {
                            "run_id": RUN_ID,
                            "status": "running",
                            "run_kind": "import_xlsx",
                            "filename": "company.xlsx",
                            "upload_path": "/data/uploads/company.xlsx",
                            "active_batch_id": None,
                            "active_batch_status": None,
                        }
                    ]
                )
            return super().execute(query, params)

    def fake_create_task(coro):
        created_coroutines.append(coro)
        coro.close()
        return _DummyTask()

    monkeypatch.setattr(upload.asyncio, "create_task", fake_create_task)
    monkeypatch.setenv("MIROTHINKER_ADMIN_UPLOAD_DIR", str(tmp_path / "admin-uploads"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            upload._handle_upload(
                domain="company",
                file=UploadFile(file=io.BytesIO(content), filename="company.xlsx"),
                conn=DuplicateConn(),
            )
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "duplicate_upload_active"
    assert exc.value.detail["active_task_id"] == str(RUN_ID)
    assert created_coroutines == []


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


def test_upload_pipeline_task_closes_with_dispatch_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    closed_runs = []

    async def dispatch(**kwargs) -> dict:
        return {
            "status": "partial",
            "items_processed": 8,
            "items_failed": 2,
            "imported": 6,
        }

    def fake_close_background_run(
        task_id,
        *,
        status,
        items_processed=None,
        items_failed=None,
        error_summary=None,
        result_summary=None,
    ) -> None:
        closed_runs.append(
            (
                task_id,
                status,
                items_processed,
                items_failed,
                error_summary,
                result_summary,
            )
        )

    monkeypatch.setattr(upload, "_dispatch_upload_pipeline", dispatch)
    monkeypatch.setattr(upload, "_close_background_run", fake_close_background_run)

    asyncio.run(
        upload._run_upload_pipeline_task(
            task_id=RUN_ID,
            domain="company",
            source_page_id=PAGE_ID,
            upload_path=tmp_path / "company.xlsx",
        )
    )

    assert closed_runs == [
        (
            RUN_ID,
            "partial",
            8,
            2,
            None,
            {"imported": 6},
        ),
    ]


def test_company_upload_dispatch_runs_real_pipeline_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    calls = []

    def fake_run_company_upload_pipeline(*, task_id, upload_path):
        calls.append((task_id, upload_path))
        return {"status": "succeeded", "items_processed": 3, "items_failed": 0}

    monkeypatch.setattr(
        upload, "_run_company_upload_pipeline", fake_run_company_upload_pipeline
    )

    summary = asyncio.run(
        upload._dispatch_upload_pipeline(
            task_id=RUN_ID,
            domain="company",
            source_page_id=PAGE_ID,
            upload_path=tmp_path / "company.xlsx",
        )
    )

    assert summary == {
        "status": "succeeded",
        "items_processed": 3,
        "items_failed": 0,
    }
    assert calls == [(RUN_ID, tmp_path / "company.xlsx")]


def test_company_upload_pipeline_enqueues_batch_scoped_enrichment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    imported_reports: list[dict] = []
    loaded_batches: list[UUID] = []
    created_batches: list[dict] = []
    scheduled_batches: list[dict] = []

    class _Report:
        records_new_company = 1
        records_updated_company = 1
        records_failed = 0
        records_parsed = 2
        batch_id = UUID("44444444-4444-4444-4444-444444444444")
        team_members_inserted = 1
        funding_events_inserted = 1
        lineage_rows = 2

    def fake_import_company_xlsx_to_postgres(*args, **kwargs):
        imported_reports.append({"args": args, "kwargs": kwargs})
        return _Report()

    def fake_load_company_ids_for_import_batch(*, dsn, batch_id):
        loaded_batches.append(batch_id)
        return ["COMP-1", "COMP-2"]

    class _BatchResult:
        batch_id = UUID("55555555-5555-5555-5555-555555555555")
        companies_total = 2
        companies_selected = 2

    def fake_create_enrichment_batch(conn, **kwargs):
        created_batches.append(kwargs)
        return _BatchResult()

    def fake_schedule_company_enrichment_batch(**kwargs):
        scheduled_batches.append(kwargs)

    monkeypatch.setattr(upload, "_resolve_upload_dsn", lambda: "postgresql://fake/test")
    monkeypatch.setattr(upload, "_ensure_admin_upload_seed", lambda **_kwargs: None)
    monkeypatch.setattr(
        "src.data_agents.company.canonical_import.import_company_xlsx_to_postgres",
        fake_import_company_xlsx_to_postgres,
    )
    monkeypatch.setattr(
        upload,
        "_load_company_ids_for_import_batch",
        fake_load_company_ids_for_import_batch,
    )
    monkeypatch.setattr(upload, "_open_enrichment_connection", lambda _dsn: object())
    monkeypatch.setattr(upload, "create_enrichment_batch", fake_create_enrichment_batch)
    monkeypatch.setattr(
        upload,
        "_schedule_company_enrichment_batch",
        fake_schedule_company_enrichment_batch,
    )

    summary = upload._run_company_upload_pipeline(
        task_id=RUN_ID,
        upload_path=tmp_path / "company.xlsx",
    )

    assert imported_reports
    assert loaded_batches == [_Report.batch_id]
    assert created_batches == [
        {
            "upload_task_id": RUN_ID,
            "import_batch_id": _Report.batch_id,
            "company_ids": ["COMP-1", "COMP-2"],
            "run_scope": {
                "source": "admin-console-upload",
                "domain": "company",
                "import_batch_id": str(_Report.batch_id),
            },
            "triggered_by": "admin-console",
        }
    ]
    assert summary["company_ids_for_enrichment"] == 2
    assert summary["enrichment"] == {
        "status": "queued",
        "batch_id": "55555555-5555-5555-5555-555555555555",
        "companies_total": 2,
        "companies_selected": 2,
    }
    assert scheduled_batches == [
        {
            "dsn": "postgresql://fake/test",
            "batch_id": UUID("55555555-5555-5555-5555-555555555555"),
        }
    ]


def test_company_upload_enrichment_accepts_context_managed_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections: list[object] = []
    commits: list[object] = []
    closed = []
    scheduled_batches: list[dict] = []

    class _Conn:
        def commit(self) -> None:
            commits.append(self)

    @contextmanager
    def fake_connection(_dsn):
        conn = _Conn()
        connections.append(conn)
        try:
            yield conn
        finally:
            closed.append(conn)

    class _BatchResult:
        batch_id = UUID("55555555-5555-5555-5555-555555555555")
        companies_total = 2
        companies_selected = 2

    def fake_create_enrichment_batch(conn, **kwargs):
        assert conn is connections[0]
        assert kwargs["upload_task_id"] == RUN_ID
        assert kwargs["company_ids"] == ["COMP-1", "COMP-2"]
        return _BatchResult()

    monkeypatch.setattr(upload, "_open_enrichment_connection", fake_connection)
    monkeypatch.setattr(upload, "create_enrichment_batch", fake_create_enrichment_batch)
    monkeypatch.setattr(
        upload,
        "_schedule_company_enrichment_batch",
        lambda **kwargs: scheduled_batches.append(kwargs),
    )

    summary = upload._enqueue_company_upload_enrichment(
        dsn="postgresql://fake/test",
        task_id=RUN_ID,
        import_batch_id=UUID("44444444-4444-4444-4444-444444444444"),
        company_ids=["COMP-1", "COMP-2"],
    )

    assert summary["status"] == "queued"
    assert commits == connections
    assert closed == connections
    assert scheduled_batches == [
        {
            "dsn": "postgresql://fake/test",
            "batch_id": UUID("55555555-5555-5555-5555-555555555555"),
        }
    ]


def test_company_upload_dispatch_uses_dry_run_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    calls = []

    def fake_dry_run(*, upload_path):
        calls.append(upload_path)
        return {
            "status": "succeeded",
            "items_processed": 3,
            "items_failed": 0,
            "dry_run": True,
        }

    def fail_real_pipeline(**kwargs):
        raise AssertionError("real pipeline must not run in dry-run mode")

    monkeypatch.setattr(upload, "_run_company_upload_dry_run", fake_dry_run)
    monkeypatch.setattr(upload, "_run_company_upload_pipeline", fail_real_pipeline)

    summary = asyncio.run(
        upload._dispatch_upload_pipeline(
            task_id=RUN_ID,
            domain="company",
            source_page_id=PAGE_ID,
            upload_path=tmp_path / "company.xlsx",
            dry_run=True,
        )
    )

    assert summary["dry_run"] is True
    assert calls == [tmp_path / "company.xlsx"]


def test_company_upload_dry_run_reports_missing_company_name_rows(tmp_path) -> None:
    workbook_path = tmp_path / "company.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "sheet1"
    ws.append(["专辑项目导出"])
    ws.append(["序号", "项目名称", "行业领域", "公司名称"])
    ws.append(["1", "有效企业", "先进制造", "深圳市星火半导体科技有限公司"])
    ws.append(["2", "缺公司名项目", "机器人", None])
    wb.save(workbook_path)

    summary = upload._run_company_upload_dry_run(upload_path=workbook_path)

    assert summary["status"] == "partial"
    assert summary["items_failed"] == 1
    assert summary["data_quality_issues"] == [
        {
            "issue_type": "missing_company_name",
            "source_rows": [4],
            "severity": "medium",
            "description": "1 company rows are missing company_name",
            "recommended_action": "Fill company_name in the source Excel rows before import.",
        }
    ]


def test_company_upload_dry_run_includes_canonical_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(upload, "_load_existing_company_ids_for_preflight", lambda: None)
    monkeypatch.setattr(
        upload,
        "_load_duplicate_upload_preflight",
        lambda _digest: {
            "duplicate_lookup": "available",
            "is_duplicate_upload": True,
            "prior_import_batches": 1,
            "prior_admin_upload_runs": 1,
        },
    )
    workbook_path = tmp_path / "company.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["公司名称", "项目名称", "网址", "产品简介", "应用场景"])
    ws.append(
        [
            "深圳甲科技有限公司",
            "甲科技",
            "https://same.example.com/a",
            "甲科技平台提供工业巡检能力。",
            "工业巡检",
        ]
    )
    ws.append(
        [
            "深圳乙科技有限公司",
            "乙科技",
            "https://same.example.com/b",
            "乙科技平台提供设备监测能力。",
            "设备监测",
        ]
    )
    wb.save(workbook_path)

    summary = upload._run_company_upload_dry_run(upload_path=workbook_path)

    preflight = summary["canonical_preflight"]
    assert preflight["records_parsed"] == 2
    assert preflight["identity_conflict_count"] == 2
    assert preflight["field_coverage"]["product_intro"] == 2
    assert preflight["field_coverage"]["application_scenarios_raw"] == 2
    assert summary["duplicate_upload_preflight"]["is_duplicate_upload"] is True


def test_company_upload_enrichment_autorun_defaults_to_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    popen_calls = []
    runner_records = []

    class _Proc:
        pid = 24680

    class _Conn:
        def commit(self) -> None:
            pass

        def close(self) -> None:
            pass

    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return _Proc()

    monkeypatch.delenv("COMPANY_UPLOAD_ENRICHMENT_AUTORUN", raising=False)
    monkeypatch.setenv("MIROTHINKER_COMPANY_ENRICHMENT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(upload.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(upload, "_open_enrichment_connection", lambda _dsn: _Conn())
    monkeypatch.setattr(
        upload,
        "record_batch_runner_started",
        lambda conn, **kwargs: runner_records.append(kwargs),
    )

    upload._schedule_company_enrichment_batch(
        dsn="postgresql://fake/test",
        batch_id=UUID("55555555-5555-5555-5555-555555555555"),
    )

    assert len(popen_calls) == 1
    command = popen_calls[0][0][0]
    assert command[:3] == [
        upload.sys.executable,
        str(upload._miroflow_agent_root() / "scripts" / "run_company_upload_enrichment_batch.py"),
        "--batch-id",
    ]
    kwargs = popen_calls[0][1]
    assert kwargs["stderr"] == upload.subprocess.STDOUT
    assert kwargs["stdout"].name.endswith(".log")
    assert (tmp_path / "logs").as_posix() in kwargs["stdout"].name
    assert runner_records == [
        {
            "batch_id": UUID("55555555-5555-5555-5555-555555555555"),
            "runner_pid": 24680,
            "runner_log_path": kwargs["stdout"].name,
        }
    ]


def test_patent_upload_dispatch_runs_real_pipeline_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    calls = []

    def fake_run_patent_upload_pipeline(*, task_id, upload_path):
        calls.append((task_id, upload_path))
        return {"status": "succeeded", "items_processed": 5, "items_failed": 0}

    monkeypatch.setattr(
        upload, "_run_patent_upload_pipeline", fake_run_patent_upload_pipeline
    )

    summary = asyncio.run(
        upload._dispatch_upload_pipeline(
            task_id=RUN_ID,
            domain="patent",
            source_page_id=PAGE_ID,
            upload_path=tmp_path / "patent.xlsx",
        )
    )

    assert summary == {
        "status": "succeeded",
        "items_processed": 5,
        "items_failed": 0,
    }
    assert calls == [(RUN_ID, tmp_path / "patent.xlsx")]


def test_patent_upload_dispatch_uses_dry_run_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    calls = []

    def fake_dry_run(*, upload_path):
        calls.append(upload_path)
        return {
            "status": "succeeded",
            "items_processed": 5,
            "items_failed": 0,
            "dry_run": True,
        }

    def fail_real_pipeline(**kwargs):
        raise AssertionError("real pipeline must not run in dry-run mode")

    monkeypatch.setattr(upload, "_run_patent_upload_dry_run", fake_dry_run)
    monkeypatch.setattr(upload, "_run_patent_upload_pipeline", fail_real_pipeline)

    summary = asyncio.run(
        upload._dispatch_upload_pipeline(
            task_id=RUN_ID,
            domain="patent",
            source_page_id=PAGE_ID,
            upload_path=tmp_path / "patent.xlsx",
            dry_run=True,
        )
    )

    assert summary["dry_run"] is True
    assert calls == [tmp_path / "patent.xlsx"]


def test_result_summary_payload_excludes_lifecycle_fields() -> None:
    assert upload._result_summary_payload(
        {
            "status": "succeeded",
            "items_processed": 10,
            "items_failed": 0,
            "imported": 9,
            "artifact_dir": "/tmp/artifacts",
            "skip_reasons": {},
            "empty": None,
        }
    ) == {
        "imported": 9,
        "artifact_dir": "/tmp/artifacts",
        "skip_reasons": {},
    }


def test_milvus_backfill_hint_points_to_domain_command() -> None:
    hint = upload._milvus_backfill_hint("company")

    assert hint["milvus_backfill_required"] is True
    assert hint["milvus_backfill_status"] == "not_triggered"
    assert "--domain company" in str(hint["milvus_backfill_command"])


def test_file_upload_pipeline_issues_writes_missing_company_name_rows() -> None:
    conn = _FakeUploadConn()
    summary = {
        "dry_run": True,
        "data_quality_issues": [
            {
                "issue_type": "missing_company_name",
                "source_rows": [4, 5],
                "severity": "medium",
                "description": "2 company rows are missing company_name",
                "recommended_action": "Fill company_name in the source Excel rows before import.",
            }
        ],
    }

    upload._file_upload_pipeline_issues(
        conn,
        task_id=RUN_ID,
        domain="company",
        result_summary=summary,
    )

    issue_call = next(call for call in conn.calls if "INSERT INTO pipeline_issue" in call[0])
    params = issue_call[1]
    assert isinstance(params, tuple)
    assert params[0] == "admin-upload:company:22222222-2222-2222-2222-222222222222"
    assert params[1] == "data_quality_flag"
    assert params[2] == "medium"
    assert "missing company_name" in params[3]
    evidence = getattr(params[4], "obj", params[4])
    assert evidence["issue_type"] == "missing_company_name"
    assert evidence["source_rows"] == [4, 5]
    assert evidence["recommended_action"] == (
        "Fill company_name in the source Excel rows before import."
    )
    assert params[5] == "admin_upload_dry_run"
