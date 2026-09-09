"""Unit tests for badcase_to_case append logic (no live web/LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from badcase_to_case import build_case, next_qid


def test_next_qid_increments_past_max():
    cases = [{"qid": 1}, {"qid": 5}, {"qid": 12}]
    assert next_qid(cases) == 13


def test_build_case_has_required_fields():
    c = build_case(qid=99, query="X", answer="Y", key_point="X 需要在回答中",
                   turn_group="问题99", is_head_turn=True)
    assert c["qid"] == 99 and c["query"] == "X" and c["answer"] == "Y"
    assert "X" in c["required_entities"] or c["required_entities"] == []
    assert c["forbidden_entities"] == []
    assert c["is_head_turn"] is True
