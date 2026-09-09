"""Unit tests for eval_latency pure stats (no live calls)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from eval_latency import _percentile, _slo_verdict


def test_percentile_basic():
    # p50 of [1,2,3,4,5] ~ 3; p95 close to 5
    assert _percentile([1, 2, 3, 4, 5], 50) == 3
    assert _percentile([1, 2, 3, 4, 5], 95) == 5


def test_slo_verdict_retrieval_pass():
    assert _slo_verdict(5.9, kind="retrieval") == "PASS"


def test_slo_verdict_retrieval_fail():
    assert _slo_verdict(6.1, kind="retrieval") == "FAIL"
