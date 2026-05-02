from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from backend.api.chat import _classify_query_with_llm


FIXTURE = Path(__file__).parent / "fixtures" / "intent_classifier_benchmark.jsonl"
EXPECTED_DISTRIBUTION = {
    "A": 50,
    "B": 20,
    "C": 15,
    "D": 5,
    "E": 5,
    "F": 3,
    "G": 2,
}
PASS_OVERALL = 0.90
PASS_PER_CLASS = 0.70
REQUIRED_FIELDS = {
    "id",
    "query",
    "expected_type",
    "category_label",
    "rationale",
    "language",
    "source",
}


@pytest.fixture(scope="module")
def benchmark_cases() -> list[dict[str, str]]:
    cases = []
    with FIXTURE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    assert len(cases) == 100, f"expected 100 cases, got {len(cases)}"
    return cases


def test_intent_classifier_fixture_contract(
    benchmark_cases: list[dict[str, str]],
) -> None:
    ids = [case.get("id") for case in benchmark_cases]
    assert ids == [f"Q{i:03d}" for i in range(1, 101)]
    assert len(set(ids)) == 100

    for case in benchmark_cases:
        missing = REQUIRED_FIELDS - set(case)
        assert not missing, (
            f"{case.get('id', '<missing id>')} missing fields: {missing}"
        )
        assert case["query"].strip(), f"{case['id']} query is blank"
        assert case["expected_type"] in EXPECTED_DISTRIBUTION
        assert case["category_label"].strip(), f"{case['id']} category_label is blank"
        assert case["rationale"].strip(), f"{case['id']} rationale is blank"
        assert case["language"] in {"zh", "en"}, f"{case['id']} has invalid language"
        assert case["source"].strip(), f"{case['id']} source is blank"

    assert (
        Counter(case["expected_type"] for case in benchmark_cases)
        == EXPECTED_DISTRIBUTION
    )


@pytest.mark.requires_classifier_llm
def test_classifier_benchmark(benchmark_cases: list[dict[str, str]]) -> None:
    results = []
    for case in benchmark_cases:
        actual = _classify_query_with_llm(case["query"])
        actual_type = (actual or {}).get("type", "UNKNOWN")
        results.append(
            {
                **case,
                "actual_type": actual_type,
                "actual_reason": (actual or {}).get("reason", ""),
                "match": actual_type == case["expected_type"],
            }
        )

    overall = sum(result["match"] for result in results) / len(results)
    by_class = {}
    for cls in EXPECTED_DISTRIBUTION:
        cls_results = [result for result in results if result["expected_type"] == cls]
        by_class[cls] = sum(result["match"] for result in cls_results) / len(
            cls_results
        )

    if overall < PASS_OVERALL or any(acc < PASS_PER_CLASS for acc in by_class.values()):
        mismatches = [result for result in results if not result["match"]]
        print("\nClassifier benchmark mismatches:")
        for mismatch in mismatches:
            print(
                "  MISS "
                f"[{mismatch['expected_type']}->{mismatch['actual_type']}] "
                f"{mismatch['id']}: {mismatch['query']}"
            )
            if mismatch["actual_reason"]:
                print(f"    reason: {mismatch['actual_reason']}")
        print(f"\n  Overall: {overall:.3f} (gate {PASS_OVERALL})")
        for cls, acc in sorted(by_class.items()):
            print(f"  {cls}: {acc:.3f} (gate {PASS_PER_CLASS})")

    assert overall >= PASS_OVERALL, f"overall {overall:.3f} < {PASS_OVERALL}"
    for cls, acc in by_class.items():
        assert acc >= PASS_PER_CLASS, f"{cls} {acc:.3f} < {PASS_PER_CLASS}"
