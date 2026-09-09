from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from backend.api import pipeline_issues

TASK_ID = UUID("ac70fd4e-c4ff-4a31-a786-54e171d9dd1d")


class _Result:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetchall(self) -> list[dict]:
        return self._rows

    def fetchone(self) -> dict | None:
        return self._rows[0] if self._rows else None


class _Transaction:
    def __enter__(self) -> _Transaction:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _PipelineIssueConn:
    def __init__(self, upload_path: Path | None = None) -> None:
        self.queries: list[str] = []
        self.params: list[dict[str, object] | None] = []
        self.upload_path = upload_path
        now = datetime(2026, 5, 5, 16, 44, tzinfo=timezone.utc)
        self.rows = [
            {
                "issue_id": "41dbcf89-1e3a-4a0b-b865-36b09e0ad337",
                "professor_id": None,
                "link_id": None,
                "institution": f"admin-upload:company:{TASK_ID}",
                "stage": "data_quality_flag",
                "severity": "medium",
                "description": "3 company rows are missing company_name",
                "evidence_snapshot": {
                    "domain": "company",
                    "task_id": str(TASK_ID),
                    "issue_type": "missing_company_name",
                    "source_rows": [1620, 1621, 1622],
                    "recommended_action": "Fill company_name in the source Excel rows before import.",
                },
                "reported_by": "admin_upload_dry_run",
                "reported_at": now,
                "resolved": False,
                "resolved_at": None,
                "resolution_notes": None,
                "resolution_round": None,
                "total_count": 1,
            }
        ]

    def execute(self, query: str, params: dict[str, object] | None = None) -> _Result:
        self.queries.append(query)
        self.params.append(params)
        compact = " ".join(query.split()).lower()
        if query.lstrip().upper().startswith("UPDATE pipeline_issue".upper()):
            assert params is not None
            row = dict(self.rows[0])
            row["resolved"] = params["resolved"]
            row["resolved_at"] = (
                datetime(2026, 5, 5, 17, 0, tzinfo=timezone.utc)
                if params["resolved"]
                else None
            )
            row["resolution_notes"] = params["resolution_notes"]
            row["resolution_round"] = params["resolution_round"]
            return _Result([row])
        if "from pipeline_issue" in compact and "where issue_id" in compact:
            return _Result(self.rows)
        if "from pipeline_run" in compact:
            run_scope = {"domain": "company"}
            if self.upload_path is not None:
                run_scope["upload_path"] = str(self.upload_path)
            return _Result([{"run_scope": run_scope}])
        return _Result(self.rows)

    def transaction(self) -> _Transaction:
        return _Transaction()


def test_list_pipeline_issues_filters_by_upload_issue_metadata() -> None:
    conn = _PipelineIssueConn()

    response = pipeline_issues.list_pipeline_issues(
        stage=None,
        severity=None,
        resolved=None,
        reported_by="admin_upload_dry_run",
        professor_id=None,
        task_id=str(TASK_ID),
        domain="company",
        issue_type="missing_company_name",
        q=None,
        page=1,
        page_size=50,
        conn=conn,
    )

    assert response.total == 1
    assert response.items[0].issue_id == "41dbcf89-1e3a-4a0b-b865-36b09e0ad337"
    assert response.items[0].evidence_snapshot
    assert response.items[0].evidence_snapshot["source_rows"] == [1620, 1621, 1622]

    query = conn.queries[0]
    assert "reported_by = %(reported_by)s" in query
    assert "evidence_snapshot->>'task_id' = %(task_id)s" in query
    assert "evidence_snapshot->>'domain' = %(domain)s" in query
    assert "evidence_snapshot->>'issue_type' = %(issue_type)s" in query
    assert conn.params[0]
    assert conn.params[0]["task_id"] == str(TASK_ID)
    assert conn.params[0]["domain"] == "company"
    assert conn.params[0]["issue_type"] == "missing_company_name"


def test_list_pipeline_issues_derives_chat_feedback_context() -> None:
    conn = _PipelineIssueConn()
    conn.rows[0].update(
        {
            "institution": "chat-feedback:session-123",
            "description": (
                "Chat feedback (incorrect_answer) for B_company_topic_search: "
                "深圳哪些公司做激光雷达"
            ),
            "evidence_snapshot": {
                "issue_type": "chat_feedback",
                "domain": "company",
                "session_id": "session-123",
                "query": "深圳哪些公司做激光雷达",
                "query_type": "B_company_topic_search",
                "answer_text": "共找到 6 个企业。",
                "answer_style": "template",
                "citations": [
                    {
                        "type": "company",
                        "id": "COMP-001",
                        "label": "不止技术",
                        "url": "/browse#company/COMP-001",
                    }
                ],
                "feedback_type": "incorrect_answer",
                "note": "结果里有不相关企业",
                "recommended_action": (
                    "Review the chat answer, routing, citations, and source evidence."
                ),
            },
            "reported_by": "chat_user_feedback",
        }
    )

    response = pipeline_issues.list_pipeline_issues(
        stage=None,
        severity=None,
        resolved=False,
        reported_by="chat_user_feedback",
        professor_id=None,
        task_id=None,
        domain="company",
        issue_type="chat_feedback",
        q="激光雷达",
        page=1,
        page_size=50,
        conn=conn,
    )

    issue = response.items[0]
    assert issue.issue_type == "chat_feedback"
    assert issue.domain == "company"
    assert issue.source_rows == []
    assert issue.recommended_action == (
        "Review the chat answer, routing, citations, and source evidence."
    )
    assert issue.chat_feedback is not None
    assert issue.chat_feedback.session_id == "session-123"
    assert issue.chat_feedback.query == "深圳哪些公司做激光雷达"
    assert issue.chat_feedback.query_type == "B_company_topic_search"
    assert issue.chat_feedback.answer_text == "共找到 6 个企业。"
    assert issue.chat_feedback.answer_style == "template"
    assert issue.chat_feedback.feedback_type == "incorrect_answer"
    assert issue.chat_feedback.note == "结果里有不相关企业"
    assert issue.chat_feedback.citations[0]["id"] == "COMP-001"

    query = conn.queries[0]
    assert "reported_by = %(reported_by)s" in query
    assert "evidence_snapshot->>'domain' = %(domain)s" in query
    assert "evidence_snapshot->>'issue_type' = %(issue_type)s" in query
    assert "description ILIKE %(q_like)s" in query
    assert conn.params[0]
    assert conn.params[0]["resolved"] is False
    assert conn.params[0]["q_like"] == "%激光雷达%"


def test_update_pipeline_issue_resolves_issue() -> None:
    conn = _PipelineIssueConn()

    response = pipeline_issues.update_pipeline_issue(
        issue_id="41dbcf89-1e3a-4a0b-b865-36b09e0ad337",
        body=pipeline_issues.PipelineIssueUpdateRequest(
            resolved=True,
            resolution_notes="checked from admin-console",
            resolution_round="admin-upload-dry-run",
        ),
        conn=conn,
    )

    assert response.resolved is True
    assert response.resolved_at is not None
    assert response.resolution_notes == "checked from admin-console"
    assert response.resolution_round == "admin-upload-dry-run"
    assert "UPDATE pipeline_issue" in conn.queries[-1]
    assert conn.params[-1]
    assert conn.params[-1]["resolved"] is True


def test_update_pipeline_issue_can_reopen_issue() -> None:
    conn = _PipelineIssueConn()

    response = pipeline_issues.update_pipeline_issue(
        issue_id="41dbcf89-1e3a-4a0b-b865-36b09e0ad337",
        body=pipeline_issues.PipelineIssueUpdateRequest(
            resolved=False,
            resolution_notes="needs another look",
            resolution_round="admin-upload-dry-run",
        ),
        conn=conn,
    )

    assert response.resolved is False
    assert response.resolved_at is None
    assert response.resolution_notes == "needs another look"


def test_update_missing_pipeline_issue_returns_404() -> None:
    class _MissingIssueConn(_PipelineIssueConn):
        def execute(
            self, query: str, params: dict[str, object] | None = None
        ) -> _Result:
            self.queries.append(query)
            self.params.append(params)
            if query.lstrip().upper().startswith("UPDATE pipeline_issue".upper()):
                return _Result([])
            return super().execute(query, params)

    with pytest.raises(HTTPException) as exc:
        pipeline_issues.update_pipeline_issue(
            issue_id="missing",
            body=pipeline_issues.PipelineIssueUpdateRequest(resolved=True),
            conn=_MissingIssueConn(),
        )

    assert exc.value.status_code == 404


def test_get_pipeline_issue_source_rows_reads_uploaded_excel_rows(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "company.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "sheet1"
    ws.append(["专辑项目导出"])
    ws.append(["序号", "项目名称", "行业领域", "公司名称"])
    ws.append(["1", "有效企业", "先进制造", "深圳市星火半导体科技有限公司"])
    ws.append(["2", "缺公司名项目", "机器人", None])
    wb.save(workbook_path)

    conn = _PipelineIssueConn(upload_path=workbook_path)
    conn.rows[0]["evidence_snapshot"]["source_rows"] = [4]

    response = pipeline_issues.get_pipeline_issue_source_rows(
        issue_id="41dbcf89-1e3a-4a0b-b865-36b09e0ad337",
        conn=conn,
    )

    assert response.issue_id == "41dbcf89-1e3a-4a0b-b865-36b09e0ad337"
    assert response.task_id == str(TASK_ID)
    assert response.domain == "company"
    assert response.sheet_name == "sheet1"
    assert response.header_row_number == 2
    assert response.rows[0].row_number == 4
    cells = {cell.header: cell.value for cell in response.rows[0].cells}
    assert cells["序号"] == "2"
    assert cells["项目名称"] == "缺公司名项目"
    assert cells["行业领域"] == "机器人"
    assert cells["公司名称"] is None
