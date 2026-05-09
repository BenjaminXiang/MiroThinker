from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.api import chat as chat_module


class _Rows:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _Conn:
    def __init__(self) -> None:
        self.sql: str = ""
        self.params: dict[str, Any] = {}

    def execute(self, sql: str, params: dict[str, Any]) -> _Rows:
        self.sql = sql
        self.params = params
        return _Rows(
            {
                "issue_id": "41dbcf89-1e3a-4a0b-b865-36b09e0ad337",
                "reported_at": datetime(2026, 5, 7, 6, 30, tzinfo=timezone.utc),
            }
        )


def test_create_chat_feedback_files_pipeline_issue_with_session_trace() -> None:
    conn = _Conn()

    response = chat_module.create_chat_feedback(
        body=chat_module.ChatFeedbackRequest(
            query="深圳哪些公司做激光雷达",
            query_type="B_company_topic_search",
            answer_text="共找到 6 个企业。",
            answer_style="template",
            citations=[
                chat_module.ChatCitation(
                    type="company",
                    id="COMP-001",
                    label="不止技术",
                    url="/browse#company/COMP-001",
                )
            ],
            note="结果里有不相关企业",
        ),
        miroflow_chat_session="session-123",
        conn=conn,
    )

    assert response.issue_id == "41dbcf89-1e3a-4a0b-b865-36b09e0ad337"
    assert response.status == "filed"
    assert "INSERT INTO pipeline_issue" in conn.sql
    assert conn.params["institution"] == "chat-feedback:session-123"
    assert conn.params["stage"] == "data_quality_flag"
    assert conn.params["severity"] == "medium"
    assert conn.params["reported_by"] == "chat_user_feedback"
    assert "B_company_topic_search" in conn.params["description"]
    evidence = conn.params["evidence_snapshot"].obj
    assert evidence["issue_type"] == "chat_feedback"
    assert evidence["domain"] == "company"
    assert evidence["session_id"] == "session-123"
    assert evidence["query"] == "深圳哪些公司做激光雷达"
    assert evidence["query_type"] == "B_company_topic_search"
    assert evidence["answer_style"] == "template"
    assert evidence["answer_text"] == "共找到 6 个企业。"
    assert evidence["citations"][0]["id"] == "COMP-001"
    assert evidence["note"] == "结果里有不相关企业"
