from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.data_agents.patent.canonical_writer import upsert_company_patent_link


def test_upsert_company_patent_link_is_idempotent_on_company_patent_role():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {
        "link_id": "22222222-2222-2222-2222-222222222222"
    }

    link_id = upsert_company_patent_link(
        conn,
        company_id="COMP-1",
        patent_id="PAT-1",
        link_role="applicant",
        evidence_source_type="patent_xlsx_applicant_exact_match",
        match_reason="applicants_parsed[0]='公司A' exact match -> COMP-1",
    )

    assert link_id == "22222222-2222-2222-2222-222222222222"
    sql = conn.execute.call_args.args[0]
    assert "INSERT INTO company_patent_link" in sql
    assert "ON CONFLICT (company_id, patent_id, link_role) DO UPDATE" in sql


def test_upsert_company_patent_link_rejects_invalid_link_role():
    conn = MagicMock()

    with pytest.raises(ValueError, match="link_role"):
        upsert_company_patent_link(
            conn,
            company_id="COMP-1",
            patent_id="PAT-1",
            link_role="founder",
            evidence_source_type="patent_xlsx_applicant_exact_match",
            match_reason="valid reason",
        )

    conn.execute.assert_not_called()


def test_upsert_company_patent_link_rejects_invalid_evidence_source_type():
    conn = MagicMock()

    with pytest.raises(ValueError, match="evidence_source_type"):
        upsert_company_patent_link(
            conn,
            company_id="COMP-1",
            patent_id="PAT-1",
            evidence_source_type="unknown",
            match_reason="valid reason",
        )

    conn.execute.assert_not_called()


def test_upsert_company_patent_link_rejects_empty_match_reason():
    conn = MagicMock()

    with pytest.raises(ValueError, match="match_reason"):
        upsert_company_patent_link(
            conn,
            company_id="COMP-1",
            patent_id="PAT-1",
            evidence_source_type="patent_xlsx_applicant_exact_match",
            match_reason="",
        )

    conn.execute.assert_not_called()
