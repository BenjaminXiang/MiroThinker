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


# -------------------------------------------------------------------------
# M1 v2 — ORCID shortcut + name_variants prompt rendering
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orcid_shortcut_accepts_without_llm_call():
    """When ORCID set on context AND candidate has matching author ORCID,
    candidate auto-accepted without LLM call."""
    ctx = ProfessorContext(
        name="Jianwei Huang",
        institution="香港中文大学（深圳）",
        research_directions=["无线通信"],
        orcid="0000-0001-2345-6789",
    )
    cand = PaperIdentityCandidate(
        index=0,
        title="Paper matched by ORCID",
        authors=["Jianwei Huang", "Other"],
        year=2024,
        venue="X",
        authors_orcid=["0000-0001-2345-6789"],
    )
    llm = MagicMock()
    results = await batch_verify_paper_identity(
        professor_context=ctx,
        candidates=[cand],
        llm_client=llm,
        llm_model="test",
    )
    assert len(results) == 1
    assert results[0].accepted is True
    assert results[0].confidence == 1.0
    assert "ORCID" in results[0].reasoning
    llm.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_orcid_shortcut_preserves_input_order_mixed():
    """2 candidates: one ORCID-match (shortcut), one non-match (LLM).
    Output preserves input order."""
    ctx = ProfessorContext(
        name="Jianwei Huang",
        institution="X",
        research_directions=["A"],
        orcid="0000-0001-2345-6789",
    )
    c0 = PaperIdentityCandidate(
        index=0,
        title="orcid match paper",
        authors=["Jianwei Huang"],
        authors_orcid=["0000-0001-2345-6789"],
    )
    c1 = PaperIdentityCandidate(
        index=1,
        title="llm-evaluated paper",
        authors=["Jianwei Huang"],
        authors_orcid=[],
    )
    llm = _llm_returning(
        {
            "decisions": [
                {
                    "index": 1,
                    "is_same_person": True,
                    "confidence": 0.88,
                    "topic_consistency": 0.7,
                    "reasoning": "LLM verified",
                }
            ]
        }
    )
    results = await batch_verify_paper_identity(
        professor_context=ctx,
        candidates=[c0, c1],
        llm_client=llm,
        llm_model="test",
    )
    assert [r.index for r in results] == [0, 1]
    assert results[0].reasoning == "ORCID match"
    assert results[0].accepted is True
    assert results[1].reasoning == "LLM verified"
    # LLM called exactly once — only for c1, not c0.
    assert llm.chat.completions.create.call_count == 1


@pytest.mark.asyncio
async def test_no_orcid_on_context_no_shortcut():
    """Context with no ORCID → everything goes through LLM."""
    ctx = _ctx()  # no orcid field set
    cand = PaperIdentityCandidate(
        index=0,
        title="Anything",
        authors=["Jianwei Huang"],
        authors_orcid=["0000-0001-2345-6789"],
    )
    llm = _llm_returning(
        {
            "decisions": [
                {
                    "index": 0,
                    "is_same_person": True,
                    "confidence": 0.9,
                    "topic_consistency": 0.8,
                    "reasoning": "ok",
                }
            ]
        }
    )
    results = await batch_verify_paper_identity(
        professor_context=ctx,
        candidates=[cand],
        llm_client=llm,
        llm_model="test",
    )
    assert llm.chat.completions.create.call_count == 1
    assert results[0].reasoning == "ok"


@pytest.mark.asyncio
async def test_prompt_renders_name_variants_when_set():
    """With name_variants on context, prompt includes variants block and rule 7."""
    from src.data_agents.professor.name_variants import resolve_name_variants

    nv = resolve_name_variants(
        canonical_name="Jianwei Huang",
        canonical_name_zh="黄建伟",
        canonical_name_en="Jianwei Huang",
    )
    ctx = ProfessorContext(
        name="黄建伟",
        institution="X",
        research_directions=["wireless"],
        name_variants=nv,
    )
    cand = PaperIdentityCandidate(
        index=0, title="T", authors=["Huang, J."], year=2023
    )
    llm = _llm_returning(
        {
            "decisions": [
                {
                    "index": 0,
                    "is_same_person": True,
                    "confidence": 0.9,
                    "topic_consistency": 0.8,
                    "reasoning": "ok",
                }
            ]
        }
    )
    await batch_verify_paper_identity(
        professor_context=ctx,
        candidates=[cand],
        llm_client=llm,
        llm_model="test",
    )
    sent_prompt = llm.chat.completions.create.call_args.kwargs["messages"][1][
        "content"
    ]
    assert "姓名变体" in sent_prompt
    assert "黄建伟" in sent_prompt
    assert "Jianwei Huang" in sent_prompt
    assert "huang" in sent_prompt.lower()  # pinyin
    # Rule 7 added
    assert "7." in sent_prompt and "变体" in sent_prompt


@pytest.mark.asyncio
async def test_prompt_no_variants_block_when_unset():
    """With name_variants unset, prompt is the pre-M1 shape (no variants block)."""
    ctx = _ctx()  # name_variants defaults None
    cand = PaperIdentityCandidate(index=0, title="T", authors=["X"], year=2023)
    llm = _llm_returning(
        {
            "decisions": [
                {
                    "index": 0,
                    "is_same_person": False,
                    "confidence": 0.1,
                    "topic_consistency": 0.0,
                    "reasoning": "no",
                }
            ]
        }
    )
    await batch_verify_paper_identity(
        professor_context=ctx,
        candidates=[cand],
        llm_client=llm,
        llm_model="test",
    )
    sent_prompt = llm.chat.completions.create.call_args.kwargs["messages"][1][
        "content"
    ]
    assert "姓名变体" not in sent_prompt
