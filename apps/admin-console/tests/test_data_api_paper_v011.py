from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.api.data import _list_papers, get_paper_detail
from backend.api.domains import DomainEnum, get_domain_object


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


def _paper_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "paper_id": "PAPER-V011",
        "title_clean": "A Paper With Full Text",
        "title_raw": "A Paper With Full Text",
        "doi": "10.0000/v011",
        "arxiv_id": None,
        "openalex_id": "W123",
        "semantic_scholar_id": None,
        "year": 2026,
        "venue": "TestConf",
        "abstract_clean": "A test abstract.",
        "authors_display": "Ada Lovelace",
        "authors_raw": None,
        "citation_count": 12,
        "canonical_source": "manual",
        "first_seen_at": None,
        "updated_at": None,
        "run_id": None,
        "pdf_url": "https://example.test/paper.pdf",
        "linked_professor_count": 1,
        "verified_professor_count": 1,
        "admin_action": None,
        "total_count": 1,
    }
    row.update(overrides)
    return row


class _FakeDataConn:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(
        self,
        query: str,
        params: dict[str, Any] | tuple[Any, ...] | None = None,
    ) -> _FakeResult:
        del params
        sql = " ".join(query.split())
        self.calls.append(sql)
        sql_lower = sql.lower()
        if sql_lower.startswith("select ppl.link_status"):
            return _FakeResult([])
        if "from paper p" in sql_lower:
            row = _paper_row(
                pdf_sha256="a" * 64,
                full_text_source="openalex",
                title_match_source="openalex",
                title_match_confidence=Decimal("0.92"),
            )
            if sql_lower.startswith("select p.*"):
                for key in (
                    "linked_professor_count",
                    "verified_professor_count",
                    "admin_action",
                    "total_count",
                ):
                    row.pop(key)
            return _FakeResult(
                [
                    row
                ]
            )
        raise AssertionError(f"Unexpected SQL: {sql}")


class _FakeDomainsConn:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(
        self,
        query: str,
        params: dict[str, Any] | tuple[Any, ...] | None = None,
    ) -> _FakeResult:
        del params
        sql = " ".join(query.split())
        self.calls.append(sql)
        sql_lower = sql.lower()
        if "paper_title_resolution_cache" in sql_lower:
            return _FakeResult(
                [
                    {
                        "pdf_url": "https://example.test/paper.pdf",
                        "pdf_sha256": "a" * 64,
                        "full_text_source": "openalex",
                        "title_match_source": "openalex",
                        "title_match_confidence": Decimal("0.92"),
                    }
                ]
            )
        if "from paper p" in sql_lower:
            return _FakeResult([_paper_row()])
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_paper_list_includes_pdf_url_without_title_cache_join() -> None:
    conn = _FakeDataConn()

    response = _list_papers(
        conn,
        q=None,
        year_min=None,
        year_max=None,
        has_verified_professor=None,
        min_citations=None,
        page=1,
        page_size=50,
    )

    assert response.items[0].pdf_url == "https://example.test/paper.pdf"
    assert "LEFT JOIN paper_full_text pft" in conn.calls[0]
    assert "paper_title_resolution_cache" not in conn.calls[0]


def test_paper_detail_includes_full_text_metadata() -> None:
    conn = _FakeDataConn()

    response = get_paper_detail("PAPER-V011", conn=conn)
    payload = response.model_dump(mode="json")

    assert payload["paper"]["pdf_url"] == "https://example.test/paper.pdf"
    assert payload["paper"]["pdf_sha256"] == "a" * 64
    assert payload["paper"]["full_text_source"] == "openalex"
    assert payload["paper"]["title_match_source"] == "openalex"
    assert payload["paper"]["title_match_confidence"] == 0.92
    assert "paper_title_resolution_cache" in conn.calls[0]


def test_domains_paper_detail_transmits_v011_fields() -> None:
    conn = _FakeDomainsConn()

    payload = get_domain_object(DomainEnum.paper, "PAPER-V011", conn=conn)

    core_facts = payload["core_facts"]
    assert core_facts["pdf_url"] == "https://example.test/paper.pdf"
    assert core_facts["pdf_sha256"] == "a" * 64
    assert core_facts["full_text_source"] == "openalex"
    assert core_facts["title_match_source"] == "openalex"
    assert core_facts["title_match_confidence"] == 0.92
    assert any("paper_title_resolution_cache" in call for call in conn.calls)
