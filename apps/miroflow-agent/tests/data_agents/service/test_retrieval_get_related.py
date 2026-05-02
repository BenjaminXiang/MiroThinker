from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.data_agents.service.retrieval import RetrievalService


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetchone(self) -> dict | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict]:
        return list(self._rows)


class _FakeConn:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.calls: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, query: str, params: tuple):
        self.calls.append((" ".join(query.split()), params))
        return _FakeResult(self._rows)


def _service(conn: _FakeConn) -> RetrievalService:
    return RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=MagicMock(),
        embedding_client=MagicMock(),
        reranker=MagicMock(),
    )


@pytest.mark.parametrize(
    ("source_domain", "source_id", "target_domain", "target_key", "link_table"),
    [
        ("professor", "PROF-1", "paper", "paper_id", "professor_paper_link"),
        ("paper", "PAPER-1", "professor", "professor_id", "professor_paper_link"),
        ("professor", "PROF-1", "company", "company_id", "professor_company_role"),
        ("company", "COMP-1", "professor", "professor_id", "professor_company_role"),
        ("professor", "PROF-1", "patent", "patent_id", "professor_patent_link"),
        ("patent", "PAT-1", "professor", "professor_id", "professor_patent_link"),
        ("company", "COMP-1", "patent", "patent_id", "company_patent_link"),
        ("patent", "PAT-1", "company", "company_id", "company_patent_link"),
    ],
)
def test_get_related_supported_pairs_join_canonical_tables(
    source_domain: str,
    source_id: str,
    target_domain: str,
    target_key: str,
    link_table: str,
):
    conn = _FakeConn([{target_key: "TARGET-1", "link_status": "verified"}])

    result = _service(conn).get_related_objects(
        source_domain=source_domain,
        source_id=source_id,
        target_domain=target_domain,
    )

    assert result == [{target_key: "TARGET-1", "link_status": "verified"}]
    assert link_table in conn.calls[0][0]
    assert "link_status" in conn.calls[0][0]
    assert conn.calls[0][1] == (source_id, 50)


def test_get_related_same_domain_returns_empty_without_query():
    conn = _FakeConn([{"paper_id": "PAPER-1"}])

    result = _service(conn).get_related_objects(
        source_domain="paper",
        source_id="PAPER-1",
        target_domain="paper",
    )

    assert result == []
    assert conn.calls == []


def test_get_related_unsupported_pair_returns_empty_without_query():
    conn = _FakeConn([{"company_id": "COMP-1"}])

    result = _service(conn).get_related_objects(
        source_domain="paper",
        source_id="PAPER-1",
        target_domain="company",
    )

    assert result == []
    assert conn.calls == []


def test_get_related_empty_source_id_returns_empty_without_query():
    conn = _FakeConn([{"paper_id": "PAPER-1"}])

    result = _service(conn).get_related_objects(
        source_domain="professor",
        source_id="",
        target_domain="paper",
    )

    assert result == []
    assert conn.calls == []


def test_get_related_clamps_limit_to_200():
    conn = _FakeConn([{"paper_id": "PAPER-1"}])

    _service(conn).get_related_objects(
        source_domain="professor",
        source_id="PROF-1",
        target_domain="paper",
        limit=500,
    )

    assert conn.calls[0][1] == ("PROF-1", 200)


def test_get_related_zero_limit_returns_empty_without_query():
    conn = _FakeConn([{"paper_id": "PAPER-1"}])

    result = _service(conn).get_related_objects(
        source_domain="professor",
        source_id="PROF-1",
        target_domain="paper",
        limit=0,
    )

    assert result == []
    assert conn.calls == []
