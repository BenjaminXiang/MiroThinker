from __future__ import annotations

from uuid import UUID

from src.data_agents.storage.postgres.homepage_recursion_ledger import (
    record_homepage_recursion_fetch_failed,
    record_homepage_recursion_processed,
    record_homepage_recursion_skipped,
    record_homepage_recursion_zero_extraction,
)


class _FakeResult:
    def fetchone(self):
        return {"ledger_id": "11111111-1111-1111-1111-111111111111"}


class _FakeConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, query: str, params: tuple):
        self.calls.append((query, params))
        return _FakeResult()


def test_homepage_recursion_ledger_helper_records_processed_status() -> None:
    conn = _FakeConn()

    ledger_id = record_homepage_recursion_processed(
        conn,
        run_id=UUID("22222222-2222-2222-2222-222222222222"),
        professor_id="PROF-1",
        url="https://people.example.edu/prof/publications.html",
        page_role="personal_homepage",
        discovery_source="second_hop_publication_link",
        recursion_depth=1,
        parent_source_page_id=UUID("33333333-3333-3333-3333-333333333333"),
        source_page_id=UUID("44444444-4444-4444-4444-444444444444"),
        publications_extracted=3,
        sections_detected=1,
        heading_texts=("Publications",),
    )

    assert ledger_id == UUID("11111111-1111-1111-1111-111111111111")
    query, params = conn.calls[-1]
    assert "homepage_recursion_page_ledger" in query
    assert "ON CONFLICT" in query
    assert "processed" in params
    assert "https://people.example.edu/prof/publications.html" in params
    assert "https://people.example.edu/prof/publications.html" in params


def test_homepage_recursion_ledger_helper_records_terminal_outcomes() -> None:
    conn = _FakeConn()

    record_homepage_recursion_zero_extraction(
        conn,
        run_id=UUID("22222222-2222-2222-2222-222222222222"),
        professor_id="PROF-1",
        url="https://people.example.edu/prof/publications.html",
        page_role="personal_homepage",
        discovery_source="second_hop_publication_link",
        recursion_depth=1,
        sections_detected=2,
        heading_texts=("Selected Publications",),
    )
    record_homepage_recursion_fetch_failed(
        conn,
        run_id=UUID("22222222-2222-2222-2222-222222222222"),
        professor_id="PROF-1",
        url="https://people.example.edu/prof/publications.html",
        page_role="personal_homepage",
        discovery_source="second_hop_publication_link",
        recursion_depth=1,
        fetch_error_type="ReadError",
        fetch_error_message="disconnected",
    )
    record_homepage_recursion_skipped(
        conn,
        run_id=UUID("22222222-2222-2222-2222-222222222222"),
        professor_id="PROF-1",
        url="https://other.example.edu/publications.html",
        page_role="unknown",
        discovery_source="second_hop_publication_link",
        recursion_depth=1,
        skip_reason="outside_personal_site_root",
    )

    params_by_status = [call[1] for call in conn.calls]
    assert any("zero_extraction" in params for params in params_by_status)
    assert any("fetch_failed" in params for params in params_by_status)
    assert any("skipped" in params for params in params_by_status)
