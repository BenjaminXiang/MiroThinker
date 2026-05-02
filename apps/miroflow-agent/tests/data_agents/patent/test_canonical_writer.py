from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.data_agents.contracts import Evidence, PatentRecord
from src.data_agents.patent.canonical_writer import upsert_patent
from src.data_agents.patent.release import record_to_patent_dict


RUN_ID = "11111111-1111-1111-1111-111111111111"


def _record(**overrides) -> PatentRecord:
    values = {
        "id": "PAT-TEST",
        "title": "一种多申请人测试专利",
        "title_en": "Test patent",
        "patent_number": "CN123456789A",
        "applicants": ["深圳市公司A有限公司", "深圳市公司B有限公司"],
        "inventors": [],
        "patent_type": "发明",
        "filing_date": "2026-05-01",
        "publication_date": "2026-06-01",
        "abstract": "该专利用于验证 PostgreSQL 写入字段映射。",
        "technology_effect": "提升多申请人专利数据的可追溯性",
        "ipc_codes": ["G06F"],
        "summary_text": "该专利用于验证 PostgreSQL 写入字段映射，覆盖申请人、日期、摘要与质量状态。",
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


def test_upsert_patent_inserts_and_is_idempotent_on_patent_id():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {"patent_id": "PAT-TEST"}

    assert upsert_patent(conn, record=_record(), run_id=RUN_ID) == "PAT-TEST"
    assert upsert_patent(conn, record=_record(), run_id=RUN_ID) == "PAT-TEST"

    sql = conn.execute.call_args.args[0]
    assert "INSERT INTO patent" in sql
    assert "ON CONFLICT (patent_id) DO UPDATE" in sql
    assert conn.execute.call_count == 2
    conn.commit.assert_not_called()


def test_upsert_patent_rejects_dry_run_sentinel_run_id():
    conn = MagicMock()

    with pytest.raises(ValueError, match="sentinel"):
        upsert_patent(
            conn,
            record=_record(),
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
        )

    conn.execute.assert_not_called()


def test_record_to_patent_dict_marks_ready_when_required_fields_exist():
    payload = record_to_patent_dict(_record())

    assert payload["quality_status"] == "ready"


def test_record_to_patent_dict_marks_needs_review_when_filing_date_missing():
    payload = record_to_patent_dict(_record(filing_date=None))

    assert payload["quality_status"] == "needs_review"


def test_upsert_patent_writes_applicants_parsed_as_jsonb_list():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {"patent_id": "PAT-TEST"}

    upsert_patent(conn, record=_record(), run_id=RUN_ID)

    params = conn.execute.call_args.args[1]
    applicants_jsonb = params[6]
    assert applicants_jsonb.obj == ["深圳市公司A有限公司", "深圳市公司B有限公司"]
