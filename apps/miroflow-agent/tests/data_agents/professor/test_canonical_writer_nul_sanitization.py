from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID

from src.data_agents.professor.canonical_writer import (
    _upsert_fact,
    upsert_source_page_for_url,
)

_RUN_ID = "00000000-0000-0000-0000-000000000001"


def test_upsert_fact_strips_nul_bytes_before_execute() -> None:
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.execute.side_effect = [select_cursor, MagicMock()]
    page_id = UUID("11111111-1111-1111-1111-111111111111")

    _upsert_fact(
        conn,
        professor_id="PROF-SZTU-44",
        fact_type="research_topic",
        value_raw="深圳技术大学\x00人工智能学院",
        value_normalized="人工\x00智能",
        source_page_id=page_id,
        evidence_span="页面内容\x00保留中文",
        confidence=Decimal("0.85"),
        run_id=_RUN_ID,
    )

    params = conn.execute.call_args_list[1].args[1]
    assert params[2] == "深圳技术大学人工智能学院"
    assert params[3] == "人工智能"
    assert params[5] == "页面内容保留中文"
    assert all("\x00" not in value for value in (params[2], params[3], params[5]))


def test_upsert_source_page_strips_nul_bytes_before_execute() -> None:
    conn = MagicMock()
    page_id = UUID("22222222-2222-2222-2222-222222222222")
    conn.execute.return_value.fetchone.return_value = {"page_id": page_id}

    returned = upsert_source_page_for_url(
        conn,
        url="https://sztu.example.edu.cn/人工\x00智能/teacher",
        page_role="official_profile\x00",
        owner_scope_kind="professor",
        owner_scope_ref="PROF-SZTU\x0044",
        fetched_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
        is_official_source=True,
        run_id=_RUN_ID,
    )

    params = conn.execute.call_args.args[1]
    assert returned == page_id
    assert params[:4] == (
        "https://sztu.example.edu.cn/人工智能/teacher",
        "official_profile",
        "professor",
        "PROF-SZTU44",
    )
    assert all("\x00" not in value for value in params[:4])
