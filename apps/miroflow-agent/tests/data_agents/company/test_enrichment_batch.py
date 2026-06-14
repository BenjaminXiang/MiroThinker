from __future__ import annotations

from uuid import UUID

from src.data_agents.company import enrichment_batch as enrichment_batch_module
from src.data_agents.company.enrichment_batch import (
    _infer_miss_reason,
    build_miss_reason_buckets,
    close_stale_running_enrichment_batches,
    create_enrichment_batch,
    mark_batch_started,
    mark_batch_finished,
    mark_company_stage_complete,
    record_batch_heartbeat,
    record_batch_runner_started,
    record_baseline_readiness_stage,
    record_search_audit,
    review_enrichment_item,
)
from src.data_agents.company.news_connectors import YiouSearchHints


BATCH_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
UPLOAD_RUN_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
IMPORT_BATCH_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


class _Result:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, rows_by_marker: dict[str, list[dict]] | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        self.rows_by_marker = rows_by_marker or {}

    def execute(self, query: str, params: object = None) -> _Result:
        sql = " ".join(query.split())
        self.calls.append((sql, params))
        for marker, rows in self.rows_by_marker.items():
            if marker in sql:
                return _Result(rows)
        if sql.lower().startswith("insert into company_enrichment_batch"):
            return _Result([{"batch_id": BATCH_ID}])
        if "select quality_status" in sql.lower():
            return _Result([{"quality_status": "needs_review", "company_id": "COMP-1"}])
        return _Result([])


def test_create_enrichment_batch_inserts_batch_and_company_state_rows() -> None:
    conn = _Conn()

    result = create_enrichment_batch(
        conn,
        upload_task_id=UPLOAD_RUN_ID,
        import_batch_id=IMPORT_BATCH_ID,
        company_ids=["COMP-1", "COMP-2"],
        run_scope={"source": "admin-upload"},
        triggered_by="admin-console",
    )

    assert result.batch_id == BATCH_ID
    assert result.companies_total == 2
    assert result.companies_selected == 2
    batch_insert = next(
        call for call in conn.calls if "INSERT INTO company_enrichment_batch" in call[0]
    )
    batch_sql, batch_params = batch_insert
    assert "miss_reason_buckets" in batch_sql
    assert "quality_report" in batch_sql
    assert getattr(
        batch_params["miss_reason_buckets"],
        "obj",
        batch_params["miss_reason_buckets"],
    ) == {}
    assert getattr(
        batch_params["quality_report"],
        "obj",
        batch_params["quality_report"],
    ) == {}
    state_insert = next(
        call for call in conn.calls if "INSERT INTO company_enrichment_company_state" in call[0]
    )
    assert state_insert[1]["company_ids"] == ["COMP-1", "COMP-2"]


def test_mark_batch_finished_clears_stale_last_error_on_success() -> None:
    conn = _Conn()

    mark_batch_finished(conn, batch_id=BATCH_ID, status="succeeded")

    sql, params = conn.calls[-1]
    assert "last_error = CASE WHEN %(status)s = 'succeeded' THEN NULL" in sql
    assert params["status"] == "succeeded"


def test_mark_batch_started_clears_stale_failure_state() -> None:
    conn = _Conn()

    mark_batch_started(conn, batch_id=BATCH_ID)

    sql, params = conn.calls[-1]
    assert "status = 'running'" in sql
    assert "current_stage = 'running'" in sql
    assert "last_error = NULL" in sql
    assert "finished_at = NULL" in sql
    assert params == (BATCH_ID,)


def test_record_batch_runner_started_persists_pid_log_and_heartbeat() -> None:
    conn = _Conn()

    record_batch_runner_started(
        conn,
        batch_id=BATCH_ID,
        runner_pid=12345,
        runner_log_path="/var/log/mirothinker/company-batch.log",
    )

    sql, params = conn.calls[-1]
    assert "runner_pid = %(runner_pid)s" in sql
    assert "runner_log_path = %(runner_log_path)s" in sql
    assert "runner_heartbeat_at = now()" in sql
    assert params["batch_id"] == BATCH_ID
    assert params["runner_pid"] == 12345
    assert params["runner_log_path"] == "/var/log/mirothinker/company-batch.log"


def test_record_batch_heartbeat_persists_progress_report_and_bucketed_reasons() -> None:
    conn = _Conn()

    record_batch_heartbeat(
        conn,
        batch_id=BATCH_ID,
        current_stage="source_product_extract",
        last_completed_company_id="COMP-42",
        quality_report={"headline": "processed 42/100"},
        miss_reason_buckets={"identity_mismatch": 3, "fetch_failure": 2},
    )

    sql, params = conn.calls[-1]
    assert "runner_heartbeat_at = now()" in sql
    assert "runner_last_seen_at = now()" in sql
    assert "last_completed_company_id" in sql
    assert params["current_stage"] == "source_product_extract"
    assert params["last_completed_company_id"] == "COMP-42"
    assert getattr(params["quality_report"], "obj", params["quality_report"]) == {
        "headline": "processed 42/100"
    }
    assert getattr(params["miss_reason_buckets"], "obj", params["miss_reason_buckets"]) == {
        "identity_mismatch": 3,
        "fetch_failure": 2,
    }


def test_build_miss_reason_buckets_maps_engineering_reasons_to_ops_buckets() -> None:
    assert build_miss_reason_buckets(
        miss_reasons={
            "no_results": 4,
            "all_results_rejected": 2,
            "identity_mismatch": 1,
            "http_403": 3,
            "llm_rejected": 2,
            "synthesis_no_facts": 1,
            "registration_only": 5,
        },
        official_failure_reasons={"timeout": 2, "captcha_or_bot_challenge": 1},
        rejected_candidate_reasons={"candidate_belongs_to_other_company": 3},
    ) == {
        "no_search_results": 4,
        "identity_mismatch": 4,
        "webpage_unavailable": 6,
        "llm_rejected": 3,
        "registration_only": 5,
        "other": 2,
    }


def test_select_representative_company_sample_is_deterministic_and_stratified() -> None:
    candidates = [
        {
            "company_id": "COMP-MED-1",
            "industry": "医疗AI",
            "sub_industry": "影像",
            "website": "https://med1.example.com",
            "source_count": 0,
        },
        {
            "company_id": "COMP-MED-2",
            "industry": "医疗AI",
            "sub_industry": "影像",
            "website": "https://med2.example.com",
            "source_count": 0,
        },
        {
            "company_id": "COMP-ROBOT-1",
            "industry": "机器人",
            "sub_industry": "水下机器人",
            "website": "",
            "source_count": 0,
        },
        {
            "company_id": "COMP-ROBOT-2",
            "industry": "机器人",
            "sub_industry": "物流机器人",
            "website": "https://robot2.example.com",
            "source_count": 2,
        },
        {
            "company_id": "COMP-SEMI-1",
            "industry": "半导体",
            "sub_industry": "光学",
            "website": None,
            "source_count": 4,
        },
    ]

    sample = enrichment_batch_module.select_representative_company_sample(
        candidates,
        sample_size=4,
    )
    repeated = enrichment_batch_module.select_representative_company_sample(
        list(reversed(candidates)),
        sample_size=4,
    )

    assert sample.company_ids == repeated.company_ids
    assert len(sample.company_ids) == 4
    assert len(set(sample.company_ids)) == 4
    selected_rows = {
        row["company_id"]: row
        for row in candidates
        if row["company_id"] in set(sample.company_ids)
    }
    assert {row["industry"] for row in selected_rows.values()} >= {"医疗AI", "机器人"}
    assert any(row["website"] for row in selected_rows.values())
    assert any(not row["website"] for row in selected_rows.values())
    assert any(int(row["source_count"] or 0) > 0 for row in selected_rows.values())
    assert sample.selection_criteria["strategy"] == "deterministic_stratified_round_robin"
    assert sample.candidates_total == 5
    assert sample.selected_count == 4
    assert sample.bucket_summary


def test_record_search_audit_persists_queries_hints_and_miss_reason() -> None:
    conn = _Conn()

    inserted = record_search_audit(
        conn,
        batch_id=BATCH_ID,
        company_id="COMP-1",
        source_adapter="iyiou",
        diagnostics={
            "records_by_query": {"旭宏医疗": 2, "旭宏医疗 王强": 0},
            "items_accepted": 1,
            "items_rejected_offsite": 0,
            "items_rejected_irrelevant_path": 1,
            "items_rejected_name_mismatch": 0,
        },
        search_hints=YiouSearchHints(
            aliases=("旭宏医疗",),
            founder_names=("王强",),
            keywords=("心电",),
            source="llm",
        ),
        miss_reason=None,
    )

    assert inserted == 2
    audit_calls = [
        call for call in conn.calls if "INSERT INTO company_enrichment_search_audit" in call[0]
    ]
    assert len(audit_calls) == 2
    params = audit_calls[0][1]
    assert params["query_text"] == "旭宏医疗"
    hints = getattr(params["llm_hints"], "obj", params["llm_hints"])
    assert hints["aliases"] == ["旭宏医疗"]


def test_record_search_audit_stores_aggregate_counters_once_not_per_query() -> None:
    conn = _Conn()

    record_search_audit(
        conn,
        batch_id=BATCH_ID,
        company_id="COMP-1",
        source_adapter="pitchhub_36kr",
        diagnostics={
            "records_by_query": {"公司简称": 3, "公司简称 创始人": 2},
            "items_accepted": 2,
            "items_rejected_offsite": 0,
            "items_rejected_irrelevant_path": 1,
            "items_rejected_name_mismatch": 4,
        },
        search_hints=None,
    )

    audit_params = [
        call[1]
        for call in conn.calls
        if "INSERT INTO company_enrichment_search_audit" in call[0]
    ]
    assert sum(params["accepted_count"] for params in audit_params) == 2
    assert sum(params["rejected_irrelevant_path"] for params in audit_params) == 1
    assert sum(params["rejected_name_mismatch"] for params in audit_params) == 4
    assert audit_params[1]["accepted_count"] == 0
    diagnostics = getattr(audit_params[0]["diagnostics"], "obj", audit_params[0]["diagnostics"])
    assert diagnostics["counter_scope"] == "company_adapter_aggregate_stored_once"


def test_infer_miss_reason_covers_operational_reason_enum() -> None:
    assert (
        _infer_miss_reason(
            records_by_query={"q": 0},
            accepted_total=0,
            diagnostics={},
        )
        == "no_results"
    )
    assert (
        _infer_miss_reason(
            records_by_query={"q": 2},
            accepted_total=0,
            diagnostics={"items_rejected_name_mismatch": 2},
        )
        == "all_results_rejected"
    )
    assert (
        _infer_miss_reason(
            records_by_query={"q": 2},
            accepted_total=0,
            diagnostics={"error": "timeout"},
        )
        == "fetch_failed"
    )
    assert (
        _infer_miss_reason(
            records_by_query={"q": 2},
            accepted_total=0,
            diagnostics={"llm_rejected": True},
        )
        == "llm_rejected"
    )
    assert (
        _infer_miss_reason(
            records_by_query={"q": 2},
            accepted_total=0,
            diagnostics={"synthesis_no_facts": True},
        )
        == "synthesis_no_facts"
    )
    assert (
        _infer_miss_reason(
            records_by_query={"q": 2},
            accepted_total=0,
            diagnostics={"persist_failed": True},
        )
        == "persist_failed"
    )


def test_mark_company_stage_complete_updates_checkpoint_counters() -> None:
    conn = _Conn()

    mark_company_stage_complete(
        conn,
        batch_id=BATCH_ID,
        company_id="COMP-1",
        stage="source_discovery",
        counters={"query_count": 2, "accepted_source_count": 1},
        details={
            "execution_policy": {
                "stage_name": "source_discovery",
                "effective_concurrency": 2,
                "timeout_seconds": 90,
                "retry_budget": 1,
                "llm_audit": {
                    "task_type": "source_judgment",
                    "llm_profile": "deepseek-v4-pro",
                    "model": "deepseek-v4-pro",
                    "cascade_strategy": "direct",
                },
            },
            "llm_task_outcome": {
                "task_type": "source_judgment",
                "llm_profile": "deepseek-v4-pro",
                "model": "deepseek-v4-pro",
                "attempts": 1,
                "failure_reason": None,
            },
        },
        miss_reason="all_results_rejected",
        last_error="source rejected by llm",
    )

    params = conn.calls[-1][1]
    sql = conn.calls[-1][0]
    assert "UPDATE company_enrichment_company_state" in sql
    assert "last_error = CASE WHEN %(status)s = 'failed'" in sql
    assert params["stage"] == "source_discovery"
    assert params["query_count"] == 2
    assert params["accepted_source_count"] == 1
    assert params["miss_reason"] == "all_results_rejected"
    stage_status = getattr(params["stage_status"], "obj", params["stage_status"])
    payload = stage_status["source_discovery"]
    assert payload["status"] == "succeeded"
    assert payload["miss_reason"] == "all_results_rejected"
    assert payload["last_error"] == "source rejected by llm"
    assert payload["execution_policy"]["llm_audit"]["task_type"] == "source_judgment"
    assert payload["llm_task_outcome"]["model"] == "deepseek-v4-pro"
    assert "api_key" not in str(payload).casefold()


def test_close_stale_running_enrichment_batches_fails_abandoned_rows() -> None:
    conn = _Conn()

    updated = close_stale_running_enrichment_batches(
        conn,
        stale_after_minutes=90,
    )

    assert updated == 0
    sql = conn.calls[0][0]
    params = conn.calls[0][1]
    assert "company_enrichment_company_state" in sql
    assert "company_enrichment_batch" in sql
    assert "stale_company_states" in sql
    assert "stale_running_timeout" in sql
    assert params["stale_after_minutes"] == 90


def test_record_baseline_readiness_stage_persists_blockers_and_promotes_ready_base() -> None:
    conn = _Conn(
        {
            "FROM company c": [
                {
                    "company_id": "COMP-READY",
                    "identity_status": "resolved",
                    "company_name_xlsx": "深圳示例医疗科技有限公司",
                    "industry": "医疗AI",
                    "description": "公司提供面向医院的AI辅助诊断平台。",
                    "snapshot_id": "S-1",
                },
                {
                    "company_id": "COMP-SPARSE",
                    "identity_status": "resolved",
                    "company_name_xlsx": "深圳空白科技有限公司",
                    "industry": None,
                    "description": None,
                    "snapshot_id": "S-2",
                },
                {
                    "company_id": "COMP-NOSNAP",
                    "identity_status": "resolved",
                    "company_name_xlsx": None,
                    "industry": None,
                    "description": None,
                    "snapshot_id": None,
                },
                {
                    "company_id": "COMP-UNRESOLVED",
                    "identity_status": "needs_review",
                    "company_name_xlsx": "深圳待定科技有限公司",
                    "industry": "机器人",
                    "description": "提供机器人控制系统。",
                    "snapshot_id": "S-3",
                },
            ]
        }
    )

    summary = record_baseline_readiness_stage(
        conn,
        batch_id=BATCH_ID,
        company_ids=[
            "COMP-READY",
            "COMP-SPARSE",
            "COMP-NOSNAP",
            "COMP-UNRESOLVED",
        ],
    )

    assert summary["companies_checked"] == 4
    assert summary["baseline_ready"] == 1
    assert summary["baseline_blocked"] == 3
    assert summary["blockers"] == {
        "missing_company_name": 1,
        "missing_latest_snapshot": 1,
        "missing_meaningful_baseline_field": 2,
        "unresolved_identity": 1,
    }
    ready_update = next(
        call for call in conn.calls if call[0].startswith("UPDATE company SET")
    )
    assert ready_update[1]["company_ids"] == ["COMP-READY"]
    state_updates = [
        call
        for call in conn.calls
        if "UPDATE company_enrichment_company_state" in call[0]
    ]
    blocked_payloads = [
        getattr(call[1]["stage_status"], "obj", call[1]["stage_status"])
        for call in state_updates
        if call[1]["company_id"] == "COMP-SPARSE"
    ]
    assert blocked_payloads
    assert blocked_payloads[0]["baseline_readiness"]["blockers"] == [
        "missing_meaningful_baseline_field"
    ]
    assert not any("UPDATE company_product" in call[0] for call in conn.calls)
    assert not any(
        "UPDATE company_application_scenario" in call[0] for call in conn.calls
    )
    assert not any("UPDATE company_signal_event" in call[0] for call in conn.calls)


def test_review_enrichment_item_updates_target_and_writes_audit() -> None:
    conn = _Conn()

    review_enrichment_item(
        conn,
        target_type="product",
        target_id="PROD-1",
        action="accept",
        actor="ops",
        note="Verified against source.",
    )

    assert any("UPDATE company_product" in call[0] for call in conn.calls)
    audit_call = next(
        call for call in conn.calls if "INSERT INTO company_enrichment_review_action" in call[0]
    )
    params = audit_call[1]
    assert params["target_type"] == "product"
    assert params["previous_status"] == "needs_review"
    assert params["new_status"] == "ready"
