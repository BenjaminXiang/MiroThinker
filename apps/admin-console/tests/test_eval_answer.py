"""Unit tests for eval_answer L1/L2 (deterministic; no live /api/chat)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_answer import score_l1_required, score_l2_forbidden


def test_l1_required_hits_when_entity_in_answer():
    case = {"required_entities": ["普渡", "云迹"], "query": "x"}
    answer = "深圳普渡科技是一家送餐机器人公司。云迹也做。"
    hit, miss = score_l1_required(case, answer)
    assert "普渡" in hit and "云迹" in hit
    assert miss == []


def test_l1_required_misses_when_entity_absent():
    case = {"required_entities": ["九号", "擎朗"], "query": "x"}
    answer = "普渡科技是一家公司。"
    hit, miss = score_l1_required(case, answer)
    assert hit == []
    assert set(miss) == {"九号", "擎朗"}


def test_l2_forbidden_flags_when_present():
    case = {"forbidden_entities": ["深圳智航无人机有限公司"]}
    answer = "深圳智航无人机有限公司是一家..."
    violations = score_l2_forbidden(case, answer)
    assert "深圳智航无人机有限公司" in violations


def test_l2_forbidden_clean_when_absent():
    case = {"forbidden_entities": ["深圳智航无人机有限公司"]}
    answer = "无界智航是另一家公司。"
    violations = score_l2_forbidden(case, answer)
    assert violations == []
