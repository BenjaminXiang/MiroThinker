from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.services import data_helpers as data_api


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _CaptureConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.queries: list[str] = []
        self.params: list[dict[str, Any] | tuple[Any, ...] | None] = []

    def execute(
        self, query: str, params: dict[str, Any] | tuple[Any, ...] | None = None
    ) -> _Rows:
        self.queries.append(query)
        self.params.append(params)
        return _Rows(self.rows)


def _professor_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "professor_id": "PROF-001",
        "canonical_name": "张三",
        "canonical_name_en": "San Zhang",
        "institution": "南方科技大学",
        "title": "教授",
        "discipline_family": "computer_science",
        "aliases": ["张教授"],
        "research_topic_count": 2,
        "h_index": 12,
        "citation_count": 345,
        "paper_count": 7,
        "metrics_computed_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "last_refreshed_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "total_count": 1,
    }
    row.update(overrides)
    return row


def test_professor_list_item_exposes_metrics_and_drops_verified_count() -> None:
    fields = data_api.ProfessorListItem.model_fields

    assert "h_index" in fields
    assert "citation_count" in fields
    assert "paper_count" in fields
    assert "metrics_computed_at" in fields
    assert "verified_paper_count" not in fields


def test_professor_list_sql_selects_metrics_without_verified_lateral_join() -> None:
    sql = data_api.PROFESSOR_LIST_SELECT_SQL

    assert "p.h_index" in sql
    assert "p.citation_count" in sql
    assert "p.paper_count" in sql
    assert "p.metrics_computed_at" in sql
    assert "p.metrics_source" in sql
    assert "verified_link_counts" not in sql
    assert "verified_paper_count" not in sql


def test_professor_detail_model_exposes_metrics_source() -> None:
    professor = data_api.ProfessorWithProvenance(
        professor_id="PROF-001",
        canonical_name="张三",
        discipline_family="computer_science",
        h_index=12,
        citation_count=345,
        paper_count=7,
        metrics_source="openalex",
    )

    payload = professor.model_dump()
    assert payload["h_index"] == 12
    assert payload["citation_count"] == 345
    assert payload["paper_count"] == 7
    assert payload["metrics_source"] == "openalex"


def test_has_verified_papers_filter_uses_paper_count() -> None:
    conn = _CaptureConn([_professor_row()])

    response = data_api._list_professors(
        conn,
        q=None,
        institution=None,
        discipline_family=None,
        has_verified_papers=True,
        metrics_source=None,
        page=1,
        page_size=50,
    )

    assert response.items[0].paper_count == 7
    assert "p.paper_count > 0" in conn.queries[0]
    assert "verified_link_counts" not in conn.queries[0]


def test_metrics_source_filter_is_passed_to_list_sql() -> None:
    conn = _CaptureConn([_professor_row()])

    data_api._list_professors(
        conn,
        q=None,
        institution=None,
        discipline_family=None,
        has_verified_papers=False,
        metrics_source="openalex",
        page=1,
        page_size=50,
    )

    assert "p.metrics_source = %(metrics_source)s" in conn.queries[0]
    assert "p.paper_count = 0" in conn.queries[0]
    assert conn.params[0]["metrics_source"] == "openalex"
