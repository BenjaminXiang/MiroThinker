from __future__ import annotations

from uuid import UUID

from src.data_agents.storage.postgres.professor_profile_section import (
    ProfessorProfileSectionInput,
    load_professor_profile_section,
    upsert_professor_profile_section,
)


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cursor(self.row)


def test_upsert_professor_profile_section_hashes_source_text_when_missing() -> None:
    section_id = UUID("00000000-0000-0000-0000-000000000042")
    conn = _Conn({"section_id": section_id})

    result = upsert_professor_profile_section(
        conn,
        ProfessorProfileSectionInput(
            professor_id="PROF-1",
            section_type="research_overview",
            language="zh",
            content="可信人工智能医学影像研究。",
            source_text="My research focuses on trustworthy AI.",
            source_language="en",
            generation_method="llm_translation",
            run_id="11111111-1111-1111-1111-111111111111",
        ),
    )

    assert result.section_id == section_id
    sql, params = conn.calls[0]
    assert "ON CONFLICT ON CONSTRAINT uq_professor_profile_section_source" in sql
    assert params["professor_id"] == "PROF-1"
    assert params["section_type"] == "research_overview"
    assert params["language"] == "zh"
    assert params["source_text_hash"]
    assert params["source_text_hash"] != "My research focuses on trustworthy AI."


def test_load_professor_profile_section_returns_latest_section() -> None:
    conn = _Conn(
        {
            "section_id": UUID("00000000-0000-0000-0000-000000000043"),
            "professor_id": "PROF-1",
            "section_type": "research_overview",
            "language": "zh",
            "content": "中文研究介绍。",
            "source_page_id": None,
            "source_language": "en",
            "source_text_hash": "abc",
            "source_span": None,
            "generation_method": "llm_translation",
            "run_id": None,
        }
    )

    row = load_professor_profile_section(
        conn,
        professor_id="PROF-1",
        section_type="research_overview",
        language="zh",
    )

    assert row is not None
    assert row.content == "中文研究介绍。"
    sql, params = conn.calls[0]
    assert "ORDER BY updated_at DESC" in sql
    assert params == {
        "professor_id": "PROF-1",
        "section_type": "research_overview",
        "language": "zh",
    }
