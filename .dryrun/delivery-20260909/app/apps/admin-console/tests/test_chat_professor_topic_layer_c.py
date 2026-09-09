from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from backend.api import chat as chat_module


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _TopicPaperCountConn:
    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts
        self.calls: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any) -> _Rows:
        self.calls.append((sql, params))
        compact_sql = " ".join(sql.split())
        assert "FROM professor_paper_link pl" in compact_sql
        assert "JOIN paper p ON p.paper_id=pl.paper_id" in compact_sql
        assert "pl.link_status='verified'" in compact_sql
        assert "active" not in compact_sql
        assert len(params) == 3
        professor_ids = list(params[0])
        assert params[1] == params[2]
        return _Rows(
            [
                {"professor_id": professor_id, "count": self.counts[professor_id]}
                for professor_id in professor_ids
                if professor_id in self.counts
            ]
        )


class _NoSqlConn:
    def execute(self, sql: str, params: Any = None) -> _Rows:
        raise AssertionError(f"Unexpected SQL for empty topic terms: {sql} {params}")


class _RetrievalService:
    def __init__(self, evidences: list[SimpleNamespace]) -> None:
        self.evidences = evidences
        self.calls: list[dict[str, Any]] = []

    def retrieve(self, **kwargs: Any) -> list[SimpleNamespace]:
        self.calls.append(kwargs)
        assert kwargs["domains"] == ("professor",)
        return self.evidences


def _professor_evidence(
    professor_id: str,
    name: str,
    *,
    score: float,
) -> SimpleNamespace:
    return SimpleNamespace(
        object_type="professor",
        object_id=professor_id,
        score=score,
        snippet=f"{name} profile",
        source_url=None,
        metadata={
            "name": name,
            "institution": "清华大学深圳国际研究生院",
        },
    )


def _enable_retrieval(
    monkeypatch: Any,
    evidences: list[SimpleNamespace],
) -> _RetrievalService:
    service = _RetrievalService(evidences)
    monkeypatch.setattr(chat_module, "chat_use_retrieval_service", lambda: True)
    monkeypatch.setattr(chat_module, "get_retrieval_service", lambda: service)
    return service


def test_professor_topic_terms_strip_stopwords_and_add_equivalents() -> None:
    terms = chat_module._professor_topic_terms("清华做视触觉的教授有哪些")

    assert "视触觉" in terms
    assert "触觉" in terms
    assert "视触" in terms
    assert "haptic" in terms
    assert "tactile" in terms
    assert "visuotactile" in terms
    assert "清华" not in terms
    assert "做" not in terms
    assert "的" not in terms
    assert "教授" not in terms
    assert "有哪些" not in terms


def test_professor_topic_rerank_uses_topic_paper_count_before_vector_rank(
    monkeypatch: Any,
) -> None:
    service = _enable_retrieval(
        monkeypatch,
        [
            _professor_evidence("PROF-FP", "黎维彬", score=0.98),
            _professor_evidence("PROF-LEGIT", "张盛", score=0.91),
            _professor_evidence("PROF-GOLD", "潘挺睿", score=0.74),
        ],
    )
    conn = _TopicPaperCountConn({"PROF-GOLD": 4, "PROF-LEGIT": 1})

    rows = chat_module._lookup_professors_by_topic(
        conn,
        institutions=("清华大学深圳国际研究生院",),
        topic="视触觉",
        limit=3,
    )

    assert [row["professor_id"] for row in rows] == [
        "PROF-GOLD",
        "PROF-LEGIT",
        "PROF-FP",
    ]
    assert rows[-1]["canonical_name"] == "黎维彬"
    assert len(rows) == 3
    assert len(service.calls) == 1
    assert conn.calls


def test_professor_topic_empty_terms_keep_vector_order_without_sql(
    monkeypatch: Any,
) -> None:
    _enable_retrieval(
        monkeypatch,
        [
            _professor_evidence("PROF-A", "甲教授", score=0.98),
            _professor_evidence("PROF-B", "乙教授", score=0.91),
            _professor_evidence("PROF-C", "丙教授", score=0.74),
        ],
    )

    rows = chat_module._lookup_professors_by_topic(
        _NoSqlConn(),
        institutions=("清华大学深圳国际研究生院",),
        topic="清华深圳大学学院教授有哪些做的",
        limit=3,
    )

    assert [row["professor_id"] for row in rows] == ["PROF-A", "PROF-B", "PROF-C"]
