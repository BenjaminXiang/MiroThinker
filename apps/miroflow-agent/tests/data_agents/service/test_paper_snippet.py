from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from src.data_agents.providers.rerank import RerankResult
from src.data_agents.service.retrieval import RetrievalService


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _PaperTitleConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, params: tuple[Any, ...]) -> _FakeResult:
        sql = " ".join(query.split()).lower()
        self.calls.append((sql, params))
        if "regexp_replace(lower(coalesce(title_clean" in sql:
            return _FakeResult(list(self._rows))
        if "from paper" in sql and "quality_status" in sql:
            object_ids = set(params)
            return _FakeResult(
                [
                    {
                        "object_id": row["paper_id"],
                        "quality_status": row.get("quality_status", "ready"),
                        "paper_has_rich_text": bool(
                            str(row.get("paper_full_text_abstract") or "").strip()
                        ),
                    }
                    for row in self._rows
                    if row["paper_id"] in object_ids
                ]
            )
        return _FakeResult([])


def test_paper_title_snippet_uses_full_text_abstract_between_abstract_and_title() -> None:
    snippet, source = RetrievalService._paper_title_snippet(
        {
            "summary_zh": None,
            "abstract_clean": None,
            "paper_full_text_abstract": "Collected full-text abstract.",
        },
        "Fallback Title",
    )

    assert snippet == "Collected full-text abstract."
    assert source == "paper_full_text_abstract"


def test_paper_title_snippet_keeps_summary_first_and_title_last() -> None:
    assert RetrievalService._paper_title_snippet(
        {
            "summary_zh": "中文摘要。",
            "abstract_clean": "English abstract.",
            "paper_full_text_abstract": "Collected full-text abstract.",
        },
        "Fallback Title",
    ) == ("中文摘要。", "summary_zh")
    assert RetrievalService._paper_title_snippet(
        {
            "summary_zh": None,
            "abstract_clean": None,
            "paper_full_text_abstract": None,
        },
        "Fallback Title",
    ) == ("Fallback Title", "title")


def test_title_exact_lookup_selects_full_text_abstract_for_presentable_partial() -> None:
    title = "Efficient semantic retrieval over partial scientific paper records"
    conn = _PaperTitleConn(
        [
            {
                "paper_id": "PAPER-PARTIAL-RICH",
                "title_clean": title,
                "year": 2025,
                "venue": "TestConf",
                "abstract_clean": None,
                "summary_zh": None,
                "paper_full_text_abstract": "Collected full-text abstract.",
                "quality_status": "partial",
                "citation_count": 10,
            }
        ]
    )
    milvus = MagicMock()
    milvus.search.return_value = [[]]
    embed = MagicMock()
    embed.embed_batch.return_value = [[0.1] * 4096]
    reranker = MagicMock()
    reranker.rerank.side_effect = lambda _query, documents, top_n=None: [
        RerankResult(index=index, score=1.0 - index * 0.1, document=document)
        for index, document in enumerate(documents[: top_n or len(documents)])
    ]
    service = RetrievalService(
        pg_conn_factory=lambda: conn,
        milvus_client=milvus,
        embedding_client=embed,
        reranker=reranker,
    )

    results = service.retrieve(
        title,
        domains=("paper",),
        final_top_k=2,
        filter_by_quality_status=True,
    )

    assert [result.object_id for result in results] == ["PAPER-PARTIAL-RICH"]
    assert results[0].snippet == "Collected full-text abstract."
    assert results[0].metadata["snippet_source"] == "paper_full_text_abstract"
    assert any("paper_full_text" in sql for sql, _params in conn.calls)
