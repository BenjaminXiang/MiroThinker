from __future__ import annotations

import json
from unittest.mock import MagicMock

from src.data_agents.paper.author_id_picker import (
    AuthorCandidate,
    pick_author_id,
)


def _llm_returning(payload: dict) -> MagicMock:
    client = MagicMock()
    content = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return client


def _cand(**kw) -> AuthorCandidate:
    base = dict(
        index=0,
        author_id="https://openalex.org/A100",
        display_name="Jianwei Huang",
        institutions=["The Chinese University of Hong Kong, Shenzhen"],
        topics=["Wireless Networks", "Game Theory"],
        works_count=200,
        cited_by_count=30000,
        h_index=60,
    )
    base.update(kw)
    return AuthorCandidate(**base)


def test_picker_single_candidate_matching_institution_skips_llm():
    llm = MagicMock()
    decision = pick_author_id(
        target_name="黄建伟",
        target_institution="香港中文大学（深圳）",
        target_directions=["无线通信"],
        candidates=[_cand(institutions=["香港中文大学（深圳）"])],
        llm_client=llm,
        llm_model="test",
    )
    assert decision.accepted_author_id == "https://openalex.org/A100"
    assert decision.confidence >= 0.75
    llm.chat.completions.create.assert_not_called()


def test_picker_returns_none_when_no_candidates():
    llm = MagicMock()
    decision = pick_author_id(
        target_name="黄建伟",
        target_institution="香港中文大学（深圳）",
        target_directions=[],
        candidates=[],
        llm_client=llm,
        llm_model="test",
    )
    assert decision.accepted_author_id is None
    llm.chat.completions.create.assert_not_called()


def test_picker_accepts_high_confidence_choice():
    llm = _llm_returning(
        {"chosen_index": 1, "confidence": 0.93, "reasoning": "inst match"}
    )
    candidates = [
        _cand(index=0, author_id="A-WRONG", institutions=["Stanford University"]),
        _cand(index=1, author_id="A-RIGHT", institutions=["CUHK Shenzhen"]),
    ]
    decision = pick_author_id(
        target_name="黄建伟",
        target_institution="香港中文大学（深圳）",
        target_directions=["无线通信"],
        candidates=candidates,
        llm_client=llm,
        llm_model="test",
    )
    assert decision.accepted_author_id == "A-RIGHT"
    assert decision.confidence == 0.93


def test_picker_returns_none_when_confidence_below_threshold():
    llm = _llm_returning(
        {"chosen_index": 0, "confidence": 0.5, "reasoning": "weak"}
    )
    candidates = [
        _cand(index=0, author_id="A-MAYBE", institutions=["Stanford University"]),
        _cand(index=1, author_id="A-OTHER", institutions=["MIT"]),
    ]
    decision = pick_author_id(
        target_name="黄建伟",
        target_institution="香港中文大学（深圳）",
        target_directions=None,
        candidates=candidates,
        llm_client=llm,
        llm_model="test",
    )
    assert decision.accepted_author_id is None
    assert decision.confidence == 0.5


def test_picker_returns_none_when_llm_declines_with_null_index():
    llm = _llm_returning(
        {"chosen_index": None, "confidence": 0.9, "reasoning": "none match"}
    )
    candidates = [
        _cand(index=0, author_id="A-A", institutions=["Beijing University"]),
        _cand(index=1, author_id="A-B", institutions=["Tokyo University"]),
    ]
    decision = pick_author_id(
        target_name="黄建伟",
        target_institution="香港中文大学（深圳）",
        target_directions=None,
        candidates=candidates,
        llm_client=llm,
        llm_model="test",
    )
    assert decision.accepted_author_id is None


def test_picker_rejects_unknown_index_from_llm():
    llm = _llm_returning(
        {"chosen_index": 99, "confidence": 0.95, "reasoning": "bogus"}
    )
    decision = pick_author_id(
        target_name="黄建伟",
        target_institution="香港中文大学（深圳）",
        target_directions=None,
        candidates=[
            _cand(index=0, author_id="A-0", institutions=["MIT"]),
            _cand(index=1, author_id="A-1", institutions=["Stanford"]),
        ],
        llm_client=llm,
        llm_model="test",
    )
    assert decision.accepted_author_id is None
    assert "99" in decision.reasoning


def test_picker_fails_safe_on_parse_error():
    llm = MagicMock()
    llm.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="not-json"))]
    )
    decision = pick_author_id(
        target_name="黄建伟",
        target_institution="香港中文大学（深圳）",
        target_directions=None,
        candidates=[
            _cand(index=0, author_id="A-0", institutions=["MIT"]),
            _cand(index=1, author_id="A-1", institutions=["Stanford"]),
        ],
        llm_client=llm,
        llm_model="test",
    )
    assert decision.accepted_author_id is None
    assert decision.error is not None


def test_picker_fails_safe_on_llm_exception():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("api down")
    decision = pick_author_id(
        target_name="黄建伟",
        target_institution="香港中文大学（深圳）",
        target_directions=None,
        candidates=[
            _cand(index=0, author_id="A-0", institutions=["MIT"]),
            _cand(index=1, author_id="A-1", institutions=["Stanford"]),
        ],
        llm_client=llm,
        llm_model="test",
    )
    assert decision.accepted_author_id is None
    assert decision.error == "api down"


def test_picker_records_considered_ids_on_llm_path():
    llm = _llm_returning(
        {"chosen_index": 0, "confidence": 0.85, "reasoning": "ok"}
    )
    decision = pick_author_id(
        target_name="黄建伟",
        target_institution="香港中文大学（深圳）",
        target_directions=None,
        candidates=[
            _cand(index=0, author_id="A-A", institutions=["MIT"]),
            _cand(index=1, author_id="A-B", institutions=["Stanford"]),
        ],
        llm_client=llm,
        llm_model="test",
    )
    assert decision.considered_author_ids == ["A-A", "A-B"]
