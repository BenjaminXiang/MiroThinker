"""Eval gate: golden-set scoring and baseline regression semantics."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval_full_testset.py"
_spec = importlib.util.spec_from_file_location("eval_full_testset", _SCRIPT)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gate  # dataclasses/pytest resolve the module by name
_spec.loader.exec_module(gate)


def _row(
    qid: str,
    hit: str,
    *,
    forbidden=(),
    citations=2,
    refusal=False,
    refusal_ok=True,
    answer="答案正文",
    error=None,
) -> dict:
    row = {
        "qid": qid,
        "required_hit": hit,
        "forbidden_hit": list(forbidden),
        "answer_coverage": 0.5,
        "citations": citations,
        "refusal_expected": refusal,
        "refusal_ok": refusal_ok,
        "product_pass": gate._product_pass(
            answer=answer,
            citations=citations,
            refusal_expected=refusal,
            refusal_ok=refusal_ok,
            forbidden=list(forbidden),
            errored=error is not None,
        ),
        "latency_seconds": 1.0,
        "answer_text": answer,
    }
    if error:
        row["error"] = error
    return row


def test_hits_normalize_whitespace_and_case() -> None:
    # q23's standard phrase is split across lines; whitespace must not matter.
    assert gate._hits("真实采集 和 仿真生成", ["真实采集和仿真生成"]) == [
        "真实采集和仿真生成"
    ]
    assert gate._hits("Embodied AI research", ["embodied ai"]) == ["embodied ai"]
    assert gate._hits("无关内容", ["该术语不在答案里"]) == []


def test_groups_head_is_one_conversation_per_head_turn() -> None:
    cases = gate.load_cases()
    head_groups = gate.groups_for(cases, mode="head")
    assert len(cases) == 27
    assert len(head_groups) == 19
    assert all(len(group) == 1 for group in head_groups)


def test_groups_full_keeps_turn_groups_together() -> None:
    cases = gate.load_cases()
    groups = gate.groups_for(cases, mode="full")
    assert sum(len(group) for group in groups) == 27
    assert max(len(group) for group in groups) >= 2  # follow-up turns stay attached


def test_summarize_counts_required_and_product() -> None:
    rows = [
        _row("1", "2/2"),
        _row("2", "0/3", answer=""),
        _row("3", "1/1", refusal=True, refusal_ok=True, citations=0),
        _row("4", "1/1", forbidden=["不该出现"]),
    ]
    summary = gate.summarize(rows, mode="full")
    assert summary["required_hits"] == 4
    assert summary["required_total"] == 7
    assert summary["forbidden_violation_cases"] == 1
    assert summary["refusal_misses"] == 0
    assert summary["product_pass"] == 2  # q1 + refusal turn
    assert summary["product_pass_rate"] == 0.5


def test_product_pass_rules() -> None:
    assert gate._product_pass(
        answer="有",
        citations=1,
        refusal_expected=False,
        refusal_ok=True,
        forbidden=[],
        errored=False,
    )
    assert not gate._product_pass(
        answer="有",
        citations=0,
        refusal_expected=False,
        refusal_ok=True,
        forbidden=[],
        errored=False,
    )
    assert not gate._product_pass(
        answer="有",
        citations=1,
        refusal_expected=False,
        refusal_ok=True,
        forbidden=["x"],
        errored=False,
    )
    # A refusal turn is usable when it refuses, even without citations.
    assert gate._product_pass(
        answer="无法确认",
        citations=0,
        refusal_expected=True,
        refusal_ok=True,
        forbidden=[],
        errored=False,
    )
    assert not gate._product_pass(
        answer="瞎编",
        citations=1,
        refusal_expected=True,
        refusal_ok=False,
        forbidden=[],
        errored=False,
    )


def test_compare_detects_hard_turn_regression_and_improvement() -> None:
    baseline = {
        "rows": [_row("1", "2/2"), _row("2", "2/3"), _row("3", "1/1")],
        "required_hits": 5,
        "product_pass": 3,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }
    current = {
        "rows": [_row("1", "0/2"), _row("2", "3/3"), _row("3", "1/1")],
        "required_hits": 4,
        "product_pass": 3,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }

    comparison = gate.compare_to_baseline(current, baseline)

    assert comparison["verdict"] == "regression"
    assert comparison["regressed"] == [
        {"qid": "1", "reason": "required hits", "was": 2, "now": 0}
    ]
    assert comparison["improved"] == [{"qid": "2", "was": 2, "now": 3}]
    assert "regression" in gate.format_comparison(comparison)


def test_single_entity_dip_is_a_fluctuation_not_a_regression() -> None:
    """The composer rephrases: losing one exact token on one turn is noise."""
    baseline = {
        "rows": [_row("1", "2/2")],
        "required_hits": 2,
        "product_pass": 1,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }
    current = {
        "rows": [_row("1", "1/2")],
        "required_hits": 1,
        "product_pass": 1,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }

    comparison = gate.compare_to_baseline(current, baseline)

    assert comparison["verdict"] == "pass"
    assert comparison["fluctuations"] == [{"qid": "1", "was": 2, "now": 1}]
    assert "within tolerance" in gate.format_comparison(comparison)


def test_total_dip_beyond_tolerance_is_a_regression() -> None:
    baseline = {
        "rows": [_row("1", "3/3")],
        "required_hits": 3,
        "product_pass": 1,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }
    current = {
        "rows": [_row("1", "1/3")],
        "required_hits": 1,
        "product_pass": 1,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }

    comparison = gate.compare_to_baseline(current, baseline, total_tolerance=1)

    assert comparison["verdict"] == "regression"
    assert any(
        item["reason"] == "total required hits" for item in comparison["regressed"]
    )


def test_total_dip_within_tolerance_passes() -> None:
    """Two one-entity dips: total falls by 2, each turn is only a fluctuation."""
    baseline = {
        "rows": [_row("1", "2/3"), _row("2", "2/2")],
        "required_hits": 4,
        "product_pass": 2,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }
    current = {
        "rows": [_row("1", "1/3"), _row("2", "1/2")],
        "required_hits": 2,
        "product_pass": 2,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }

    comparison = gate.compare_to_baseline(current, baseline, total_tolerance=2)

    assert comparison["verdict"] == "pass"
    assert len(comparison["fluctuations"]) == 2


def test_compare_passes_when_nothing_drops() -> None:
    baseline = {
        "rows": [_row("1", "2/2")],
        "required_hits": 2,
        "product_pass": 1,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }
    current = {
        "rows": [_row("1", "2/2")],
        "required_hits": 2,
        "product_pass": 1,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }

    assert gate.compare_to_baseline(current, baseline)["verdict"] == "pass"
    assert "pass" in gate.format_comparison(gate.compare_to_baseline(current, baseline))


@pytest.mark.parametrize(
    "key,value",
    [("forbidden_violation_cases", 1), ("refusal_misses", 1), ("errors", 1)],
)
def test_compare_treats_worse_counters_as_regression(key: str, value: int) -> None:
    baseline = {
        "rows": [_row("1", "1/1")],
        "required_hits": 1,
        "product_pass": 1,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }
    current = dict(baseline, **{key: value})

    comparison = gate.compare_to_baseline(current, baseline)

    assert comparison["verdict"] == "regression"
    assert any(item["reason"] == key for item in comparison["regressed"])


def test_compare_flags_a_turn_that_stopped_running() -> None:
    baseline = {
        "rows": [_row("1", "1/1"), _row("9", "1/1")],
        "required_hits": 2,
        "product_pass": 2,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }
    current = {
        "rows": [_row("1", "1/1")],
        "required_hits": 1,
        "product_pass": 1,
        "forbidden_violation_cases": 0,
        "refusal_misses": 0,
        "errors": 0,
    }

    comparison = gate.compare_to_baseline(current, baseline)

    assert comparison["verdict"] == "regression"
    assert comparison["regressed"][0] == {"qid": "9", "reason": "turn no longer runs"}
