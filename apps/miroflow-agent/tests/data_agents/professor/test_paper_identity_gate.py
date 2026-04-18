from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.identity_verifier import ProfessorContext
from src.data_agents.professor.paper_identity_gate import (
    PaperIdentityCandidate,
    batch_verify_paper_identity,
)


def _llm_returning(payload: dict) -> MagicMock:
    """Build a mock llm_client whose chat.completions.create returns *payload* as JSON."""
    client = MagicMock()
    content = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return client


def _ctx() -> ProfessorContext:
    return ProfessorContext(
        name="黄建伟",
        institution="香港中文大学（深圳）",
        department="理工学院",
        research_directions=["无线通信", "博弈论", "移动众包"],
    )


def _cand(i: int, **kw) -> PaperIdentityCandidate:
    base = dict(
        title=f"candidate paper {i}",
        authors=["Jianwei Huang", f"Coauthor {i}"],
        year=2023,
        venue="IEEE Trans. Wireless Commun.",
        abstract=None,
    )
    base.update(kw)
    return PaperIdentityCandidate(index=i, **base)


@pytest.mark.asyncio
async def test_gate_accepts_paper_when_llm_high_confidence_match():
    llm = _llm_returning(
        {
            "decisions": [
                {"index": 0, "is_same_person": True, "confidence": 0.95, "reasoning": "strong match"}
            ]
        }
    )
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=[_cand(0)],
        llm_client=llm,
        llm_model="test",
    )
    assert results[0].accepted is True
    assert results[0].confidence == 0.95


@pytest.mark.asyncio
async def test_gate_rejects_when_below_threshold():
    llm = _llm_returning(
        {
            "decisions": [
                {"index": 0, "is_same_person": True, "confidence": 0.7, "reasoning": "weak"}
            ]
        }
    )
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=[_cand(0)],
        llm_client=llm,
        llm_model="test",
    )
    assert results[0].accepted is False


@pytest.mark.asyncio
async def test_gate_rejects_explicit_no_match():
    llm = _llm_returning(
        {
            "decisions": [
                {"index": 0, "is_same_person": False, "confidence": 0.92, "reasoning": "different field"}
            ]
        }
    )
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=[_cand(0)],
        llm_client=llm,
        llm_model="test",
    )
    assert results[0].accepted is False


@pytest.mark.asyncio
async def test_gate_preserves_input_order_even_if_llm_reorders():
    llm = _llm_returning(
        {
            "decisions": [
                {"index": 2, "is_same_person": True, "confidence": 0.9, "reasoning": ""},
                {"index": 0, "is_same_person": False, "confidence": 0.95, "reasoning": ""},
                {"index": 1, "is_same_person": True, "confidence": 0.85, "reasoning": ""},
            ]
        }
    )
    candidates = [_cand(0), _cand(1), _cand(2)]
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=candidates,
        llm_client=llm,
        llm_model="test",
    )
    assert [r.index for r in results] == [0, 1, 2]
    assert [r.accepted for r in results] == [False, True, True]


@pytest.mark.asyncio
async def test_gate_defaults_to_reject_on_json_parse_failure():
    llm = MagicMock()
    llm.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="not json at all"))]
    )
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=[_cand(0)],
        llm_client=llm,
        llm_model="test",
    )
    assert results[0].accepted is False
    assert results[0].error is not None


@pytest.mark.asyncio
async def test_gate_defaults_to_reject_on_llm_exception():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("api down")
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=[_cand(0), _cand(1)],
        llm_client=llm,
        llm_model="test",
    )
    assert [r.accepted for r in results] == [False, False]
    assert all(r.error == "api down" for r in results)


@pytest.mark.asyncio
async def test_gate_rejects_missing_decisions_for_unreturned_paper():
    llm = _llm_returning(
        {
            "decisions": [
                {"index": 0, "is_same_person": True, "confidence": 0.9, "reasoning": ""},
            ]
        }
    )
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=[_cand(0), _cand(1)],
        llm_client=llm,
        llm_model="test",
    )
    assert results[0].accepted is True
    assert results[1].accepted is False
    assert "no decision" in results[1].reasoning.lower()


@pytest.mark.asyncio
async def test_gate_batches_large_candidate_lists():
    # Return "True, 0.9" for every candidate index we receive; verify that the
    # mock was called multiple times when candidates exceed BATCH_SIZE.
    call_count = {"n": 0}

    def make_response(**kwargs):
        call_count["n"] += 1
        # Echo back decisions covering the candidates we were sent.
        body = kwargs["messages"][1]["content"]
        # Extract indices in the prompt text
        import re as _re
        indices = [int(m) for m in _re.findall(r"^\[(\d+)\]", body, flags=_re.MULTILINE)]
        decisions = [
            {"index": i, "is_same_person": True, "confidence": 0.9, "reasoning": "ok"}
            for i in indices
        ]
        content = f"```json\n{json.dumps({'decisions': decisions})}\n```"
        return MagicMock(choices=[MagicMock(message=MagicMock(content=content))])

    llm = MagicMock()
    llm.chat.completions.create.side_effect = make_response

    # 40 candidates → with BATCH_SIZE=15 expect ceil(40/15)=3 calls
    candidates = [_cand(i) for i in range(40)]
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=candidates,
        llm_client=llm,
        llm_model="test",
    )
    assert len(results) == 40
    assert all(r.accepted for r in results)
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_gate_captures_topic_consistency_score_from_llm():
    llm = _llm_returning(
        {
            "decisions": [
                {
                    "index": 0,
                    "is_same_person": True,
                    "confidence": 0.95,
                    "topic_consistency": 0.82,
                    "reasoning": "wireless + game theory match",
                }
            ]
        }
    )
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=[_cand(0)],
        llm_client=llm,
        llm_model="test",
    )
    assert results[0].accepted is True
    assert results[0].topic_consistency == 0.82


@pytest.mark.asyncio
async def test_gate_topic_consistency_defaults_none_when_llm_omits_field():
    llm = _llm_returning(
        {
            "decisions": [
                {"index": 0, "is_same_person": True, "confidence": 0.9, "reasoning": ""}
            ]
        }
    )
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=[_cand(0)],
        llm_client=llm,
        llm_model="test",
    )
    assert results[0].accepted is True
    assert results[0].topic_consistency is None


@pytest.mark.asyncio
async def test_gate_topic_consistency_preserved_even_when_rejected():
    llm = _llm_returning(
        {
            "decisions": [
                {
                    "index": 0,
                    "is_same_person": False,
                    "confidence": 0.9,
                    "topic_consistency": 0.15,
                    "reasoning": "right field, wrong author",
                }
            ]
        }
    )
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=[_cand(0)],
        llm_client=llm,
        llm_model="test",
    )
    assert results[0].accepted is False
    assert results[0].topic_consistency == 0.15


@pytest.mark.asyncio
async def test_gate_handles_empty_candidate_list():
    llm = MagicMock()
    results = await batch_verify_paper_identity(
        professor_context=_ctx(),
        candidates=[],
        llm_client=llm,
        llm_model="test",
    )
    assert results == []
    llm.chat.completions.create.assert_not_called()
