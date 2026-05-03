from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.api.domains import DomainEnum, get_domain_object

NOW = datetime(2026, 5, 2, tzinfo=timezone.utc)


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _DomainDetailConn:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.calls: list[str] = []

    def execute(
        self,
        query: str,
        params: dict[str, Any] | tuple[Any, ...] | None = None,
    ) -> _FakeResult:
        del params
        sql = " ".join(query.split())
        self.calls.append(sql)
        if "paper_title_resolution_cache" in sql.lower():
            return _FakeResult([])
        return _FakeResult([self.row])


def _professor_row() -> dict[str, Any]:
    return {
        "professor_id": "PROF-QS",
        "canonical_name": "Ada Lovelace",
        "canonical_name_en": None,
        "canonical_name_zh": None,
        "aliases": [],
        "discipline_family": "computer_science",
        "identity_status": "resolved",
        "quality_status": "needs_review",
        "profile_summary": "Test professor.",
        "last_refreshed_at": NOW,
        "updated_at": NOW,
        "research_topic_count": 0,
        "total_count": 1,
    }


def _company_row() -> dict[str, Any]:
    return {
        "company_id": "COMP-QS",
        "canonical_name": "Quality Status Ltd",
        "registered_name": "Quality Status Ltd",
        "aliases": [],
        "identity_status": "resolved",
        "quality_status": "low_confidence",
        "last_refreshed_at": NOW,
        "updated_at": NOW,
        "snapshot_created_at": NOW,
        "total_count": 1,
    }


def _paper_row() -> dict[str, Any]:
    return {
        "paper_id": "PAPER-QS",
        "title_clean": "Quality Status Paper",
        "title_raw": "Quality Status Paper",
        "quality_status": "ready",
        "admin_action": None,
        "updated_at": NOW,
        "first_seen_at": NOW,
        "linked_professor_count": 0,
        "verified_professor_count": 0,
        "total_count": 1,
    }


def _patent_row() -> dict[str, Any]:
    return {
        "patent_id": "PAT-QS",
        "patent_number": "CNQS",
        "title_clean": "Quality Status Patent",
        "title_raw": "Quality Status Patent",
        "status": None,
        "quality_status": "needs_enrichment",
        "updated_at": NOW,
        "first_seen_at": NOW,
        "total_count": 1,
    }


def _get_with_conn(domain: str, object_id: str, conn: _DomainDetailConn) -> dict[str, Any]:
    return get_domain_object(DomainEnum(domain), object_id, conn=conn)


def test_get_professor_detail_returns_quality_status() -> None:
    conn = _DomainDetailConn(_professor_row())

    payload = _get_with_conn("professor", "PROF-QS", conn)

    assert payload["quality_status"] == "needs_review"
    assert "p.quality_status" in conn.calls[0]


def test_get_company_detail_returns_quality_status() -> None:
    conn = _DomainDetailConn(_company_row())

    payload = _get_with_conn("company", "COMP-QS", conn)

    assert payload["quality_status"] == "low_confidence"
    assert "c.quality_status" in conn.calls[0]


def test_get_paper_detail_returns_quality_status() -> None:
    conn = _DomainDetailConn(_paper_row())

    payload = _get_with_conn("paper", "PAPER-QS", conn)

    assert payload["quality_status"] == "ready"
    assert "p.quality_status" in conn.calls[0]


def test_get_patent_detail_returns_quality_status() -> None:
    conn = _DomainDetailConn(_patent_row())

    payload = _get_with_conn("patent", "PAT-QS", conn)

    assert payload["quality_status"] == "needs_enrichment"
    assert "patent.quality_status" in conn.calls[0]
