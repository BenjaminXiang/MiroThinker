# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.17 — unit tests for the name-identity gate.

Fully mocked LLM; no network. Verifies:
  * pinyin / Wade-Giles / self-declared English name acceptance
  * unrelated-person / fragment rejection
  * sub-threshold confidence always rejects
  * parse / LLM-exception always reject (fail-safe)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.name_identity_gate import (
    CONFIDENCE_THRESHOLD,
    NameIdentityCandidate,
    NameIdentityDecision,
    batch_verify_name_identity,
    verify_name_identity,
)


def _llm_returning(payload: dict, *, use_fence: bool = False) -> MagicMock:
    """Build a sync mock llm_client whose chat.completions.create returns *payload*."""
    body = json.dumps(payload, ensure_ascii=False)
    content = f"```json\n{body}\n```" if use_fence else body
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return client


# ---------------------------------------------------------------------------
# Accept cases
# ---------------------------------------------------------------------------


def test_accept_exact_pinyin():
    llm = _llm_returning({"is_same_person": True, "confidence": 0.95, "reasoning": "standard pinyin"})
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="熊会元", candidate_name_en="Huiyuan Xiong"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is True
    assert decision.confidence == pytest.approx(0.95)
    assert decision.error is None


def test_accept_hyphenated_pinyin():
    llm = _llm_returning({"is_same_person": True, "confidence": 0.92, "reasoning": "hyphenated pinyin"})
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="夏树涛", candidate_name_en="Shu-Tao Xia"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is True


def test_accept_reversed_order():
    # Both "Li Qiang" and "Qiang Li" should work for 李强
    llm_western = _llm_returning({"is_same_person": True, "confidence": 0.9, "reasoning": "western order"})
    llm_eastern = _llm_returning({"is_same_person": True, "confidence": 0.9, "reasoning": "eastern order"})

    d_western = verify_name_identity(
        NameIdentityCandidate(canonical_name="李强", candidate_name_en="Qiang Li"),
        llm_client=llm_western,
        llm_model="gemma-4",
    )
    d_eastern = verify_name_identity(
        NameIdentityCandidate(canonical_name="李强", candidate_name_en="Li Qiang"),
        llm_client=llm_eastern,
        llm_model="gemma-4",
    )
    assert d_western.accepted is True
    assert d_eastern.accepted is True


def test_accept_self_declared_english():
    llm = _llm_returning({"is_same_person": True, "confidence": 0.88, "reasoning": "self-declared English name"})
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="张辰", candidate_name_en="Steve Zhang"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is True


# ---------------------------------------------------------------------------
# Reject — unrelated person
# ---------------------------------------------------------------------------


def test_reject_unrelated_thomas_hardy():
    llm = _llm_returning({"is_same_person": False, "confidence": 0.05, "reasoning": "no phonetic or semantic match"})
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="张成萍", candidate_name_en="Thomas Hardy"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is False


def test_reject_unrelated_chunbo_li():
    llm = _llm_returning({"is_same_person": False, "confidence": 0.1, "reasoning": "different person"})
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="舒阳", candidate_name_en="Chunbo Li"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is False


def test_reject_unrelated_xiaoyang_guo():
    llm = _llm_returning({"is_same_person": False, "confidence": 0.08, "reasoning": "different person"})
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="曹磊峰", candidate_name_en="Xiaoyang Guo"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is False


# ---------------------------------------------------------------------------
# Reject — non-person fragment
# ---------------------------------------------------------------------------


def test_reject_fragment_laser_technol():
    llm = _llm_returning({"is_same_person": False, "confidence": 0.02, "reasoning": "journal name abbreviation"})
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="张春香", candidate_name_en="Laser Technol"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is False


def test_reject_fragment_senior_member():
    llm = _llm_returning({"is_same_person": False, "confidence": 0.02, "reasoning": "IEEE membership grade, not a name"})
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="廖庆敏", candidate_name_en="Senior Member"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is False


def test_reject_fragment_area_graphene():
    llm = _llm_returning({"is_same_person": False, "confidence": 0.03, "reasoning": "research area fragment"})
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="苏阳", candidate_name_en="Area Graphene"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is False


# ---------------------------------------------------------------------------
# Threshold + fail-safe
# ---------------------------------------------------------------------------


def test_reject_below_confidence_threshold_even_if_same_person_true():
    # Even when is_same_person=True, if confidence < CONFIDENCE_THRESHOLD it must reject.
    assert CONFIDENCE_THRESHOLD == 0.8
    llm = _llm_returning({"is_same_person": True, "confidence": 0.75, "reasoning": "weak"})
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="李强", candidate_name_en="Jian Li"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is False


def test_fail_safe_on_llm_exception():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("upstream gemma 503")
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="李强", candidate_name_en="Qiang Li"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is False
    assert decision.error == "llm_exception"


def test_fail_safe_on_unparseable_json():
    llm = MagicMock()
    llm.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="this is not json at all"))]
    )
    decision = verify_name_identity(
        NameIdentityCandidate(canonical_name="李强", candidate_name_en="Qiang Li"),
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert decision.accepted is False
    assert decision.error == "parse"


# ---------------------------------------------------------------------------
# Batch verification — tolerates fence, preserves order, one LLM failure
# doesn't poison other decisions
# ---------------------------------------------------------------------------


def test_batch_accepts_fenced_json_output():
    llm = _llm_returning(
        {"is_same_person": True, "confidence": 0.95, "reasoning": "ok"},
        use_fence=True,
    )
    # Patch the mock so each candidate gets its own fresh payload
    decisions = batch_verify_name_identity(
        [NameIdentityCandidate(canonical_name="熊会元", candidate_name_en="Huiyuan Xiong")],
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert len(decisions) == 1
    assert decisions[0].accepted is True


def test_batch_isolates_individual_failure():
    """One LLM exception for candidate B should not affect candidate A."""
    call_count = {"n": 0}

    def _side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return MagicMock(
                choices=[MagicMock(message=MagicMock(
                    content='{"is_same_person": true, "confidence": 0.9, "reasoning": "ok"}'
                ))]
            )
        raise RuntimeError("transient")

    llm = MagicMock()
    llm.chat.completions.create.side_effect = _side_effect

    decisions = batch_verify_name_identity(
        [
            NameIdentityCandidate(canonical_name="熊会元", candidate_name_en="Huiyuan Xiong"),
            NameIdentityCandidate(canonical_name="张三", candidate_name_en="Something Broken"),
        ],
        llm_client=llm,
        llm_model="gemma-4",
    )
    assert len(decisions) == 2
    assert decisions[0].accepted is True
    assert decisions[1].accepted is False
    assert decisions[1].error == "llm_exception"


def test_decision_dataclass_is_immutable():
    """Callers shouldn't be able to mutate a cached decision."""
    d = NameIdentityDecision(accepted=True, confidence=0.9, reasoning="ok", error=None)
    with pytest.raises(Exception):  # FrozenInstanceError / AttributeError
        d.accepted = False  # type: ignore[misc]
