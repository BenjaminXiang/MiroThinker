from __future__ import annotations

import json
from unittest.mock import MagicMock

from src.data_agents.paper.citation_parser import (
    CitationInput,
    parse_citations,
)


def _llm_returning(payload: dict) -> MagicMock:
    client = MagicMock()
    content = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return client


def test_parses_typical_citation_into_structured_fields():
    llm = _llm_returning(
        {
            "results": [
                {
                    "index": 0,
                    "is_paper": True,
                    "confidence": 0.92,
                    "authors": ["Zheng X", "Zhang N", "Wu HJ", "Wu H"],
                    "title": "Estimating and accounting for tumor purity in cancer methylation microarray analysis",
                    "venue": "Genome Biology",
                    "year": 2017,
                    "reasoning": "complete citation",
                }
            ]
        }
    )
    results = parse_citations(
        items=[
            CitationInput(
                index=0,
                raw_string="Zheng X*, Zhang N, Wu HJ, Wu H*. (2017) Estimating and accounting for tumor purity in cancer methylation microarray analysis. Genome Biology 18:17",
            )
        ],
        llm_client=llm,
        llm_model="test",
    )
    assert results[0].is_paper
    assert results[0].authors == ["Zheng X", "Zhang N", "Wu HJ", "Wu H"]
    assert results[0].year == 2017
    assert results[0].venue == "Genome Biology"


def test_rejects_education_entry_as_non_paper():
    llm = _llm_returning(
        {
            "results": [
                {
                    "index": 0,
                    "is_paper": False,
                    "confidence": 0.95,
                    "authors": [],
                    "title": None,
                    "venue": None,
                    "year": None,
                    "reasoning": "education entry",
                }
            ]
        }
    )
    results = parse_citations(
        items=[
            CitationInput(
                index=0,
                raw_string="March, 2011, Master of Science, Nagoya University, Japan",
            )
        ],
        llm_client=llm,
        llm_model="test",
    )
    assert not results[0].is_paper
    assert results[0].authors == []


def test_low_confidence_paper_still_treated_as_non_paper_output():
    llm = _llm_returning(
        {
            "results": [
                {
                    "index": 0,
                    "is_paper": True,
                    "confidence": 0.4,
                    "authors": ["Someone"],
                    "title": "Unclear",
                    "venue": None,
                    "year": None,
                    "reasoning": "uncertain",
                }
            ]
        }
    )
    results = parse_citations(
        items=[
            CitationInput(index=0, raw_string="Someone. Something. Maybe 2020?")
        ],
        llm_client=llm,
        llm_model="test",
    )
    # Below the 0.7 threshold → output fields cleared.
    assert not results[0].is_paper
    assert results[0].authors == []
    assert results[0].confidence == 0.4


def test_preserves_order_across_llm_reordering():
    llm = _llm_returning(
        {
            "results": [
                {"index": 2, "is_paper": True, "confidence": 0.9, "authors": ["C"], "title": "t2", "venue": "v", "year": 2023, "reasoning": ""},
                {"index": 0, "is_paper": True, "confidence": 0.9, "authors": ["A"], "title": "t0", "venue": "v", "year": 2021, "reasoning": ""},
                {"index": 1, "is_paper": False, "confidence": 0.9, "authors": [], "title": None, "venue": None, "year": None, "reasoning": "edu"},
            ]
        }
    )
    items = [
        CitationInput(index=0, raw_string="A. t0. v 2021"),
        CitationInput(index=1, raw_string="M.S. 2019 SUSTech"),
        CitationInput(index=2, raw_string="C. t2. v 2023"),
    ]
    results = parse_citations(items=items, llm_client=llm, llm_model="test")
    assert [r.index for r in results] == [0, 1, 2]
    assert [r.is_paper for r in results] == [True, False, True]


def test_fail_safe_on_parse_error():
    llm = MagicMock()
    llm.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="not-json"))]
    )
    results = parse_citations(
        items=[CitationInput(index=0, raw_string="anything")],
        llm_client=llm,
        llm_model="test",
    )
    assert not results[0].is_paper
    assert results[0].error is not None


def test_fail_safe_on_llm_exception():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("api down")
    results = parse_citations(
        items=[
            CitationInput(index=0, raw_string="x1"),
            CitationInput(index=1, raw_string="x2"),
        ],
        llm_client=llm,
        llm_model="test",
    )
    assert all(not r.is_paper for r in results)
    assert all(r.error == "api down" for r in results)


def test_batches_large_input_list():
    call_count = {"n": 0}

    def respond(**kwargs):
        call_count["n"] += 1
        import re as _re
        body = kwargs["messages"][1]["content"]
        idxs = [int(m) for m in _re.findall(r"^\[(\d+)\]", body, flags=_re.MULTILINE)]
        results = [
            {"index": i, "is_paper": True, "confidence": 0.9, "authors": ["X"], "title": f"t{i}", "venue": "v", "year": 2023, "reasoning": ""}
            for i in idxs
        ]
        content = f"```json\n{json.dumps({'results': results})}\n```"
        return MagicMock(choices=[MagicMock(message=MagicMock(content=content))])

    llm = MagicMock()
    llm.chat.completions.create.side_effect = respond

    items = [CitationInput(index=i, raw_string=f"cite {i}") for i in range(25)]
    results = parse_citations(items=items, llm_client=llm, llm_model="test")
    # BATCH_SIZE=10 → ceil(25/10) = 3 calls
    assert call_count["n"] == 3
    assert len(results) == 25


def test_empty_input_returns_empty_without_llm():
    llm = MagicMock()
    results = parse_citations(items=[], llm_client=llm, llm_model="test")
    assert results == []
    llm.chat.completions.create.assert_not_called()


def test_tolerates_null_authors_field_from_llm():
    """Gemma occasionally emits ``"authors": null`` instead of ``[]`` for
    non-paper entries. We must coerce to empty list rather than crash."""
    llm = _llm_returning(
        {
            "results": [
                {
                    "index": 0,
                    "is_paper": False,
                    "confidence": 0.9,
                    "authors": None,
                    "title": None,
                    "venue": None,
                    "year": None,
                    "reasoning": "not a paper",
                }
            ]
        }
    )
    results = parse_citations(
        items=[CitationInput(index=0, raw_string="Some non-paper line")],
        llm_client=llm,
        llm_model="test",
    )
    assert not results[0].is_paper
    assert results[0].authors == []
    # Crucially: this must NOT be a fail-safe reject. The parse should have
    # succeeded with null coerced to [].
    assert results[0].error is None
    assert results[0].reasoning == "not a paper"


def test_missing_result_for_item_defaults_to_non_paper():
    llm = _llm_returning({"results": [
        {"index": 0, "is_paper": True, "confidence": 0.9, "authors": ["A"], "title": "t", "venue": "v", "year": 2023, "reasoning": ""},
    ]})
    results = parse_citations(
        items=[
            CitationInput(index=0, raw_string="A. t. v 2023"),
            CitationInput(index=1, raw_string="B. t. v 2024"),
        ],
        llm_client=llm,
        llm_model="test",
    )
    assert results[0].is_paper
    assert not results[1].is_paper
    assert "no result" in results[1].reasoning.lower()
