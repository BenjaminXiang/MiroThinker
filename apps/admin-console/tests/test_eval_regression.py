"""Unit tests for eval_regression gate logic (no live /api/chat)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_regression import decide_exit, REGRESSION


def test_exit_zero_when_no_regression():
    current = {"rows": [{"qid": 1, "l1_hit": ["x"], "l1_miss": [], "l2_violations": [], "l3_avg": 0.8}]}
    golden = {"rows": [{"qid": 1, "l1_hit": ["x"], "l1_miss": [], "l2_violations": [], "l3_avg": 0.7}]}
    # l1 stable (x hit both), l2 clean, l3 improved -> no regression
    assert decide_exit(current, golden, l3_threshold=0.6) == 0


def test_exit_one_when_l1_regressed():
    current = {"rows": [{"qid": 1, "l1_hit": [], "l1_miss": ["x"], "l2_violations": [], "l3_avg": 0.8}]}
    golden = {"rows": [{"qid": 1, "l1_hit": ["x"], "l1_miss": [], "l2_violations": [], "l3_avg": 0.8}]}
    # l1 regressed (x was hit in golden, now missed) -> exit 1
    assert decide_exit(current, golden, l3_threshold=0.6) == 1


def test_exit_one_when_l2_regressed():
    current = {"rows": [{"qid": 1, "l1_hit": [], "l1_miss": [], "l2_violations": ["bad"], "l3_avg": 0.9}]}
    golden = {"rows": [{"qid": 1, "l1_hit": [], "l1_miss": [], "l2_violations": [], "l3_avg": 0.9}]}
    assert decide_exit(current, golden, l3_threshold=0.6) == 1


def test_exit_one_when_l3_below_threshold():
    current = {"rows": [{"qid": 1, "l1_hit": [], "l1_miss": [], "l2_violations": [], "l3_avg": 0.4}]}
    golden = {"rows": [{"qid": 1, "l1_hit": [], "l1_miss": [], "l2_violations": [], "l3_avg": 0.8}]}
    assert decide_exit(current, golden, l3_threshold=0.6) == 1
