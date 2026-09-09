from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.data_agents.contracts import Evidence, PatentRecord
from src.data_agents.patent.canonical_writer import upsert_patent


RUN_ID = "11111111-1111-1111-1111-111111111111"


def _record(**overrides) -> PatentRecord:
    values = {
        "id": "PAT-IDENTITY",
        "title": "一种身份状态测试专利",
        "patent_number": "CN123456789A",
        "applicants": ["深圳市测试科技有限公司"],
        "patent_type": "发明",
        "filing_date": "2026-05-01",
        "summary_text": "该专利用于验证专利身份状态写入逻辑，摘要文本满足最小长度要求。",
        "summary_text_method": "fallback_template",
        "evidence": [
            Evidence(
                source_type="xlsx_import",
                source_file="patent.xlsx",
                fetched_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                confidence=1.0,
            )
        ],
        "last_updated": datetime(2026, 5, 1, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return PatentRecord(**values)


def test_upsert_patent_marks_identity_confirmed_when_patent_number_is_set():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {"patent_id": "PAT-IDENTITY"}

    upsert_patent(conn, record=_record(), run_id=RUN_ID)

    sql = conn.execute.call_args.args[0]
    params = conn.execute.call_args.args[1]
    assert "identity_status" in sql
    assert params[19] == "confirmed"


def test_upsert_patent_marks_identity_unverified_when_patent_number_is_empty():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {"patent_id": "PAT-IDENTITY"}

    upsert_patent(conn, record=_record(patent_number=None), run_id=RUN_ID)

    params = conn.execute.call_args.args[1]
    assert params[19] == "unverified"
