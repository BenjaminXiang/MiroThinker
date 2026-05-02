from __future__ import annotations

from unittest.mock import MagicMock

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


def test_get_professor_by_id():
    conn = _FakeConn([{"professor_id": "PROF-1", "canonical_name": "Ada"}])
    result = _service(conn).get_object(domain="professor", object_id="PROF-1")

    assert result == {"professor_id": "PROF-1", "canonical_name": "Ada"}
    assert "FROM professor" in conn.calls[0][0]
    assert "identity_status = 'resolved'" in conn.calls[0][0]
    assert conn.calls[0][1] == ("PROF-1",)


def test_get_company_by_id():
    conn = _FakeConn([{"company_id": "COMP-1", "canonical_name": "ACME"}])
    result = _service(conn).get_object(domain="company", object_id="COMP-1")

    assert result["company_id"] == "COMP-1"
    assert "FROM company" in conn.calls[0][0]
    assert "identity_status = 'resolved'" in conn.calls[0][0]


def test_get_paper_by_id():
    conn = _FakeConn([{"paper_id": "PAPER-1", "title_clean": "Paper"}])
    result = _service(conn).get_object(domain="paper", object_id="PAPER-1")

    assert result["paper_id"] == "PAPER-1"
    assert "FROM paper" in conn.calls[0][0]


def test_get_patent_by_id():
    conn = _FakeConn([{"patent_id": "PAT-1", "title_clean": "Patent"}])
    result = _service(conn).get_object(domain="patent", object_id="PAT-1")

    assert result["patent_id"] == "PAT-1"
    assert "FROM patent" in conn.calls[0][0]
    assert "status" in conn.calls[0][0]


def test_get_unknown_id_returns_none():
    conn = _FakeConn([])
    assert _service(conn).get_object(domain="professor", object_id="missing") is None


def test_get_empty_id_returns_none_without_query():
    conn = _FakeConn([{"professor_id": "PROF-1"}])
    assert _service(conn).get_object(domain="professor", object_id="") is None
    assert conn.calls == []


def test_get_object_accepts_fastapi_generator_dependency_shape():
    conn = _FakeConn([{"paper_id": "PAPER-1"}])

    def _factory():
        yield conn

    svc = RetrievalService(
        pg_conn_factory=_factory,
        milvus_client=MagicMock(),
        embedding_client=MagicMock(),
        reranker=MagicMock(),
    )

    assert svc.get_object(domain="paper", object_id="PAPER-1") == {"paper_id": "PAPER-1"}
